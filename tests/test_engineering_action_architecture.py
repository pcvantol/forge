"""Architecture consistency tests for the Engineering Action reconciliation."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EngineeringActionArchitectureTests(unittest.TestCase):
    def test_canonical_chain_places_action_between_intent_and_runtime_prompt(self) -> None:
        document = (ROOT / "docs/architecture/engineering-action.md").read_text()
        self.assertIn(
            "Mission\n  ↓ governs\nMission Planner\n  ↓ creates and reconciles\n"
            "Engineering Intent\n  ↓ contains\nEngineering Action",
            document,
        )
        self.assertIn("Engineering Action\n  ↓ produces\nRuntime Prompt", document)

    def test_mission_contains_engineering_intents(self) -> None:
        document = (ROOT / "docs/architecture/engineering-mission.md").read_text()
        self.assertIn("Engineering Intents", document)

    def test_engineering_intent_contains_engineering_actions(self) -> None:
        document = (ROOT / "docs/architecture/engineering-intent.md").read_text()
        self.assertIn("contains one or more Engineering Actions", document)

    def test_runtime_prompt_remains_provider_specific(self) -> None:
        document = (ROOT / "docs/architecture/runtime-prompt-generation.md").read_text()
        self.assertRegex(document, r"provider-specific\s+execution artifact")
        self.assertIn("Engineering Action", document)


if __name__ == "__main__":
    unittest.main()
