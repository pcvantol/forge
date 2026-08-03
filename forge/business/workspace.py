"""Local, auditable Business Workspace storage and business-only transitions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

from forge.models.mission_candidate import MissionCandidate, MissionCandidateStatus


class BusinessWorkspaceError(ValueError):
    pass


@dataclass(frozen=True)
class MissionCandidateHistoryEntry:
    revision: int
    event: str
    actor: str
    occurred_at: str
    rationale: str


class BusinessWorkspace:
    """Owns Portfolio decisions. It cannot create a Mission, execute work, or mutate repositories."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS mission_candidate (
              candidate_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mission_candidate_history (
              candidate_id TEXT NOT NULL, revision INTEGER NOT NULL, event TEXT NOT NULL, actor TEXT NOT NULL,
              occurred_at TEXT NOT NULL, rationale TEXT NOT NULL, PRIMARY KEY(candidate_id, revision),
              FOREIGN KEY(candidate_id) REFERENCES mission_candidate(candidate_id)
            );
            CREATE TRIGGER IF NOT EXISTS mission_candidate_history_no_update BEFORE UPDATE ON mission_candidate_history
            BEGIN SELECT RAISE(ABORT, 'mission candidate history is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS mission_candidate_history_no_delete BEFORE DELETE ON mission_candidate_history
            BEGIN SELECT RAISE(ABORT, 'mission candidate history is append-only'); END;
        """)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "BusinessWorkspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def create(self, candidate: MissionCandidate, *, actor: str, occurred_at: str) -> MissionCandidate:
        if candidate.status is not MissionCandidateStatus.BUSINESS_REVIEW:
            raise BusinessWorkspaceError("new candidates must enter business_review")
        self._write(candidate, 1, "created", actor, occurred_at, candidate.business_rationale, insert=True)
        return self.get(candidate.id)

    def get(self, candidate_id: str) -> MissionCandidate:
        row = self._connection.execute("SELECT document FROM mission_candidate WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise BusinessWorkspaceError(f"unknown mission candidate: {candidate_id}")
        return MissionCandidate.from_dict(json.loads(row["document"]))

    def list(self, *, status: MissionCandidateStatus | None = None) -> tuple[MissionCandidate, ...]:
        query = "SELECT document FROM mission_candidate" + (" WHERE status = ?" if status else "") + " ORDER BY candidate_id"
        rows = self._connection.execute(query, () if status is None else (status.value,)).fetchall()
        return tuple(MissionCandidate.from_dict(json.loads(row["document"])) for row in rows)

    def refine(self, candidate_id: str, *, actor: str, occurred_at: str, rationale: str, **changes: object) -> MissionCandidate:
        candidate, revision = self._current(candidate_id)
        if candidate.status is not MissionCandidateStatus.BUSINESS_REVIEW:
            raise BusinessWorkspaceError("only candidates in business_review may be refined")
        allowed = {"title", "summary", "business_objective", "business_value", "priority", "business_rationale", "maturity", "dependencies", "required_disciplines"}
        if not changes or set(changes) - allowed:
            raise BusinessWorkspaceError("business refinement may update only business candidate fields")
        refined = replace(candidate, **changes)
        self._write(refined, revision + 1, "refined", actor, occurred_at, rationale)
        return self.get(candidate_id)

    def approve_for_architecture(self, candidate_id: str, *, actor: str, occurred_at: str, rationale: str) -> MissionCandidate:
        return self._transition(candidate_id, MissionCandidateStatus.APPROVED_FOR_ARCHITECTURE, "approved_for_architecture", actor, occurred_at, rationale)

    def reject(self, candidate_id: str, *, actor: str, occurred_at: str, rationale: str) -> MissionCandidate:
        return self._transition(candidate_id, MissionCandidateStatus.REJECTED, "rejected", actor, occurred_at, rationale)

    def archive(self, candidate_id: str, *, actor: str, occurred_at: str, rationale: str) -> MissionCandidate:
        return self._transition(candidate_id, MissionCandidateStatus.ARCHIVED, "archived", actor, occurred_at, rationale)

    def history(self, candidate_id: str) -> tuple[MissionCandidateHistoryEntry, ...]:
        self.get(candidate_id)
        rows = self._connection.execute("SELECT revision, event, actor, occurred_at, rationale FROM mission_candidate_history WHERE candidate_id = ? ORDER BY revision", (candidate_id,)).fetchall()
        return tuple(MissionCandidateHistoryEntry(**dict(row)) for row in rows)

    def _transition(self, candidate_id: str, target: MissionCandidateStatus, event: str, actor: str, occurred_at: str, rationale: str) -> MissionCandidate:
        candidate, revision = self._current(candidate_id)
        if candidate.status is not MissionCandidateStatus.BUSINESS_REVIEW:
            raise BusinessWorkspaceError(f"mission candidate transition {candidate.status.value} -> {target.value} is not permitted")
        if not all((actor, occurred_at, rationale)):
            raise BusinessWorkspaceError("business decision requires actor, time, and rationale")
        self._write(replace(candidate, status=target), revision + 1, event, actor, occurred_at, rationale)
        return self.get(candidate_id)

    def _current(self, candidate_id: str) -> tuple[MissionCandidate, int]:
        row = self._connection.execute("SELECT revision, document FROM mission_candidate WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise BusinessWorkspaceError(f"unknown mission candidate: {candidate_id}")
        return MissionCandidate.from_dict(json.loads(row["document"])), row["revision"]

    def _write(self, candidate: MissionCandidate, revision: int, event: str, actor: str, occurred_at: str, rationale: str, *, insert: bool = False) -> None:
        if not all((actor, occurred_at, rationale)):
            raise BusinessWorkspaceError("business change requires actor, time, and rationale")
        document = json.dumps(candidate.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        try:
            with self._connection:
                if insert:
                    self._connection.execute("INSERT INTO mission_candidate VALUES (?, ?, ?, ?)", (candidate.id, revision, candidate.status.value, document))
                else:
                    self._connection.execute("UPDATE mission_candidate SET revision = ?, status = ?, document = ? WHERE candidate_id = ?", (revision, candidate.status.value, document, candidate.id))
                self._connection.execute("INSERT INTO mission_candidate_history VALUES (?, ?, ?, ?, ?, ?)", (candidate.id, revision, event, actor, occurred_at, rationale))
        except sqlite3.IntegrityError as error:
            raise BusinessWorkspaceError(f"mission candidate already exists: {candidate.id}") from error
