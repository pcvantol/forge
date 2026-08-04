"""Append-only local Repository Truth store for immutable Decision Evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Callable

from forge.models.decision_evidence import DecisionEvidence, DecisionReference


class DecisionEvidenceRepositoryError(ValueError):
    pass


class DecisionEvidenceRepository:
    """Persists one immutable document per decision and rejects unresolved references."""

    def __init__(self, path: Path, *, reference_resolver: Callable[[DecisionReference], bool]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._reference_resolver = reference_resolver
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS decision_evidence (
              decision_id TEXT PRIMARY KEY, content_digest TEXT NOT NULL UNIQUE, document TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS decision_evidence_no_update BEFORE UPDATE ON decision_evidence
            BEGIN SELECT RAISE(ABORT, 'decision evidence is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS decision_evidence_no_delete BEFORE DELETE ON decision_evidence
            BEGIN SELECT RAISE(ABORT, 'decision evidence is immutable'); END;
        """)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "DecisionEvidenceRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def append(self, evidence: DecisionEvidence) -> DecisionEvidence:
        references = (evidence.repository_context, evidence.mission_context, evidence.repository_maturity_reference,
                      *evidence.evidence_references, *evidence.execution_evidence_references,
                      evidence.confidence.repository_truth, evidence.confidence.architecture_review,
                      evidence.confidence.execution_evidence, evidence.confidence.mission_state)
        if not all(self._reference_resolver(reference) for reference in references):
            raise DecisionEvidenceRepositoryError("all Decision Evidence references must resolve to Repository Truth")
        try:
            with self._connection:
                self._connection.execute("INSERT INTO decision_evidence VALUES (?, ?, ?)",
                                         (evidence.id, evidence.content_digest, json.dumps(evidence.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)))
        except sqlite3.IntegrityError as error:
            raise DecisionEvidenceRepositoryError("decision evidence id or immutable content already exists") from error
        return evidence

    def get(self, decision_id: str) -> DecisionEvidence:
        row = self._connection.execute("SELECT document FROM decision_evidence WHERE decision_id = ?", (decision_id,)).fetchone()
        if row is None:
            raise DecisionEvidenceRepositoryError(f"unknown decision evidence: {decision_id}")
        return DecisionEvidence.from_dict(json.loads(row["document"]))

    def list(self) -> tuple[DecisionEvidence, ...]:
        rows = self._connection.execute("SELECT document FROM decision_evidence ORDER BY decision_id").fetchall()
        return tuple(DecisionEvidence.from_dict(json.loads(row["document"])) for row in rows)
