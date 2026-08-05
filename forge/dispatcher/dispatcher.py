"""Persistent, FIFO dispatch of Architecture-approved Missions only.

This boundary activates Mission work.  It does not create Missions, plan
Intents or Actions, render prompts, invoke an Execution Host, or execute.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import sqlite3
from pathlib import Path
from typing import Callable, Protocol

from forge.architecture import ArchitectureWorkspace
from forge.intake import MissionIntake
from forge.models.architecture_mission import ArchitectureMission
from forge.state import MissionExecutionStatus, MissionStateStore

# Historical portfolio identifier set retained for the bootstrap regression
# harness only. It does not affect operational queue ordering.
BOOTSTRAP_MISSION_SEQUENCE = ("MISSION-0001", "MISSION-0002", "MISSION-0003", "MISSION-0004", "MISSION-0005")


class DispatcherStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class MissionDispatcherError(ValueError):
    pass


@dataclass(frozen=True)
class MissionDispatchRecord:
    mission_id: str
    status: DispatcherStatus
    sequence: int
    occurred_at: str


class CompletionHook(Protocol):
    def __call__(self, mission_id: str) -> None: ...


class ApprovedMissionQueue:
    """A read-only, governance-filtered queue; recommendations never enter it."""

    def __init__(self, workspace: ArchitectureWorkspace) -> None:
        self._workspace = workspace

    def missions(self) -> tuple[ArchitectureMission, ...]:
        return self._workspace.approved_for_engineering()


class MissionDispatcherStore:
    """Local durable dispatcher lifecycle with a database-enforced one-active invariant."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS mission_dispatch (
              mission_id TEXT PRIMARY KEY, status TEXT NOT NULL, sequence INTEGER NOT NULL, occurred_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_mission ON mission_dispatch(status) WHERE status = 'ACTIVE';
        """)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def active(self) -> MissionDispatchRecord | None:
        row = self._connection.execute("SELECT * FROM mission_dispatch WHERE status = 'ACTIVE'").fetchone()
        return None if row is None else self._record(row)

    def get(self, mission_id: str) -> MissionDispatchRecord | None:
        row = self._connection.execute("SELECT * FROM mission_dispatch WHERE mission_id = ?", (mission_id,)).fetchone()
        return None if row is None else self._record(row)

    def records(self) -> tuple[MissionDispatchRecord, ...]:
        return tuple(self._record(row) for row in self._connection.execute("SELECT * FROM mission_dispatch ORDER BY sequence, mission_id"))

    def activate(self, mission_id: str, *, occurred_at: str) -> MissionDispatchRecord:
        if self.active() is not None:
            raise MissionDispatcherError("only one Mission may be active")
        existing = self.get(mission_id)
        if existing and existing.status not in {DispatcherStatus.PENDING, DispatcherStatus.BLOCKED, DispatcherStatus.FAILED}:
            raise MissionDispatcherError("Mission dispatch lifecycle cannot be activated")
        sequence = existing.sequence if existing else len(self.records()) + 1
        try:
            with self._connection:
                if existing:
                    self._connection.execute("UPDATE mission_dispatch SET status = ?, occurred_at = ? WHERE mission_id = ?", (DispatcherStatus.ACTIVE.value, occurred_at, mission_id))
                else:
                    self._connection.execute("INSERT INTO mission_dispatch VALUES (?, ?, ?, ?)", (mission_id, DispatcherStatus.ACTIVE.value, sequence, occurred_at))
        except sqlite3.IntegrityError as error:
            raise MissionDispatcherError("only one Mission may be active") from error
        return self.get(mission_id)  # type: ignore[return-value]

    def pending(self, mission_id: str, *, occurred_at: str) -> MissionDispatchRecord:
        if self.get(mission_id) is not None:
            raise MissionDispatcherError("Mission already has a dispatch record")
        with self._connection:
            self._connection.execute(
                "INSERT INTO mission_dispatch VALUES (?, ?, ?, ?)",
                (mission_id, DispatcherStatus.PENDING.value, len(self.records()) + 1, occurred_at),
            )
        return self.get(mission_id)  # type: ignore[return-value]

    def transition(self, mission_id: str, status: DispatcherStatus, *, occurred_at: str) -> MissionDispatchRecord:
        current = self.get(mission_id)
        if current is None or current.status is not DispatcherStatus.ACTIVE:
            raise MissionDispatcherError("only the active Mission may change terminal dispatch state")
        if status not in {DispatcherStatus.COMPLETED, DispatcherStatus.BLOCKED, DispatcherStatus.FAILED, DispatcherStatus.ARCHIVED}:
            raise MissionDispatcherError("dispatch transition must be terminal or explicitly blocked")
        with self._connection:
            self._connection.execute("UPDATE mission_dispatch SET status = ?, occurred_at = ? WHERE mission_id = ?", (status.value, occurred_at, mission_id))
        return self.get(mission_id)  # type: ignore[return-value]

    @staticmethod
    def _record(row: sqlite3.Row) -> MissionDispatchRecord:
        return MissionDispatchRecord(row["mission_id"], DispatcherStatus(row["status"]), row["sequence"], row["occurred_at"])


class MissionDispatcher:
    """Activate one approved Mission, then wait for its independently verified completion."""

    def __init__(self, queue: ApprovedMissionQueue, intake: MissionIntake, states: MissionStateStore, store: MissionDispatcherStore, *, clock: Callable[[], str], architecture_review: CompletionHook | None = None, recommendations: CompletionHook | None = None) -> None:
        self._queue, self._intake, self._states, self._store = queue, intake, states, store
        self._clock, self._architecture_review, self._recommendations = clock, architecture_review, recommendations

    @property
    def is_idle(self) -> bool:
        return self._store.active() is None and not any(item.id not in {record.mission_id for record in self._store.records()} for item in self._queue.missions())

    def dispatch(self) -> MissionDispatchRecord | None:
        active = self.resume()
        if active:
            return active
        if any(item.status in {DispatcherStatus.BLOCKED, DispatcherStatus.FAILED} for item in self._store.records()):
            return None
        completed = {item.mission_id for item in self._store.records() if item.status in {DispatcherStatus.COMPLETED, DispatcherStatus.ARCHIVED}}
        mission = next((item for item in self._queue.missions() if item.id not in completed), None)
        if mission is None:
            return None
        if self._store.get(mission.id) is None:
            self._store.pending(mission.id, occurred_at=self._clock())
            self._intake.admit_approved_mission(mission)
        return self._store.activate(mission.id, occurred_at=self._clock())

    def resume(self) -> MissionDispatchRecord | None:
        active = self._store.active()
        if active is None:
            return None
        state = self._states.get(active.mission_id)
        if state.status in {MissionExecutionStatus.COMPLETED, MissionExecutionStatus.ARCHIVED}:
            raise MissionDispatcherError("active dispatcher record has terminal Mission State")
        return active

    def complete(self, mission_id: str) -> MissionDispatchRecord | None:
        state = self._states.get(mission_id)
        if state.status is not MissionExecutionStatus.COMPLETED:
            raise MissionDispatcherError("Mission completion requires verified completed Mission State")
        evidence = getattr(state, "execution_evidence", None)
        if evidence is not None and (not evidence.get("receipt_id") or evidence.get("outcome") != "complete"):
            raise MissionDispatcherError("Mission completion requires host-issued complete execution evidence")
        self._store.transition(mission_id, DispatcherStatus.COMPLETED, occurred_at=self._clock())
        if self._architecture_review:
            self._architecture_review(mission_id)
        if self._recommendations:
            self._recommendations(mission_id)
        return self.dispatch()

    def hold(self, mission_id: str, status: MissionExecutionStatus) -> MissionDispatchRecord:
        """Reflect a loop-owned deterministic pause without advancing the queue."""
        if status not in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED}:
            raise MissionDispatcherError("dispatcher hold requires blocked or failed Mission State")
        state = self._states.get(mission_id)
        if state.status is not status:
            raise MissionDispatcherError("dispatcher hold requires matching durable Mission State")
        dispatch_status = DispatcherStatus.BLOCKED if status is MissionExecutionStatus.BLOCKED else DispatcherStatus.FAILED
        return self._store.transition(mission_id, dispatch_status, occurred_at=self._clock())

    def recover(self, mission_id: str) -> MissionDispatchRecord:
        """Reactivate an explicitly recovered Mission; it does not plan or execute it."""
        state = self._states.get(mission_id)
        if state.status not in {MissionExecutionStatus.READY, MissionExecutionStatus.ACTIVE}:
            raise MissionDispatcherError("dispatcher recovery requires a recovered Mission State")
        return self._store.activate(mission_id, occurred_at=self._clock())
