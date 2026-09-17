#!/usr/bin/env python3
"""Bounded product-owned update controller for one installed Forge runtime.

This is an external maintenance provisioner, not a Forge Runtime command.  It
stages one exact qualified wheel in an immutable slot, takes the canonical
runtime mutation lock, creates and verifies a SQLite backup, qualifies Forge's
own migration on an isolated copy, fences the legacy command resolver, invokes
the candidate's owning migrator, and atomically activates the candidate.

The durable operation is intentionally narrow: callers must supply every
installation, artifact, source, identity, interpreter, and resolver binding.
It never starts a service, Mission, planner, provider, reset, or EP submission.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.parser import BytesParser
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Callable, Iterator, Mapping, Sequence
import zipfile

try:
    import fcntl
except ImportError:  # pragma: no cover - supported installation target is POSIX.
    fcntl = None  # type: ignore[assignment]


CONTRACT_VERSION = "forge-installed-update/v1"
SCHEMA_BEFORE = 37
SCHEMA_AFTER = 38
NEW_SCHEMA_38_TABLES = frozenset({
    "operational_reset_state",
    "operational_reset_operations",
    "operational_reset_audit",
    "operational_reset_tombstones",
    "operational_reset_artifact_steps",
})
VOLATILE_METADATA_KEYS = frozenset({
    "schema_version", "migration_version", "last_migration", "forge_version",
    "database_version", "last_access_at", "integrity_status",
})
ACTIVE_MISSION_STATES = frozenset({
    "READY", "ACTIVE", "WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE",
    "READY_TO_CONTINUE", "INTEGRATION_RUNNING",
})
ACTIVE_SUBMISSION_STATES = frozenset({
    "CREATED", "SUBMITTED", "ACCEPTED", "EXECUTING", "RECEIPT_AVAILABLE",
})
TERMINAL_PERMIT_STATES = frozenset({"CONSUMED", "CANCELLED", "EXPIRED", "FAILED", "REVOKED"})


class InstalledForgeUpdateError(RuntimeError):
    """The selected installation cannot be updated without weakening a gate."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise InstalledForgeUpdateError(f"required regular file is unavailable: {path}")
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_directory(path: Path, *, create: bool = False) -> Path:
    if not path.is_absolute():
        raise InstalledForgeUpdateError(f"path must be absolute: {path}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise InstalledForgeUpdateError(f"directory is unavailable or unsafe: {path}")
    return path


def _atomic_json(path: Path, value: object) -> None:
    _safe_directory(path.parent, create=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise InstalledForgeUpdateError(f"durable JSON evidence is unavailable or unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InstalledForgeUpdateError(f"durable JSON evidence is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise InstalledForgeUpdateError(f"durable JSON evidence is not an object: {path}")
    return value


def _replace_symlink(path: Path, target: str) -> None:
    _safe_directory(path.parent, create=True)
    temporary = path.with_name(f".{path.name}.link-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(target)
    os.replace(temporary, path)


def _resolved_link(path: Path) -> Path:
    if not path.is_symlink():
        raise InstalledForgeUpdateError(f"managed resolver is not a symlink: {path}")
    return path.resolve(strict=True)


def _environment() -> dict[str, str]:
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
    }
    if os.environ.get("HOME"):
        environment["HOME"] = os.environ["HOME"]
    return environment


def _run(arguments: Sequence[str], *, cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            tuple(arguments), cwd=cwd, env=_environment(), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=True,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        stdout = getattr(error, "stdout", "") or ""
        stderr = getattr(error, "stderr", "") or ""
        diagnostic = (stdout + "\n" + stderr).strip()[-2000:]
        raise InstalledForgeUpdateError(
            f"bounded subprocess failed: {arguments[0]}: {diagnostic or type(error).__name__}"
        ) from error


def installed_identity(interpreter: Path, *, cwd: Path) -> dict[str, Any]:
    program = """
import importlib.metadata, json, pathlib, sys
import forge
from forge._version import canonical_version
print(json.dumps({
    "version": canonical_version(),
    "distribution_version": importlib.metadata.version("forge-autonomy"),
    "module": str(pathlib.Path(forge.__file__).resolve()),
    "sys_executable": str(pathlib.Path(sys.executable).resolve()),
    "prefix": str(pathlib.Path(sys.prefix).resolve()),
}, sort_keys=True))
"""
    result = _run((str(interpreter), "-I", "-c", program), cwd=cwd)
    try:
        identity = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InstalledForgeUpdateError("installed identity readback is malformed") from error
    if not isinstance(identity, dict):
        raise InstalledForgeUpdateError("installed identity readback is malformed")
    return identity


@dataclass(frozen=True)
class UpdateRequest:
    operation_id: str
    version: str
    product_source: str
    wheel: str
    wheel_sha256: str
    qualification_receipt: str
    qualification_receipt_sha256: str
    controller_source: str
    controller_sha256: str
    data_root: str
    runtime_root: str
    runtime_id: str
    installation_id: str
    peer_configuration_digest: str
    resolver: str
    resolver_sha256: str
    existing_interpreter: str
    existing_version: str
    base_python: str

    def validate(self) -> None:
        identifiers = (self.operation_id, self.runtime_id, self.installation_id)
        if any(not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value)
               for value in identifiers):
            raise InstalledForgeUpdateError("operation and installation identities must be filesystem-safe")
        if self.version != "2.7.22" or self.existing_version != "2.7.21":
            raise InstalledForgeUpdateError("this bounded controller supports only the selected 2.7.21 to 2.7.22 update")
        for label, digest in (
            ("wheel", self.wheel_sha256), ("qualification receipt", self.qualification_receipt_sha256),
            ("controller", self.controller_sha256), ("resolver", self.resolver_sha256),
            ("peer configuration", self.peer_configuration_digest),
        ):
            if not digest.startswith("sha256:") or len(digest) != 71:
                raise InstalledForgeUpdateError(f"{label} digest is invalid")
        if len(self.product_source) != 40 or len(self.controller_source) != 40:
            raise InstalledForgeUpdateError("source revisions must be exact 40-character revisions")
        paths = (
            self.wheel, self.qualification_receipt, self.data_root, self.runtime_root,
            self.resolver, self.existing_interpreter, self.base_python,
        )
        if any(not Path(value).is_absolute() for value in paths):
            raise InstalledForgeUpdateError("all installation paths must be absolute")

    @property
    def digest(self) -> str:
        return _digest_bytes(_json_bytes(asdict(self)))


def validate_qualified_artifact(request: UpdateRequest) -> dict[str, Any]:
    wheel = Path(request.wheel)
    if file_digest(wheel) != request.wheel_sha256:
        raise InstalledForgeUpdateError("wheel digest does not match the selected qualified artifact")
    expected_name = f"forge_autonomy-{request.version}-py3-none-any.whl"
    if wheel.name != expected_name:
        raise InstalledForgeUpdateError("wheel filename does not match the selected product and version")
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            if any(name.startswith("/") or ".." in Path(name).parts for name in names):
                raise InstalledForgeUpdateError("wheel contains an unsafe member path")
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata_names) != 1:
                raise InstalledForgeUpdateError("wheel metadata is missing or ambiguous")
            metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
    except zipfile.BadZipFile as error:
        raise InstalledForgeUpdateError("wheel is not a valid ZIP artifact") from error
    if metadata.get("Name") != "forge-autonomy" or metadata.get("Version") != request.version:
        raise InstalledForgeUpdateError("wheel package metadata does not match Forge 2.7.22")

    receipt_path = Path(request.qualification_receipt)
    if file_digest(receipt_path) != request.qualification_receipt_sha256:
        raise InstalledForgeUpdateError("qualification receipt digest changed")
    receipt = _read_json(receipt_path)
    qualification = receipt.get("qualification")
    artifacts = receipt.get("artifacts")
    if (
        receipt.get("state") != "RELEASE_COMPLETE"
        or receipt.get("product") != "forge"
        or receipt.get("component") != "forge-autonomy"
        or receipt.get("version") != request.version
        or receipt.get("source_revision") != request.product_source
        or not isinstance(qualification, dict)
        or qualification.get("exact_main_sha") != request.product_source
        or qualification.get("qualification") != "forge-production-distribution"
        or not isinstance(artifacts, dict)
        or artifacts.get("wheel") != request.wheel_sha256
    ):
        raise InstalledForgeUpdateError("release-complete qualification does not bind the exact wheel and source")
    return {
        "wheel": str(wheel), "wheel_sha256": request.wheel_sha256,
        "receipt": str(receipt_path), "receipt_sha256": request.qualification_receipt_sha256,
        "release_operation_id": receipt.get("operation_id"),
    }


def _sqlite_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return value


def _table_digest(connection: sqlite3.Connection, table: str) -> tuple[int, str]:
    quoted = '"' + table.replace('"', '""') + '"'
    rows = [
        [_sqlite_value(value) for value in row]
        for row in connection.execute(f"SELECT * FROM {quoted}").fetchall()
    ]
    rows.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return len(rows), _digest_bytes(_json_bytes(rows))


def database_snapshot(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise InstalledForgeUpdateError(f"runtime database is unavailable or unsafe: {path}")
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        tables = sorted(row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ))
        table_metrics = {
            table: {"count": count, "digest": digest}
            for table in tables
            for count, digest in (_table_digest(connection, table),)
        }
        metadata = dict(connection.execute("SELECT key,value FROM runtime_metadata"))
        protected_metadata = {
            key: value for key, value in metadata.items() if key not in VOLATILE_METADATA_KEYS
        }
        peer_row = connection.execute(
            "SELECT binding_id,configuration_revision,configuration_digest,document "
            "FROM execution_host_peer_configuration WHERE singleton=1"
        ).fetchone() if "execution_host_peer_configuration" in tables else None
        peer = None if peer_row is None else {
            "binding_id": peer_row[0], "configuration_revision": peer_row[1],
            "configuration_digest": peer_row[2], "document_digest": _digest_bytes(str(peer_row[3]).encode()),
        }
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
            "SELECT dataset_generation,active_operation_id,state FROM operational_reset_state"
        )] if "operational_reset_state" in tables else []
    except sqlite3.Error as error:
        raise InstalledForgeUpdateError("runtime database readback failed") from error
    finally:
        if "connection" in locals():
            connection.close()
    snapshot = {
        "database": str(path), "integrity_check": integrity,
        "foreign_key_check": foreign_keys, "user_version": user_version,
        "metadata": metadata, "protected_metadata_digest": _digest_bytes(_json_bytes(protected_metadata)),
        "tables": table_metrics, "peer": peer,
        "writer_state": {
            "dispatcher": dispatcher, "missions": missions, "submissions": submissions,
            "generation_permits": permits, "planning": planning, "operational_reset": reset,
        },
    }
    logical = {key: value for key, value in snapshot.items() if key != "database"}
    snapshot["content_digest"] = _digest_bytes(_json_bytes(logical))
    snapshot["snapshot_digest"] = _digest_bytes(_json_bytes(snapshot))
    return snapshot


def assert_selected_installation(request: UpdateRequest, snapshot: Mapping[str, Any]) -> None:
    metadata = snapshot.get("metadata")
    peer = snapshot.get("peer")
    if not isinstance(metadata, Mapping):
        raise InstalledForgeUpdateError("runtime metadata readback is missing")
    if metadata.get("runtime_id") != request.runtime_id:
        raise InstalledForgeUpdateError("selected data root belongs to a different runtime")
    if metadata.get("installation_id") != request.installation_id:
        raise InstalledForgeUpdateError("selected data root belongs to a different installation")
    if snapshot.get("user_version") not in {SCHEMA_BEFORE, SCHEMA_AFTER}:
        raise InstalledForgeUpdateError("selected runtime schema is outside the bounded update path")
    if not isinstance(peer, Mapping) or peer.get("configuration_digest") != request.peer_configuration_digest:
        raise InstalledForgeUpdateError("selected peer configuration changed")
    marker = Path(request.data_root) / "instance" / "runtime-instance.json"
    if marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8").strip() != request.runtime_id:
        raise InstalledForgeUpdateError("runtime instance marker does not bind the selected runtime")


def assert_quiescent(snapshot: Mapping[str, Any]) -> None:
    writer = snapshot.get("writer_state")
    if not isinstance(writer, Mapping):
        raise InstalledForgeUpdateError("writer-state readback is missing")
    dispatcher = writer.get("dispatcher")
    if not isinstance(dispatcher, list) or len(dispatcher) != 1 or any(
        row.get("status") != "IDLE" or row.get("active_mission_id") is not None
        for row in dispatcher if isinstance(row, Mapping)
    ):
        raise InstalledForgeUpdateError("Forge dispatcher is not durably idle")
    missions = writer.get("missions") or []
    active_missions = [row for row in missions if isinstance(row, Mapping) and row.get("status") in ACTIVE_MISSION_STATES]
    if active_missions:
        raise InstalledForgeUpdateError("Forge has active or automatically resumable Mission state")
    submissions = writer.get("submissions") or []
    if any(isinstance(row, Mapping) and row.get("state") in ACTIVE_SUBMISSION_STATES for row in submissions):
        raise InstalledForgeUpdateError("Forge has an active scheduler submission")
    permits = writer.get("generation_permits") or []
    if any(isinstance(row, Mapping) and row.get("state") not in TERMINAL_PERMIT_STATES for row in permits):
        raise InstalledForgeUpdateError("Forge has an active provider-generation permit")
    for row in writer.get("planning") or []:
        if not isinstance(row, Mapping):
            raise InstalledForgeUpdateError("Forge planning state is malformed")
        for key in ("current_queue", "pending_engineering_actions", "blocked_engineering_actions"):
            try:
                value = json.loads(str(row.get(key)))
            except json.JSONDecodeError as error:
                raise InstalledForgeUpdateError("Forge planning queue is unreadable") from error
            if value:
                raise InstalledForgeUpdateError("Forge planning queue is not empty")
    reset = writer.get("operational_reset") or []
    if any(not isinstance(row, Mapping) or row.get("active_operation_id") is not None or row.get("state") != "IDLE"
           for row in reset):
        raise InstalledForgeUpdateError("Forge operational reset maintenance is active")


def verify_preservation(before: Mapping[str, Any], after: Mapping[str, Any], request: UpdateRequest) -> dict[str, Any]:
    if after.get("integrity_check") != "ok" or after.get("foreign_key_check") != []:
        raise InstalledForgeUpdateError("migrated runtime failed SQLite integrity validation")
    if after.get("user_version") != SCHEMA_AFTER:
        raise InstalledForgeUpdateError("Forge owning migration did not reach schema 38")
    before_metadata, after_metadata = before.get("metadata"), after.get("metadata")
    if not isinstance(before_metadata, Mapping) or not isinstance(after_metadata, Mapping):
        raise InstalledForgeUpdateError("migration metadata readback is incomplete")
    for key, expected in (
        ("runtime_id", request.runtime_id), ("installation_id", request.installation_id),
    ):
        if before_metadata.get(key) != expected or after_metadata.get(key) != expected:
            raise InstalledForgeUpdateError(f"migration changed selected {key}")
    if after.get("protected_metadata_digest") != before.get("protected_metadata_digest"):
        raise InstalledForgeUpdateError("migration changed protected runtime metadata")
    if after.get("peer") != before.get("peer"):
        raise InstalledForgeUpdateError("migration changed the configured Forge-to-EP peer binding")
    before_tables, after_tables = before.get("tables"), after.get("tables")
    if not isinstance(before_tables, Mapping) or not isinstance(after_tables, Mapping):
        raise InstalledForgeUpdateError("migration table readback is incomplete")
    for table, metric in before_tables.items():
        if table == "runtime_metadata":
            continue
        if after_tables.get(table) != metric:
            raise InstalledForgeUpdateError(f"migration changed historical table contents: {table}")
    new_tables = set(after_tables) - set(before_tables)
    if new_tables != set(NEW_SCHEMA_38_TABLES):
        raise InstalledForgeUpdateError("migration produced an unexpected schema-38 table set")
    expected_counts = {table: 0 for table in NEW_SCHEMA_38_TABLES}
    expected_counts["operational_reset_state"] = 1
    if any(after_tables[table]["count"] != count for table, count in expected_counts.items()):
        raise InstalledForgeUpdateError("migration initialized unexpected operational-reset data")
    reset = after.get("writer_state", {}).get("operational_reset", [])
    if reset != [{"dataset_generation": 0, "active_operation_id": None, "state": "IDLE"}]:
        raise InstalledForgeUpdateError("schema-38 reset state is not an idle, fresh control record")
    return {
        "status": "PASS", "from_schema": SCHEMA_BEFORE, "to_schema": SCHEMA_AFTER,
        "preserved_table_count": len(before_tables) - 1,
        "added_tables": sorted(new_tables),
        "protected_metadata_digest": after.get("protected_metadata_digest"),
        "peer_configuration_digest": request.peer_configuration_digest,
    }


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    if fcntl is None:
        raise InstalledForgeUpdateError("POSIX installation locking is unavailable")
    _safe_directory(path.parent, create=True)
    if path.is_symlink():
        raise InstalledForgeUpdateError(f"installation lock path is unsafe: {path}")
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise InstalledForgeUpdateError(f"concurrent maintenance owns lock: {path}") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _copy_sqlite_backup(source: Path, destination: Path) -> dict[str, Any]:
    _safe_directory(destination.parent, create=True)
    if destination.exists() or destination.is_symlink():
        raise InstalledForgeUpdateError("installation backup already exists without matching durable evidence")
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    if temporary.exists():
        temporary.unlink()
    try:
        source_connection = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        destination_connection = sqlite3.connect(temporary)
        source_connection.backup(destination_connection)
        destination_connection.commit()
        if destination_connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise InstalledForgeUpdateError("SQLite backup integrity check failed")
        if destination_connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise InstalledForgeUpdateError("SQLite backup foreign-key check failed")
        destination_connection.close()
        source_connection.close()
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except sqlite3.Error as error:
        raise InstalledForgeUpdateError("consistent SQLite backup failed") from error
    finally:
        for connection_name in ("destination_connection", "source_connection"):
            connection = locals().get(connection_name)
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
        if temporary.exists():
            temporary.unlink()
    verification = database_snapshot(destination)
    return {
        "path": str(destination), "sha256": file_digest(destination),
        "size": destination.stat().st_size, "integrity_check": verification["integrity_check"],
        "foreign_key_check": verification["foreign_key_check"],
        "snapshot_digest": verification["snapshot_digest"],
    }


def _candidate_migrate(executable: Path, data_root: Path, *, cwd: Path) -> dict[str, Any]:
    result = _run((str(executable), "--data-root", str(data_root), "server", "init"), cwd=cwd)
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InstalledForgeUpdateError("candidate migration readback is malformed") from error
    if output.get("storage_schema") != str(SCHEMA_AFTER) or output.get("initialized") is not True:
        raise InstalledForgeUpdateError("candidate migration did not return schema-38 installed readback")
    return output


class InstalledForgeUpdateController:
    def __init__(
        self,
        request: UpdateRequest,
        *,
        process_reader: Callable[[], Sequence[str]] | None = None,
        interrupt_after: str | None = None,
    ) -> None:
        request.validate()
        self.request = request
        self.data_root = Path(request.data_root)
        self.runtime_root = Path(request.runtime_root)
        self.database = self.data_root / "forge.db"
        self.operation_root = self.data_root / "artifacts" / "installation" / request.operation_id
        self.state_path = self.operation_root / "operation.json"
        self.receipt_path = self.operation_root / "receipt.json"
        self.backup_root = self.data_root / "backups" / "installation" / request.operation_id
        self.backup_path = self.backup_root / "forge-schema37.sqlite3"
        self.slot = self.runtime_root / "slots" / f"{request.version}-{request.wheel_sha256.removeprefix('sha256:')[:12]}"
        self.slot_receipt = self.slot / "forge-installation-slot.json"
        self.current = self.runtime_root / "current"
        self.stable_resolver = self.runtime_root / "bin" / "forge"
        self.fenced_resolver = self.runtime_root / "fenced" / "forge"
        self.legacy_entrypoint = self.runtime_root / "legacy" / (
            request.resolver_sha256.removeprefix("sha256:")[:16] + "-forge"
        )
        self.process_reader = process_reader or self._processes
        self.interrupt_after = interrupt_after

    def _state(self) -> dict[str, Any]:
        if self.state_path.exists():
            state = _read_json(self.state_path)
            if state.get("contract_version") != CONTRACT_VERSION or state.get("request") != asdict(self.request):
                raise InstalledForgeUpdateError("durable update operation conflicts with the requested target")
            return state
        state = {
            "contract_version": CONTRACT_VERSION, "operation_id": self.request.operation_id,
            "request": asdict(self.request), "request_digest": self.request.digest,
            "phase": "PREPARED", "created_at": _now(), "updated_at": _now(),
            "history": [{"phase": "PREPARED", "at": _now()}],
        }
        _atomic_json(self.state_path, state)
        return state

    def _advance(self, state: dict[str, Any], phase: str, **evidence: object) -> dict[str, Any]:
        updated = {**state, **evidence, "phase": phase, "updated_at": _now()}
        history = list(state.get("history", []))
        history.append({"phase": phase, "at": updated["updated_at"]})
        updated["history"] = history
        _atomic_json(self.state_path, updated)
        return updated

    def _interrupt(self, point: str) -> None:
        if self.interrupt_after == point:
            raise InstalledForgeUpdateError(f"simulated interruption after {point}")

    def _processes(self) -> Sequence[str]:
        result = _run(("/bin/ps", "-axo", "pid=,ppid=,command="), cwd=self.runtime_root, timeout=30)
        processes: list[str] = []
        own = {os.getpid(), os.getppid()}
        for line in result.stdout.splitlines():
            fields = line.strip().split(None, 2)
            if len(fields) != 3:
                continue
            try:
                pid, parent = int(fields[0]), int(fields[1])
            except ValueError:
                continue
            if pid in own or parent in own:
                continue
            processes.append(fields[2])
        return processes

    def _assert_no_runtime_process(self) -> None:
        needles = (
            self.request.data_root, self.request.resolver, self.request.existing_interpreter,
            str(self.runtime_root / "venv"), str(self.slot),
        )
        matches = [command for command in self.process_reader() if any(needle in command for needle in needles)]
        if matches:
            raise InstalledForgeUpdateError("a selected Forge runtime process is still active")

    def _stage(self, state: dict[str, Any]) -> dict[str, Any]:
        qualification = validate_qualified_artifact(self.request)
        if file_digest(Path(__file__)) != self.request.controller_sha256:
            raise InstalledForgeUpdateError("installation controller bytes do not match the protected candidate")
        if self.slot_receipt.exists():
            receipt = _read_json(self.slot_receipt)
            if receipt.get("request_digest") != self.request.digest:
                raise InstalledForgeUpdateError("immutable candidate slot belongs to a different request")
        elif self.slot.exists() and not self.slot.is_symlink():
            identity = installed_identity(self.slot / "bin" / "python", cwd=self.runtime_root)
            if (
                identity.get("version") != self.request.version
                or identity.get("distribution_version") != self.request.version
                or not str(identity.get("module", "")).startswith(str(self.slot.resolve()) + os.sep)
            ):
                raise InstalledForgeUpdateError("unreceipted candidate slot cannot be safely adopted")
            _atomic_json(self.slot_receipt, {
                "contract_version": CONTRACT_VERSION, "request_digest": self.request.digest,
                "wheel_sha256": self.request.wheel_sha256, "product_source": self.request.product_source,
                "version": self.request.version, "identity": identity, "staged_at": _now(),
                "recovered_after_atomic_slot_move": True,
            })
        else:
            stage = self.runtime_root / "slots" / f".stage-{self.request.operation_id}"
            _safe_directory(stage.parent, create=True)
            if stage.is_symlink():
                raise InstalledForgeUpdateError("candidate staging path is unsafe")
            _run((self.request.base_python, "-m", "venv", str(stage)), cwd=self.runtime_root)
            candidate_python = stage / "bin" / "python"
            _run((str(candidate_python), "-m", "pip", "install", "--no-index", "--no-deps", self.request.wheel),
                 cwd=self.runtime_root)
            identity = installed_identity(candidate_python, cwd=self.runtime_root)
            if (
                identity.get("version") != self.request.version
                or identity.get("distribution_version") != self.request.version
                or not str(identity.get("module", "")).startswith(str(stage.resolve()) + os.sep)
                or Path(str(identity.get("prefix"))).resolve() != stage.resolve()
            ):
                raise InstalledForgeUpdateError("candidate slot identity is inconsistent")
            if self.slot.exists() or self.slot.is_symlink():
                raise InstalledForgeUpdateError("candidate slot appeared concurrently")
            os.replace(stage, self.slot)
        identity = installed_identity(self.slot / "bin" / "python", cwd=self.runtime_root)
        if identity.get("version") != self.request.version or not str(identity.get("module", "")).startswith(str(self.slot) + os.sep):
            raise InstalledForgeUpdateError("staged candidate readback changed")
        if not self.slot_receipt.exists():
            _atomic_json(self.slot_receipt, {
                "contract_version": CONTRACT_VERSION, "request_digest": self.request.digest,
                "wheel_sha256": self.request.wheel_sha256, "product_source": self.request.product_source,
                "version": self.request.version, "identity": identity, "staged_at": _now(),
            })
        return self._advance(state, "STAGED", artifact_qualification=qualification, candidate=identity,
                             candidate_slot=str(self.slot))

    def _adopt_resolver(self, state: dict[str, Any]) -> dict[str, Any]:
        resolver = Path(self.request.resolver)
        _safe_directory(self.runtime_root / "legacy", create=True)
        _safe_directory(self.runtime_root / "bin", create=True)
        _safe_directory(self.runtime_root / "fenced", create=True)
        if not self.legacy_entrypoint.exists():
            if resolver.is_symlink() or not resolver.is_file() or file_digest(resolver) != self.request.resolver_sha256:
                raise InstalledForgeUpdateError("legacy command resolver changed before adoption")
            identity = installed_identity(Path(self.request.existing_interpreter), cwd=self.runtime_root)
            if identity.get("version") != self.request.existing_version:
                raise InstalledForgeUpdateError("legacy interpreter no longer provides the selected Forge version")
            shutil.copy2(resolver, self.legacy_entrypoint)
            os.chmod(self.legacy_entrypoint, resolver.stat().st_mode & 0o777)
        elif file_digest(self.legacy_entrypoint) != self.request.resolver_sha256:
            raise InstalledForgeUpdateError("retained legacy entrypoint changed")
        fence = (
            "#!/bin/sh\n"
            f"echo 'Forge installation maintenance is active: {self.request.operation_id}' >&2\n"
            "exit 75\n"
        )
        if not self.fenced_resolver.exists():
            descriptor = os.open(self.fenced_resolver, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(fence)
        elif self.fenced_resolver.read_text(encoding="utf-8") != fence:
            raise InstalledForgeUpdateError("maintenance fence launcher changed")
        if not self.current.exists() and not self.current.is_symlink():
            _replace_symlink(self.current, os.path.relpath(self.legacy_entrypoint, self.runtime_root))
        if not self.stable_resolver.exists() and not self.stable_resolver.is_symlink():
            _replace_symlink(self.stable_resolver, "../current")
        elif _resolved_link(self.stable_resolver) != _resolved_link(self.current):
            # The stable link follows current; compare its textual contract, not
            # a transient current target, when it already exists.
            if os.readlink(self.stable_resolver) != "../current":
                raise InstalledForgeUpdateError("stable Forge resolver changed")
        expected_external = self.stable_resolver.resolve(strict=True)
        if resolver.is_symlink():
            if resolver.resolve(strict=True) != expected_external:
                raise InstalledForgeUpdateError("external Forge resolver was retargeted")
        else:
            if file_digest(resolver) != self.request.resolver_sha256:
                raise InstalledForgeUpdateError("external Forge resolver changed")
            _replace_symlink(resolver, str(self.stable_resolver))
        return self._advance(state, "ADOPTED", resolver={
            "external": str(resolver), "stable": str(self.stable_resolver),
            "legacy": str(self.legacy_entrypoint), "legacy_sha256": self.request.resolver_sha256,
        })

    def _backup(self, state: dict[str, Any], before: Mapping[str, Any]) -> dict[str, Any]:
        existing = state.get("backup")
        if isinstance(existing, Mapping):
            if existing.get("path") != str(self.backup_path) or file_digest(self.backup_path) != existing.get("sha256"):
                raise InstalledForgeUpdateError("durable installation backup changed")
            backup = dict(existing)
        else:
            backup = _copy_sqlite_backup(self.database, self.backup_path)
            backup["created_at"] = _now()
            backup["source_wal_present"] = self.database.with_name(self.database.name + "-wal").exists()
            backup["source_shm_present"] = self.database.with_name(self.database.name + "-shm").exists()
        return self._advance(state, "BACKED_UP", before=before, backup=backup)

    def _qualify_copy(self, state: dict[str, Any], before: Mapping[str, Any]) -> dict[str, Any]:
        existing = state.get("migration_qualification")
        if isinstance(existing, Mapping) and existing.get("status") == "PASS":
            return state
        root = self.operation_root / "qualification-copy"
        _safe_directory(root, create=True)
        database = root / "forge.db"
        temporary = root / f".forge.db.tmp-{os.getpid()}"
        shutil.copy2(self.backup_path, temporary)
        os.replace(temporary, database)
        for suffix in ("-wal", "-shm"):
            sidecar = root / ("forge.db" + suffix)
            if sidecar.exists() and not sidecar.is_symlink():
                sidecar.unlink()
        instance = _safe_directory(root / "instance", create=True)
        marker = instance / "runtime-instance.json"
        marker.write_text(self.request.runtime_id + "\n", encoding="utf-8")
        os.chmod(marker, 0o600)
        copy_before = database_snapshot(database)
        if copy_before.get("content_digest") != before.get("content_digest"):
            raise InstalledForgeUpdateError("isolated qualification copy does not match the consistent backup")
        _candidate_migrate(self.slot / "bin" / "forge", root, cwd=self.runtime_root)
        copy_after = database_snapshot(database)
        qualification = verify_preservation(copy_before, copy_after, self.request)
        qualification.update({
            "qualified_at": _now(), "copy_root": str(root),
            "before_snapshot_digest": copy_before["snapshot_digest"],
            "after_snapshot_digest": copy_after["snapshot_digest"],
        })
        return self._advance(state, "MIGRATION_QUALIFIED", migration_qualification=qualification)

    def _fence(self, state: dict[str, Any]) -> dict[str, Any]:
        _replace_symlink(self.current, os.path.relpath(self.fenced_resolver, self.runtime_root))
        if _resolved_link(Path(self.request.resolver)) != self.fenced_resolver.resolve():
            raise InstalledForgeUpdateError("external resolver did not enter the maintenance fence")
        return self._advance(state, "FENCED", safety_disposition="LEGACY_COMMAND_FENCED")

    def _restore_legacy_before_migration(self, state: dict[str, Any], error: Exception) -> None:
        _replace_symlink(self.current, os.path.relpath(self.legacy_entrypoint, self.runtime_root))
        self._advance(
            state, state.get("phase", "RECOVERY_PENDING"),
            safety_disposition="LEGACY_RESTORED_BEFORE_MIGRATION", last_error=str(error),
        )

    def _migrate_live(self, state: dict[str, Any], before: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        current = database_snapshot(self.database)
        if current.get("user_version") == SCHEMA_BEFORE:
            state = self._fence(state)
            self._interrupt("fence")
            output = _candidate_migrate(self.slot / "bin" / "forge", self.data_root, cwd=self.runtime_root)
            after = database_snapshot(self.database)
            preservation = verify_preservation(before, after, self.request)
            state = self._advance(
                state, "MIGRATED", live_migration={
                    **preservation, "migrated_at": _now(), "candidate_output": output,
                    "before_snapshot_digest": before["snapshot_digest"],
                    "after_snapshot_digest": after["snapshot_digest"],
                }, safety_disposition="CANDIDATE_REQUIRED_SCHEMA_38",
            )
            self._interrupt("migration")
            return state, after
        if current.get("user_version") == SCHEMA_AFTER:
            preservation = verify_preservation(before, current, self.request)
            if state.get("phase") not in {"MIGRATED", "ACTIVATING", "ACTIVATED", "COMPLETE"}:
                state = self._advance(
                    state, "MIGRATED", live_migration={
                        **preservation, "reconciled_at": _now(),
                        "before_snapshot_digest": before["snapshot_digest"],
                        "after_snapshot_digest": current["snapshot_digest"],
                    }, safety_disposition="CANDIDATE_REQUIRED_SCHEMA_38",
                )
            return state, current
        raise InstalledForgeUpdateError("live runtime schema changed outside the bounded operation")

    def _activate(self, state: dict[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
        state = self._advance(state, "ACTIVATING", safety_disposition="CANDIDATE_ACTIVATION_IN_PROGRESS")
        candidate = self.slot / "bin" / "forge"
        _replace_symlink(self.current, os.path.relpath(candidate, self.runtime_root))
        self._interrupt("activation")
        if _resolved_link(Path(self.request.resolver)) != candidate.resolve():
            raise InstalledForgeUpdateError("external command resolver did not activate the candidate")
        identity = installed_identity(self.slot / "bin" / "python", cwd=self.runtime_root)
        version = _run((self.request.resolver, "--version"), cwd=self.runtime_root).stdout.strip()
        status_result = _run(
            (self.request.resolver, "--data-root", self.request.data_root, "server", "status"),
            cwd=self.runtime_root,
        )
        try:
            status = json.loads(status_result.stdout)
        except json.JSONDecodeError as error:
            raise InstalledForgeUpdateError("activated CLI status readback is malformed") from error
        if (
            identity.get("version") != self.request.version
            or version != self.request.version
            or identity.get("sys_executable") != str((self.slot / "bin" / "python").resolve())
            or not str(identity.get("module", "")).startswith(str(self.slot) + os.sep)
            or status.get("product_version") != self.request.version
            or status.get("data_root") != self.request.data_root
            or status.get("instance_id") != self.request.runtime_id
            or status.get("storage_schema") != str(SCHEMA_AFTER)
        ):
            raise InstalledForgeUpdateError("activated Forge CLI readback does not match the selected installation")
        final_snapshot = database_snapshot(self.database)
        preservation = verify_preservation(state["before"], final_snapshot, self.request)
        return self._advance(
            state, "ACTIVATED", installed_readback={
                "identity": identity, "cli_version": version, "status": status,
                "database_snapshot_digest": final_snapshot["snapshot_digest"],
                "preservation": preservation, "resolver": self.request.resolver,
                "resolved_executable": str(candidate.resolve()),
            }, safety_disposition="CANDIDATE_ACTIVE",
        )

    def _secure_failure(self, state: dict[str, Any], error: Exception) -> None:
        """Leave a pre-migration legacy route or a schema-38-safe candidate/fence."""
        current = database_snapshot(self.database)
        if current.get("user_version") == SCHEMA_BEFORE and self.legacy_entrypoint.exists():
            self._restore_legacy_before_migration(state, error)
            return
        candidate = (self.slot / "bin" / "forge").resolve()
        if not self.current.is_symlink() or _resolved_link(self.current) != candidate:
            _replace_symlink(self.current, os.path.relpath(self.fenced_resolver, self.runtime_root))
        self._advance(
            state, state.get("phase", "RECOVERY_PENDING"),
            safety_disposition="SCHEMA_38_OLD_BINARY_FENCED", last_error=str(error),
        )

    def run(self) -> dict[str, Any]:
        _safe_directory(self.data_root)
        _safe_directory(self.runtime_root)
        _safe_directory(self.operation_root, create=True)
        os.chmod(self.operation_root, 0o700)
        state = self._state()
        if state.get("phase") == "COMPLETE":
            receipt = _read_json(self.receipt_path)
            if receipt.get("request_digest") != self.request.digest:
                raise InstalledForgeUpdateError("completed update receipt conflicts with this request")
            return receipt

        state = self._stage(state)
        self._interrupt("stage")
        update_lock = self.runtime_root / "locks" / "installation-update.lock"
        runtime_lock = self.data_root / "forge-runtime-mutation.lock"
        with ExitStack() as locks:
            locks.enter_context(exclusive_lock(update_lock))
            locks.enter_context(exclusive_lock(runtime_lock))
            self._assert_no_runtime_process()
            live = database_snapshot(self.database)
            assert_selected_installation(self.request, live)
            assert_quiescent(live)
            try:
                state = self._adopt_resolver(state)
                self._interrupt("adoption")
                before = state.get("before")
                if not isinstance(before, Mapping):
                    if live.get("user_version") != SCHEMA_BEFORE:
                        raise InstalledForgeUpdateError("schema 38 lacks this operation's pre-migration snapshot")
                    before = live
                assert_selected_installation(self.request, before)
                if before.get("user_version") != SCHEMA_BEFORE:
                    raise InstalledForgeUpdateError("durable pre-migration snapshot is not schema 37")
                state = self._backup(state, before)
                self._interrupt("backup")
                state = self._qualify_copy(state, before)
                self._interrupt("qualification")
                state, after = self._migrate_live(state, before)
                state = self._activate(state, after)
                receipt = {
                    "contract_version": CONTRACT_VERSION,
                    "operation_id": self.request.operation_id,
                    "request_digest": self.request.digest,
                    "state": "COMPLETE",
                    "product": "forge",
                    "version": self.request.version,
                    "product_source": self.request.product_source,
                    "wheel_sha256": self.request.wheel_sha256,
                    "controller_source": self.request.controller_source,
                    "controller_sha256": self.request.controller_sha256,
                    "runtime_id": self.request.runtime_id,
                    "installation_id": self.request.installation_id,
                    "data_root": self.request.data_root,
                    "backup": state["backup"],
                    "migration_qualification": state["migration_qualification"],
                    "live_migration": state["live_migration"],
                    "installed_readback": state["installed_readback"],
                    "credential_disposition": "PRESERVED_UNCHANGED",
                    "service_disposition": "NOT_STARTED",
                    "mission_disposition": "NOT_STARTED_OR_RESUMED",
                    "reset_disposition": "NOT_EXECUTED",
                    "completed_at": _now(),
                }
                _atomic_json(self.receipt_path, receipt)
                self._advance(state, "COMPLETE", receipt_sha256=file_digest(self.receipt_path),
                              safety_disposition="CANDIDATE_ACTIVE")
                return receipt
            except Exception as error:
                try:
                    self._secure_failure(state, error)
                except Exception:
                    pass
                raise


def _request_from_args(args: argparse.Namespace) -> UpdateRequest:
    return UpdateRequest(
        operation_id=args.operation_id, version=args.version, product_source=args.product_source,
        wheel=str(args.wheel), wheel_sha256=args.wheel_sha256,
        qualification_receipt=str(args.qualification_receipt),
        qualification_receipt_sha256=args.qualification_receipt_sha256,
        controller_source=args.controller_source, controller_sha256=args.controller_sha256,
        data_root=str(args.data_root), runtime_root=str(args.runtime_root),
        runtime_id=args.runtime_id, installation_id=args.installation_id,
        peer_configuration_digest=args.peer_configuration_digest,
        resolver=str(args.resolver), resolver_sha256=args.resolver_sha256,
        existing_interpreter=str(args.existing_interpreter), existing_version=args.existing_version,
        base_python=str(args.base_python),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely update one exact installed Forge runtime")
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--product-source", required=True)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--wheel-sha256", required=True)
    parser.add_argument("--qualification-receipt", required=True, type=Path)
    parser.add_argument("--qualification-receipt-sha256", required=True)
    parser.add_argument("--controller-source", required=True)
    parser.add_argument("--controller-sha256", required=True)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--installation-id", required=True)
    parser.add_argument("--peer-configuration-digest", required=True)
    parser.add_argument("--resolver", required=True, type=Path)
    parser.add_argument("--resolver-sha256", required=True)
    parser.add_argument("--existing-interpreter", required=True, type=Path)
    parser.add_argument("--existing-version", required=True)
    parser.add_argument("--base-python", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = InstalledForgeUpdateController(_request_from_args(args)).run()
    except (InstalledForgeUpdateError, OSError, sqlite3.Error, ValueError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
