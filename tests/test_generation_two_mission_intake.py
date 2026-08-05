"""Regression coverage for the first governed Generation 2 Business Mission."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.generation_two import intake_portfolio_intelligence_foundation
from forge.runtime import RuntimeDatabase


class GenerationTwoMissionIntakeTests(unittest.TestCase):
    def test_allocates_the_first_operational_mission_and_registers_its_lifecycle(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            missions = root / "missions"
            missions.mkdir()
            for number in range(1, 6):
                (missions / f"MISSION-{number:04d}.md").write_text("seed\n", encoding="utf-8")
            database = RuntimeDatabase(root, forge_version="test")
            self.addCleanup(database.close)
            receipt = intake_portfolio_intelligence_foundation(database, repository_root=root)
            self.assertEqual(receipt.mission_id, "MISSION-0006")
            self.assertEqual(receipt.intake_evidence_id, "MISSION-0006-intake-evidence-1")
            self.assertEqual(receipt.lifecycle_state, "registered")
            self.assertEqual((receipt.business_approval_state, receipt.architecture_approval_state), ("approved", "approved"))
            self.assertEqual((receipt.engineering_intent_count, receipt.engineering_action_count, receipt.runtime_prompt_count), (2, 3, 3))
            self.assertEqual(database.get_document("planning_state", "1")["planner_runtime_metadata"]["runtime_prompt_count"], 3)
            lifecycle = [row["lifecycle"] for row in database._connection.execute(
                "SELECT lifecycle FROM mission_lifecycle_events WHERE mission_id = ? ORDER BY sequence", (receipt.mission_id,)
            )]
            self.assertEqual(lifecycle, ["business_review", "business_approved", "architecture_review", "architecture_approved", "registered"])

    def test_allocation_is_idempotent_for_the_canonical_business_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / "missions").mkdir()
            database = RuntimeDatabase(root, forge_version="test")
            self.addCleanup(database.close)
            first = intake_portfolio_intelligence_foundation(database, repository_root=root)
            second = intake_portfolio_intelligence_foundation(database, repository_root=root)
            self.assertEqual(first.mission_id, second.mission_id)
            self.assertEqual(database._connection.execute("SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
