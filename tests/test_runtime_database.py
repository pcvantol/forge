"""Regression coverage for the Forge Runtime Database Foundation."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from forge.runtime import RUNTIME_SCHEMA_VERSION, RuntimeDatabase, RuntimeIntegrityError


class RuntimeDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.database = RuntimeDatabase(self.root, forge_version="test")
        self.addCleanup(self.database.close)
        self.addCleanup(self.directory.cleanup)

    def _mission(self) -> dict[str, object]:
        return {"mission_id": "mission-1", "status": "READY", "progress": {"percent_complete": 0}, "resume": {}, "execution_policy": {"mode": "local"}}

    def _review(self) -> dict[str, object]:
        return {"id": "review-1", "mission_id": "mission-1", "input_digest": "sha256:review", "repository_maturity": [], "pressure": {"architecture": "low", "implementation": "low"}, "confidence": "high", "reviewed_at": "2026-08-04T00:00:00Z"}

    def test_creation_uses_canonical_runtime_path_and_versioned_metadata(self) -> None:
        self.assertEqual(self.database.path, self.root / ".forge" / "runtime.db")
        self.assertTrue(self.database.path.exists())
        self.assertEqual(self.database.metadata["schema_version"], str(RUNTIME_SCHEMA_VERSION))
        self.database.validate_integrity()

    def test_mission_review_recommendation_decision_and_execution_reference_persist(self) -> None:
        self.database.save_mission_state(self._mission())
        self.database.record_architecture_review(self._review())
        recommendation = {"id": "recommendation-1", "architecture_review_id": "review-1", "confidence": {"score": 80}, "dependencies": {}, "required_disciplines": ["engineering"], "recommendation_timestamp": "2026-08-04T00:00:00Z"}
        self.database.record_mission_recommendation(recommendation, mission_id="mission-1")
        self.database.record_execution_reference(reference_id="execution-1", mission_id="mission-1", execution_host="engineering-platform", execution_run_id="run-1", correlation="correlation-1", executed_at="2026-08-04T00:00:00Z", outcome="complete")
        decision = {"id": "decision-1", "decision_type": "mission_planning", "mission_context": {"artifact_id": "mission-1"}, "repository_context": {"artifact_id": "repository-truth-1"}, "reasoning_summary": "bounded", "evidence_references": [], "alternatives_considered": [], "confidence": {"score": 80, "architecture_review": {"artifact_id": "review-1"}, "mission_state": {"artifact_id": "mission-1"}}, "execution_evidence_references": [{"artifact_id": "execution-1"}], "timestamp": "2026-08-04T00:00:00Z"}
        self.database.record_decision_evidence(decision)
        self.assertEqual(self.database.get_document("mission_state", "mission-1")["status"], "READY")
        self.assertEqual(self.database.get_document("architecture_reviews", "review-1")["id"], "review-1")
        self.assertEqual(self.database.get_document("mission_recommendations", "recommendation-1")["id"], "recommendation-1")
        self.assertEqual(self.database.get_document("decision_evidence", "decision-1")["id"], "decision-1")

    def test_restart_recovery_and_foreign_reference_validation_fail_closed(self) -> None:
        self.database.save_mission_state(self._mission())
        self.database.close()
        self.database = RuntimeDatabase(self.root, forge_version="test")
        self.assertEqual(self.database.get_document("mission_state", "mission-1")["mission_id"], "mission-1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.record_execution_reference(reference_id="bad", mission_id="missing", execution_host="host", execution_run_id="run", correlation="correlation", executed_at="now", outcome="failed")

    def test_newer_schema_and_missing_metadata_are_rejected(self) -> None:
        self.database.close()
        connection = sqlite3.connect(self.root / ".forge" / "runtime.db")
        connection.execute("PRAGMA user_version=99")
        connection.commit(); connection.close()
        with self.assertRaises(RuntimeIntegrityError):
            RuntimeDatabase(self.root)

    def test_decision_requires_a_persisted_execution_reference(self) -> None:
        self.database.save_mission_state(self._mission())
        self.database.record_architecture_review(self._review())
        decision = {"id": "decision-1", "mission_context": {"artifact_id": "mission-1"}, "repository_context": {"artifact_id": "repository-truth-1"},
                    "confidence": {"architecture_review": {"artifact_id": "review-1"}, "mission_state": {"artifact_id": "mission-1"}},
                    "execution_evidence_references": [{"artifact_id": "missing"}]}
        with self.assertRaisesRegex(Exception, "execution reference"):
            self.database.record_decision_evidence(decision)


if __name__ == "__main__":
    unittest.main()
