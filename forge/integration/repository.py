"""Immutable local storage for Forge integration evidence."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from forge.models.integration import IntegrationEvidence


class IntegrationEvidenceRepositoryError(ValueError):
    pass


class IntegrationEvidenceRepository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS integration_evidence (
              integration_id TEXT PRIMARY KEY, content_digest TEXT NOT NULL UNIQUE, document TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS integration_evidence_no_update BEFORE UPDATE ON integration_evidence
            BEGIN SELECT RAISE(ABORT, 'integration evidence is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS integration_evidence_no_delete BEFORE DELETE ON integration_evidence
            BEGIN SELECT RAISE(ABORT, 'integration evidence is immutable'); END;
        """)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "IntegrationEvidenceRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def append(self, evidence: IntegrationEvidence) -> IntegrationEvidence:
        try:
            with self._connection:
                self._connection.execute("INSERT INTO integration_evidence VALUES (?, ?, ?)", (
                    evidence.id, evidence.content_digest,
                    json.dumps(evidence.to_dict(), sort_keys=True, separators=(",", ":")),
                ))
        except sqlite3.IntegrityError as error:
            raise IntegrationEvidenceRepositoryError("integration evidence id or immutable content already exists") from error
        return evidence

    def list_for_mission(self, mission_id: str) -> tuple[IntegrationEvidence, ...]:
        rows = self._connection.execute("SELECT document FROM integration_evidence WHERE json_extract(document, '$.mission_id') = ? ORDER BY integration_id", (mission_id,)).fetchall()
        return tuple(IntegrationEvidence.from_dict(json.loads(row["document"])) for row in rows)
