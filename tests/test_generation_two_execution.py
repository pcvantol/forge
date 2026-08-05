"""Regression coverage for Generation 2 operational Mission planning."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.generation_two import intake_portfolio_intelligence_foundation
from forge.generation_two_execution import (
    ACTION_REPOSITORY_TRUTH,
    MISSION_ID,
    PLANNING_DECISION_ID,
    activate_and_plan_portfolio_intelligence,
)
from forge.runtime import RuntimeDatabase


class GenerationTwoExecutionTests(unittest.TestCase):
    def test_active_mission_gets_real_intents_actions_and_only_the_next_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / "missions").mkdir()
            for number in range(1, 6):
                (root / "missions" / f"MISSION-{number:04d}.md").write_text("seed\n", encoding="utf-8")
            database = RuntimeDatabase(root, forge_version="test")
            self.addCleanup(database.close)
            intake_portfolio_intelligence_foundation(database, repository_root=root)

            receipt = activate_and_plan_portfolio_intelligence(database)

            self.assertEqual(receipt.mission_id, MISSION_ID)
            self.assertEqual(receipt.active_action_id, ACTION_REPOSITORY_TRUTH)
            self.assertEqual(len(receipt.engineering_intent_ids), 2)
            self.assertEqual(len(receipt.engineering_action_ids), 3)
            state = database.get_document("mission_state", MISSION_ID)
            self.assertEqual(state["lifecycle"], "ACTIVE")
            self.assertEqual(len(state["engineering_intents"]), 2)
            self.assertEqual(len(state["engineering_actions"]), 3)
            self.assertEqual(state["runtime_prompts"][0]["action_id"], ACTION_REPOSITORY_TRUTH)
            self.assertEqual(database.get_document("decision_evidence", PLANNING_DECISION_ID)["chosen_alternative"], "sequential")
            self.assertEqual(database._connection.execute("SELECT COUNT(*) FROM execution_receipts").fetchone()[0], 0)
            self.assertEqual(activate_and_plan_portfolio_intelligence(database), receipt)


if __name__ == "__main__":
    unittest.main()
