"""Regression coverage for immutable, read-only Execution Context."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.generation_two import intake_portfolio_intelligence_foundation
from forge.generation_two_execution import MISSION_ID, activate_and_plan_portfolio_intelligence
from forge.runtime import RuntimeDatabase
from forge.runtime.execution_context import project_execution_context


class ExecutionContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        (root / "missions").mkdir()
        for number in range(1, 6):
            (root / "missions" / f"MISSION-{number:04d}.md").write_text("seed\n", encoding="utf-8")
        self.database = RuntimeDatabase(root, forge_version="test")
        self.addCleanup(self.database.close)
        self.addCleanup(self.temporary.cleanup)
        intake_portfolio_intelligence_foundation(self.database, repository_root=root)
        activate_and_plan_portfolio_intelligence(self.database)

    def test_reconciliation_appends_a_compact_context_without_prompt_or_reasoning(self) -> None:
        evidence = self.database.runtime_evidence()
        evidence.mission_runtime_projection(MISSION_ID)
        context = evidence.execution_context_api().get(MISSION_ID)
        self.assertEqual(context["context_id"], "execution-context:MISSION-0006:1")
        self.assertEqual(context["execution_phase"], "Engineering")
        self.assertEqual(context["mission_lifecycle"], "Active")
        self.assertEqual(context["mission_recommendation_status"], "MISSION_ALLOCATED")
        self.assertEqual(context["running_intents"][0]["id"], "MISSION-0006-intent-repository-runtime-evidence")
        self.assertEqual(context["current_engineering_action"]["id"], "MISSION-0006-action-repository-truth")
        self.assertEqual(context["context_schema_version"], "1")
        self.assertNotIn("runtime_prompts", context)
        self.assertNotIn("reasoning_summary", context)
        self.assertNotIn("prompt", repr(context).lower())

    def test_lifecycle_projection_uses_the_canonical_operator_vocabulary(self) -> None:
        values = {
            "RECOMMENDATION": "Recommendation", "BUSINESS_REVIEW": "Business Review",
            "ARCHITECTURE_REVIEW": "Architecture Review", "MISSION_CANDIDATE": "Mission Candidate",
            "REGISTERED": "Allocated", "ACTIVE": "Active", "PAUSED": "Paused",
            "WAITING_FOR_GOVERNANCE": "Waiting For Governance", "WAITING_FOR_RECEIPT": "Waiting For Receipt",
            "COMPLETE": "Mission Complete", "EXECUTION_COMPLETE": "Execution Complete",
        }
        for source, expected in values.items():
            context = project_execution_context(
                state={"lifecycle": source, "status": source},
                projection={"mission_id": MISSION_ID, "execution_receipts": ()}, context_version=1,
            )
            self.assertEqual(context["mission_lifecycle"], expected)

    def test_identical_reconciled_runtime_input_has_a_deterministic_context(self) -> None:
        state = {"lifecycle": "ACTIVE", "status": "ACTIVE", "mission_title": "Stable Mission"}
        projection = {"mission_id": MISSION_ID, "execution_receipts": (), "completed_intents": ()}
        self.assertEqual(
            project_execution_context(state=state, projection=projection, context_version=7),
            project_execution_context(state=state, projection=projection, context_version=7),
        )

    def test_completion_context_includes_only_compact_final_runtime_evidence(self) -> None:
        context = project_execution_context(
            state={"lifecycle": "COMPLETE", "status": "COMPLETE", "completion_timestamp": "2026-08-06T00:00:00Z",
                   "mission_completion_summary": "The approved Mission is complete."},
            projection={"mission_id": MISSION_ID, "execution_receipts": (), "remaining_engineering_actions": ()},
            context_version=1,
        )
        self.assertEqual(context["mission_completion_summary"], "The approved Mission is complete.")
        self.assertEqual(context["completion_timestamp"], "2026-08-06T00:00:00Z")
        self.assertEqual(context["final_runtime_state"]["mission_lifecycle"], "Mission Complete")

    def test_context_history_is_immutable_and_versioned_per_reconciliation(self) -> None:
        evidence = self.database.runtime_evidence()
        evidence.mission_runtime_projection(MISSION_ID)
        evidence.mission_runtime_projection(MISSION_ID)
        history = evidence.execution_context_history(MISSION_ID)
        self.assertEqual([item["context_version"] for item in history], [1, 2])
        with self.assertRaises(Exception):
            self.database._connection.execute(
                "UPDATE execution_context_snapshots SET document = '{}' WHERE context_id = ?", (history[0]["context_id"],)
            )

    def test_schema_thirteen_migrates_to_the_immutable_context_history(self) -> None:
        path = self.database.path
        self.database._connection.execute("DROP TABLE execution_context_snapshots")
        self.database._connection.execute("PRAGMA user_version=13")
        self.database._connection.execute("UPDATE runtime_metadata SET value = '13' WHERE key IN ('schema_version', 'migration_version', 'last_migration')")
        self.database._connection.commit()
        self.database.close()
        self.database = RuntimeDatabase(self.database.repository_root, path=path, forge_version="test")
        self.assertEqual(self.database.metadata["schema_version"], "21")
        self.assertIn("execution_context_snapshots", {
            row["name"] for row in self.database._connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        })


if __name__ == "__main__":
    unittest.main()
