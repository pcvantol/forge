"""Legacy bootstrap compatibility, never substantive execution qualification."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.dispatcher import BOOTSTRAP_MISSION_SEQUENCE
from forge.runtime import RuntimeDatabase
from forge.qualification.bootstrap_sequence import (
    BootstrapQualificationBlocked,
    load_canonical_bootstrap_portfolio,
    run_bootstrap_sequence_qualification,
)


class UncalledEvidenceSource:
    def __init__(self):
        self.calls = []

    def _called(self, name):
        self.calls.append(name)
        raise AssertionError("legacy qualification must not call the Host")

    def submit(self, request): return self._called("submit")
    def receipt_for(self, correlation_id): return self._called("receipt_for")
    def report_for(self, run_id): return self._called("report_for")


def seed_retained_legacy_result(database, identifiers):
    """Synthetic pre-v2 persisted-history fixture, not new completion evidence.

    Explicitly exercise legacy readback compatibility. No production evaluator,
    host or qualification execution is being used to claim these facts.
    """
    for identifier in identifiers:
        database.save_mission_state({"mission_id": identifier, "status": "COMPLETED",
            "progress": {}, "resume": {}, "execution_policy": {"mode": "historical_fixture"},
            "completion": {"schema_version": "1.0", "legacy_retained_fixture": True}})
        for lifecycle in ("ACTIVATED", "COMPLETED"):
            database.record_mission_lifecycle(identifier, lifecycle, "2026-08-04T00:00:00Z")
        review_id, receipt_id = identifier + ":review", identifier + ":receipt"
        decision_id = identifier + ":decision"
        database.record_architecture_review({"id": review_id, "mission_id": identifier,
            "input_digest": "sha256:historical", "repository_maturity": [],
            "pressure": {"architecture": "low", "implementation": "low"}, "confidence": "high",
            "reviewed_at": "2026-08-04T00:00:00Z"})
        database.record_mission_recommendation({"id": identifier + ":recommendation",
            "architecture_review_id": review_id, "priority": "low", "confidence": {},
            "dependencies": {}, "required_disciplines": [],
            "recommendation_timestamp": "2026-08-04T00:00:00Z", "origin": "maintenance",
            "recommendation_source": "repository_truth", "repository_evidence": [{
                "id": "historical-truth", "revision": "historical", "locator": "fixture://history",
                "content_digest": "sha256:historical"}], "decision_evidence_references": [decision_id]},
            mission_id=identifier)
        database.record_execution_receipt(receipt_id=receipt_id, mission_id=identifier,
            execution_host="historical-host", execution_run_id=identifier + ":run",
            engineering_report_id=identifier + ":report", correlation_identity=identifier + ":correlation",
            executed_at="2026-08-04T00:00:00Z", outcome="complete")
        database.record_decision_evidence({"id": decision_id, "decision_type": "mission_planning",
            "reasoning_summary": "retained historical fixture", "evidence_references": [],
            "alternatives_considered": [], "timestamp": "2026-08-04T00:00:00Z",
            "mission_context": {"artifact_id": identifier},
            "repository_context": {"artifact_id": "historical-truth"},
            "confidence": {"architecture_review": {"artifact_id": review_id},
                           "mission_state": {"artifact_id": identifier}},
            "execution_receipt_references": [{"artifact_id": receipt_id}]})
    database.save_dispatcher_state(status="IDLE", mission_sequence=BOOTSTRAP_MISSION_SEQUENCE)
    database.save_planning_state({"planner_version": "retained-legacy-fixture", "current_queue": [],
        "pending_engineering_actions": [], "blocked_engineering_actions": [],
        "execution_policy": {"mode": "historical_fixture"},
        "planner_runtime_metadata": {"source": "retained_fixture"}})


class BootstrapSequenceQualificationTests(unittest.TestCase):
    def test_new_legacy_seed_execution_is_refused_before_host_or_approval(self):
        with TemporaryDirectory() as directory:
            root, source = Path(directory), UncalledEvidenceSource()
            with self.assertRaisesRegex(BootstrapQualificationBlocked, "LEGACY_ASSESSMENT_CONTRACT_MISSING"):
                run_bootstrap_sequence_qualification(root, source)
            self.assertEqual(source.calls, [])
            self.assertFalse((root / "architecture.sqlite").exists())
            self.assertFalse((root / "dispatcher.sqlite").exists())
            database = RuntimeDatabase(root)
            self.addCleanup(database.close)
            evidence = database.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE)
            self.assertFalse(evidence["qualified"])
            self.assertTrue(all(not item["qualified"] for item in evidence["missions"]))
            self.assertEqual(database._connection.execute("SELECT COUNT(*) FROM mission_state").fetchone()[0], 0)

    def test_retained_terminal_legacy_readback_is_idempotent_without_reassessment(self):
        with TemporaryDirectory() as directory:
            root, source = Path(directory), UncalledEvidenceSource()
            database = RuntimeDatabase(root)
            seed_retained_legacy_result(database, BOOTSTRAP_MISSION_SEQUENCE)
            before = database.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE)
            self.assertTrue(before["qualified"])
            database.close()
            first = run_bootstrap_sequence_qualification(root, source)
            second = run_bootstrap_sequence_qualification(root, source)
            self.assertEqual(first, second)
            self.assertEqual(first.answer, "YES")
            self.assertEqual(source.calls, [])
            database = RuntimeDatabase(root)
            self.addCleanup(database.close)
            self.assertEqual(before, database.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE))

    def test_canonical_mission_definitions_drive_portfolio_not_generic_missions(self):
        portfolio = load_canonical_bootstrap_portfolio(Path(__file__).parents[1])
        self.assertEqual(tuple(item.identifier for item in portfolio), BOOTSTRAP_MISSION_SEQUENCE)
        self.assertEqual(portfolio[0].title, "Autonomous Engineering Foundation")
        self.assertIn("autonomously executing approved engineering Missions", portfolio[0].statement)
        self.assertNotEqual(portfolio[0].source_digest, portfolio[1].source_digest)

    def test_partial_legacy_history_cannot_resume_and_is_never_rewritten(self):
        with TemporaryDirectory() as directory:
            root, source = Path(directory), UncalledEvidenceSource()
            database = RuntimeDatabase(root)
            seed_retained_legacy_result(database, BOOTSTRAP_MISSION_SEQUENCE[:1])
            before = database.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE)
            database.close()
            for _ in range(2):
                with self.assertRaisesRegex(BootstrapQualificationBlocked, "LEGACY_ASSESSMENT_CONTRACT_MISSING"):
                    run_bootstrap_sequence_qualification(root, source, interrupt_after_host_dispatch=True)
            self.assertEqual(source.calls, [])
            database = RuntimeDatabase(root)
            self.addCleanup(database.close)
            self.assertEqual(before, database.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE))

    def test_json_cache_cannot_authorize_legacy_execution_or_false_pass(self):
        with TemporaryDirectory() as directory:
            root, source = Path(directory), UncalledEvidenceSource()
            cache = root / "bootstrap-sequence-evidence.json"
            cache.write_text(json.dumps({"mission_sequence": list(BOOTSTRAP_MISSION_SEQUENCE),
                "dispatcher_status": "IDLE", "missions": [{"mission_id": identifier,
                "completion_outcome": "COMPLETED", "execution_evidence": {}, "execution_lineage": []}
                for identifier in BOOTSTRAP_MISSION_SEQUENCE]}), encoding="utf-8")
            before = cache.read_bytes()
            with self.assertRaisesRegex(BootstrapQualificationBlocked, "LEGACY_ASSESSMENT_CONTRACT_MISSING"):
                run_bootstrap_sequence_qualification(root, source)
            self.assertEqual(cache.read_bytes(), before)
            self.assertEqual(source.calls, [])


if __name__ == "__main__":
    unittest.main()
