"""Canonical SQLite storage for Forge runtime state.

This boundary owns Forge planning, mission, review, recommendation and decision
state.  It stores only references to Execution Host artefacts; it never copies
Execution Evidence, reports, telemetry, or host runtime state.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping
import uuid

from .bootstrap import (RUNTIME_INITIALIZATION_VERSION, RuntimeIdentity, RuntimeResolver,
                        canonical_repository_root, repository_identity, repository_uuid)


RUNTIME_SCHEMA_VERSION = 13
_REQUIRED_METADATA = frozenset((
    "schema_version", "migration_version", "forge_version", "created_at",
    "last_migration", "integrity_status",
    "runtime_id", "repository_identity", "repository_root", "database_version",
    "database_location", "last_access_at", "status", "instance_version", "initialization_version",
))
_TABLES = frozenset((
    "mission_state", "mission_runtime_projections", "architecture_reviews", "mission_recommendations",
    "decision_evidence", "execution_receipts", "planning_state", "bootstrap_portfolio_state", "mission_lifecycle_events",
    "dispatcher_state", "runtime_metadata",
    "delegation_requests", "integration_evidence", "mission_id_allocations", "mission_intake_evidence",
))


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RuntimeDatabaseError(RuntimeError):
    """A runtime database operation could not preserve Forge's contract."""


class RuntimeIntegrityError(RuntimeDatabaseError):
    """The runtime database is inconsistent and must not be used."""


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise RuntimeDatabaseError(f"runtime database cannot serialize {type(value).__name__}")


def _document(value: Any, label: str) -> dict[str, Any]:
    result = _json_value(value)
    if not isinstance(result, dict):
        raise RuntimeDatabaseError(f"{label} must be a mapping or Forge value object")
    return result


class RuntimeDatabase:
    """The sole Forge runtime database owner.

    ``path`` is injectable for tests, but production defaults to
    ``.forge/runtime.db`` beneath the supplied workspace root (or current
    directory).  Opening is fail-closed: migrations and integrity validation
    complete before callers receive the database.
    """

    def __init__(self, workspace_root: Path | str = ".", *, path: Path | str | None = None,
                 forge_version: str = "0.0") -> None:
        if path is None:
            # Canonical creation and registration are a single inter-process
            # transaction owned by RuntimeBootstrap.  Keep this compatibility
            # entry point without permitting a second unclaimed create path.
            from .bootstrap import RuntimeBootstrap
            opened = RuntimeBootstrap(workspace_root, forge_version=forge_version).open()
            self.__dict__.update(opened.__dict__)
            return
        self.repository_root = canonical_repository_root(workspace_root)
        # Explicit paths are reserved for bootstrap and relocation after their
        # resolver/claim step.
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        try:
            self._configure()
            self._migrate(forge_version)
            self._initialize_runtime_identity()
            self.validate_integrity()
        except Exception:
            self._connection.close()
            raise

    def _configure(self) -> None:
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")

    def _migrate(self, forge_version: str) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if version > RUNTIME_SCHEMA_VERSION:
            raise RuntimeIntegrityError("runtime database schema is newer than this Forge version")
        if version == 0:
            with self._connection:
                self._connection.executescript("""
                    CREATE TABLE runtime_metadata (
                        key TEXT PRIMARY KEY, value TEXT NOT NULL
                    );
                    CREATE TRIGGER runtime_identity_immutable BEFORE UPDATE ON runtime_metadata
                    WHEN OLD.key IN ('runtime_id', 'repository_identity', 'repository_root', 'repository_uuid', 'created_at', 'initialization_version')
                         AND NEW.value <> OLD.value
                    BEGIN SELECT RAISE(ABORT, 'runtime identity is immutable'); END;
                    CREATE TABLE mission_state (
                        mission_id TEXT PRIMARY KEY, lifecycle TEXT NOT NULL,
                        status TEXT NOT NULL, current_intent TEXT, current_action TEXT,
                        progress TEXT NOT NULL, resume_point TEXT NOT NULL,
                        execution_policy TEXT, document TEXT NOT NULL
                    );
                    CREATE TABLE mission_runtime_projections (
                        mission_id TEXT PRIMARY KEY, source_digest TEXT NOT NULL,
                        document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                    CREATE TABLE architecture_reviews (
                        review_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        repository_reference TEXT NOT NULL, repository_maturity TEXT NOT NULL,
                        architecture_pressure TEXT NOT NULL, implementation_pressure TEXT NOT NULL,
                        confidence TEXT NOT NULL, reviewed_at TEXT NOT NULL, document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                    CREATE TABLE mission_recommendations (
                        recommendation_id TEXT PRIMARY KEY, mission_id TEXT,
                        review_id TEXT NOT NULL, confidence TEXT NOT NULL, priority TEXT NOT NULL,
                        dependencies TEXT NOT NULL, required_disciplines TEXT NOT NULL,
                        approval_state TEXT NOT NULL, recommended_at TEXT NOT NULL, document TEXT NOT NULL,
                        origin TEXT NOT NULL, recommendation_source TEXT NOT NULL,
                        repository_evidence TEXT NOT NULL, decision_evidence_references TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id),
                        FOREIGN KEY (review_id) REFERENCES architecture_reviews(review_id)
                    );
                    CREATE TABLE execution_receipts (
                        receipt_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        execution_host TEXT NOT NULL, execution_run_id TEXT NOT NULL,
                        engineering_report_id TEXT NOT NULL, correlation_identity TEXT NOT NULL,
                        executed_at TEXT NOT NULL, outcome TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id),
                        UNIQUE (execution_host, execution_run_id, correlation_identity)
                    );
                    CREATE TABLE decision_evidence (
                        decision_id TEXT PRIMARY KEY, decision_type TEXT NOT NULL,
                        mission_id TEXT NOT NULL, review_id TEXT, reasoning_summary TEXT NOT NULL,
                        evidence_references TEXT NOT NULL, alternatives TEXT NOT NULL,
                        confidence TEXT NOT NULL, execution_receipts TEXT NOT NULL,
                        decided_at TEXT NOT NULL, document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id),
                        FOREIGN KEY (review_id) REFERENCES architecture_reviews(review_id)
                    );
                    CREATE TABLE mission_lifecycle_events (
                        mission_id TEXT NOT NULL, sequence INTEGER NOT NULL, transition_sequence INTEGER NOT NULL UNIQUE,
                        lifecycle TEXT NOT NULL, occurred_at TEXT NOT NULL,
                        PRIMARY KEY (mission_id, sequence),
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                    CREATE TRIGGER mission_lifecycle_events_immutable_update BEFORE UPDATE ON mission_lifecycle_events
                    BEGIN SELECT RAISE(ABORT, 'mission lifecycle events are immutable'); END;
                    CREATE TRIGGER mission_lifecycle_events_immutable_delete BEFORE DELETE ON mission_lifecycle_events
                    BEGIN SELECT RAISE(ABORT, 'mission lifecycle events are immutable'); END;
                    CREATE TABLE dispatcher_state (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        status TEXT NOT NULL, active_mission_id TEXT,
                        mission_sequence TEXT NOT NULL, document TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS planning_state (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        planner_version TEXT NOT NULL, current_queue TEXT NOT NULL,
                        pending_engineering_actions TEXT NOT NULL, blocked_engineering_actions TEXT NOT NULL,
                        execution_policy TEXT NOT NULL, planner_runtime_metadata TEXT NOT NULL,
                        document TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS bootstrap_portfolio_state (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        document TEXT NOT NULL
                    );
                    CREATE TABLE delegation_requests (
                        delegation_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        action_id TEXT NOT NULL, capability_id TEXT NOT NULL,
                        provider TEXT NOT NULL, approval_state TEXT NOT NULL,
                        result_state TEXT NOT NULL, requested_at TEXT NOT NULL,
                        document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                    CREATE TABLE integration_evidence (
                        integration_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        outcome TEXT NOT NULL, merge_result TEXT NOT NULL,
                        integrated_at TEXT NOT NULL, content_digest TEXT NOT NULL UNIQUE,
                        document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                    CREATE TABLE mission_id_allocations (
                        mission_id TEXT PRIMARY KEY,
                        allocated_at TEXT NOT NULL,
                        source TEXT NOT NULL UNIQUE
                    );
                    CREATE TABLE mission_intake_evidence (
                        evidence_id TEXT PRIMARY KEY,
                        mission_id TEXT NOT NULL,
                        decided_at TEXT NOT NULL,
                        document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                    CREATE TRIGGER architecture_reviews_immutable_update BEFORE UPDATE ON architecture_reviews
                    BEGIN SELECT RAISE(ABORT, 'architecture reviews are immutable'); END;
                    CREATE TRIGGER architecture_reviews_immutable_delete BEFORE DELETE ON architecture_reviews
                    BEGIN SELECT RAISE(ABORT, 'architecture reviews are immutable'); END;
                    CREATE TRIGGER mission_recommendations_immutable_update BEFORE UPDATE ON mission_recommendations
                    BEGIN SELECT RAISE(ABORT, 'mission recommendations are immutable'); END;
                    CREATE TRIGGER mission_recommendations_immutable_delete BEFORE DELETE ON mission_recommendations
                    BEGIN SELECT RAISE(ABORT, 'mission recommendations are immutable'); END;
                    CREATE TRIGGER decision_evidence_immutable_update BEFORE UPDATE ON decision_evidence
                    BEGIN SELECT RAISE(ABORT, 'decision evidence is immutable'); END;
                    CREATE TRIGGER decision_evidence_immutable_delete BEFORE DELETE ON decision_evidence
                    BEGIN SELECT RAISE(ABORT, 'decision evidence is immutable'); END;
                    CREATE TRIGGER execution_receipts_immutable_update BEFORE UPDATE ON execution_receipts
                    BEGIN SELECT RAISE(ABORT, 'execution receipts are immutable'); END;
                    CREATE TRIGGER execution_receipts_immutable_delete BEFORE DELETE ON execution_receipts
                    BEGIN SELECT RAISE(ABORT, 'execution receipts are immutable'); END;
                    CREATE TRIGGER integration_evidence_immutable_update BEFORE UPDATE ON integration_evidence
                    BEGIN SELECT RAISE(ABORT, 'integration evidence is immutable'); END;
                    CREATE TRIGGER integration_evidence_immutable_delete BEFORE DELETE ON integration_evidence
                    BEGIN SELECT RAISE(ABORT, 'integration evidence is immutable'); END;
                    CREATE TRIGGER mission_intake_evidence_immutable_update BEFORE UPDATE ON mission_intake_evidence
                    BEGIN SELECT RAISE(ABORT, 'mission intake evidence is immutable'); END;
                    CREATE TRIGGER mission_intake_evidence_immutable_delete BEFORE DELETE ON mission_intake_evidence
                    BEGIN SELECT RAISE(ABORT, 'mission intake evidence is immutable'); END;
                """)
                self._set_metadata({
                    "schema_version": str(RUNTIME_SCHEMA_VERSION),
                    "migration_version": str(RUNTIME_SCHEMA_VERSION),
                    "forge_version": forge_version,
                    "created_at": _timestamp(),
                    "last_migration": str(RUNTIME_SCHEMA_VERSION),
                    "integrity_status": "valid",
                })
                self._connection.execute(f"PRAGMA user_version={RUNTIME_SCHEMA_VERSION}")
        elif version == 1:
            with self._connection:
                self._connection.executescript("""
                    CREATE TABLE mission_lifecycle_events (
                        mission_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                        lifecycle TEXT NOT NULL, occurred_at TEXT NOT NULL,
                        PRIMARY KEY (mission_id, sequence),
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                    CREATE TRIGGER mission_lifecycle_events_immutable_update BEFORE UPDATE ON mission_lifecycle_events
                    BEGIN SELECT RAISE(ABORT, 'mission lifecycle events are immutable'); END;
                    CREATE TRIGGER mission_lifecycle_events_immutable_delete BEFORE DELETE ON mission_lifecycle_events
                    BEGIN SELECT RAISE(ABORT, 'mission lifecycle events are immutable'); END;
                    CREATE TABLE dispatcher_state (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        status TEXT NOT NULL, active_mission_id TEXT,
                        mission_sequence TEXT NOT NULL, document TEXT NOT NULL
                    );
                    CREATE TABLE delegation_requests (
                        delegation_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        action_id TEXT NOT NULL, capability_id TEXT NOT NULL,
                        provider TEXT NOT NULL, approval_state TEXT NOT NULL,
                        result_state TEXT NOT NULL, requested_at TEXT NOT NULL,
                        document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                """)
                self._set_metadata({"schema_version": "3", "migration_version": "3", "last_migration": "3"})
                self._connection.execute("PRAGMA user_version=3")
            self._migrate(forge_version)
        elif version == 2:
            with self._connection:
                self._connection.executescript("""
                    CREATE TABLE delegation_requests (
                        delegation_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        action_id TEXT NOT NULL, capability_id TEXT NOT NULL,
                        provider TEXT NOT NULL, approval_state TEXT NOT NULL,
                        result_state TEXT NOT NULL, requested_at TEXT NOT NULL,
                        document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                """)
                self._set_metadata({"schema_version": "3", "migration_version": "3", "last_migration": "3"})
                self._connection.execute("PRAGMA user_version=3")
            self._migrate(forge_version)
        elif version == 3:
            with self._connection:
                self._connection.executescript("""
                    CREATE TABLE execution_receipts (
                        receipt_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        execution_host TEXT NOT NULL, execution_run_id TEXT NOT NULL,
                        engineering_report_id TEXT NOT NULL, correlation_identity TEXT NOT NULL,
                        executed_at TEXT NOT NULL, outcome TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id),
                        UNIQUE (execution_host, execution_run_id, correlation_identity)
                    );
                    INSERT INTO execution_receipts
                      SELECT reference_id, mission_id, execution_host, execution_run_id, reference_id, correlation, executed_at, outcome
                      FROM execution_references;
                    CREATE TABLE decision_evidence_v4 (
                        decision_id TEXT PRIMARY KEY, decision_type TEXT NOT NULL,
                        mission_id TEXT NOT NULL, review_id TEXT, reasoning_summary TEXT NOT NULL,
                        evidence_references TEXT NOT NULL, alternatives TEXT NOT NULL,
                        confidence TEXT NOT NULL, execution_receipts TEXT NOT NULL,
                        decided_at TEXT NOT NULL, document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id),
                        FOREIGN KEY (review_id) REFERENCES architecture_reviews(review_id)
                    );
                    INSERT INTO decision_evidence_v4
                      SELECT decision_id, decision_type, mission_id, review_id, reasoning_summary,
                             evidence_references, alternatives, confidence, execution_references, decided_at, document
                      FROM decision_evidence;
                    DROP TRIGGER decision_evidence_immutable_update;
                    DROP TRIGGER decision_evidence_immutable_delete;
                    DROP TABLE decision_evidence;
                    ALTER TABLE decision_evidence_v4 RENAME TO decision_evidence;
                    DROP TABLE execution_references;
                    CREATE TABLE IF NOT EXISTS planning_state (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        planner_version TEXT NOT NULL, current_queue TEXT NOT NULL,
                        pending_engineering_actions TEXT NOT NULL, blocked_engineering_actions TEXT NOT NULL,
                        execution_policy TEXT NOT NULL, planner_runtime_metadata TEXT NOT NULL,
                        document TEXT NOT NULL
                    );
                    CREATE TRIGGER decision_evidence_immutable_update BEFORE UPDATE ON decision_evidence
                    BEGIN SELECT RAISE(ABORT, 'decision evidence is immutable'); END;
                    CREATE TRIGGER decision_evidence_immutable_delete BEFORE DELETE ON decision_evidence
                    BEGIN SELECT RAISE(ABORT, 'decision evidence is immutable'); END;
                    CREATE TRIGGER execution_receipts_immutable_update BEFORE UPDATE ON execution_receipts
                    BEGIN SELECT RAISE(ABORT, 'execution receipts are immutable'); END;
                    CREATE TRIGGER execution_receipts_immutable_delete BEFORE DELETE ON execution_receipts
                    BEGIN SELECT RAISE(ABORT, 'execution receipts are immutable'); END;
                """)
                self._set_metadata({"schema_version": "7", "migration_version": "7", "last_migration": "7", "instance_version": "1"})
                self._connection.execute("PRAGMA user_version=7")
            self._migrate(forge_version)
        elif version == 4:
            with self._connection:
                self._connection.executescript("""
                    CREATE TRIGGER runtime_identity_immutable BEFORE UPDATE ON runtime_metadata
                    WHEN OLD.key IN ('runtime_id', 'repository_identity', 'repository_root', 'created_at')
                         AND NEW.value <> OLD.value
                    BEGIN SELECT RAISE(ABORT, 'runtime identity is immutable'); END;
                """)
                self._set_metadata({"schema_version": "7", "migration_version": "7", "last_migration": "7", "instance_version": "1"})
                self._connection.execute("PRAGMA user_version=7")
            self._migrate(forge_version)
        elif version == 5:
            with self._connection:
                self._connection.executescript("""
                    CREATE TABLE integration_evidence (
                        integration_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        outcome TEXT NOT NULL, merge_result TEXT NOT NULL,
                        integrated_at TEXT NOT NULL, content_digest TEXT NOT NULL UNIQUE,
                        document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                    CREATE TRIGGER integration_evidence_immutable_update BEFORE UPDATE ON integration_evidence
                    BEGIN SELECT RAISE(ABORT, 'integration evidence is immutable'); END;
                    CREATE TRIGGER integration_evidence_immutable_delete BEFORE DELETE ON integration_evidence
                    BEGIN SELECT RAISE(ABORT, 'integration evidence is immutable'); END;
                """)
                self._set_metadata({"schema_version": "7", "migration_version": "7", "last_migration": "7", "instance_version": "1"})
                self._connection.execute("PRAGMA user_version=7")
            self._migrate(forge_version)
        elif version == 6:
            with self._connection:
                self._set_metadata({"schema_version": "7",
                                    "migration_version": "7",
                                    "last_migration": "7",
                                    "instance_version": "1"})
                self._connection.execute("PRAGMA user_version=7")
            self._migrate(forge_version)
        elif version == 7:
            with self._connection:
                columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(mission_lifecycle_events)")}
                if "transition_sequence" not in columns:
                    self._connection.execute("ALTER TABLE mission_lifecycle_events ADD COLUMN transition_sequence INTEGER")
                self._connection.execute("UPDATE mission_lifecycle_events SET transition_sequence = rowid WHERE transition_sequence IS NULL")
                self._connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS mission_lifecycle_events_transition_sequence ON mission_lifecycle_events(transition_sequence)")
                self._set_metadata({"schema_version": "8", "migration_version": "8", "last_migration": "8", "instance_version": "1"})
                self._connection.execute("PRAGMA user_version=8")
            self._migrate(forge_version)
        elif version == 8:
            with self._connection:
                self._connection.executescript("""
                    DROP TRIGGER runtime_identity_immutable;
                    CREATE TRIGGER runtime_identity_immutable BEFORE UPDATE ON runtime_metadata
                    WHEN OLD.key IN ('runtime_id', 'repository_identity', 'repository_root', 'repository_uuid', 'created_at', 'initialization_version')
                         AND NEW.value <> OLD.value
                    BEGIN SELECT RAISE(ABORT, 'runtime identity is immutable'); END;
                """)
                self._set_metadata({"schema_version": "9",
                                    "migration_version": "9",
                                    "last_migration": "9",
                                    "initialization_version": RUNTIME_INITIALIZATION_VERSION})
                self._connection.execute("PRAGMA user_version=9")
            self._migrate(forge_version)
        elif version == 9:
            with self._connection:
                self._connection.execute("""
                    CREATE TABLE IF NOT EXISTS bootstrap_portfolio_state (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        document TEXT NOT NULL
                    )
                """)
                self._set_metadata({"schema_version": str(RUNTIME_SCHEMA_VERSION),
                                    "migration_version": str(RUNTIME_SCHEMA_VERSION),
                                    "last_migration": str(RUNTIME_SCHEMA_VERSION)})
                self._connection.execute(f"PRAGMA user_version={RUNTIME_SCHEMA_VERSION}")
        elif version == 10:
            with self._connection:
                self._connection.executescript("""
                    CREATE TABLE mission_id_allocations (
                        mission_id TEXT PRIMARY KEY,
                        allocated_at TEXT NOT NULL,
                        source TEXT NOT NULL UNIQUE
                    );
                    CREATE TABLE mission_intake_evidence (
                        evidence_id TEXT PRIMARY KEY,
                        mission_id TEXT NOT NULL,
                        decided_at TEXT NOT NULL,
                        document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    );
                    CREATE TRIGGER mission_intake_evidence_immutable_update BEFORE UPDATE ON mission_intake_evidence
                    BEGIN SELECT RAISE(ABORT, 'mission intake evidence is immutable'); END;
                    CREATE TRIGGER mission_intake_evidence_immutable_delete BEFORE DELETE ON mission_intake_evidence
                    BEGIN SELECT RAISE(ABORT, 'mission intake evidence is immutable'); END;
                """)
                self._set_metadata({"schema_version": "11", "migration_version": "11", "last_migration": "11"})
                self._connection.execute("PRAGMA user_version=11")
        elif version == 11:
            with self._connection:
                self._connection.executescript("""
                    ALTER TABLE mission_recommendations ADD COLUMN origin TEXT NOT NULL DEFAULT 'business';
                    ALTER TABLE mission_recommendations ADD COLUMN recommendation_source TEXT NOT NULL DEFAULT 'legacy';
                    ALTER TABLE mission_recommendations ADD COLUMN repository_evidence TEXT NOT NULL DEFAULT '[]';
                    ALTER TABLE mission_recommendations ADD COLUMN decision_evidence_references TEXT NOT NULL DEFAULT '[]';
                """)
                self._set_metadata({"schema_version": "12", "migration_version": "12", "last_migration": "12"})
                self._connection.execute("PRAGMA user_version=12")
        elif version == 12:
            with self._connection:
                self._connection.execute("""
                    CREATE TABLE mission_runtime_projections (
                        mission_id TEXT PRIMARY KEY, source_digest TEXT NOT NULL,
                        document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
                    )
                """)
                self._set_metadata({"schema_version": "13", "migration_version": "13", "last_migration": "13"})
                self._connection.execute("PRAGMA user_version=13")
        elif version != RUNTIME_SCHEMA_VERSION:
            raise RuntimeIntegrityError("runtime database migration path is unavailable")

    def _initialize_runtime_identity(self) -> None:
        metadata = self.metadata
        now = _timestamp()
        created_at = metadata.get("created_at")
        if not created_at or created_at == "created_by_runtime_database":
            created_at = now
        values = {
            "runtime_id": metadata.get("runtime_id") or f"forge-runtime-{uuid.uuid4()}",
            "repository_identity": metadata.get("repository_identity") or repository_identity(self.repository_root),
            "repository_root": metadata.get("repository_root") or str(self.repository_root),
            "database_version": str(RUNTIME_SCHEMA_VERSION), "instance_version": "1",
            "initialization_version": metadata.get("initialization_version") or RUNTIME_INITIALIZATION_VERSION,
            "database_location": str(self.path.resolve()),
            "created_at": created_at, "last_access_at": now, "status": "active",
        }
        if values["repository_identity"] != repository_identity(self.repository_root):
            raise RuntimeIntegrityError("runtime database belongs to a different repository")
        current_repository_uuid = repository_uuid(self.repository_root)
        stored_repository_uuid = metadata.get("repository_uuid")
        if stored_repository_uuid and current_repository_uuid and stored_repository_uuid != current_repository_uuid:
            raise RuntimeIntegrityError("runtime database repository UUID is inconsistent")
        if stored_repository_uuid:
            values["repository_uuid"] = stored_repository_uuid
        elif current_repository_uuid:
            values["repository_uuid"] = current_repository_uuid
        with self._connection:
            self._set_metadata(values)

    def _set_metadata(self, values: Mapping[str, str]) -> None:
        self._connection.executemany(
            "INSERT INTO runtime_metadata(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            tuple(values.items()),
        )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "RuntimeDatabase":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def metadata(self) -> dict[str, str]:
        return {row["key"]: row["value"] for row in self._connection.execute("SELECT key, value FROM runtime_metadata")}

    @property
    def runtime_identity(self) -> RuntimeIdentity:
        return RuntimeIdentity.from_metadata(self.metadata)

    @property
    def runtime_instance(self):
        """Return the Runtime Instance represented by this validated storage."""
        from .bootstrap import RuntimeInstance
        identity = self.runtime_identity
        return RuntimeInstance(identity, self.path.resolve(), identity.last_access_at, identity.status)

    def validate_integrity(self, *, record_status: bool = True) -> None:
        check = self._connection.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise RuntimeIntegrityError("SQLite integrity check failed")
        tables = {row["name"] for row in self._connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not _TABLES <= tables:
            raise RuntimeIntegrityError("runtime database schema is incomplete")
        metadata = self.metadata
        if not _REQUIRED_METADATA <= metadata.keys():
            raise RuntimeIntegrityError("runtime database metadata is incomplete")
        if metadata["schema_version"] != str(RUNTIME_SCHEMA_VERSION) or metadata["migration_version"] != str(RUNTIME_SCHEMA_VERSION):
            raise RuntimeIntegrityError("runtime database metadata version is inconsistent")
        if self._connection.execute("PRAGMA user_version").fetchone()[0] != RUNTIME_SCHEMA_VERSION:
            raise RuntimeIntegrityError("runtime database schema version is inconsistent")
        identity = self.runtime_identity
        if identity.repository_identity != repository_identity(self.repository_root) or not identity.runtime_id or identity.status != "active":
            raise RuntimeIntegrityError("runtime identity is inconsistent")
        current_repository_uuid = repository_uuid(self.repository_root)
        if identity.repository_uuid and current_repository_uuid and identity.repository_uuid != current_repository_uuid:
            raise RuntimeIntegrityError("runtime identity repository UUID is inconsistent")
        if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeIntegrityError("runtime database foreign references are invalid")
        transitions = tuple(row[0] for row in self._connection.execute(
            "SELECT transition_sequence FROM mission_lifecycle_events ORDER BY transition_sequence"
        ))
        if transitions != tuple(range(1, len(transitions) + 1)):
            raise RuntimeIntegrityError("mission lifecycle transition order is inconsistent")
        for row in self._connection.execute("SELECT decision_id, execution_receipts FROM decision_evidence"):
            try:
                references = json.loads(row["execution_receipts"])
            except (TypeError, json.JSONDecodeError) as error:
                raise RuntimeIntegrityError("decision execution receipts are malformed") from error
            for reference in references:
                identifier = reference.get("artifact_id") if isinstance(reference, dict) else None
                if not isinstance(identifier, str) or not self._connection.execute(
                    "SELECT 1 FROM execution_receipts WHERE receipt_id = ?", (identifier,)
                ).fetchone():
                    raise RuntimeIntegrityError("decision references an unknown Forge execution receipt")
        if record_status:
            self._connection.execute("UPDATE runtime_metadata SET value = 'valid' WHERE key = 'integrity_status'")
            self._connection.commit()

    def save_mission_state(self, state: Any) -> dict[str, Any]:
        document = _document(state, "mission state")
        mission_id = document.get("mission_id") or document.get("id")
        lifecycle = document.get("lifecycle") or document.get("status")
        required = (mission_id, lifecycle, document.get("status"), document.get("progress"), document.get("resume", document.get("resume_point")), document.get("execution_policy"))
        if not isinstance(mission_id, str) or not mission_id or not isinstance(lifecycle, str) or not lifecycle or any(value is None for value in required[2:]):
            raise RuntimeDatabaseError("mission state requires identity, lifecycle, status, progress, resume point, and execution policy")
        with self._connection:
            self._connection.execute("""INSERT INTO mission_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mission_id) DO UPDATE SET lifecycle=excluded.lifecycle, status=excluded.status,
                current_intent=excluded.current_intent, current_action=excluded.current_action, progress=excluded.progress,
                resume_point=excluded.resume_point, execution_policy=excluded.execution_policy, document=excluded.document""", (
                mission_id, lifecycle, str(document.get("status", lifecycle)), self._dump(document.get("current_engineering_intent")),
                self._dump(document.get("current_engineering_action")), self._dump(document.get("progress", {})),
                self._dump(document.get("resume", document.get("resume_point", {}))), self._dump(document.get("execution_policy")), self._dump(document),
            ))
        return document

    def save_mission_runtime_projection(self, projection: Any) -> dict[str, Any]:
        """Persist the canonical, mutable operational view of one Mission."""
        document = _document(projection, "mission runtime projection")
        mission_id, source_digest = document.get("mission_id"), document.get("source_digest")
        if not all(isinstance(value, str) and value for value in (mission_id, source_digest)):
            raise RuntimeDatabaseError("mission runtime projection requires mission identity and source digest")
        if not source_digest.startswith("sha256:") or len(source_digest) != 71:
            raise RuntimeDatabaseError("mission runtime projection requires a sha256 source digest")
        with self._connection:
            self._connection.execute(
                "INSERT INTO mission_runtime_projections VALUES (?, ?, ?) "
                "ON CONFLICT(mission_id) DO UPDATE SET source_digest=excluded.source_digest, document=excluded.document",
                (mission_id, source_digest, self._dump(document)),
            )
        return document

    def allocate_next_mission_id(self, *, source: str, allocated_at: str) -> str:
        """Atomically allocate the next Mission identifier from Repository Truth."""
        if not source or not allocated_at:
            raise RuntimeDatabaseError("mission allocation requires source and timestamp")
        existing = self._connection.execute(
            "SELECT mission_id FROM mission_id_allocations WHERE source = ?", (source,)
        ).fetchone()
        if existing is not None:
            return str(existing["mission_id"])
        identifiers: set[str] = set()
        pattern = re.compile(r"MISSION-(\d{4,})")
        # Active Mission documents are written only after an allocation has
        # committed. They are deliberately excluded here so a staged document
        # cannot reserve a number outside this atomic Runtime boundary.
        missions_root = self.repository_root / "missions"
        if missions_root.exists():
            for path in missions_root.glob("MISSION-*.md"):
                if path.is_file():
                    identifiers.update(match.group(1) for match in pattern.finditer(path.name))
        with self._connection:
            rows = self._connection.execute("SELECT mission_id FROM mission_id_allocations").fetchall()
            identifiers.update(match.group(1) for row in rows for match in pattern.finditer(str(row["mission_id"])))
            mission_id = f"MISSION-{max((int(value) for value in identifiers), default=0) + 1:04d}"
            self._connection.execute("INSERT INTO mission_id_allocations VALUES (?, ?, ?)", (mission_id, allocated_at, source))
        return mission_id

    def record_mission_intake_evidence(self, evidence: Any) -> dict[str, Any]:
        """Persist pre-approval evidence without fabricating execution provenance."""
        document = _document(evidence, "mission intake evidence")
        required = ("id", "mission_id", "timestamp", "recommendation", "business_value",
                    "architectural_value", "expected_repository_impact", "confidence", "alternatives_considered")
        if any(not document.get(name) for name in required):
            raise RuntimeDatabaseError("mission intake evidence requires complete pre-approval rationale")
        if not isinstance(document["alternatives_considered"], list):
            raise RuntimeDatabaseError("mission intake evidence alternatives must be a list")
        with self._connection:
            self._connection.execute(
                "INSERT INTO mission_intake_evidence VALUES (?, ?, ?, ?)",
                (document["id"], document["mission_id"], document["timestamp"], self._dump(document)),
            )
        return document

    def record_mission_lifecycle(self, mission_id: str, lifecycle: str, occurred_at: str) -> None:
        """Append the operational lifecycle used by qualification; it cannot be rewritten."""
        if not all(isinstance(value, str) and value for value in (mission_id, lifecycle, occurred_at)):
            raise RuntimeDatabaseError("mission lifecycle requires identity, state, and timestamp")
        with self._connection:
            sequence = self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM mission_lifecycle_events WHERE mission_id = ?", (mission_id,)
            ).fetchone()[0]
            transition_sequence = self._connection.execute(
                "SELECT COALESCE(MAX(transition_sequence), 0) + 1 FROM mission_lifecycle_events"
            ).fetchone()[0]
            self._connection.execute(
                "INSERT INTO mission_lifecycle_events (mission_id, sequence, transition_sequence, lifecycle, occurred_at) VALUES (?, ?, ?, ?, ?)",
                (mission_id, sequence, transition_sequence, lifecycle, occurred_at),
            )

    def has_mission_lifecycle(self, mission_id: str, lifecycle: str) -> bool:
        """Return whether an immutable lifecycle event was already recorded."""
        return self._connection.execute(
            "SELECT 1 FROM mission_lifecycle_events WHERE mission_id = ? AND lifecycle = ?",
            (mission_id, lifecycle),
        ).fetchone() is not None

    def has_document(self, table: str, identifier: str) -> bool:
        """Check an owned document without exposing host evidence."""
        lookup = {
            "mission_runtime_projections": "mission_id", "mission_intake_evidence": "evidence_id", "architecture_reviews": "review_id", "mission_recommendations": "recommendation_id",
            "decision_evidence": "decision_id", "integration_evidence": "integration_id",
        }
        if table not in lookup:
            raise RuntimeDatabaseError("table is not a Forge document store")
        return self._connection.execute(
            f"SELECT 1 FROM {table} WHERE {lookup[table]} = ?", (identifier,)
        ).fetchone() is not None

    def has_execution_receipt(self, receipt_id: str) -> bool:
        """Check an immutable Forge receipt reference by host-issued identity."""
        return self._connection.execute(
            "SELECT 1 FROM execution_receipts WHERE receipt_id = ?", (receipt_id,)
        ).fetchone() is not None

    def save_dispatcher_state(self, *, status: str, mission_sequence: tuple[str, ...],
                              active_mission_id: str | None = None) -> None:
        """Persist dispatcher terminal/sequencing authority in the Runtime Database."""
        if status not in {"ACTIVE", "IDLE"} or not mission_sequence:
            raise RuntimeDatabaseError("dispatcher state requires a status and mission sequence")
        if status == "IDLE" and active_mission_id is not None:
            raise RuntimeDatabaseError("idle dispatcher cannot retain an active Mission")
        document = {"status": status, "active_mission_id": active_mission_id, "mission_sequence": list(mission_sequence)}
        with self._connection:
            self._connection.execute(
                "INSERT INTO dispatcher_state VALUES (1, ?, ?, ?, ?) ON CONFLICT(singleton) DO UPDATE SET status=excluded.status, active_mission_id=excluded.active_mission_id, mission_sequence=excluded.mission_sequence, document=excluded.document",
                (status, active_mission_id, self._dump(mission_sequence), self._dump(document)),
            )

    def record_architecture_review(self, review: Any, *, timestamp: str | None = None) -> dict[str, Any]:
        document = _document(review, "architecture review")
        review_id, mission_id = document.get("id"), document.get("mission_id")
        if not all(isinstance(value, str) and value for value in (review_id, mission_id, document.get("input_digest"), document.get("confidence"), timestamp or document.get("timestamp", document.get("reviewed_at")))):
            raise RuntimeDatabaseError("architecture review requires identity, repository reference, confidence, and timestamp")
        pressure = document.get("pressure", {})
        if not isinstance(pressure, dict) or not all(isinstance(pressure.get(key), str) and pressure[key] for key in ("architecture", "implementation")) or document.get("repository_maturity") is None:
            raise RuntimeDatabaseError("architecture review requires maturity and architecture/implementation pressure")
        with self._connection:
            self._connection.execute("INSERT INTO architecture_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                review_id, mission_id, self._dump(document.get("repository_reference", document.get("input_digest", "repository_truth"))),
                self._dump(document.get("repository_maturity", [])), str(pressure.get("architecture", "unknown")),
                str(pressure.get("implementation", "unknown")), str(document.get("confidence", "unknown")),
                timestamp or str(document.get("timestamp", document.get("reviewed_at", "unknown"))), self._dump(document),
            ))
        return document

    def record_mission_recommendation(self, recommendation: Any, *, mission_id: str | None = None,
                                      approval_state: str = "advisory") -> dict[str, Any]:
        document = _document(recommendation, "mission recommendation")
        identifier, review_id = document.get("id"), document.get("architecture_review_id")
        required = (identifier, review_id, document.get("confidence"), document.get("priority", document.get("estimated_effort")), document.get("dependencies"), document.get("required_disciplines"), document.get("recommendation_timestamp"), document.get("origin"), document.get("recommendation_source"), document.get("repository_evidence"), document.get("decision_evidence_references"))
        if not all(value is not None for value in required) or not isinstance(identifier, str) or not identifier or not isinstance(review_id, str) or not review_id:
            raise RuntimeDatabaseError("mission recommendation requires identity, review, origin, source, Repository Truth and Decision Evidence references, priority, confidence, dependencies, disciplines, and timestamp")
        with self._connection:
            self._connection.execute("""INSERT INTO mission_recommendations
                (recommendation_id, mission_id, review_id, confidence, priority, dependencies, required_disciplines,
                 approval_state, recommended_at, document, origin, recommendation_source, repository_evidence,
                 decision_evidence_references) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                identifier, mission_id, review_id, self._dump(document.get("confidence", {})),
                str(document.get("priority", document.get("estimated_effort", "advisory"))), self._dump(document.get("dependencies", {})),
                self._dump(document.get("required_disciplines", [])), approval_state,
                str(document.get("recommendation_timestamp", "unknown")), self._dump(document),
                str(document["origin"]), str(document["recommendation_source"]), self._dump(document["repository_evidence"]),
                self._dump(document["decision_evidence_references"]),
            ))
        return document

    def record_execution_receipt(self, *, receipt_id: str, mission_id: str, execution_host: str,
                                 execution_run_id: str, engineering_report_id: str,
                                 correlation_identity: str, executed_at: str, outcome: str) -> None:
        if not all((receipt_id, mission_id, execution_host, execution_run_id, engineering_report_id, correlation_identity, executed_at, outcome)):
            raise RuntimeDatabaseError("execution receipt requires complete identity, report, correlation, and outcome")
        with self._connection:
            self._connection.execute("INSERT INTO execution_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                     (receipt_id, mission_id, execution_host, execution_run_id, engineering_report_id, correlation_identity, executed_at, outcome))

    def save_planning_state(self, state: Any) -> dict[str, Any]:
        """Persist the mutable, Forge-owned planner snapshot independently of dispatch."""
        document = _document(state, "planning state")
        required = ("planner_version", "current_queue", "pending_engineering_actions", "blocked_engineering_actions", "execution_policy", "planner_runtime_metadata")
        if any(item not in document or document[item] is None for item in required) or not isinstance(document["planner_version"], str) or not document["planner_version"]:
            raise RuntimeDatabaseError("planning state requires planner version, queue, pending/blocked actions, policy, and metadata")
        with self._connection:
            self._connection.execute(
                "INSERT INTO planning_state VALUES (1, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(singleton) DO UPDATE SET planner_version=excluded.planner_version, current_queue=excluded.current_queue, pending_engineering_actions=excluded.pending_engineering_actions, blocked_engineering_actions=excluded.blocked_engineering_actions, execution_policy=excluded.execution_policy, planner_runtime_metadata=excluded.planner_runtime_metadata, document=excluded.document",
                (document["planner_version"], self._dump(document["current_queue"]), self._dump(document["pending_engineering_actions"]), self._dump(document["blocked_engineering_actions"]), self._dump(document["execution_policy"]), self._dump(document["planner_runtime_metadata"]), self._dump(document)),
            )
        return document

    def record_delegation_request(self, request: Any) -> dict[str, Any]:
        """Persist the Forge-owned delegation record, never provider execution data."""
        document = _document(request, "delegation request")
        required = ("id", "mission_id", "action_id", "capability_id", "provider", "approval_state", "result_state", "requested_at")
        if any(not isinstance(document.get(item), str) or not document[item] for item in required):
            raise RuntimeDatabaseError("delegation request requires complete identity and lifecycle fields")
        with self._connection:
            self._connection.execute("INSERT INTO delegation_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                     tuple(document[item] for item in required[:8]) + (self._dump(document),))
        return document

    def record_decision_evidence(self, evidence: Any) -> dict[str, Any]:
        document = _document(evidence, "decision evidence")
        identifier = document.get("id")
        mission = document.get("mission_context", {})
        mission_id = mission.get("artifact_id") if isinstance(mission, dict) else None
        confidence = document.get("confidence", {})
        review = confidence.get("architecture_review", {}) if isinstance(confidence, dict) else {}
        review_id = review.get("artifact_id") if isinstance(review, dict) else None
        mission_state = confidence.get("mission_state", {}) if isinstance(confidence, dict) else {}
        state_id = mission_state.get("artifact_id") if isinstance(mission_state, dict) else None
        repository_truth = document.get("repository_context", {})
        repository_truth_id = repository_truth.get("artifact_id") if isinstance(repository_truth, dict) else None
        planning_types = {"mission_planning", "engineering_intent", "engineering_action_selection", "execution_policy"}
        required_references = (identifier, mission_id, state_id, repository_truth_id)
        if not all(isinstance(item, str) and item for item in required_references):
            raise RuntimeDatabaseError("decision evidence requires mission state and repository truth references")
        if review_id is not None and (not isinstance(review_id, str) or not review_id):
            raise RuntimeDatabaseError("decision evidence architecture review reference is invalid")
        if review_id is None and document.get("decision_type") not in planning_types:
            raise RuntimeDatabaseError("non-planning decision evidence requires an architecture review reference")
        if state_id != mission_id:
            raise RuntimeDatabaseError("decision evidence mission state must reference its mission")
        references = document.get("execution_receipt_references", [])
        if not all(isinstance(item, str) and item for item in (document.get("decision_type"), document.get("reasoning_summary"), document.get("timestamp"))) or not isinstance(document.get("evidence_references"), list) or not isinstance(document.get("alternatives_considered"), list):
            raise RuntimeDatabaseError("decision evidence requires type, reasoning, evidence, alternatives, and timestamp")
        for reference in references:
            reference_id = reference.get("artifact_id") if isinstance(reference, dict) else None
            if not isinstance(reference_id, str) or not self._connection.execute(
                "SELECT 1 FROM execution_receipts WHERE receipt_id = ?", (reference_id,)
            ).fetchone():
                raise RuntimeDatabaseError("decision evidence references an unknown Forge execution receipt")
        with self._connection:
            self._connection.execute("INSERT INTO decision_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                identifier, str(document.get("decision_type", "unknown")), mission_id, review_id,
                str(document["reasoning_summary"]), self._dump(document["evidence_references"]),
                self._dump(document["alternatives_considered"]), self._dump(confidence), self._dump(references),
                str(document["timestamp"]), self._dump(document),
            ))
        return document

    def record_integration_evidence(self, evidence: Any) -> dict[str, Any]:
        """Persist immutable Forge integration evidence bound to known receipts."""
        document = _document(evidence, "integration evidence")
        required = ("id", "mission_id", "outcome", "merge_result", "timestamp", "content_digest")
        if any(not isinstance(document.get(item), str) or not document[item] for item in required):
            raise RuntimeDatabaseError("integration evidence requires identity, mission, outcome, merge result, timestamp, and digest")
        if not self._connection.execute("SELECT 1 FROM mission_state WHERE mission_id = ?", (document["mission_id"],)).fetchone():
            raise RuntimeDatabaseError("integration evidence references an unknown Mission")
        receipts = document.get("execution_receipt_references", [])
        if not isinstance(receipts, list) or not receipts:
            raise RuntimeDatabaseError("integration evidence requires execution receipt references")
        for receipt_id in receipts:
            if not isinstance(receipt_id, str) or not self.has_execution_receipt(receipt_id):
                raise RuntimeDatabaseError("integration evidence references an unknown Forge execution receipt")
        with self._connection:
            self._connection.execute("INSERT INTO integration_evidence VALUES (?, ?, ?, ?, ?, ?, ?)", (
                document["id"], document["mission_id"], document["outcome"], document["merge_result"],
                document["timestamp"], document["content_digest"], self._dump(document),
            ))
        return document

    def get_document(self, table: str, identifier: str) -> dict[str, Any]:
        lookup = {"mission_state": ("mission_id", "document"), "mission_runtime_projections": ("mission_id", "document"), "mission_intake_evidence": ("evidence_id", "document"), "architecture_reviews": ("review_id", "document"),
                  "mission_recommendations": ("recommendation_id", "document"), "decision_evidence": ("decision_id", "document"), "planning_state": ("singleton", "document"),
                  "delegation_requests": ("delegation_id", "document"), "integration_evidence": ("integration_id", "document")}
        if table not in lookup:
            raise RuntimeDatabaseError("table is not a Forge document store")
        key, column = lookup[table]
        row = self._connection.execute(f"SELECT {column} FROM {table} WHERE {key} = ?", (identifier,)).fetchone()
        if row is None:
            raise RuntimeDatabaseError(f"unknown {table} record: {identifier}")
        return json.loads(row[column])

    def runtime_evidence(self) -> "RuntimeEvidence":
        """Return the canonical query layer without exposing host evidence."""
        from .evidence import RuntimeEvidence
        return RuntimeEvidence(self)

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
