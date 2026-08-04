"""Canonical SQLite storage for Forge runtime state.

This boundary owns Forge planning, mission, review, recommendation and decision
state.  It stores only references to Execution Host artefacts; it never copies
Execution Evidence, reports, telemetry, or host runtime state.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


RUNTIME_SCHEMA_VERSION = 1
_REQUIRED_METADATA = frozenset((
    "schema_version", "migration_version", "forge_version", "created_at",
    "last_migration", "integrity_status",
))
_TABLES = frozenset((
    "mission_state", "architecture_reviews", "mission_recommendations",
    "decision_evidence", "execution_references", "runtime_metadata",
))


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
        self.path = Path(path) if path is not None else Path(workspace_root) / ".forge" / "runtime.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        try:
            self._configure()
            self._migrate(forge_version)
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
                    CREATE TABLE mission_state (
                        mission_id TEXT PRIMARY KEY, lifecycle TEXT NOT NULL,
                        status TEXT NOT NULL, current_intent TEXT, current_action TEXT,
                        progress TEXT NOT NULL, resume_point TEXT NOT NULL,
                        execution_policy TEXT, document TEXT NOT NULL
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
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id),
                        FOREIGN KEY (review_id) REFERENCES architecture_reviews(review_id)
                    );
                    CREATE TABLE execution_references (
                        reference_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        execution_host TEXT NOT NULL, execution_run_id TEXT NOT NULL,
                        correlation TEXT NOT NULL, executed_at TEXT NOT NULL, outcome TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id),
                        UNIQUE (execution_host, execution_run_id, correlation)
                    );
                    CREATE TABLE decision_evidence (
                        decision_id TEXT PRIMARY KEY, decision_type TEXT NOT NULL,
                        mission_id TEXT NOT NULL, review_id TEXT, reasoning_summary TEXT NOT NULL,
                        evidence_references TEXT NOT NULL, alternatives TEXT NOT NULL,
                        confidence TEXT NOT NULL, execution_references TEXT NOT NULL,
                        decided_at TEXT NOT NULL, document TEXT NOT NULL,
                        FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id),
                        FOREIGN KEY (review_id) REFERENCES architecture_reviews(review_id)
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
                """)
                self._set_metadata({
                    "schema_version": str(RUNTIME_SCHEMA_VERSION),
                    "migration_version": str(RUNTIME_SCHEMA_VERSION),
                    "forge_version": forge_version,
                    "created_at": "created_by_runtime_database",
                    "last_migration": str(RUNTIME_SCHEMA_VERSION),
                    "integrity_status": "valid",
                })
                self._connection.execute(f"PRAGMA user_version={RUNTIME_SCHEMA_VERSION}")
        elif version != RUNTIME_SCHEMA_VERSION:
            raise RuntimeIntegrityError("runtime database migration path is unavailable")

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

    def validate_integrity(self) -> None:
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
        if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeIntegrityError("runtime database foreign references are invalid")
        for row in self._connection.execute("SELECT decision_id, execution_references FROM decision_evidence"):
            try:
                references = json.loads(row["execution_references"])
            except (TypeError, json.JSONDecodeError) as error:
                raise RuntimeIntegrityError("decision execution references are malformed") from error
            for reference in references:
                identifier = reference.get("artifact_id") if isinstance(reference, dict) else None
                if not isinstance(identifier, str) or not self._connection.execute(
                    "SELECT 1 FROM execution_references WHERE reference_id = ?", (identifier,)
                ).fetchone():
                    raise RuntimeIntegrityError("decision references an unknown Forge execution reference")
        self._connection.execute("UPDATE runtime_metadata SET value = 'valid' WHERE key = 'integrity_status'")
        self._connection.commit()

    def save_mission_state(self, state: Any) -> dict[str, Any]:
        document = _document(state, "mission state")
        mission_id = document.get("mission_id") or document.get("id")
        lifecycle = document.get("lifecycle") or document.get("status")
        if not isinstance(mission_id, str) or not mission_id or not isinstance(lifecycle, str) or not lifecycle:
            raise RuntimeDatabaseError("mission state requires mission_id and lifecycle")
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

    def record_architecture_review(self, review: Any, *, timestamp: str | None = None) -> dict[str, Any]:
        document = _document(review, "architecture review")
        review_id, mission_id = document.get("id"), document.get("mission_id")
        if not isinstance(review_id, str) or not isinstance(mission_id, str):
            raise RuntimeDatabaseError("architecture review requires id and mission_id")
        pressure = document.get("pressure", {})
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
        if not isinstance(identifier, str) or not isinstance(review_id, str):
            raise RuntimeDatabaseError("mission recommendation requires id and architecture_review_id")
        with self._connection:
            self._connection.execute("INSERT INTO mission_recommendations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                identifier, mission_id, review_id, self._dump(document.get("confidence", {})),
                str(document.get("priority", document.get("estimated_effort", "advisory"))), self._dump(document.get("dependencies", {})),
                self._dump(document.get("required_disciplines", [])), approval_state,
                str(document.get("recommendation_timestamp", "unknown")), self._dump(document),
            ))
        return document

    def record_execution_reference(self, *, reference_id: str, mission_id: str, execution_host: str,
                                   execution_run_id: str, correlation: str, executed_at: str, outcome: str) -> None:
        if not all((reference_id, mission_id, execution_host, execution_run_id, correlation, executed_at, outcome)):
            raise RuntimeDatabaseError("execution reference requires complete identity and outcome")
        with self._connection:
            self._connection.execute("INSERT INTO execution_references VALUES (?, ?, ?, ?, ?, ?, ?)",
                                     (reference_id, mission_id, execution_host, execution_run_id, correlation, executed_at, outcome))

    def record_decision_evidence(self, evidence: Any) -> dict[str, Any]:
        document = _document(evidence, "decision evidence")
        identifier = document.get("id")
        mission = document.get("mission_context", {})
        mission_id = mission.get("artifact_id") if isinstance(mission, dict) else None
        confidence = document.get("confidence", {})
        review = confidence.get("architecture_review", {}) if isinstance(confidence, dict) else {}
        review_id = review.get("artifact_id") if isinstance(review, dict) else None
        if not isinstance(identifier, str) or not isinstance(mission_id, str):
            raise RuntimeDatabaseError("decision evidence requires id and mission reference")
        references = document.get("execution_evidence_references", [])
        for reference in references:
            reference_id = reference.get("artifact_id") if isinstance(reference, dict) else None
            if not isinstance(reference_id, str) or not self._connection.execute(
                "SELECT 1 FROM execution_references WHERE reference_id = ?", (reference_id,)
            ).fetchone():
                raise RuntimeDatabaseError("decision evidence references an unknown Forge execution reference")
        with self._connection:
            self._connection.execute("INSERT INTO decision_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                identifier, str(document.get("decision_type", "unknown")), mission_id, review_id,
                str(document.get("reasoning_summary", "")), self._dump(document.get("evidence_references", [])),
                self._dump(document.get("alternatives_considered", [])), self._dump(confidence), self._dump(references),
                str(document.get("timestamp", "unknown")), self._dump(document),
            ))
        return document

    def get_document(self, table: str, identifier: str) -> dict[str, Any]:
        lookup = {"mission_state": ("mission_id", "document"), "architecture_reviews": ("review_id", "document"),
                  "mission_recommendations": ("recommendation_id", "document"), "decision_evidence": ("decision_id", "document")}
        if table not in lookup:
            raise RuntimeDatabaseError("table is not a Forge document store")
        key, column = lookup[table]
        row = self._connection.execute(f"SELECT {column} FROM {table} WHERE {key} = ?", (identifier,)).fetchone()
        if row is None:
            raise RuntimeDatabaseError(f"unknown {table} record: {identifier}")
        return json.loads(row[column])

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
