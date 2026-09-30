"""Product-owned installed lifecycle boundaries for Forge Server Runtime.

The update assessment is strictly read-only.  The uninstall dispatcher owns
only Forge's mutable instance data; service definitions and immutable runtime
slots remain deployment-owner resources under the frozen Server V1 contract.
"""
from __future__ import annotations

import base64
import csv
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
from typing import Any, Callable, Iterator, Mapping
import zipfile

from .runtime.database import RUNTIME_SCHEMA_VERSION

try:  # Supported Server Runtime deployment targets are POSIX hosts.
    import fcntl
except ImportError:  # pragma: no cover - fail closed on unsupported hosts.
    fcntl = None  # type: ignore[assignment]


LIFECYCLE_CONTRACT = "forge-server-runtime-lifecycle/v1"
CONTROL_DIRECTORY = ".forge-server-runtime-lifecycle"
SUPPORTED_TRANSITIONS = {
    ("2.7.21", "2.7.22"): (37, 38),
    ("2.7.22", "2.7.23"): (38, 38),
    ("2.7.22", "2.7.24"): (38, 38),
    ("2.7.23", "2.7.24"): (38, 38),
    ("2.7.24", "2.7.25"): (38, 39),
    ("2.7.25", "2.7.26"): (39, 39),
    ("2.7.26", "2.7.27"): (39, 39),
    ("2.7.27", "2.7.28"): (39, 39),
    ("2.7.28", "2.7.29"): (39, 39),
    ("2.7.29", "2.7.30"): (39, 39),
    ("2.7.30", "2.7.31"): (39, 39),
    ("2.7.31", "2.7.32"): (39, 39),
    ("2.7.31", "2.7.33"): (39, 39),
    ("2.7.32", "2.7.33"): (39, 39),
    ("2.7.33", "2.7.34"): (39, 39),
    ("2.7.34", "2.7.35"): (39, 39),
    ("2.7.35", "2.7.38"): (39, 39),
    ("2.7.36", "2.7.38"): (39, 39),
    ("2.7.37", "2.7.38"): (39, 39),
    ("2.7.38", "2.7.39"): (39, 40),
}
SAME_SCHEMA_39_TRANSITIONS = frozenset(
    transition for transition, schemas in SUPPORTED_TRANSITIONS.items() if schemas == (39, 39)
)
NORMAL_RELEASE_TRANSITIONS = frozenset(
    transition for transition in SUPPORTED_TRANSITIONS if transition != ("2.7.21", "2.7.22")
)
SAFE_MISSION_STATES = frozenset({
    "BLOCKED", "FAILED", "COMPLETED", "ARCHIVED", "INTEGRATION_BLOCKED", "INTEGRATION_COMPLETE",
})
SAFE_SUBMISSION_STATES = frozenset({"RECONCILED", "BLOCKED", "FAILED", "SUPERSEDED"})
TERMINAL_PERMIT_STATES = frozenset({"INVALIDATED", "INVALIDATED_BY_OPERATIONAL_RESET"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_SOURCE = re.compile(r"[0-9a-f]{40}")


class InstalledLifecycleError(RuntimeError):
    """The selected lifecycle operation cannot proceed safely."""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _validate_identifier(label: str, value: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None or value in {".", ".."}:
        raise InstalledLifecycleError(f"{label} is not a safe opaque identity")


def _assert_no_symlink_components(path: Path, *, allow_missing: bool = False) -> None:
    if not path.is_absolute():
        raise InstalledLifecycleError(f"path must be absolute: {path}")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if allow_missing:
                return
            raise InstalledLifecycleError(f"required path is unavailable: {current}") from None
        if stat.S_ISLNK(mode):
            raise InstalledLifecycleError(f"path contains a symbolic-link component: {current}")


def _read_regular_bytes(path: Path, *, maximum_bytes: int = 512 * 1024 * 1024) -> bytes:
    _assert_no_symlink_components(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise InstalledLifecycleError(f"required regular file is unavailable: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise InstalledLifecycleError(f"required regular file is unavailable: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise InstalledLifecycleError(f"required file exceeds its bounded size: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: object) -> None:
    _assert_no_symlink_components(path.parent, allow_missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink_components(path.parent)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_regular_bytes(path, maximum_bytes=1024 * 1024))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstalledLifecycleError(f"durable lifecycle evidence is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise InstalledLifecycleError(f"durable lifecycle evidence is not an object: {path}")
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def validate_candidate_wheel(path: Path, version: str, expected_digest: str) -> tuple[bytes, dict[str, str]]:
    """Validate the exact canonical Forge wheel without executing candidate code."""
    if _DIGEST.fullmatch(expected_digest) is None:
        raise InstalledLifecycleError("candidate artifact digest is invalid")
    expected_name = f"forge_autonomy-{version}-py3-none-any.whl"
    if path.name != expected_name:
        raise InstalledLifecycleError("wheel filename does not match the selected product and version")
    wheel_bytes = _read_regular_bytes(path)
    if _digest_bytes(wheel_bytes) != expected_digest:
        raise InstalledLifecycleError("wheel digest does not match the selected candidate artifact")
    dist_info = f"forge_autonomy-{version}.dist-info"
    try:
        with zipfile.ZipFile(BytesIO(wheel_bytes)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise InstalledLifecycleError("wheel contains duplicate member paths")
            for info in infos:
                parts = Path(info.filename).parts
                mode = info.external_attr >> 16
                if (
                    info.filename.startswith("/") or "\\" in info.filename or ".." in parts
                    or not parts or parts[0] not in {"forge", dist_info} or stat.S_ISLNK(mode)
                ):
                    raise InstalledLifecycleError("wheel contains an unsafe or unexpected member path")
            metadata_name = f"{dist_info}/METADATA"
            wheel_metadata_name = f"{dist_info}/WHEEL"
            record_name = f"{dist_info}/RECORD"
            if any(name not in names for name in (metadata_name, wheel_metadata_name, record_name)):
                raise InstalledLifecycleError("wheel metadata is missing or ambiguous")
            metadata = BytesParser().parsebytes(archive.read(metadata_name))
            wheel_metadata = BytesParser().parsebytes(archive.read(wheel_metadata_name))
            if (
                metadata.get("Name") != "forge-autonomy" or metadata.get("Version") != version
                or wheel_metadata.get("Root-Is-Purelib") != "true"
                or "py3-none-any" not in wheel_metadata.get_all("Tag", [])
            ):
                raise InstalledLifecycleError("wheel package metadata does not match Forge")
            rows = list(csv.reader(StringIO(archive.read(record_name).decode("utf-8"))))
            if any(len(row) != 3 for row in rows):
                raise InstalledLifecycleError("wheel RECORD is malformed")
            records = {row[0]: (row[1], row[2]) for row in rows}
            files = [info for info in infos if not info.is_dir()]
            if len(records) != len(rows) or set(records) != {info.filename for info in files}:
                raise InstalledLifecycleError("wheel RECORD does not exactly enumerate the artifact")
            manifest: dict[str, str] = {}
            for info in files:
                payload = archive.read(info.filename)
                manifest[info.filename] = _digest_bytes(payload)
                recorded_hash, recorded_size = records[info.filename]
                if info.filename == record_name:
                    if recorded_hash or recorded_size:
                        raise InstalledLifecycleError("wheel RECORD self-entry is not canonical")
                    continue
                encoded = base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b"=").decode("ascii")
                if recorded_hash != f"sha256={encoded}" or recorded_size != str(len(payload)):
                    raise InstalledLifecycleError("wheel RECORD does not bind an artifact member")
    except (UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise InstalledLifecycleError("wheel is not a valid canonical ZIP artifact") from error
    return wheel_bytes, manifest


@dataclass(frozen=True)
class UpdateAssessmentRequest:
    data_root: str
    runtime_id: str
    installation_id: str
    installed_version: str
    installed_source: str
    installed_artifact_digest: str
    candidate_version: str
    candidate_source: str
    candidate_wheel: str
    candidate_artifact_digest: str

    def validate(self) -> None:
        _validate_identifier("runtime identity", self.runtime_id)
        _validate_identifier("installation identity", self.installation_id)
        if not Path(self.data_root).is_absolute() or not Path(self.candidate_wheel).is_absolute():
            raise InstalledLifecycleError("assessment paths must be absolute")
        if _SOURCE.fullmatch(self.installed_source) is None or _SOURCE.fullmatch(self.candidate_source) is None:
            raise InstalledLifecycleError("assessment source revisions must be exact")
        if (
            _DIGEST.fullmatch(self.installed_artifact_digest) is None
            or _DIGEST.fullmatch(self.candidate_artifact_digest) is None
        ):
            raise InstalledLifecycleError("assessment artifact digests are invalid")


def _runtime_snapshot(data_root: Path) -> dict[str, Any]:
    _assert_no_symlink_components(data_root)
    database = data_root / "forge.db"
    marker = data_root / "instance" / "runtime-instance.json"
    marker_value = _read_regular_bytes(marker, maximum_bytes=1024).decode("utf-8").strip()
    _assert_no_symlink_components(database)
    sidecars = tuple(Path(str(database) + suffix) for suffix in ("-wal", "-shm"))
    source_paths = (database,) + tuple(path for path in sidecars if path.exists())
    before = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns, _digest_bytes(_read_regular_bytes(path)))
                   for path in source_paths)
    scratch: tempfile.TemporaryDirectory[str] | None = None
    try:
        if len(source_paths) > 1:
            scratch = tempfile.TemporaryDirectory(prefix="forge-lifecycle-readback-")
            copied_database = Path(scratch.name) / database.name
            for path in source_paths:
                (Path(scratch.name) / path.name).write_bytes(_read_regular_bytes(path))
            uri = copied_database.resolve().as_uri() + "?mode=rw"
        else:
            uri = database.resolve().as_uri() + "?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True, timeout=0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        metadata = dict(connection.execute("SELECT key,value FROM runtime_metadata"))
        tables = {str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        dispatcher = [dict(row) for row in connection.execute(
            "SELECT status,active_mission_id FROM dispatcher_state"
        )] if "dispatcher_state" in tables else []
        missions = [dict(row) for row in connection.execute(
            "SELECT mission_id,status FROM mission_state ORDER BY mission_id"
        )] if "mission_state" in tables else []
        submissions = [dict(row) for row in connection.execute(
            "SELECT submission_id,state FROM scheduler_submissions ORDER BY submission_id"
        )] if "scheduler_submissions" in tables else []
        permits = [dict(row) for row in connection.execute(
            "SELECT permit_id,state FROM planning_provider_generation_permits ORDER BY permit_id"
        )] if "planning_provider_generation_permits" in tables else []
        planning = [dict(row) for row in connection.execute(
            "SELECT current_queue,pending_engineering_actions,blocked_engineering_actions FROM planning_state"
        )] if "planning_state" in tables else []
        reset = [dict(row) for row in connection.execute(
            "SELECT active_operation_id,state FROM operational_reset_state"
        )] if "operational_reset_state" in tables else []
        peer_detach = [dict(row) for row in connection.execute(
            "SELECT operation_id,phase FROM execution_host_peer_detach_operations ORDER BY operation_id"
        )] if "execution_host_peer_detach_operations" in tables else []
    except (OSError, UnicodeError, sqlite3.Error, IndexError, ValueError) as error:
        raise InstalledLifecycleError("runtime database readback failed") from error
    finally:
        if "connection" in locals():
            connection.close()
        if scratch is not None:
            scratch.cleanup()
    after_paths = (database,) + tuple(path for path in sidecars if path.exists())
    after = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns, _digest_bytes(_read_regular_bytes(path)))
                  for path in after_paths)
    if after != before:
        raise InstalledLifecycleError("runtime storage changed during read-only assessment")
    snapshot = {
        "marker": marker_value, "integrity": integrity, "foreign_keys": len(foreign_keys),
        "user_version": user_version, "metadata": metadata,
        "writer_state": {
            "dispatcher": dispatcher, "missions": missions, "submissions": submissions,
            "generation_permits": permits, "planning": planning, "operational_reset": reset,
            "peer_detach": peer_detach,
        },
    }
    snapshot["digest"] = _digest_bytes(_json_bytes(snapshot))
    return snapshot


def _assert_identity(
    snapshot: Mapping[str, Any], *, runtime_id: str, installation_id: str, installed_version: str | None = None,
    expected_schema: int = RUNTIME_SCHEMA_VERSION,
) -> None:
    metadata = snapshot.get("metadata")
    if not isinstance(metadata, Mapping):
        raise InstalledLifecycleError("runtime metadata readback is missing")
    if snapshot.get("marker") != runtime_id or metadata.get("runtime_id") != runtime_id:
        raise InstalledLifecycleError("selected data root belongs to a different runtime")
    if metadata.get("installation_id") != installation_id:
        raise InstalledLifecycleError("selected data root belongs to a different installation")
    if installed_version is not None and metadata.get("forge_version") != installed_version:
        raise InstalledLifecycleError("installed inventory version does not match runtime metadata")
    if snapshot.get("integrity") != "ok" or snapshot.get("foreign_keys") != 0:
        raise InstalledLifecycleError("selected runtime storage integrity is unavailable")
    if snapshot.get("user_version") != expected_schema:
        raise InstalledLifecycleError("selected runtime schema is unsupported")
    if metadata.get("schema_version") != str(expected_schema):
        raise InstalledLifecycleError("selected runtime metadata schema is unsupported")


def assess_update(request: UpdateAssessmentRequest) -> dict[str, Any]:
    """Return an exact read-only update decision; uncertainty never authorizes mutation."""
    candidate = {
        "version": request.candidate_version,
        "source_revision": request.candidate_source,
        "artifact_digest": request.candidate_artifact_digest,
    }
    selected = {
        "runtime_id": request.runtime_id,
        "installation_id": request.installation_id,
        "version": request.installed_version,
        "source_revision": request.installed_source,
        "artifact_digest": request.installed_artifact_digest,
    }
    try:
        request.validate()
        _, manifest = validate_candidate_wheel(
            Path(request.candidate_wheel), request.candidate_version, request.candidate_artifact_digest,
        )
        snapshot = _runtime_snapshot(Path(request.data_root))
        source_schemas = {
            before for (source, _target), (before, _after) in SUPPORTED_TRANSITIONS.items()
            if source == request.installed_version
        }
        if len(source_schemas) > 1:
            raise InstalledLifecycleError("installed version has ambiguous schema lineage")
        expected_schema = next(iter(source_schemas), RUNTIME_SCHEMA_VERSION)
        _assert_identity(
            snapshot, runtime_id=request.runtime_id, installation_id=request.installation_id,
            installed_version=request.installed_version,
            expected_schema=expected_schema,
        )
        exact_current = (
            request.installed_version == request.candidate_version
            and request.installed_source == request.candidate_source
            and request.installed_artifact_digest == request.candidate_artifact_digest
        )
        transition = (request.installed_version, request.candidate_version)
        if exact_current:
            state, reasons = "UP_TO_DATE", ["EXACT_ARTIFACT_ALREADY_SELECTED"]
        elif transition in SUPPORTED_TRANSITIONS:
            before_schema, after_schema = SUPPORTED_TRANSITIONS[transition]
            if snapshot["user_version"] != before_schema:
                state, reasons = "INCOMPATIBLE", ["RUNTIME_SCHEMA_OUTSIDE_BOUNDED_TRANSITION"]
            else:
                state, reasons = "UPDATE_AVAILABLE", ["EXACT_SUPPORTED_TRANSITION"]
        else:
            state, reasons = "INCOMPATIBLE", ["UNSUPPORTED_VERSION_TRANSITION"]
        evidence = {
            "runtime_snapshot_digest": snapshot["digest"],
            "candidate_manifest_digest": _digest_bytes(_json_bytes(manifest)),
        }
    except (InstalledLifecycleError, OSError, UnicodeError, ValueError) as error:
        state, reasons = "UNKNOWN", ["ASSESSMENT_FAILED_CLOSED"]
        evidence = {"error": str(error)}
    payload = {
        "contract": LIFECYCLE_CONTRACT,
        "operation": "UPDATE_ASSESSMENT",
        "state": state,
        "mutating": False,
        "selected_installation": selected,
        "candidate": candidate,
        "reason_codes": reasons,
        "evidence": evidence,
    }
    payload["assessment_digest"] = _digest_bytes(_json_bytes(payload))
    return payload


def _assert_quiescent(snapshot: Mapping[str, Any]) -> None:
    writer = snapshot.get("writer_state")
    if not isinstance(writer, Mapping):
        raise InstalledLifecycleError("writer-state readback is missing")
    dispatcher = writer.get("dispatcher")
    if not isinstance(dispatcher, list) or len(dispatcher) > 1 or (
        dispatcher and (
            not isinstance(dispatcher[0], Mapping) or dispatcher[0].get("status") != "IDLE"
            or dispatcher[0].get("active_mission_id") is not None
        )
    ):
        raise InstalledLifecycleError("Forge dispatcher is not durably idle")
    if any(row.get("status") not in SAFE_MISSION_STATES for row in writer.get("missions", ())):
        raise InstalledLifecycleError("Forge has non-terminal or non-paused Mission state")
    if any(row.get("state") not in SAFE_SUBMISSION_STATES for row in writer.get("submissions", ())):
        raise InstalledLifecycleError("Forge has a non-terminal scheduler submission")
    if any(row.get("state") not in TERMINAL_PERMIT_STATES for row in writer.get("generation_permits", ())):
        raise InstalledLifecycleError("Forge has an active provider-generation permit")
    for row in writer.get("planning", ()):
        for key in ("current_queue", "pending_engineering_actions", "blocked_engineering_actions"):
            try:
                value = json.loads(str(row.get(key)))
            except json.JSONDecodeError as error:
                raise InstalledLifecycleError("Forge planning queue is unreadable") from error
            if value:
                raise InstalledLifecycleError("Forge planning queue is not empty")
    if any(row.get("active_operation_id") is not None or row.get("state") != "IDLE"
           for row in writer.get("operational_reset", ())):
        raise InstalledLifecycleError("Forge operational reset maintenance is active")
    if any(row.get("phase") != "COMPLETE" for row in writer.get("peer_detach", ())):
        raise InstalledLifecycleError("Forge EP peer detach is unfinished")


@dataclass(frozen=True)
class UninstallRequest:
    operation_id: str
    instance_id: str
    runtime_id: str
    installation_id: str
    data_root: str
    instances_root: str

    def validate(self) -> None:
        for label, value in (
            ("operation identity", self.operation_id), ("instance identity", self.instance_id),
            ("runtime identity", self.runtime_id), ("installation identity", self.installation_id),
        ):
            _validate_identifier(label, value)
        if self.instance_id != self.runtime_id:
            raise InstalledLifecycleError("deployment instance does not bind the selected Forge runtime")
        data_root, instances_root = Path(self.data_root), Path(self.instances_root)
        if not data_root.is_absolute() or not instances_root.is_absolute():
            raise InstalledLifecycleError("uninstall paths must be absolute")
        _assert_no_symlink_components(instances_root)
        _assert_no_symlink_components(data_root, allow_missing=True)
        if data_root.parent != instances_root or data_root.name == CONTROL_DIRECTORY:
            raise InstalledLifecycleError("data root is not one direct managed instance root")

    @property
    def digest(self) -> str:
        return _digest_bytes(_json_bytes(asdict(self)))


@contextmanager
def _exclusive_locks(paths: tuple[Path, ...]) -> Iterator[None]:
    if fcntl is None:
        raise InstalledLifecycleError("POSIX lifecycle locking is unavailable")
    handles = []
    try:
        for path in paths:
            _assert_no_symlink_components(path.parent)
            if path.is_symlink():
                raise InstalledLifecycleError(f"lifecycle lock path is unsafe: {path}")
            handle = path.open("a+", encoding="utf-8")
            handles.append(handle)
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise InstalledLifecycleError(f"concurrent runtime activity owns lock: {path}") from error
        yield
    finally:
        for handle in reversed(handles):
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


def _assert_tree_has_no_links(root: Path) -> str:
    """Prove one mutable instance tree is exclusively product-owned and safe."""
    _assert_no_symlink_components(root)
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode):
        raise InstalledLifecycleError("instance root is not a directory")
    if stat.S_IMODE(root_info.st_mode) & 0o022:
        raise InstalledLifecycleError("instance root is group/world writable")
    entries: list[dict[str, object]] = []
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        parent = Path(directory)
        for name in sorted(names + files):
            path = parent / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise InstalledLifecycleError(f"instance tree contains an unsafe symbolic link: {path}")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise InstalledLifecycleError(f"instance tree contains an unsupported filesystem entry: {path}")
            if stat.S_IMODE(info.st_mode) & 0o022:
                raise InstalledLifecycleError(f"instance tree contains a group/world writable entry: {path}")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise InstalledLifecycleError(f"instance tree contains a non-exclusive hardlinked file: {path}")
            entries.append({
                "path": str(path.relative_to(root)), "mode": stat.S_IFMT(info.st_mode),
                "permissions": stat.S_IMODE(info.st_mode),
                "links": info.st_nlink if stat.S_ISREG(info.st_mode) else None,
                "size": info.st_size if stat.S_ISREG(info.st_mode) else None,
            })
    return _digest_bytes(_json_bytes(entries))


class InstalledUninstallDispatcher:
    """Durable, idempotent deletion of one exact quiescent Forge instance."""

    def __init__(
        self, request: UninstallRequest, *, interrupt_after: str | None = None,
        clock: Callable[[], str] = _now,
    ) -> None:
        request.validate()
        self.request = request
        self.data_root = Path(request.data_root)
        self.instances_root = Path(request.instances_root)
        identity = sha256(request.instance_id.encode()).hexdigest()
        self.control_root = self.instances_root / CONTROL_DIRECTORY / identity
        self.operation_root = self.control_root / "operations" / request.operation_id
        self.state_path = self.operation_root / "state.json"
        self.receipt_path = self.operation_root / "receipt.json"
        self.quarantine = self.operation_root / "detached-instance"
        self.lifecycle_lock = self.control_root / "lifecycle.lock"
        self.interrupt_after = interrupt_after
        self.clock = clock

    def _interrupt(self, phase: str) -> None:
        if self.interrupt_after == phase:
            raise InterruptedError(f"interrupted after {phase}")

    def _state(self) -> dict[str, Any]:
        if self.state_path.exists():
            state = _read_json(self.state_path)
            if state.get("request") != asdict(self.request) or state.get("request_digest") != self.request.digest:
                raise InstalledLifecycleError("operation identity already belongs to another uninstall request")
            return state
        state = {
            "contract": LIFECYCLE_CONTRACT, "operation": "UNINSTALL",
            "request": asdict(self.request), "request_digest": self.request.digest,
            "phase": "PREPARED", "prepared_at": self.clock(),
        }
        _atomic_json(self.state_path, state)
        return state

    def _save(self, state: dict[str, Any], phase: str, **evidence: object) -> dict[str, Any]:
        state = {**state, **evidence, "phase": phase, "updated_at": self.clock()}
        _atomic_json(self.state_path, state)
        return state

    def _verify_complete(self, state: Mapping[str, Any]) -> dict[str, Any]:
        if self.data_root.exists() or self.data_root.is_symlink() or self.quarantine.exists():
            raise InstalledLifecycleError("completed uninstall target was recreated or retained")
        receipt = _read_json(self.receipt_path)
        expected = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        if (
            receipt.get("request_digest") != self.request.digest or receipt.get("state") != "COMPLETE"
            or receipt.get("receipt_digest") != _digest_bytes(_json_bytes(expected))
            or state.get("receipt_digest") != receipt.get("receipt_digest")
        ):
            raise InstalledLifecycleError("completed uninstall receipt is inconsistent")
        return receipt

    def run(self) -> dict[str, Any]:
        self.control_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.control_root, 0o700)
        with _exclusive_locks((self.lifecycle_lock,)):
            state = self._state()
            if state.get("phase") == "COMPLETE":
                return self._verify_complete(state)
            if self.data_root.exists():
                lock_paths = (
                    self.data_root / "locks" / "forge-server-runtime.lock",
                    self.data_root / "forge-mission-controller.lock",
                    self.data_root / "forge-runtime-mutation.lock",
                    self.data_root / "locks" / "runtime.lock",
                )
                with _exclusive_locks(lock_paths):
                    snapshot = _runtime_snapshot(self.data_root)
                    _assert_identity(
                        snapshot, runtime_id=self.request.runtime_id,
                        installation_id=self.request.installation_id,
                    )
                    _assert_quiescent(snapshot)
                    tree_digest = _assert_tree_has_no_links(self.data_root)
                    state = self._save(
                        state, "VERIFIED", runtime_snapshot_digest=snapshot["digest"],
                        instance_tree_digest=tree_digest,
                    )
                    self._interrupt("verified")
                    if self.quarantine.exists():
                        raise InstalledLifecycleError("uninstall quarantine conflicts with the selected instance")
                    os.replace(self.data_root, self.quarantine)
                    _fsync_directory(self.instances_root)
                    _fsync_directory(self.operation_root)
            elif not self.quarantine.exists() and state.get("phase") not in {"DETACHED", "REMOVED"}:
                raise InstalledLifecycleError("selected instance disappeared outside its owning uninstall operation")
            if self.quarantine.exists():
                state = self._save(state, "DETACHED")
                self._interrupt("detached")
                shutil.rmtree(self.quarantine)
                _fsync_directory(self.operation_root)
            state = self._save(state, "REMOVED")
            self._interrupt("removed")
            receipt = {
                "contract": LIFECYCLE_CONTRACT, "operation": "UNINSTALL",
                "operation_id": self.request.operation_id, "instance_id": self.request.instance_id,
                "runtime_id": self.request.runtime_id, "installation_id": self.request.installation_id,
                "request_digest": self.request.digest, "state": "COMPLETE",
                "mutable_instance_data": "REMOVED", "service_definition": "DEPLOYMENT_OWNER",
                "immutable_runtime_slots": "PRESERVED", "completed_at": self.clock(),
            }
            receipt["receipt_digest"] = _digest_bytes(_json_bytes(receipt))
            _atomic_json(self.receipt_path, receipt)
            state = self._save(state, "COMPLETE", receipt_digest=receipt["receipt_digest"])
            return self._verify_complete(state)


def uninstall_status(instances_root: str, instance_id: str, operation_id: str) -> dict[str, Any]:
    """Read one exact durable uninstall operation without recreating its target."""
    _validate_identifier("instance identity", instance_id)
    _validate_identifier("operation identity", operation_id)
    root = Path(instances_root)
    if not root.is_absolute():
        raise InstalledLifecycleError("instances root must be absolute")
    _assert_no_symlink_components(root)
    identity = sha256(instance_id.encode()).hexdigest()
    operation_root = root / CONTROL_DIRECTORY / identity / "operations" / operation_id
    state = _read_json(operation_root / "state.json")
    result = {
        "contract": state.get("contract"), "operation": state.get("operation"),
        "operation_id": operation_id, "instance_id": instance_id, "phase": state.get("phase"),
        "request_digest": state.get("request_digest"),
    }
    if state.get("phase") == "COMPLETE":
        receipt = _read_json(operation_root / "receipt.json")
        result.update({"state": receipt.get("state"), "receipt_digest": receipt.get("receipt_digest")})
    else:
        result["state"] = "IN_PROGRESS"
    return result
