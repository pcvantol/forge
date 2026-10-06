"""Owner-issued, Mission-scoped bearer capabilities for Workspace reviews.

This credential has no relationship to the Workspace status read grant or the
Forge Server administrator credential. Every request rereads its private file.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
from typing import Any, Iterator

from .models.producer import redact_action_summary

try:
    import fcntl
except ImportError:  # pragma: no cover - mutation fails closed without OS locking
    fcntl = None  # type: ignore[assignment]


CONTRACT_VERSION = "forge-workspace-review-grants/v1"
PRINCIPAL_PREFIX = "forge-workspace-review-principal:v1:"
SUPPORTED_ROLE = "platform_architect"
SUPPORTED_ACTOR = "primary_operator"
SUPPORTED_CAPABILITY = "ARCHITECTURE_APPROVAL"
_GRANT_ID = re.compile(r"[0-9a-f]{32}\Z")
_PRINCIPAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_MISSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_UTC_SECOND = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def _time(value: object) -> datetime:
    if not isinstance(value, str) or _UTC_SECOND.fullmatch(value) is None:
        raise ValueError("review grant expiry must be UTC seconds")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError("review grant expiry is invalid") from error


def _private_directory(path: Path, *, create: bool) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("review grant directory must not be a symbolic link")
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    details = path.stat()
    if not stat.S_ISDIR(details.st_mode) or details.st_mode & 0o077:
        raise ValueError("review grant directory must be private")


def _private_bytes(path: Path) -> bytes:
    _private_directory(path.parent, create=False)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as source:
            details = os.fstat(source.fileno())
            if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077 or details.st_size > 65536:
                raise ValueError("review grant file must be private, regular and bounded")
            return source.read(65537)
    except OSError as error:
        raise ValueError("review grant file is unavailable") from error


def _write_private(path: Path, raw: bytes) -> None:
    _private_directory(path.parent, create=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".review-grants-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        if path.is_symlink():
            raise ValueError("review grant path must not be a symbolic link")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _new_token(path: Path, token: str) -> None:
    if path.parent.is_symlink() or path.exists() or path.is_symlink():
        raise ValueError("review token output path is unavailable")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write((token + "\n").encode("utf-8"))
        output.flush()
        os.fsync(output.fileno())


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    if fcntl is None:
        raise ValueError("review grant lifecycle locking is unavailable")
    _private_directory(path.parent, create=True)
    lock = path.parent / ".workspace-review-grants.lock"
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
            raise ValueError("review grant lock must be private and regular")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _validate_record(value: object, instance_id: str) -> dict[str, Any]:
    required = {"grant_id", "principal_id", "instance_id", "mission_ids", "role",
                "role_actor", "capability", "expires_at", "token_sha256", "state", "revision"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("review grant record is malformed")
    if (not isinstance(value["grant_id"], str) or _GRANT_ID.fullmatch(value["grant_id"]) is None
            or not isinstance(value["principal_id"], str)
            or _PRINCIPAL_ID.fullmatch(value["principal_id"]) is None
            or redact_action_summary(value["principal_id"]) != value["principal_id"]
            or value["instance_id"] != instance_id
            or value["role"] != SUPPORTED_ROLE or value["role_actor"] != SUPPORTED_ACTOR
            or value["capability"] != SUPPORTED_CAPABILITY
            or not isinstance(value["state"], str)
            or value["state"] not in {"ACTIVE", "REVOKED"}
            or type(value["revision"]) is not int or value["revision"] < 1
            or not isinstance(value["token_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", value["token_sha256"]) is None):
        raise ValueError("review grant record is invalid")
    mission_ids = value["mission_ids"]
    if (not isinstance(mission_ids, list) or not 0 < len(mission_ids) <= 32
            or any(not isinstance(item, str) or _MISSION_ID.fullmatch(item) is None
                   for item in mission_ids)
            or mission_ids != sorted(set(mission_ids))):
        raise ValueError("review grant Mission set is invalid")
    _time(value["expires_at"])
    return value


@dataclass(frozen=True)
class ReviewPrincipal:
    grant_id: str
    principal_id: str
    instance_id: str
    mission_ids: tuple[str, ...]
    role: str
    role_actor: str
    capability: str
    expires_at: str

    @property
    def reference(self) -> str:
        return PRINCIPAL_PREFIX + self.grant_id


class WorkspaceReviewGrant:
    """One instance's bounded grants, revalidated for each read and mutation."""

    def __init__(self, root: Path, instance_id: str,
                 path: Path | None = None) -> None:
        self.root = root
        self.instance_id = instance_id
        self.path = path or root / "credentials" / "workspace-review" / "grants.json"

    def _records(self, *, missing_ok: bool = False) -> list[dict[str, Any]]:
        try:
            value = json.loads(_private_bytes(self.path))
        except (OSError, ValueError) as error:
            if missing_ok and not self.path.exists() and not self.path.is_symlink():
                return []
            raise ValueError("review grants are unavailable") from error
        if (not isinstance(value, dict) or set(value) != {"contract_version", "instance_id", "records"}
                or value["contract_version"] != CONTRACT_VERSION
                or value["instance_id"] != self.instance_id
                or not isinstance(value["records"], list) or len(value["records"]) > 64):
            raise ValueError("review grant store is malformed")
        records = [_validate_record(record, self.instance_id) for record in value["records"]]
        identifiers = [record["grant_id"] for record in records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("review grant identifiers conflict")
        return records

    def _save(self, records: list[dict[str, Any]]) -> None:
        raw = json.dumps({"contract_version": CONTRACT_VERSION,
                          "instance_id": self.instance_id, "records": records},
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(raw) > 65536:
            raise ValueError("review grant store is too large")
        _write_private(self.path, raw)

    @staticmethod
    def _principal(record: dict[str, Any]) -> ReviewPrincipal:
        return ReviewPrincipal(
            record["grant_id"], record["principal_id"], record["instance_id"],
            tuple(record["mission_ids"]), record["role"], record["role_actor"],
            record["capability"], record["expires_at"],
        )

    def authenticate(self, authorization: str | None) -> ReviewPrincipal | None:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            return None
        token = authorization[7:]
        if not token or len(token) > 256:
            return None
        digest = sha256(token.encode("utf-8")).hexdigest()
        try:
            records = self._records()
        except ValueError:
            return None
        matching = [record for record in records
                    if secrets.compare_digest(digest, record["token_sha256"])]
        if len(matching) != 1:
            return None
        record = matching[0]
        if record["state"] != "ACTIVE" or _time(record["expires_at"]) <= datetime.now(UTC):
            return None
        return self._principal(record)

    def authorizes_reference(self, reference: str, mission_id: str, *,
                             role: str, role_actor: str, capability: str) -> bool:
        if not isinstance(reference, str) or not reference.startswith(PRINCIPAL_PREFIX):
            return False
        grant_id = reference[len(PRINCIPAL_PREFIX):]
        if _GRANT_ID.fullmatch(grant_id) is None:
            return False
        try:
            records = self._records()
        except ValueError:
            return False
        return any(record["grant_id"] == grant_id and record["state"] == "ACTIVE"
                   and _time(record["expires_at"]) > datetime.now(UTC)
                   and mission_id in record["mission_ids"] and record["role"] == role
                   and record["role_actor"] == role_actor and record["capability"] == capability
                   for record in records)

    def issue(self, *, principal_id: str, mission_ids: tuple[str, ...],
              expires_at: str, token_path: Path) -> dict[str, object]:
        if (not isinstance(principal_id, str) or _PRINCIPAL_ID.fullmatch(principal_id) is None
                or redact_action_summary(principal_id) != principal_id):
            raise ValueError("review principal identifier is invalid")
        selected = sorted(set(mission_ids))
        if (not selected or len(selected) > 32
                or any(not isinstance(item, str) or _MISSION_ID.fullmatch(item) is None
                       for item in selected)):
            raise ValueError("review Mission set is invalid")
        expiry = _time(expires_at)
        now = datetime.now(UTC)
        if expiry <= now or expiry > now + timedelta(days=90):
            raise ValueError("review grant expiry must be future and within 90 days")
        if token_path.resolve() == self.path.resolve():
            raise ValueError("review token and grant store paths must differ")
        from ._version import canonical_version
        from .runtime.bootstrap import RuntimeBootstrap
        from .state.mission_state import MissionStateStore
        database = RuntimeBootstrap(data_root=str(self.root), forge_version=canonical_version()).open()
        try:
            states = MissionStateStore(database, data_root=str(self.root))
            for mission_id in selected:
                states.get(mission_id)
        finally:
            database.close()
        with _locked(self.path):
            records = self._records(missing_ok=True)
            if len(records) >= 64 or any(record["principal_id"] == principal_id and
                                         record["state"] == "ACTIVE" for record in records):
                raise ValueError("review principal already has an active grant or store is full")
            grant_id = secrets.token_hex(16)
            token = secrets.token_urlsafe(48)
            record = {"grant_id": grant_id, "principal_id": principal_id,
                      "instance_id": self.instance_id, "mission_ids": selected,
                      "role": SUPPORTED_ROLE, "role_actor": SUPPORTED_ACTOR,
                      "capability": SUPPORTED_CAPABILITY, "expires_at": expires_at,
                      "token_sha256": sha256(token.encode("utf-8")).hexdigest(),
                      "state": "ACTIVE", "revision": 1}
            _new_token(token_path, token)
            try:
                self._save([*records, record])
            except Exception:
                token_path.unlink(missing_ok=True)
                raise
            return {"contract_version": CONTRACT_VERSION, "grant_id": grant_id,
                    "principal_id": principal_id, "instance_id": self.instance_id,
                    "mission_ids": selected, "role": SUPPORTED_ROLE,
                    "role_actor": SUPPORTED_ACTOR, "capability": SUPPORTED_CAPABILITY,
                    "expires_at": expires_at, "state": "ACTIVE", "revision": 1}

    def revoke(self, grant_id: str) -> dict[str, object]:
        if not isinstance(grant_id, str) or _GRANT_ID.fullmatch(grant_id) is None:
            raise ValueError("review grant identifier is invalid")
        with _locked(self.path):
            records = self._records()
            selected = next((record for record in records if record["grant_id"] == grant_id), None)
            if selected is None:
                raise ValueError("review grant does not exist")
            if selected["state"] == "ACTIVE":
                selected["state"] = "REVOKED"
                selected["revision"] += 1
                self._save(records)
            return {"contract_version": CONTRACT_VERSION, "grant_id": grant_id,
                    "instance_id": self.instance_id, "state": "REVOKED",
                    "revision": selected["revision"]}


def main(argv: list[str] | None = None) -> int:
    """Installed owner provisioning; the bearer is written only to a private file."""
    parser = argparse.ArgumentParser(prog="forge-workspace-review-grant")
    parser.add_argument("--data-root", required=True)
    actions = parser.add_subparsers(dest="action", required=True)
    issue = actions.add_parser("issue")
    issue.add_argument("--principal-id", required=True)
    issue.add_argument("--mission-id", action="append", required=True)
    issue.add_argument("--expires-at", required=True)
    issue.add_argument("--token-file", required=True)
    revoke = actions.add_parser("revoke")
    revoke.add_argument("--grant-id", required=True)
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root)
        grant = WorkspaceReviewGrant(Path(instance.data_root), instance.instance_id)
        result = (grant.issue(principal_id=args.principal_id,
                              mission_ids=tuple(args.mission_id),
                              expires_at=args.expires_at, token_path=Path(args.token_file))
                  if args.action == "issue" else grant.revoke(args.grant_id))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
