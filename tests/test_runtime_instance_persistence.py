"""Regression coverage for persistent, instance-first Forge runtime recovery."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from forge.runtime import RuntimeBootstrap, RuntimeRecovery, RuntimeResolutionError, RuntimeResolver, repository_identity


class RuntimeInstancePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.runtime_root = self.root / "persistent-runtime"
        self.repository.mkdir()
        self._git("init")
        self._git("config", "user.email", "forge@example.invalid")
        self._git("config", "user.name", "Forge Test")
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "fixture")
        self.addCleanup(self.temporary.cleanup)

    def _git(self, *arguments: str) -> None:
        subprocess.run(("git", "-C", str(self.repository), *arguments), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _open(self):
        return RuntimeBootstrap(self.repository, configured_runtime_root=self.runtime_root, forge_version="test").open()

    def _persist_slice(self, database) -> None:
        database.save_mission_state({"mission_id": "mission-1", "status": "COMPLETED", "progress": {}, "resume": {}, "execution_policy": {"mode": "test"}})
        database.record_architecture_review({"id": "review-1", "mission_id": "mission-1", "input_digest": "truth", "repository_maturity": [], "pressure": {"architecture": "low", "implementation": "low"}, "confidence": "high", "reviewed_at": "2026-08-05T00:00:00Z"})
        database.record_execution_receipt(receipt_id="receipt-1", mission_id="mission-1", execution_host="host", execution_run_id="run", engineering_report_id="report", correlation_identity="correlation", executed_at="2026-08-05T00:00:00Z", outcome="complete")
        database.record_decision_evidence({"id": "decision-1", "decision_type": "planning", "reasoning_summary": "persisted", "evidence_references": [], "alternatives_considered": [], "timestamp": "2026-08-05T00:00:00Z", "mission_context": {"artifact_id": "mission-1"}, "repository_context": {"artifact_id": "truth"}, "confidence": {"architecture_review": {"artifact_id": "review-1"}, "mission_state": {"artifact_id": "mission-1"}}, "execution_receipt_references": [{"artifact_id": "receipt-1"}]})
        database.save_planning_state({"planner_version": "test", "current_queue": [], "pending_engineering_actions": [], "blocked_engineering_actions": [], "execution_policy": {"mode": "test"}, "planner_runtime_metadata": {}})

    def test_identity_persists_across_restart_and_runtime_recovery(self) -> None:
        database = self._open()
        self._persist_slice(database)
        runtime_id = database.runtime_instance.identity.runtime_id
        database.close()
        reopened = self._open()
        self.addCleanup(reopened.close)
        recovered = RuntimeRecovery(reopened).recover()
        self.assertEqual(reopened.runtime_instance.identity.runtime_id, runtime_id)
        self.assertEqual(recovered["runtime_instance"]["runtime_id"], runtime_id)
        self.assertEqual(recovered["mission_state"][0]["mission_id"], "mission-1")
        self.assertEqual(recovered["decision_evidence"][0]["id"], "decision-1")
        self.assertEqual(recovered["execution_receipts"][0]["receipt_id"], "receipt-1")

    def test_first_initialization_claims_one_durable_canonical_instance(self) -> None:
        self._git("config", "forge.repositoryUUID", "fixture-repository-uuid")
        database = RuntimeBootstrap(self.repository, forge_version="test").open()
        self.addCleanup(database.close)
        identity = database.runtime_identity
        resolver = RuntimeResolver(self.repository)
        self.assertEqual(database.path, (self.repository / ".git" / "forge-runtime" / "runtime.db").resolve())
        self.assertEqual(resolver.resolve().path, database.path)
        self.assertEqual(identity.initialization_version, "1")
        self.assertEqual(identity.repository_uuid, "fixture-repository-uuid")
        for table in ("mission_state", "decision_evidence", "architecture_reviews", "mission_recommendations", "execution_receipts", "planning_state", "bootstrap_portfolio_state"):
            self.assertEqual(database._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_existing_claim_wins_over_a_different_configured_location(self) -> None:
        first = self._open()
        runtime_id = first.runtime_identity.runtime_id
        first.close()
        alternate = self.root / "another-runtime" / "runtime.db"
        opened = RuntimeBootstrap(self.repository, configured_location=alternate, forge_version="test").open()
        self.addCleanup(opened.close)
        self.assertEqual(opened.runtime_identity.runtime_id, runtime_id)
        self.assertFalse(alternate.exists())

    def test_runtime_survives_repository_cleanup_and_workspace_relocation(self) -> None:
        database = self._open()
        runtime_id = database.runtime_instance.identity.runtime_id
        database.close()
        shutil.rmtree(self.repository / ".forge", ignore_errors=True)
        relocated = self.root / "relocated-repository"
        shutil.move(str(self.repository), str(relocated))
        self.repository = relocated
        reopened = self._open()
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.runtime_instance.identity.runtime_id, runtime_id)
        self.assertEqual(repository_identity(relocated), repository_identity(self.root / "relocated-repository"))

    def test_branch_transition_resolves_the_same_registered_instance(self) -> None:
        database = self._open()
        runtime_id = database.runtime_instance.identity.runtime_id
        database.close()
        worktree = self.root / "feature-worktree"
        self._git("worktree", "add", "-b", "runtime-instance-test", str(worktree))
        opened = RuntimeBootstrap(worktree, configured_runtime_root=self.runtime_root, forge_version="test").open()
        self.addCleanup(opened.close)
        self.assertEqual(opened.runtime_instance.identity.runtime_id, runtime_id)

    def test_missing_registered_instance_fails_closed_without_replacement(self) -> None:
        database = self._open()
        location = database.path
        database.close()
        location.unlink()
        with self.assertRaisesRegex(RuntimeResolutionError, "location is missing"):
            RuntimeResolver(self.repository, configured_runtime_root=self.runtime_root).resolve()

    def test_multiple_instances_and_registry_identity_mismatch_fail_closed(self) -> None:
        database = self._open()
        database.close()
        duplicate = self.repository / ".forge" / "runtime-copy.db"
        duplicate.parent.mkdir()
        shutil.copy2(self.runtime_root / repository_identity(self.repository) / "runtime.db", duplicate)
        with self.assertRaisesRegex(RuntimeResolutionError, "multiple"):
            RuntimeResolver(self.repository, configured_runtime_root=self.runtime_root).resolve()
        duplicate.unlink()
        registry = RuntimeResolver(self.repository, configured_runtime_root=self.runtime_root).registry_path
        registry.write_text('{"registry_version":"1","runtime_id":"wrong"}', encoding="utf-8")
        with self.assertRaises(RuntimeResolutionError):
            RuntimeResolver(self.repository, configured_runtime_root=self.runtime_root).resolve()


if __name__ == "__main__":
    unittest.main()
