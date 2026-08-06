"""Regression coverage for the persisted operational Mission Runtime view."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.generation_two import intake_portfolio_intelligence_foundation
from forge.generation_two_execution import (
    ACTION_MISSION_CANDIDATES,
    MISSION_ID,
    activate_and_plan_portfolio_intelligence,
)
from forge.runtime import RuntimeDatabase, RuntimeDatabaseError


class MissionRuntimeProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "missions").mkdir()
        for number in range(1, 6):
            (self.root / "missions" / f"MISSION-{number:04d}.md").write_text("seed\n", encoding="utf-8")
        self.database = RuntimeDatabase(self.root, forge_version="test")
        self.addCleanup(self.database.close)
        self.addCleanup(self.temporary.cleanup)
        intake_portfolio_intelligence_foundation(self.database, repository_root=self.root)
        activate_and_plan_portfolio_intelligence(self.database)

    def test_reconciles_and_persists_exactly_one_operational_action(self) -> None:
        projection = self.database.runtime_evidence().mission_runtime_projection(MISSION_ID)
        self.assertEqual(projection["next_executable_engineering_action"]["id"], "MISSION-0006-action-repository-truth")
        self.assertEqual(projection["approved_mission_queue"], [MISSION_ID])
        self.assertEqual(projection["completed_engineering_actions"], [])
        self.assertEqual(len(projection["decision_evidence_references"]), 1)
        self.assertEqual(projection["intake_evidence_references"][0]["artifact_id"], "MISSION-0006-intake-evidence-1")
        self.assertEqual(self.database.runtime_evidence().persisted_mission_runtime_projection(MISSION_ID), projection)

    def test_fails_closed_when_multiple_actions_are_executable(self) -> None:
        state = self.database.get_document("mission_state", MISSION_ID)
        state["engineering_actions"][1]["dependencies"] = []
        state["engineering_actions"][1]["status"] = "READY"
        self.database.save_mission_state(state)
        with self.assertRaisesRegex(RuntimeDatabaseError, "exactly one executable"):
            self.database.runtime_evidence().mission_runtime_projection(MISSION_ID)

    def test_runtime_projection_tracks_the_final_action_after_prior_actions_complete(self) -> None:
        state = self.database.get_document("mission_state", MISSION_ID)
        for action in state["engineering_actions"][:2]:
            action["status"] = "COMPLETED"
        state["current_engineering_action"] = state["engineering_actions"][2]
        state["current_engineering_intent"] = state["engineering_intents"][1]
        state["progress"] = {"percent_complete": 66, "completed_engineering_intents": 1,
                             "remaining_engineering_intents": 1, "completed_engineering_actions": 2,
                             "remaining_engineering_actions": 1}
        state["runtime_prompts"] = [{"id": "codex-cli-runtime-prompt:final", "action_id": ACTION_MISSION_CANDIDATES,
                                     "intent_id": state["current_engineering_intent"]["id"], "status": "READY_FOR_ENGINEERING_PLATFORM"}]
        self.database.save_mission_state(state)
        planning = self.database.get_document("planning_state", "1")
        planning["pending_engineering_actions"] = [ACTION_MISSION_CANDIDATES]
        self.database.save_planning_state(planning)
        projection = self.database.runtime_evidence().mission_runtime_projection(MISSION_ID)
        self.assertEqual(projection["next_executable_engineering_action"]["id"], ACTION_MISSION_CANDIDATES)
        self.assertEqual(len(projection["completed_engineering_actions"]), 2)

    def test_completed_mission_projects_no_further_engineering_action(self) -> None:
        state = self.database.get_document("mission_state", MISSION_ID)
        for action in state["engineering_actions"]:
            action["status"] = "COMPLETED"
        for intent in state["engineering_intents"]:
            intent["status"] = "COMPLETED"
        state.update({"lifecycle": "COMPLETE", "status": "COMPLETE", "current_engineering_action": None,
                      "current_engineering_intent": None, "runtime_prompts": [],
                      "progress": {"percent_complete": 100, "completed_engineering_intents": 2,
                                   "remaining_engineering_intents": 0, "completed_engineering_actions": 3,
                                   "remaining_engineering_actions": 0}})
        self.database.save_mission_state(state)
        planning = self.database.get_document("planning_state", "1")
        planning.update({"current_queue": [], "pending_engineering_actions": []})
        self.database.save_planning_state(planning)
        self.database.save_dispatcher_state(status="IDLE", mission_sequence=(MISSION_ID,))
        projection = self.database.runtime_evidence().mission_runtime_projection(MISSION_ID)
        self.assertIsNone(projection["next_executable_engineering_action"])
        self.assertEqual(len(projection["remaining_engineering_actions"]), 0)


if __name__ == "__main__":
    unittest.main()
