"""An explicit, revocable Forge Server read grant for one installed instance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile

from .execution_host_configuration import PeerConfigurationError, read_peer_configuration


CONTRACT_VERSION = "forge-workspace-read-grant/v1"


def _private_file(path: Path) -> bytes:
    """Read a private regular file without following a final-component symlink."""
    if path.parent.is_symlink():
        raise ValueError("read grant directory must not be a symbolic link")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            details = os.fstat(source.fileno())
            if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
                raise ValueError("read grant file must be private and regular")
            return source.read(4097)
    except OSError as error:
        raise ValueError("read grant file is unavailable") from error


def _document(path: Path) -> dict[str, object]:
    try:
        raw = _private_file(path)
        if len(raw) > 4096:
            raise ValueError("read grant file is too large")
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("read grant file is invalid") from error
    if not isinstance(value, dict) or set(value) != {
        "contract_version", "instance_id", "repository_id", "token_sha256", "revision", "state",
    }:
        raise ValueError("read grant document is invalid")
    if value["contract_version"] != CONTRACT_VERSION or value["state"] not in {"ACTIVE", "REVOKED"}:
        raise ValueError("read grant document is invalid")
    if type(value["revision"]) is not int or value["revision"] < 1:
        raise ValueError("read grant document is invalid")
    for name in ("instance_id", "repository_id"):
        if not isinstance(value[name], str) or not value[name] or len(value[name]) > 256:
            raise ValueError("read grant document is invalid")
    digest = value["token_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("read grant document is invalid")
    return value


def _repository_id(root: Path) -> str:
    try:
        peer = read_peer_configuration(root)
    except PeerConfigurationError as error:
        raise ValueError("repository binding is unavailable") from error
    if peer.configuration is None:
        raise ValueError("repository binding is unavailable")
    return peer.configuration.ep_repository_id


def _write_private(path: Path, content: bytes) -> None:
    if path.parent.is_symlink():
        raise ValueError("read grant directory must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("read grant path must not be a symbolic link")
    descriptor, temporary = tempfile.mkstemp(prefix=".forge-read-grant-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_new_private(path: Path, content: bytes) -> None:
    if path.parent.is_symlink():
        raise ValueError("token output directory must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


class WorkspaceReadGrant:
    """A grant file is revalidated on each request, so rotation and revocation are immediate."""

    def __init__(self, root: Path, instance_id: str, path: Path) -> None:
        self.root = root
        self.instance_id = instance_id
        self.path = path

    def authenticate(self, authorization: str | None) -> bool:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            return False
        try:
            document = self._bound_document()
        except ValueError:
            return False
        token = authorization[7:]
        return bool(token) and secrets.compare_digest(
            hashlib.sha256(token.encode("utf-8")).hexdigest(), document["token_sha256"]
        )

    def _bound_document(self) -> dict[str, object]:
        document = _document(self.path)
        if (document["state"] != "ACTIVE" or document["instance_id"] != self.instance_id
                or document["repository_id"] != _repository_id(self.root)):
            raise ValueError("read grant binding is unavailable")
        return document

    def scope(self) -> dict[str, str]:
        document = self._bound_document()
        return {
            "contract_version": "forge-workspace-status-read/v1",
            "instance_id": self.instance_id,
            "repository_id": document["repository_id"],
        }

    def issue(self, repository_id: str, token_path: Path, *, rotate: bool = False) -> int:
        if not repository_id or repository_id != _repository_id(self.root):
            raise ValueError("repository binding does not match the selected Forge instance")
        if token_path.resolve() == self.path.resolve():
            raise ValueError("token output and read grant paths must differ")
        if token_path.exists() or token_path.is_symlink():
            raise ValueError("token output path already exists")
        if self.path.exists() or self.path.is_symlink():
            if not rotate:
                raise ValueError("read grant already exists")
            previous = _document(self.path)
            if previous["instance_id"] != self.instance_id or previous["repository_id"] != repository_id:
                raise ValueError("read grant binding does not match")
            revision = previous["revision"] + 1
        elif rotate:
            raise ValueError("read grant does not exist")
        else:
            revision = 1
        token = secrets.token_urlsafe(48)
        document = {
            "contract_version": CONTRACT_VERSION,
            "instance_id": self.instance_id,
            "repository_id": repository_id,
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "revision": revision,
            "state": "ACTIVE",
        }
        _write_new_private(token_path, (token + "\n").encode("utf-8"))
        _write_private(self.path, json.dumps(document, sort_keys=True).encode("utf-8"))
        return revision

    def revoke(self) -> int:
        document = _document(self.path)
        if document["instance_id"] != self.instance_id:
            raise ValueError("read grant binding does not match")
        document["state"] = "REVOKED"
        document["revision"] += 1
        _write_private(self.path, json.dumps(document, sort_keys=True).encode("utf-8"))
        return document["revision"]


def main(argv: list[str] | None = None) -> int:
    """Installed operator command; tokens are written only to private files."""
    parser = argparse.ArgumentParser(prog="forge-workspace-read-grant")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("action", choices=("issue", "rotate", "revoke"))
    parser.add_argument("--repository-id")
    parser.add_argument("--token-file")
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root)
        root = Path(instance.data_root)
        grant = WorkspaceReadGrant(root, instance.instance_id, root / "credentials" / "workspace-read-grant.json")
        if args.action == "revoke":
            revision = grant.revoke()
        else:
            if not args.repository_id or not args.token_file:
                raise ValueError("--repository-id and --token-file are required")
            revision = grant.issue(args.repository_id, Path(args.token_file), rotate=args.action == "rotate")
        print(json.dumps({"status": "REVOKED" if args.action == "revoke" else "ACTIVE",
                          "revision": revision, "instance_id": instance.instance_id}, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
