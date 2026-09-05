"""Local Architecture Workspace governance and approval persistence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.mission_candidate import MissionCandidate, MissionCandidateStatus


class ArchitectureWorkspaceError(ValueError):
    pass


@dataclass(frozen=True)
class ArchitectureMissionHistoryEntry:
    revision: int
    event: str
    actor: str
    occurred_at: str
    rationale: str


class ArchitectureWorkspace:
    """Legacy local workspace storage for offline/tests; not production authority.

    Supported Forge governance mutations use :meth:`for_runtime`, which is
    bound to the resolved Runtime Instance and canonical evidence repository.
    """

    @classmethod
    def for_runtime(cls, database: object, repository: object, context: object) -> object:
        """Return the canonical runtime-bound Architecture approval service."""
        from forge.governance_authority import CanonicalArchitectureWorkspace
        if getattr(repository, "database", None) is not database:
            raise ArchitectureWorkspaceError("Architecture governance repository must use the resolved Runtime Instance")
        return CanonicalArchitectureWorkspace(repository, context)

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS architecture_mission (
              mission_id TEXT PRIMARY KEY, candidate_id TEXT UNIQUE NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL, document TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS architecture_mission_history (
              mission_id TEXT NOT NULL, revision INTEGER NOT NULL, event TEXT NOT NULL, actor TEXT NOT NULL,
              occurred_at TEXT NOT NULL, rationale TEXT NOT NULL, PRIMARY KEY(mission_id, revision),
              FOREIGN KEY(mission_id) REFERENCES architecture_mission(mission_id)
            );
            CREATE TRIGGER IF NOT EXISTS architecture_mission_history_no_update BEFORE UPDATE ON architecture_mission_history
            BEGIN SELECT RAISE(ABORT, 'architecture mission history is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS architecture_mission_history_no_delete BEFORE DELETE ON architecture_mission_history
            BEGIN SELECT RAISE(ABORT, 'architecture mission history is append-only'); END;
        """)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ArchitectureWorkspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def admit(self, candidate: MissionCandidate, *, actor: str, occurred_at: str, rationale: str) -> ArchitectureMission:
        if candidate.status is not MissionCandidateStatus.APPROVED_FOR_ARCHITECTURE:
            raise ArchitectureWorkspaceError("only business-approved candidates may enter architecture review")
        mission = ArchitectureMission.from_candidate(candidate)
        self._write(mission, 1, "admitted_from_business", actor, occurred_at, rationale, insert=True)
        return self.get(mission.id)

    create = admit

    def get(self, mission_id: str) -> ArchitectureMission:
        row = self._connection.execute("SELECT document FROM architecture_mission WHERE mission_id = ?", (mission_id,)).fetchone()
        if row is None:
            raise ArchitectureWorkspaceError(f"unknown architecture mission: {mission_id}")
        return ArchitectureMission.from_dict(json.loads(row["document"]))

    def list(self, *, status: ArchitectureMissionStatus | None = None) -> tuple[ArchitectureMission, ...]:
        query = "SELECT document FROM architecture_mission" + (" WHERE status = ?" if status else "") + " ORDER BY mission_id"
        rows = self._connection.execute(query, () if status is None else (status.value,)).fetchall()
        return tuple(ArchitectureMission.from_dict(json.loads(row["document"])) for row in rows)

    def approved_for_engineering(self) -> tuple[ArchitectureMission, ...]:
        """Return the governed queue source in deterministic approval order."""
        rows = self._connection.execute(
            """
            SELECT mission.document
            FROM architecture_mission AS mission
            JOIN architecture_mission_history AS history
              ON history.mission_id = mission.mission_id
             AND history.event = 'approved_for_engineering'
            WHERE mission.status = ?
            ORDER BY history.occurred_at, mission.mission_id
            """,
            (ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING.value,),
        ).fetchall()
        return tuple(ArchitectureMission.from_dict(json.loads(row["document"])) for row in rows)

    def refine(self, mission_id: str, *, actor: str, occurred_at: str, rationale: str, **changes: object) -> ArchitectureMission:
        mission, revision = self._current(mission_id)
        if mission.status is not ArchitectureMissionStatus.ARCHITECTURE_REVIEW:
            raise ArchitectureWorkspaceError("only Missions in architecture_review may be refined")
        allowed = {"scope", "engineering_constraints", "acceptance_criteria", "technical_assumptions", "dependencies", "required_capabilities", "required_disciplines", "risks"}
        if not changes or set(changes) - allowed:
            raise ArchitectureWorkspaceError("architecture refinement may update only engineering governance fields")
        refined = replace(mission, **changes)
        self._write(refined, revision + 1, "refined", actor, occurred_at, rationale)
        return self.get(mission_id)

    def approve_for_engineering(self, mission_id: str, *, actor: str, occurred_at: str, rationale: str) -> ArchitectureMission:
        mission, revision = self._current(mission_id)
        if mission.status is not ArchitectureMissionStatus.ARCHITECTURE_REVIEW:
            raise ArchitectureWorkspaceError(f"architecture mission transition {mission.status.value} -> approved_for_engineering is not permitted")
        if not mission.is_engineering_ready():
            raise ArchitectureWorkspaceError("engineering approval requires a complete architectural refinement")
        return self._transition(mission, revision, ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING, "approved_for_engineering", actor, occurred_at, rationale)

    def return_to_business(self, mission_id: str, *, actor: str, occurred_at: str, rationale: str) -> ArchitectureMission:
        return self._terminal_transition(mission_id, ArchitectureMissionStatus.RETURNED_TO_BUSINESS, "returned_to_business", actor, occurred_at, rationale)

    def reject(self, mission_id: str, *, actor: str, occurred_at: str, rationale: str) -> ArchitectureMission:
        return self._terminal_transition(mission_id, ArchitectureMissionStatus.REJECTED, "rejected", actor, occurred_at, rationale)

    def archive(self, mission_id: str, *, actor: str, occurred_at: str, rationale: str) -> ArchitectureMission:
        return self._terminal_transition(mission_id, ArchitectureMissionStatus.ARCHIVED, "archived", actor, occurred_at, rationale)

    def history(self, mission_id: str) -> tuple[ArchitectureMissionHistoryEntry, ...]:
        self.get(mission_id)
        rows = self._connection.execute("SELECT revision, event, actor, occurred_at, rationale FROM architecture_mission_history WHERE mission_id = ? ORDER BY revision", (mission_id,)).fetchall()
        return tuple(ArchitectureMissionHistoryEntry(**dict(row)) for row in rows)

    def _terminal_transition(self, mission_id: str, target: ArchitectureMissionStatus, event: str, actor: str, occurred_at: str, rationale: str) -> ArchitectureMission:
        mission, revision = self._current(mission_id)
        if mission.status is not ArchitectureMissionStatus.ARCHITECTURE_REVIEW:
            raise ArchitectureWorkspaceError(f"architecture mission transition {mission.status.value} -> {target.value} is not permitted")
        return self._transition(mission, revision, target, event, actor, occurred_at, rationale)

    def _transition(self, mission: ArchitectureMission, revision: int, target: ArchitectureMissionStatus, event: str, actor: str, occurred_at: str, rationale: str) -> ArchitectureMission:
        if not all((actor, occurred_at, rationale)):
            raise ArchitectureWorkspaceError("architecture decision requires actor, time, and rationale")
        self._write(replace(mission, status=target), revision + 1, event, actor, occurred_at, rationale)
        return self.get(mission.id)

    def _current(self, mission_id: str) -> tuple[ArchitectureMission, int]:
        row = self._connection.execute("SELECT revision, document FROM architecture_mission WHERE mission_id = ?", (mission_id,)).fetchone()
        if row is None:
            raise ArchitectureWorkspaceError(f"unknown architecture mission: {mission_id}")
        return ArchitectureMission.from_dict(json.loads(row["document"])), row["revision"]

    def _write(self, mission: ArchitectureMission, revision: int, event: str, actor: str, occurred_at: str, rationale: str, *, insert: bool = False) -> None:
        if not all((actor, occurred_at, rationale)):
            raise ArchitectureWorkspaceError("architecture change requires actor, time, and rationale")
        document = json.dumps(mission.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        try:
            with self._connection:
                if insert:
                    self._connection.execute("INSERT INTO architecture_mission VALUES (?, ?, ?, ?, ?)", (mission.id, mission.candidate_id, revision, mission.status.value, document))
                else:
                    self._connection.execute("UPDATE architecture_mission SET revision = ?, status = ?, document = ? WHERE mission_id = ?", (revision, mission.status.value, document, mission.id))
                self._connection.execute("INSERT INTO architecture_mission_history VALUES (?, ?, ?, ?, ?, ?)", (mission.id, revision, event, actor, occurred_at, rationale))
        except sqlite3.IntegrityError as error:
            raise ArchitectureWorkspaceError(f"architecture mission already exists: {mission.id}") from error
