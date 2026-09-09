#!/usr/bin/env python3
"""Fail-closed durable state for one Forge PyPI release operation.

The record binds already-qualified wheel and source-distribution bytes to an
exact protected-main source revision.  It does not allocate a product version,
perform a build, publish a package by itself, install Forge, or grant release
authority.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping


_OPERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
_SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
_REVISION = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_STATES = ("PREPARED", "QUALIFIED", "PUBLISHED", "CLEANUP_PENDING", "RELEASE_COMPLETE")
_ALLOWED = {
    "PREPARED": frozenset({"QUALIFIED"}),
    "QUALIFIED": frozenset({"PUBLISHED"}),
    "PUBLISHED": frozenset({"CLEANUP_PENDING", "RELEASE_COMPLETE"}),
    "CLEANUP_PENDING": frozenset({"RELEASE_COMPLETE"}),
    "RELEASE_COMPLETE": frozenset(),
}


class ReleaseOperationError(ValueError):
    """An immutable release identity or allowed state transition is invalid."""


def _json_compatible(value: object) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _json_compatible(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(_json_compatible(item) for item in value)
    return False


@dataclass(frozen=True)
class ReleaseOperation:
    """Immutable release identity plus its persisted lifecycle state."""

    operation_id: str
    product: str
    component: str
    version: str
    policy_revision: str
    source_revision: str
    artifacts: Mapping[str, str]
    state: str = "PREPARED"
    qualification: Mapping[str, object] | None = None
    publication_receipt: Mapping[str, object] | None = None
    cleanup: Mapping[str, object] | None = None

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        version: str,
        policy_revision: str,
        source_revision: str,
        artifacts: Mapping[str, str],
    ) -> "ReleaseOperation":
        if not isinstance(operation_id, str) or _OPERATION.fullmatch(operation_id) is None:
            raise ReleaseOperationError("release operation ID is invalid")
        if not isinstance(version, str) or _SEMVER.fullmatch(version) is None:
            raise ReleaseOperationError("release version is invalid")
        if not isinstance(policy_revision, str) or not policy_revision:
            raise ReleaseOperationError("release policy revision is invalid")
        if not isinstance(source_revision, str) or _REVISION.fullmatch(source_revision) is None:
            raise ReleaseOperationError("release source revision is invalid")
        if not isinstance(artifacts, Mapping) or set(artifacts) != {"wheel", "sdist"} or any(
            not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in artifacts.values()
        ):
            raise ReleaseOperationError("release artifacts must bind exact wheel and source-distribution SHA-256 values")
        return cls(
            operation_id=operation_id,
            product="forge",
            component="forge-autonomy",
            version=version,
            policy_revision=policy_revision,
            source_revision=source_revision,
            artifacts=dict(artifacts),
        )

    @classmethod
    def parse(cls, value: object) -> "ReleaseOperation":
        expected = {
            "operation_id", "product", "component", "version", "policy_revision", "source_revision",
            "artifacts", "state", "qualification", "publication_receipt", "cleanup",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ReleaseOperationError("release operation record has unknown or missing fields")
        if value.get("product") != "forge" or value.get("component") != "forge-autonomy":
            raise ReleaseOperationError("release operation has the wrong Forge product/component identity")
        operation = cls.create(
            operation_id=value["operation_id"], version=value["version"],
            policy_revision=value["policy_revision"], source_revision=value["source_revision"],
            artifacts=value["artifacts"],
        )
        state = value["state"]
        if state not in _STATES:
            raise ReleaseOperationError("release operation state is invalid")
        evidence: dict[str, Mapping[str, object] | None] = {}
        for key in ("qualification", "publication_receipt", "cleanup"):
            candidate = value[key]
            if candidate is not None and (
                not isinstance(candidate, Mapping) or not candidate or not _json_compatible(candidate)
            ):
                raise ReleaseOperationError(f"release operation {key} is invalid")
            evidence[key] = candidate
        if state in {"QUALIFIED", "PUBLISHED", "CLEANUP_PENDING", "RELEASE_COMPLETE"} and evidence["qualification"] is None:
            raise ReleaseOperationError("release operation is missing qualification evidence")
        if state in {"PUBLISHED", "CLEANUP_PENDING", "RELEASE_COMPLETE"} and evidence["publication_receipt"] is None:
            raise ReleaseOperationError("published release operation is missing publication receipt")
        if state in {"CLEANUP_PENDING", "RELEASE_COMPLETE"} and evidence["cleanup"] is None:
            raise ReleaseOperationError("post-publication release operation is missing cleanup evidence")
        return cls(
            **{
                **asdict(operation),
                "state": state,
                "qualification": evidence["qualification"],
                "publication_receipt": evidence["publication_receipt"],
                "cleanup": evidence["cleanup"],
            }
        )

    def same_identity(self, other: "ReleaseOperation") -> bool:
        return (
            self.operation_id, self.product, self.component, self.version, self.policy_revision,
            self.source_revision, dict(self.artifacts),
        ) == (
            other.operation_id, other.product, other.component, other.version, other.policy_revision,
            other.source_revision, dict(other.artifacts),
        )

    def transition(self, state: str, *, evidence: Mapping[str, object]) -> "ReleaseOperation":
        if state not in _ALLOWED.get(self.state, frozenset()):
            raise ReleaseOperationError(f"release transition {self.state} -> {state} is not permitted")
        if not isinstance(evidence, Mapping) or not evidence or not _json_compatible(evidence):
            raise ReleaseOperationError("release transition requires durable JSON evidence")
        values = asdict(self)
        values["state"] = state
        if state == "QUALIFIED":
            values["qualification"] = dict(evidence)
        elif state == "PUBLISHED":
            values["publication_receipt"] = dict(evidence)
        else:
            values["cleanup"] = dict(evidence)
        return ReleaseOperation(**values)


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


class ReleaseOperationStore:
    """One-file-lock release journal for a single Forge product release."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self._descriptor: int | None = None
        self._owner: str | None = None

    def _path(self, operation_id: str) -> Path:
        if not isinstance(operation_id, str) or _OPERATION.fullmatch(operation_id) is None:
            raise ReleaseOperationError("release operation ID is invalid")
        return self.root / "operations" / f"{operation_id}.json"

    @property
    def _lock(self) -> Path:
        return self.root / "release-operation.lock"

    def acquire(self, operation_id: str) -> None:
        self._path(operation_id)
        if self._descriptor is not None:
            raise ReleaseOperationError("this release operation store already owns the release lock")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self._lock, os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(descriptor)
            raise ReleaseOperationError("another release operation owns the release lock") from error
        try:
            os.ftruncate(descriptor, 0)
            os.write(descriptor, (operation_id + "\n").encode("utf-8"))
            os.fsync(descriptor)
        except BaseException:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
            raise
        self._descriptor, self._owner = descriptor, operation_id

    def release(self, operation_id: str) -> None:
        if self._descriptor is None or self._owner != operation_id:
            raise ReleaseOperationError("release operation does not own the release lock")
        try:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self._descriptor)
            self._descriptor, self._owner = None, None

    def _require_lock(self, operation_id: str) -> None:
        if self._descriptor is None or self._owner != operation_id:
            raise ReleaseOperationError("release operation must own the release lock")

    def load(self, operation_id: str) -> ReleaseOperation | None:
        path = self._path(operation_id)
        if not path.exists():
            return None
        try:
            return ReleaseOperation.parse(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            raise ReleaseOperationError("release operation record is unreadable") from error

    def save(self, operation: ReleaseOperation) -> ReleaseOperation:
        self._require_lock(operation.operation_id)
        existing = self.load(operation.operation_id)
        if existing is not None and existing != operation:
            raise ReleaseOperationError("release operation record is immutable; save only an identical recovery record")
        _atomic_json(self._path(operation.operation_id), asdict(operation))
        return operation

    def replace(self, previous: ReleaseOperation, current: ReleaseOperation) -> ReleaseOperation:
        self._require_lock(previous.operation_id)
        if not previous.same_identity(current) or self.load(previous.operation_id) != previous:
            raise ReleaseOperationError("release operation changed before transition")
        _atomic_json(self._path(current.operation_id), asdict(current))
        return current

    def record_publication(self, operation: ReleaseOperation) -> None:
        self._require_lock(operation.operation_id)
        if operation.state not in {"PUBLISHED", "CLEANUP_PENDING", "RELEASE_COMPLETE"}:
            raise ReleaseOperationError("only a published release may reserve its immutable identity")
        path = self.root / "published" / f"{operation.product}-{operation.component}-{operation.version}.json"
        identity = {
            "operation_id": operation.operation_id,
            "policy_revision": operation.policy_revision,
            "source_revision": operation.source_revision,
            "artifacts": dict(operation.artifacts),
            "publication_receipt": dict(operation.publication_receipt or {}),
        }
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ReleaseOperationError("published release identity is unreadable") from error
            if existing != identity:
                raise ReleaseOperationError("published release identity already exists with different bytes or provenance")
            return
        _atomic_json(path, identity)

    @staticmethod
    def artifact_digest(path: Path) -> str:
        candidate = Path(path).expanduser().resolve()
        if not candidate.is_file():
            raise ReleaseOperationError("release artifact is unavailable")
        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()


def _read_evidence(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseOperationError("release evidence is unreadable") from error
    if not isinstance(value, Mapping) or not value or not _json_compatible(value):
        raise ReleaseOperationError("release evidence must be a non-empty JSON object")
    return value


def _expected(args: argparse.Namespace) -> ReleaseOperation:
    def digest(path: Path | None, supplied: str | None, label: str) -> str:
        if path is not None and supplied is not None:
            raise ReleaseOperationError(f"release {label} accepts either a path or a digest, not both")
        if path is not None:
            return ReleaseOperationStore.artifact_digest(path)
        if not isinstance(supplied, str) or _SHA256.fullmatch(supplied) is None:
            raise ReleaseOperationError(f"release {label} requires an exact artifact path or SHA-256 digest")
        return supplied

    return ReleaseOperation.create(
        operation_id=args.operation_id,
        version=args.version,
        policy_revision=args.policy_revision,
        source_revision=args.source_revision,
        artifacts={
            "wheel": digest(args.wheel, args.wheel_digest, "wheel"),
            "sdist": digest(args.sdist, args.sdist_digest, "source distribution"),
        },
    )


def _load_expected(store: ReleaseOperationStore, expected: ReleaseOperation, *, qualified: bool = True) -> ReleaseOperation:
    current = store.load(expected.operation_id)
    if current is None or not current.same_identity(expected):
        raise ReleaseOperationError("release operation does not bind the exact requested identity")
    if qualified and current.state not in {"QUALIFIED", "PUBLISHED", "CLEANUP_PENDING", "RELEASE_COMPLETE"}:
        raise ReleaseOperationError("release operation is not qualified")
    return current


def prepare_qualified(store: ReleaseOperationStore, expected: ReleaseOperation, evidence: Mapping[str, object]) -> ReleaseOperation:
    store.acquire(expected.operation_id)
    try:
        current = store.load(expected.operation_id)
        if current is None:
            current = store.save(expected)
        elif not current.same_identity(expected):
            raise ReleaseOperationError("release operation ID already binds different bytes or provenance")
        if current.state == "PREPARED":
            current = store.replace(current, current.transition("QUALIFIED", evidence=evidence))
        elif dict(current.qualification or {}) != dict(evidence):
            raise ReleaseOperationError("qualified release evidence changed during resume")
        return _load_expected(store, expected)
    finally:
        store.release(expected.operation_id)


def mark_published(store: ReleaseOperationStore, expected: ReleaseOperation, evidence: Mapping[str, object]) -> ReleaseOperation:
    store.acquire(expected.operation_id)
    try:
        current = _load_expected(store, expected)
        if current.state == "QUALIFIED":
            current = store.replace(current, current.transition("PUBLISHED", evidence=evidence))
        elif current.state not in {"PUBLISHED", "CLEANUP_PENDING", "RELEASE_COMPLETE"}:
            raise ReleaseOperationError("release operation cannot be published from its current state")
        elif dict(current.publication_receipt or {}) != dict(evidence):
            raise ReleaseOperationError("published release receipt changed during resume")
        store.record_publication(current)
        return current
    finally:
        store.release(expected.operation_id)


def mark_cleanup_pending(store: ReleaseOperationStore, expected: ReleaseOperation, evidence: Mapping[str, object]) -> ReleaseOperation:
    store.acquire(expected.operation_id)
    try:
        current = _load_expected(store, expected)
        if current.state == "PUBLISHED":
            return store.replace(current, current.transition("CLEANUP_PENDING", evidence=evidence))
        if current.state == "CLEANUP_PENDING" and dict(current.cleanup or {}) == dict(evidence):
            return current
        raise ReleaseOperationError("release operation cannot record this cleanup-pending result")
    finally:
        store.release(expected.operation_id)


def complete(store: ReleaseOperationStore, expected: ReleaseOperation, evidence: Mapping[str, object]) -> ReleaseOperation:
    store.acquire(expected.operation_id)
    try:
        current = _load_expected(store, expected)
        if current.state in {"PUBLISHED", "CLEANUP_PENDING"}:
            current = store.replace(current, current.transition("RELEASE_COMPLETE", evidence=evidence))
        elif current.state != "RELEASE_COMPLETE" or dict(current.cleanup or {}) != dict(evidence):
            raise ReleaseOperationError("release operation cannot complete from its current state")
        store.record_publication(current)
        return current
    finally:
        store.release(expected.operation_id)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare-qualified", action="store_true")
    actions.add_argument("--validate-qualified", action="store_true")
    actions.add_argument("--mark-published", action="store_true")
    actions.add_argument("--mark-cleanup-pending", action="store_true")
    actions.add_argument("--complete", action="store_true")
    actions.add_argument("--show", action="store_true")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--policy-revision", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    parser.add_argument("--wheel-digest")
    parser.add_argument("--sdist-digest")
    parser.add_argument("--evidence-file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    needs_evidence = args.prepare_qualified or args.mark_published or args.mark_cleanup_pending or args.complete
    if args.evidence_file is None and needs_evidence:
        raise ReleaseOperationError("this release transition requires --evidence-file")
    if args.evidence_file is not None and (args.validate_qualified or args.show):
        raise ReleaseOperationError("this release operation does not accept --evidence-file")
    expected = _expected(args)
    store = ReleaseOperationStore(args.evidence_root)
    if args.prepare_qualified:
        result = prepare_qualified(store, expected, _read_evidence(args.evidence_file))
    elif args.validate_qualified:
        store.acquire(expected.operation_id)
        try:
            result = _load_expected(store, expected)
        finally:
            store.release(expected.operation_id)
    elif args.mark_published:
        result = mark_published(store, expected, _read_evidence(args.evidence_file))
    elif args.mark_cleanup_pending:
        result = mark_cleanup_pending(store, expected, _read_evidence(args.evidence_file))
    elif args.complete:
        result = complete(store, expected, _read_evidence(args.evidence_file))
    else:
        store.acquire(expected.operation_id)
        try:
            result = _load_expected(store, expected, qualified=False)
        finally:
            store.release(expected.operation_id)
    print(json.dumps(asdict(result), sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseOperationError as error:
        raise SystemExit(f"RELEASE_OPERATION_ERROR: {error}") from error
