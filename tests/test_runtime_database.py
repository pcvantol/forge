"""Regression coverage for the Forge Runtime Database Foundation."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from forge.runtime import RUNTIME_SCHEMA_VERSION, RuntimeDatabase, RuntimeIntegrityError, RuntimeResolver


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
        self.assertEqual(self.database.path, RuntimeResolver(self.root).default_location)
        self.assertTrue(self.database.path.exists())
        self.assertEqual(self.database.metadata["schema_version"], str(RUNTIME_SCHEMA_VERSION))
        self.database.validate_integrity()

    def test_insert_only_mission_state_creation_never_overwrites(self) -> None:
        self.database.create_mission_state(self._mission())
        conflicting = self._mission(); conflicting["status"] = "ACTIVE"
        with self.assertRaisesRegex(Exception, "already exists"):
            self.database.create_mission_state(conflicting)
        self.assertEqual(self.database.get_document("mission_state", "mission-1")["status"], "READY")

    def test_mission_review_recommendation_decision_and_execution_receipt_persist(self) -> None:
        self.database.save_mission_state(self._mission())
        self.database.record_architecture_review(self._review())
        recommendation = {"id": "recommendation-1", "architecture_review_id": "review-1", "priority": "high", "confidence": {"score": 80}, "dependencies": {}, "required_disciplines": ["engineering"], "recommendation_timestamp": "2026-08-04T00:00:00Z", "origin": "maintenance", "recommendation_source": "repository_truth", "repository_evidence": [{"id": "truth", "revision": "abc", "locator": "repository://truth", "content_digest": "sha256:truth"}], "decision_evidence_references": ["decision-1"]}
        self.database.record_mission_recommendation(recommendation, mission_id="mission-1")
        self.database.record_execution_receipt(receipt_id="execution-1", mission_id="mission-1", execution_host="engineering-platform", execution_run_id="run-1", engineering_report_id="report-1", correlation_identity="correlation-1", executed_at="2026-08-04T00:00:00Z", outcome="complete")
        decision = {"id": "decision-1", "decision_type": "mission_planning", "mission_context": {"artifact_id": "mission-1"}, "repository_context": {"artifact_id": "repository-truth-1"}, "reasoning_summary": "bounded", "evidence_references": [], "alternatives_considered": [], "confidence": {"score": 80, "architecture_review": {"artifact_id": "review-1"}, "mission_state": {"artifact_id": "mission-1"}}, "execution_receipt_references": [{"artifact_id": "execution-1"}], "timestamp": "2026-08-04T00:00:00Z"}
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
            self.database.record_execution_receipt(receipt_id="bad", mission_id="missing", execution_host="host", execution_run_id="run", engineering_report_id="report", correlation_identity="correlation", executed_at="now", outcome="failed")

    def test_newer_schema_and_missing_metadata_are_rejected(self) -> None:
        self.database.close()
        connection = sqlite3.connect(self.database.path)
        connection.execute("PRAGMA user_version=99")
        connection.commit(); connection.close()
        with self.assertRaises(RuntimeIntegrityError):
            RuntimeDatabase(self.root)

    def test_version_three_execution_references_migrate_to_immutable_receipts(self) -> None:
        self.database.close()
        connection = sqlite3.connect(self.database.path)
        connection.execute("DROP TRIGGER execution_receipts_immutable_update")
        connection.execute("DROP TRIGGER execution_receipts_immutable_delete")
        connection.execute("DROP TABLE execution_receipts")
        connection.execute("CREATE TABLE execution_references (reference_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, execution_host TEXT NOT NULL, execution_run_id TEXT NOT NULL, correlation TEXT NOT NULL, executed_at TEXT NOT NULL, outcome TEXT NOT NULL, FOREIGN KEY (mission_id) REFERENCES mission_state(mission_id), UNIQUE (execution_host, execution_run_id, correlation))")
        connection.execute("ALTER TABLE decision_evidence RENAME COLUMN execution_receipts TO execution_references")
        connection.execute("UPDATE runtime_metadata SET value='3' WHERE key IN ('schema_version', 'migration_version', 'last_migration')")
        connection.execute("PRAGMA user_version=3")
        connection.commit(); connection.close()
        self.database = RuntimeDatabase(self.root, forge_version="test")
        tables = {row[0] for row in self.database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("execution_receipts", tables)
        self.assertNotIn("execution_references", tables)
        self.database.validate_integrity()

    def test_decision_requires_a_persisted_execution_receipt(self) -> None:
        self.database.save_mission_state(self._mission())
        self.database.record_architecture_review(self._review())
        decision = {"id": "decision-1", "decision_type": "mission_planning", "reasoning_summary": "bounded", "evidence_references": [], "alternatives_considered": [], "timestamp": "2026-08-04T00:00:00Z", "mission_context": {"artifact_id": "mission-1"}, "repository_context": {"artifact_id": "repository-truth-1"},
                    "confidence": {"architecture_review": {"artifact_id": "review-1"}, "mission_state": {"artifact_id": "mission-1"}},
                    "execution_receipt_references": [{"artifact_id": "missing"}]}
        with self.assertRaisesRegex(Exception, "execution receipt"):
            self.database.record_decision_evidence(decision)

    def test_planning_state_is_durable_and_required_fields_fail_closed(self) -> None:
        state = {"planner_version": "1", "current_queue": ["mission-1"], "pending_engineering_actions": ["action-1"], "blocked_engineering_actions": [], "execution_policy": {"mode": "local"}, "planner_runtime_metadata": {"revision": 1}}
        self.database.save_planning_state(state)
        self.assertEqual(self.database.get_document("planning_state", "1"), state)
        with self.assertRaises(RuntimeError):
            self.database.save_planning_state({"planner_version": "1"})

    def test_action_derivation_is_durable_idempotent_and_mission_scoped(self) -> None:
        self.database.save_mission_state(self._mission())
        record = {"derivation_id": "derivation-1", "mission_id": "mission-1", "snapshot_digest": "sha256:snapshot",
                  "contract_version": "1.0", "provider_configuration": "fixture-v1", "lifecycle": "SNAPSHOT_CREATED"}
        self.database.save_action_derivation(record)
        self.database.close()
        self.database = RuntimeDatabase(self.root, forge_version="test")
        self.assertEqual(self.database.get_document("action_derivations", "derivation-1"), record)
        self.database.save_action_derivation({**record, "lifecycle": "MATERIALIZED"})
        with self.assertRaisesRegex(RuntimeError, "identical action derivation"):
            self.database.save_action_derivation({**record, "derivation_id": "other"})

    def test_token_preflight_receipt_is_immutable_durable_and_single_use(self) -> None:
        self.database.save_mission_state(self._mission())
        receipt = {"receipt_id": "preflight-1", "mission_id": "mission-1", "main_head": "a" * 40,
                   "policy_digest": "sha256:policy", "request_digest": "sha256:request",
                   "evidence_digest": "sha256:evidence", "effective_contract_digest": "sha256:contract",
                   "provider_id": "provider", "input_tokens": 10, "input_token_bound": 20,
                   "context_token_bound": 30, "output_token_bound": 15,
                   "context_with_requested_output": 25, "result": "PASS", "created_at": "2026-09-05T00:00:00Z"}
        self.database.create_token_preflight_receipt(receipt)
        self.database.close(); self.database = RuntimeDatabase(self.root, forge_version="test")
        boundary = {key: receipt[key] for key in ("main_head", "policy_digest", "request_digest", "evidence_digest", "effective_contract_digest")}
        self.assertEqual(self.database.consume_token_preflight_receipt("preflight-1", boundary), receipt)
        with self.assertRaises(RuntimeIntegrityError):
            self.database.consume_token_preflight_receipt("preflight-1", boundary)
        with self.assertRaises(sqlite3.IntegrityError):
            self.database._connection.execute("UPDATE token_preflight_receipts SET result='FAIL' WHERE receipt_id='preflight-1'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database._connection.execute(
                "INSERT INTO token_preflight_receipts SELECT 'forged', mission_id, main_head, policy_digest, request_digest, evidence_digest, effective_contract_digest, provider_id, input_tokens, input_token_bound, context_token_bound, output_token_bound, context_with_requested_output, result, created_at, document FROM token_preflight_receipts WHERE receipt_id='preflight-1'"
            )
        with self.assertRaises(RuntimeIntegrityError):
            self.database.create_token_preflight_receipt({**receipt, "input_tokens": 11})
        with self.assertRaises(RuntimeIntegrityError):
            self.database.consume_token_preflight_receipt("preflight-1", {**boundary, "request_digest": "sha256:other"})
        with self.assertRaises(sqlite3.IntegrityError):
            self.database._connection.execute("DELETE FROM token_preflight_receipt_consumptions WHERE receipt_id='preflight-1'")
        with self.assertRaisesRegex(RuntimeError, "secret material"):
            self.database.create_token_preflight_receipt({**receipt, "receipt_id": "secret", "api_key": "forbidden"})

    def test_schema26_migrates_token_preflight_receipts_before_restart(self) -> None:
        self.database.close()
        connection = sqlite3.connect(self.database.path)
        for trigger in ("token_preflight_receipts_authorized_insert", "token_preflight_receipts_immutable_update", "token_preflight_receipts_immutable_delete",
                        "token_preflight_receipt_consumptions_immutable_update", "token_preflight_receipt_consumptions_immutable_delete"):
            connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute("DROP TABLE token_preflight_receipt_consumptions")
        connection.execute("DROP TABLE token_preflight_receipts")
        connection.execute("UPDATE runtime_metadata SET value='26' WHERE key IN ('schema_version','migration_version','last_migration')")
        connection.execute("PRAGMA user_version=26")
        connection.commit(); connection.close()
        self.database = RuntimeDatabase(self.root, forge_version="test")
        self.assertEqual(self.database.metadata["schema_version"], str(RUNTIME_SCHEMA_VERSION))
        self.assertTrue(self.database._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='token_preflight_receipts'"
        ).fetchone())

    def test_token_preflight_failure_is_immutable_secret_free_and_migrated(self) -> None:
        self.database.save_mission_state(self._mission())
        failure = {"failure_id": "token-preflight-failure-00000000-0000-0000-0000-000000000001", "mission_id": "mission-1", "provider_id": "provider",
                   "occurred_at": "2026-09-06T00:00:00Z", "main_head": "a" * 40, "policy_digest": "sha256:" + "b" * 64,
                   "request_digest": "sha256:" + "c" * 64, "evidence_digest": "sha256:" + "d" * 64,
                   "effective_contract_digest": "sha256:" + "e" * 64, "layer": "PROVIDER_AVAILABILITY",
                   "status": 400, "provider_type": "invalid_request_error", "provider_code": "invalid_schema"}
        self.database.record_token_preflight_failure(failure)
        with self.assertRaises(sqlite3.IntegrityError):
            self.database._connection.execute("UPDATE token_preflight_failures SET provider_id='other' WHERE failure_id=?", (failure["failure_id"],))
        with self.assertRaises(RuntimeError):
            self.database.record_token_preflight_failure({**failure, "failure_id": "failure-2", "secret": "forbidden"})
        with self.assertRaisesRegex(RuntimeError, "unsupported diagnostic fields"):
            self.database.record_token_preflight_failure({**failure, "failure_id": "token-preflight-failure-00000000-0000-0000-0000-000000000002", "payload": "untrusted"})
        with self.assertRaisesRegex(RuntimeError, "not allow-listed"):
            self.database.record_token_preflight_failure({**failure, "failure_id": "token-preflight-failure-00000000-0000-0000-0000-000000000003", "provider_code": "sk-proj-secret"})
        self.database.close()
        self.database = RuntimeDatabase(self.root, forge_version="test")
        self.assertTrue(self.database._connection.execute("SELECT 1 FROM token_preflight_failures WHERE failure_id=?", (failure["failure_id"],)).fetchone())

    def test_schema27_migrates_bounded_token_preflight_failures_before_restart(self) -> None:
        self.database.close()
        connection = sqlite3.connect(self.database.path)
        for trigger in ("token_preflight_failures_authorized_insert", "token_preflight_failures_immutable_update",
                        "token_preflight_failures_immutable_delete"):
            connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute("DROP TABLE token_preflight_failures")
        connection.execute("UPDATE runtime_metadata SET value='27' WHERE key IN ('schema_version','migration_version','last_migration')")
        connection.execute("PRAGMA user_version=27")
        connection.commit(); connection.close()
        self.database = RuntimeDatabase(self.root, forge_version="test")
        self.assertEqual(self.database.metadata["schema_version"], str(RUNTIME_SCHEMA_VERSION))
        self.assertTrue(self.database._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='token_preflight_failures'"
        ).fetchone())

    def test_execution_receipts_are_immutable(self) -> None:
        self.database.save_mission_state(self._mission())
        self.database.record_execution_receipt(receipt_id="receipt-1", mission_id="mission-1", execution_host="host", execution_run_id="run", engineering_report_id="report", correlation_identity="correlation", executed_at="2026-08-04T00:00:00Z", outcome="complete")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database._connection.execute("UPDATE execution_receipts SET outcome='failed' WHERE receipt_id='receipt-1'")

    def test_delegation_request_is_durable_and_mission_scoped(self) -> None:
        self.database.save_mission_state(self._mission())
        request = {"id": "delegation-1", "mission_id": "mission-1", "action_id": "action-1", "capability_id": "review",
                   "provider": "human", "approval_state": "pending", "result_state": "pending",
                   "requested_at": "2026-08-04T00:00:00Z"}
        self.database.record_delegation_request(request)
        self.assertEqual(self.database.get_document("delegation_requests", "delegation-1")["action_id"], "action-1")

    def test_integration_evidence_is_durable_immutable_and_receipt_bound(self) -> None:
        self.database.save_mission_state(self._mission())
        self.database.record_execution_receipt(receipt_id="receipt-1", mission_id="mission-1", execution_host="host", execution_run_id="run", engineering_report_id="report", correlation_identity="correlation", executed_at="now", outcome="complete")
        evidence = {"id": "integration-1", "mission_id": "mission-1", "outcome": "complete", "merge_result": "merge_ready", "timestamp": "now", "content_digest": "sha256:integration", "execution_receipt_references": ["receipt-1"]}
        self.database.record_integration_evidence(evidence)
        self.assertEqual(self.database.get_document("integration_evidence", "integration-1")["id"], "integration-1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database._connection.execute("UPDATE integration_evidence SET outcome='blocked' WHERE integration_id='integration-1'")


if __name__ == "__main__":
    unittest.main()
