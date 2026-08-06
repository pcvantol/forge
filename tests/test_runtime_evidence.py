"""Regression coverage for Runtime Database evidence projections."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from forge.runtime import RuntimeDatabase


class RuntimeEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = RuntimeDatabase(Path(self.temporary.name))
        self.addCleanup(self.database.close)
        self.addCleanup(self.temporary.cleanup)
        self.database.save_mission_state({"mission_id": "mission-1", "status": "COMPLETED", "progress": {}, "resume": {}, "execution_policy": {"mode": "local"}, "completion": {"success": True}})
        self.database.record_mission_lifecycle("mission-1", "ACTIVATED", "2026-08-04T00:00:00Z")
        self.database.record_mission_lifecycle("mission-1", "COMPLETED", "2026-08-04T00:01:00Z")
        self.database.record_architecture_review({"id": "review-1", "mission_id": "mission-1", "input_digest": "sha256:truth", "repository_maturity": [], "pressure": {"architecture": "low", "implementation": "low"}, "confidence": "high", "reviewed_at": "2026-08-04T00:00:00Z"})
        self.database.record_mission_recommendation({"id": "recommendation-1", "architecture_review_id": "review-1", "priority": "low", "confidence": {}, "dependencies": {}, "required_disciplines": [], "recommendation_timestamp": "2026-08-04T00:00:00Z", "origin": "maintenance", "recommendation_source": "repository_truth", "repository_evidence": [{"id": "truth", "revision": "abc", "locator": "repository://truth", "content_digest": "sha256:truth"}], "decision_evidence_references": ["decision-1"]}, mission_id="mission-1")
        self.database.record_execution_receipt(receipt_id="receipt-1", mission_id="mission-1", execution_host="engineering-platform", execution_run_id="run-1", engineering_report_id="report-1", correlation_identity="correlation-1", executed_at="2026-08-04T00:00:00Z", outcome="complete")
        self.database.record_decision_evidence({"id": "decision-1", "decision_type": "mission_planning", "reasoning_summary": "bounded", "evidence_references": [], "alternatives_considered": [], "timestamp": "2026-08-04T00:00:00Z", "mission_context": {"artifact_id": "mission-1"}, "repository_context": {"artifact_id": "repository-truth-1"}, "confidence": {"architecture_review": {"artifact_id": "review-1"}, "mission_state": {"artifact_id": "mission-1"}}, "execution_receipt_references": [{"artifact_id": "receipt-1"}]})
        self.database.save_dispatcher_state(status="IDLE", mission_sequence=("mission-1",))

    def test_qualification_and_reports_are_runtime_database_projections(self) -> None:
        evidence = self.database.runtime_evidence()
        qualification = evidence.mission_qualification("mission-1")
        self.assertTrue(qualification["qualified"])
        self.assertEqual(qualification["ownership"]["execution_evidence"], "execution_host")
        self.assertEqual(evidence.bootstrap_qualification(("mission-1",))["source"], "runtime_database")
        self.assertEqual(evidence.architecture_review_report("review-1")["source"], "runtime_database")
        self.assertEqual(evidence.mission_recommendation_report("recommendation-1")["source"], "runtime_database")
        self.assertEqual(evidence.decision_evidence_report("decision-1")["execution_receipts"][0]["execution_run_id"], "run-1")

    def test_decision_evidence_reference_is_pinned_to_the_runtime_instance(self) -> None:
        evidence = self.database.runtime_evidence()
        reference = evidence.decision_evidence_reference("decision-1")
        report = evidence.decision_evidence_report("decision-1")

        self.assertEqual(reference.runtime_id, self.database.runtime_identity.runtime_id)
        self.assertEqual(reference.repository_identity, self.database.runtime_identity.repository_identity)
        self.assertEqual(reference.locator, f"runtime://{reference.runtime_id}/decision-evidence/decision-1")
        self.assertEqual(report["decision_evidence_reference"], reference.to_dict())
        self.assertEqual(report["runtime_instance"]["runtime_id"], reference.runtime_id)

    def test_workspace_projections_do_not_reconstruct_repository_or_host_evidence(self) -> None:
        projection = self.database.runtime_evidence().business_workspace("mission-1")
        self.assertEqual(set(projection), {"mission_state", "mission_recommendations", "decision_evidence", "architecture_reviews", "execution_receipts"})
        self.assertNotIn("execution_evidence", projection)

    def test_qualification_rejects_duplicate_or_out_of_order_lifecycle(self) -> None:
        self.database.record_mission_lifecycle("mission-1", "COMPLETED", "2026-08-04T00:02:00Z")
        self.assertFalse(self.database.runtime_evidence().bootstrap_qualification(("mission-1",))["qualified"])


if __name__ == "__main__":
    unittest.main()
