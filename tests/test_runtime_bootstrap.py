"""Regression coverage for Runtime Database bootstrap, resolution and recovery."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from forge.runtime import (
    RuntimeBootstrap,
    RuntimeRecovery,
    RuntimeResolutionError,
    RuntimeResolver,
)


class RuntimeBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def _database(self):
        database = RuntimeBootstrap(self.root, forge_version="test").open()
        self.addCleanup(database.close)
        return database

    def _persist_complete_runtime_slice(self, database) -> None:
        database.save_mission_state({"mission_id": "mission-1", "status": "COMPLETED", "progress": {}, "resume": {}, "execution_policy": {"mode": "test"}, "completion": {"success": True}})
        database.record_architecture_review({"id": "review-1", "mission_id": "mission-1", "input_digest": "truth", "repository_maturity": [], "pressure": {"architecture": "low", "implementation": "low"}, "confidence": "high", "reviewed_at": "2026-08-04T00:00:00Z"})
        database.record_execution_receipt(receipt_id="receipt-1", mission_id="mission-1", execution_host="host", execution_run_id="run", engineering_report_id="report", correlation_identity="correlation", executed_at="2026-08-04T00:00:00Z", outcome="complete")
        database.record_decision_evidence({"id": "decision-1", "decision_type": "planning", "reasoning_summary": "runtime-only", "evidence_references": [], "alternatives_considered": [], "timestamp": "2026-08-04T00:00:00Z", "mission_context": {"artifact_id": "mission-1"}, "repository_context": {"artifact_id": "truth"}, "confidence": {"architecture_review": {"artifact_id": "review-1"}, "mission_state": {"artifact_id": "mission-1"}}, "execution_receipt_references": [{"artifact_id": "receipt-1"}]})
        database.save_planning_state({"planner_version": "test", "current_queue": [], "pending_engineering_actions": [], "blocked_engineering_actions": [], "execution_policy": {"mode": "test"}, "planner_runtime_metadata": {}})

    def test_bootstrap_creates_identity_and_resolves_registered_runtime(self) -> None:
        database = self._database()
        identity = database.runtime_identity
        self.assertTrue(identity.runtime_id.startswith("forge-runtime-"))
        self.assertTrue(identity.repository_identity.startswith("forge-repository-"))
        self.assertEqual(identity.database_location, str(database.path.resolve()))
        self.assertEqual(RuntimeResolver(self.root).resolve().path, database.path.resolve())

    def test_configured_location_bootstraps_and_becomes_canonical(self) -> None:
        configured = self.root / "durable-runtime" / "forge.db"
        database = RuntimeBootstrap(self.root, configured_location=configured, forge_version="test").open()
        self.addCleanup(database.close)
        self.assertEqual(database.path, configured.resolve())
        self.assertEqual(RuntimeResolver(self.root).resolve().path, configured.resolve())

    def test_runtime_identity_is_immutable(self) -> None:
        database = self._database()
        with self.assertRaises(sqlite3.IntegrityError):
            database._connection.execute("UPDATE runtime_metadata SET value = 'other' WHERE key = 'runtime_id'")
        with self.assertRaises(sqlite3.IntegrityError):
            database._connection.execute("UPDATE runtime_metadata SET value = 'other' WHERE key = 'initialization_version'")

    def test_recovery_reads_only_persisted_runtime_records_after_restart(self) -> None:
        database = self._database()
        self._persist_complete_runtime_slice(database)
        identity = database.runtime_identity
        database.close()
        recovered_database = RuntimeBootstrap(self.root, forge_version="test").open()
        self.addCleanup(recovered_database.close)
        recovered = RuntimeRecovery(recovered_database).recover()
        self.assertEqual(recovered["runtime_identity"]["runtime_id"], identity.runtime_id)
        self.assertEqual(recovered["mission_state"][0]["mission_id"], "mission-1")
        self.assertEqual(recovered["execution_receipts"][0]["receipt_id"], "receipt-1")
        self.assertEqual(recovered["planning_state"]["planner_version"], "test")
        self.assertEqual(recovered["source"], "runtime_instance")

    def test_multiple_runtime_candidates_fail_closed(self) -> None:
        database = self._database()
        database.close()
        duplicate = self.root / ".forge" / "duplicate" / "runtime-copy.db"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_bytes(database.path.read_bytes())
        with self.assertRaises(RuntimeResolutionError):
            RuntimeResolver(self.root).resolve()

    def test_relocation_preserves_runtime_identity_and_recovers_records(self) -> None:
        database = self._database()
        self._persist_complete_runtime_slice(database)
        identity = database.runtime_identity.runtime_id
        database.close()
        destination = self.root / "runtime-store" / "canonical.db"
        location = RuntimeResolver(self.root).relocate(destination)
        self.assertEqual(location.path, destination.resolve())
        recovered = RuntimeBootstrap(self.root, forge_version="test").open()
        self.addCleanup(recovered.close)
        self.assertEqual(recovered.runtime_identity.runtime_id, identity)
        self.assertEqual(RuntimeRecovery(recovered).recover()["execution_receipts"][0]["receipt_id"], "receipt-1")


if __name__ == "__main__":
    unittest.main()
