"""Versioned, transactional persistence for canonical Mission execution state.

This module deliberately stores value snapshots and evidence references rather
than host objects.  It has no dependency on a Scheduler implementation,
Execution Host implementation, Engineering Platform, network, or process
memory.  SQLite supplies atomic commits and crash-safe recovery.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


MISSION_STATE_SCHEMA_VERSION = "1.4"


class MissionExecutionStatus(str, Enum):
    """The runtime lifecycle owned by the Mission State Store.

    This is intentionally distinct from ``forge.models.mission.MissionStatus``:
    that immutable contract expresses governed Mission meaning, while this enum
    records durable operational execution state.
    """

    CREATED = "CREATED"
    APPROVED_PLANNABLE = "APPROVED_PLANNABLE"
    READY = "READY"
    ACTIVE = "ACTIVE"
    WAITING_FOR_EXECUTION = "WAITING_FOR_EXECUTION"
    WAITING_FOR_EVIDENCE = "WAITING_FOR_EVIDENCE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    WAITING_EXTERNAL_CAPABILITY = "WAITING_EXTERNAL_CAPABILITY"
    WAITING_EXTERNAL_APPROVAL = "WAITING_EXTERNAL_APPROVAL"
    WAITING_EXTERNAL_RESULT = "WAITING_EXTERNAL_RESULT"
    READY_TO_CONTINUE = "READY_TO_CONTINUE"
    WAITING_INTEGRATION = "WAITING_INTEGRATION"
    INTEGRATION_RUNNING = "INTEGRATION_RUNNING"
    INTEGRATION_BLOCKED = "INTEGRATION_BLOCKED"
    INTEGRATION_COMPLETE = "INTEGRATION_COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class MissionStateStoreError(ValueError):
    """Raised when a durable Mission state operation violates its contract."""


@dataclass(frozen=True)
class MissionStateHistoryEntry:
    """An append-only, immutable record of one persisted state transition."""

    sequence: int
    from_status: MissionExecutionStatus | None
    to_status: MissionExecutionStatus
    occurred_at: str
    reason: str


@dataclass(frozen=True)
class MissionExecutionState:
    """The complete restart-safe snapshot for one Mission execution."""

    mission_id: str
    mission: Mapping[str, Any]
    intents: tuple[Mapping[str, Any], ...]
    actions: tuple[Mapping[str, Any], ...]
    status: MissionExecutionStatus
    progress: Mapping[str, Any]
    resume: Mapping[str, Any]
    execution_correlation: Mapping[str, Any] | None
    execution_evidence: Mapping[str, Any] | None
    revision: int
    current_engineering_intent: Mapping[str, Any] | None = None
    current_engineering_action: Mapping[str, Any] | None = None
    execution_history: tuple[Mapping[str, Any], ...] = ()
    waiting_reason: str | None = None
    repository_truth: Mapping[str, Any] | None = None
    completion: Mapping[str, Any] | None = None
    execution_policy: Mapping[str, Any] | None = None
    pause_reason: Mapping[str, Any] | None = None
    approval_record: Mapping[str, Any] | None = None
    delegations: tuple[Mapping[str, Any], ...] = ()
    integration: Mapping[str, Any] | None = None
    schema_version: str = MISSION_STATE_SCHEMA_VERSION


_ALLOWED_TRANSITIONS: dict[MissionExecutionStatus, frozenset[MissionExecutionStatus]] = {
    MissionExecutionStatus.CREATED: frozenset((MissionExecutionStatus.READY, MissionExecutionStatus.ARCHIVED)),
    MissionExecutionStatus.READY: frozenset((MissionExecutionStatus.ACTIVE, MissionExecutionStatus.WAITING_EXTERNAL_CAPABILITY, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED, MissionExecutionStatus.ARCHIVED)),
    MissionExecutionStatus.ACTIVE: frozenset((MissionExecutionStatus.WAITING_FOR_EXECUTION, MissionExecutionStatus.WAITING_EXTERNAL_CAPABILITY, MissionExecutionStatus.WAITING_INTEGRATION, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.WAITING_FOR_EXECUTION: frozenset((MissionExecutionStatus.WAITING_FOR_EVIDENCE, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.WAITING_FOR_EVIDENCE: frozenset((MissionExecutionStatus.ACTIVE, MissionExecutionStatus.AWAITING_APPROVAL, MissionExecutionStatus.COMPLETED, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.AWAITING_APPROVAL: frozenset((MissionExecutionStatus.ACTIVE, MissionExecutionStatus.COMPLETED, MissionExecutionStatus.ARCHIVED)),
    MissionExecutionStatus.WAITING_EXTERNAL_CAPABILITY: frozenset((MissionExecutionStatus.WAITING_EXTERNAL_APPROVAL, MissionExecutionStatus.WAITING_EXTERNAL_RESULT, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.WAITING_EXTERNAL_APPROVAL: frozenset((MissionExecutionStatus.WAITING_EXTERNAL_RESULT, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.WAITING_EXTERNAL_RESULT: frozenset((MissionExecutionStatus.WAITING_EXTERNAL_CAPABILITY, MissionExecutionStatus.READY_TO_CONTINUE, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.READY_TO_CONTINUE: frozenset((MissionExecutionStatus.READY, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.WAITING_INTEGRATION: frozenset((MissionExecutionStatus.INTEGRATION_RUNNING, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.INTEGRATION_RUNNING: frozenset((MissionExecutionStatus.WAITING_INTEGRATION, MissionExecutionStatus.INTEGRATION_BLOCKED, MissionExecutionStatus.INTEGRATION_COMPLETE, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.INTEGRATION_BLOCKED: frozenset((MissionExecutionStatus.WAITING_INTEGRATION, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED)),
    MissionExecutionStatus.INTEGRATION_COMPLETE: frozenset((MissionExecutionStatus.COMPLETED, MissionExecutionStatus.ARCHIVED)),
    MissionExecutionStatus.BLOCKED: frozenset((MissionExecutionStatus.READY, MissionExecutionStatus.ACTIVE, MissionExecutionStatus.ARCHIVED)),
    MissionExecutionStatus.FAILED: frozenset((MissionExecutionStatus.READY, MissionExecutionStatus.ACTIVE, MissionExecutionStatus.ARCHIVED)),
    MissionExecutionStatus.COMPLETED: frozenset((MissionExecutionStatus.ARCHIVED,)),
    MissionExecutionStatus.ARCHIVED: frozenset(),
}


def _snapshot(value: Any) -> Any:
    """Convert Forge's immutable values into deterministic JSON-compatible data."""
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict"):
        return _snapshot(value.to_dict())
    if is_dataclass(value):
        return _snapshot(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _snapshot(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_snapshot(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise MissionStateStoreError(f"mission state cannot persist {type(value).__name__}")


def _document(value: Any, label: str) -> dict[str, Any]:
    snapshot = _snapshot(value)
    if not isinstance(snapshot, dict):
        raise MissionStateStoreError(f"{label} must be a mapping or Forge value object")
    return snapshot


def _documents(values: Sequence[Any], label: str) -> tuple[dict[str, Any], ...]:
    return tuple(_document(value, label) for value in values)


def _derive_progress(actions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(actions)
    complete = sum(action.get("status") == "COMPLETE" for action in actions)
    return {
        "total_actions": total,
        "completed_actions": complete,
        "remaining_action_ids": [str(action.get("id", "")) for action in actions if action.get("status") != "COMPLETE"],
        "percent_complete": 0 if not total else (complete * 100) // total,
    }


def _current_work(actions: Sequence[Mapping[str, Any]], intents: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    action = next((item for item in actions if item.get("status") in {"ACTIVE", "WAITING_FOR_RESULT", "BLOCKED", "FAILED"}), None)
    if action is None:
        return None, None
    intent = next((item for item in intents if item.get("id") == action.get("intent_id") and item.get("revision") == action.get("intent_revision")), None)
    return (None if intent is None else dict(intent), dict(action))


class MissionStateStore:
    """A local SQLite store with atomic snapshots and append-only history."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS mission_state (
                mission_id TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL,
                revision INTEGER NOT NULL,
                status TEXT NOT NULL,
                document TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mission_state_history (
                mission_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                PRIMARY KEY (mission_id, sequence),
                FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id)
            );
            CREATE TRIGGER IF NOT EXISTS mission_state_history_no_update
            BEFORE UPDATE ON mission_state_history
            BEGIN SELECT RAISE(ABORT, 'mission state history is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS mission_state_history_no_delete
            BEFORE DELETE ON mission_state_history
            BEGIN SELECT RAISE(ABORT, 'mission state history is append-only'); END;
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "MissionStateStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def create(
        self,
        mission: Any,
        intents: Sequence[Any],
        actions: Sequence[Any],
        *,
        occurred_at: str,
        resume: Mapping[str, Any] | None = None,
        execution_policy: Mapping[str, Any] | None = None,
    ) -> MissionExecutionState:
        mission_document = _document(mission, "mission")
        mission_id = mission_document.get("id")
        if not isinstance(mission_id, str) or not mission_id:
            raise MissionStateStoreError("mission snapshot requires a non-empty id")
        if not intents or not actions or not occurred_at:
            raise MissionStateStoreError("mission state requires intents, actions, and creation time")
        document = {
            "schema_version": MISSION_STATE_SCHEMA_VERSION,
            "mission_id": mission_id,
            "mission": mission_document,
            "intents": list(_documents(intents, "intent")),
            "actions": list(_documents(actions, "action")),
            "status": MissionExecutionStatus.CREATED.value,
            "progress": _derive_progress(_documents(actions, "action")),
            "resume": _document(resume or {}, "resume"),
            "execution_correlation": None,
            "execution_evidence": None,
            "current_engineering_intent": None, "current_engineering_action": None,
            "execution_history": [], "waiting_reason": None, "repository_truth": None,
            "completion": None,
            "execution_policy": None if execution_policy is None else _document(execution_policy, "execution policy"),
            "pause_reason": None, "approval_record": None,
            "delegations": [],
            "integration": None,
            "revision": 1,
        }
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO mission_state VALUES (?, ?, ?, ?, ?)",
                    (mission_id, MISSION_STATE_SCHEMA_VERSION, 1, MissionExecutionStatus.CREATED.value, self._encode(document)),
                )
                self._append_history(mission_id, 1, None, MissionExecutionStatus.CREATED, occurred_at, "created")
        except sqlite3.IntegrityError as error:
            raise MissionStateStoreError(f"mission state already exists: {mission_id}") from error
        return self.get(mission_id)

    def create_pending(self, mission: Any, *, occurred_at: str, resume: Mapping[str, Any] | None = None,
                       execution_policy: Mapping[str, Any] | None = None) -> MissionExecutionState:
        """Persist an approved Mission before planning creates Intents and Actions.

        Dispatcher admission deliberately records no tactical work.  The AI
        Mission Planner remains the only component that may populate it.
        """
        mission_document = _document(mission, "mission")
        mission_id = mission_document.get("id")
        if not isinstance(mission_id, str) or not mission_id or not occurred_at:
            raise MissionStateStoreError("pending mission state requires identity and creation time")
        document = {
            "schema_version": MISSION_STATE_SCHEMA_VERSION, "mission_id": mission_id,
            "mission": mission_document, "intents": [], "actions": [],
            "status": MissionExecutionStatus.CREATED.value, "progress": _derive_progress(()),
            "resume": _document(resume or {}, "resume"), "execution_correlation": None,
            "execution_evidence": None, "current_engineering_intent": None,
            "current_engineering_action": None, "execution_history": [], "waiting_reason": None,
            "repository_truth": None, "completion": None,
            "execution_policy": None if execution_policy is None else _document(execution_policy, "execution policy"),
            "pause_reason": None, "approval_record": None, "revision": 1,
            "delegations": [], "integration": None,
        }
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO mission_state VALUES (?, ?, ?, ?, ?)",
                    (mission_id, MISSION_STATE_SCHEMA_VERSION, 1, MissionExecutionStatus.CREATED.value, self._encode(document)),
                )
                self._append_history(mission_id, 1, None, MissionExecutionStatus.CREATED, occurred_at, "dispatcher_intake")
        except sqlite3.IntegrityError as error:
            raise MissionStateStoreError(f"mission state already exists: {mission_id}") from error
        return self.get(mission_id)

    def get(self, mission_id: str) -> MissionExecutionState:
        row = self._connection.execute("SELECT document FROM mission_state WHERE mission_id = ?", (mission_id,)).fetchone()
        if row is None:
            raise MissionStateStoreError(f"unknown mission state: {mission_id}")
        return self._decode(row["document"])

    def transition(
        self,
        mission_id: str,
        status: MissionExecutionStatus,
        *,
        occurred_at: str,
        reason: str,
        actions: Sequence[Any] | None = None,
        intents: Sequence[Any] | None = None,
        execution_correlation: Any | None = None,
        execution_evidence: Any | None = None,
        resume: Mapping[str, Any] | None = None,
        repository_truth: Mapping[str, Any] | None = None,
        completion: Mapping[str, Any] | None = None,
        execution_policy: Mapping[str, Any] | None = None,
        pause_reason: Mapping[str, Any] | None = None,
        approval_record: Mapping[str, Any] | None = None,
        delegations: Sequence[Mapping[str, Any]] | None = None,
        integration: Mapping[str, Any] | None = None,
    ) -> MissionExecutionState:
        if not occurred_at or not reason:
            raise MissionStateStoreError("transition time and reason are required")
        current = self.get(mission_id)
        if status not in _ALLOWED_TRANSITIONS[current.status]:
            raise MissionStateStoreError(f"mission state transition {current.status.value} -> {status.value} is not permitted")
        next_actions = _documents(actions, "action") if actions is not None else current.actions
        next_intents = _documents(intents, "intent") if intents is not None else current.intents
        current_intent, current_action = _current_work(next_actions, next_intents)
        document = self._as_document(current)
        history = list(document["execution_history"])
        if execution_evidence is not None:
            history.append(_document(execution_evidence, "execution evidence"))
        document.update({
            "status": status.value,
            "actions": list(next_actions),
            "intents": list(next_intents),
            "progress": _derive_progress(next_actions),
            "resume": _document(resume, "resume") if resume is not None else document["resume"],
            "execution_correlation": _document(execution_correlation, "execution correlation") if execution_correlation is not None else document["execution_correlation"],
            "execution_evidence": _document(execution_evidence, "execution evidence") if execution_evidence is not None else document["execution_evidence"],
            "current_engineering_intent": current_intent,
            "current_engineering_action": current_action,
            "execution_history": history,
            "waiting_reason": reason if status in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED, MissionExecutionStatus.WAITING_FOR_EXECUTION, MissionExecutionStatus.WAITING_FOR_EVIDENCE} else None,
            "repository_truth": _document(repository_truth, "repository truth") if repository_truth is not None else document["repository_truth"],
            "completion": _document(completion, "completion") if completion is not None else document["completion"],
            "execution_policy": _document(execution_policy, "execution policy") if execution_policy is not None else document.get("execution_policy"),
            "pause_reason": _document(pause_reason, "pause reason") if pause_reason is not None else (None if status is not MissionExecutionStatus.AWAITING_APPROVAL else document.get("pause_reason")),
            "approval_record": _document(approval_record, "approval record") if approval_record is not None else document.get("approval_record"),
            "delegations": [_document(item, "delegation") for item in delegations] if delegations is not None else document.get("delegations", []),
            "integration": _document(integration, "integration") if integration is not None else document.get("integration"),
            "revision": current.revision + 1,
        })
        if status is MissionExecutionStatus.COMPLETED:
            evidence = document["execution_evidence"]
            required = ("host_id", "receipt_id", "host_run_id", "correlation_id", "report_id", "outcome",
                        "repository_evidence", "execution_started_at", "execution_completed_at", "execution_duration_ms")
            if not isinstance(evidence, dict) or any(not evidence.get(item) for item in required):
                raise MissionStateStoreError("completed mission state requires complete host-issued execution evidence")
            repository = evidence["repository_evidence"]
            if not isinstance(repository, dict) or any(not repository.get(item) for item in (
                "mission_id", "intent_id", "intent_revision", "action_id", "runtime_prompt_id",
                "correlation_id", "host_run_id", "report_id",
            )):
                raise MissionStateStoreError("completed mission state requires complete execution lineage")
            if evidence["outcome"] != "complete" or any(
                evidence[item] != repository[item] for item in ("correlation_id", "host_run_id", "report_id")
            ):
                raise MissionStateStoreError("completed mission state requires correlated complete host evidence")
            if document["progress"]["percent_complete"] != 100:
                raise MissionStateStoreError("completed mission state requires every action to be complete")
        with self._connection:
            self._connection.execute(
                "UPDATE mission_state SET revision = ?, status = ?, document = ? WHERE mission_id = ?",
                (document["revision"], status.value, self._encode(document), mission_id),
            )
            self._append_history(mission_id, document["revision"], current.status, status, occurred_at, reason)
        return self.get(mission_id)

    def set_execution_policy(self, mission_id: str, policy: Mapping[str, Any], *, occurred_at: str) -> MissionExecutionState:
        """Persist the resolved policy once before planning or execution progresses."""
        state = self.get(mission_id)
        if state.execution_policy is not None:
            return state
        document = self._as_document(state)
        document["execution_policy"] = _document(policy, "execution policy")
        document["revision"] = state.revision + 1
        with self._connection:
            self._connection.execute("UPDATE mission_state SET revision = ?, document = ? WHERE mission_id = ?",
                                     (document["revision"], self._encode(document), mission_id))
            self._append_history(mission_id, document["revision"], state.status, state.status,
                                 occurred_at, "execution_policy_resolved")
        return self.get(mission_id)

    def history(self, mission_id: str) -> tuple[MissionStateHistoryEntry, ...]:
        self.get(mission_id)
        rows = self._connection.execute(
            "SELECT sequence, from_status, to_status, occurred_at, reason FROM mission_state_history WHERE mission_id = ? ORDER BY sequence",
            (mission_id,),
        ).fetchall()
        return tuple(
            MissionStateHistoryEntry(
                row["sequence"],
                None if row["from_status"] is None else MissionExecutionStatus(row["from_status"]),
                MissionExecutionStatus(row["to_status"]), row["occurred_at"], row["reason"],
            ) for row in rows
        )

    def resumable(self) -> tuple[MissionExecutionState, ...]:
        rows = self._connection.execute(
            "SELECT document FROM mission_state WHERE status NOT IN (?, ?) ORDER BY mission_id",
            (MissionExecutionStatus.COMPLETED.value, MissionExecutionStatus.ARCHIVED.value),
        ).fetchall()
        return tuple(self._decode(row["document"]) for row in rows)

    def _append_history(self, mission_id: str, sequence: int, from_status: MissionExecutionStatus | None, to_status: MissionExecutionStatus, occurred_at: str, reason: str) -> None:
        self._connection.execute(
            "INSERT INTO mission_state_history VALUES (?, ?, ?, ?, ?, ?)",
            (mission_id, sequence, None if from_status is None else from_status.value, to_status.value, occurred_at, reason),
        )

    @staticmethod
    def _encode(document: Mapping[str, Any]) -> str:
        return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _as_document(state: MissionExecutionState) -> dict[str, Any]:
        return {
            "schema_version": state.schema_version, "mission_id": state.mission_id, "mission": dict(state.mission),
            "intents": [dict(item) for item in state.intents], "actions": [dict(item) for item in state.actions],
            "status": state.status.value, "progress": dict(state.progress), "resume": dict(state.resume),
            "execution_correlation": None if state.execution_correlation is None else dict(state.execution_correlation),
            "execution_evidence": None if state.execution_evidence is None else dict(state.execution_evidence),
            "current_engineering_intent": None if state.current_engineering_intent is None else dict(state.current_engineering_intent),
            "current_engineering_action": None if state.current_engineering_action is None else dict(state.current_engineering_action),
            "execution_history": [dict(item) for item in state.execution_history],
            "waiting_reason": state.waiting_reason,
            "repository_truth": None if state.repository_truth is None else dict(state.repository_truth),
            "completion": None if state.completion is None else dict(state.completion), "revision": state.revision,
            "execution_policy": None if state.execution_policy is None else dict(state.execution_policy),
            "pause_reason": None if state.pause_reason is None else dict(state.pause_reason),
            "approval_record": None if state.approval_record is None else dict(state.approval_record),
            "delegations": [dict(item) for item in state.delegations],
            "integration": None if state.integration is None else dict(state.integration),
        }

    @staticmethod
    def _decode(serialized: str) -> MissionExecutionState:
        document = json.loads(serialized)
        if document.get("schema_version") not in {"1.0", "1.1", "1.2", "1.3", MISSION_STATE_SCHEMA_VERSION}:
            raise MissionStateStoreError("mission state schema version is unsupported")
        return MissionExecutionState(
            mission_id=document["mission_id"], mission=document["mission"], intents=tuple(document["intents"]),
            actions=tuple(document["actions"]), status=MissionExecutionStatus(document["status"]),
            progress=document["progress"], resume=document["resume"],
            execution_correlation=document["execution_correlation"], execution_evidence=document["execution_evidence"],
            revision=document["revision"], current_engineering_intent=document.get("current_engineering_intent"),
            current_engineering_action=document.get("current_engineering_action"),
            execution_history=tuple(document.get("execution_history", ())), waiting_reason=document.get("waiting_reason"),
            repository_truth=document.get("repository_truth"), completion=document.get("completion"),
            execution_policy=document.get("execution_policy"), pause_reason=document.get("pause_reason"),
            approval_record=document.get("approval_record"),
            delegations=tuple(document.get("delegations", ())),
            integration=document.get("integration"),
            schema_version=document["schema_version"],
        )
