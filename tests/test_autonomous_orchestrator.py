from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.autonomous_orchestrator import AutonomousMissionOrchestrator, ExecutionReceipt
from forge.runtime import RuntimeDatabase


class AutonomousMissionOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory(); root = Path(self.temporary.name)
        (root / "missions").mkdir()
        self.runtime = RuntimeDatabase(root, forge_version="test")
        self.addCleanup(self.runtime.close); self.addCleanup(self.temporary.cleanup)
        self.runtime.save_dispatcher_state(status="ACTIVE", mission_sequence=("MISSION-0007",), active_mission_id="MISSION-0007")
        self.runtime.save_mission_state({"mission_id": "MISSION-0007", "lifecycle": "ACTIVE", "status": "ACTIVE",
            "progress": {"percent_complete": 0}, "resume": {"phase": "orchestration"}, "execution_policy": {"mode": "bounded"},
            "governance": {"business_approval": "approved", "architecture_approval": "approved"},
            "engineering_intents": [{"id": "intent-1", "status": "APPROVED"}],
            "engineering_actions": [{"id": "action-1", "intent_id": "intent-1", "status": "READY", "dependencies": []},
                                   {"id": "action-2", "intent_id": "intent-1", "status": "READY", "dependencies": ["action-1"]}],
            "current_engineering_intent": None, "current_engineering_action": None, "runtime_prompts": [],
            "decision_evidence_ids": [], "execution_receipt_references": []})
        self.orchestrator = AutonomousMissionOrchestrator(self.runtime, timestamp="2026-08-06T08:33:44Z")

    def receipt(self, action: str, outcome: str = "complete") -> ExecutionReceipt:
        return ExecutionReceipt(f"receipt-{action}", action, "engineering-platform", f"run-{action}", f"report-{action}", f"correlation-{action}", "2026-08-06T08:34:00Z", outcome)

    def test_continues_through_receipts_to_completion_with_auditable_iterations(self) -> None:
        first = self.orchestrator.advance("MISSION-0007")
        self.assertEqual((first.state, first.current_action_id, first.iteration_number), ("WAITING_FOR_EXECUTION", "action-1", 1))
        second = self.orchestrator.advance("MISSION-0007", self.receipt("action-1"))
        self.assertEqual((second.current_action_id, second.iteration_number), ("action-2", 2))
        final = self.orchestrator.advance("MISSION-0007", self.receipt("action-2"))
        self.assertEqual(final.state, "COMPLETE")
        state = self.runtime.get_document("mission_state", "MISSION-0007")
        self.assertEqual(len(state["iteration_history"]), 2)
        self.assertEqual(len(state["execution_receipt_references"]), 2)
        projection = self.runtime.runtime_evidence().mission_runtime_projection("MISSION-0007")
        self.assertIsNone(projection["next_executable_engineering_action"])

    def test_governance_is_revalidated_before_each_dispatch(self) -> None:
        state = self.runtime.get_document("mission_state", "MISSION-0007")
        state["governance"]["business_approval"] = "revoked"; self.runtime.save_mission_state(state)
        result = self.orchestrator.advance("MISSION-0007")
        self.assertEqual(result.state, "WAITING_BUSINESS_APPROVAL")
        self.assertIsNone(result.current_action_id)

    def test_failure_pauses_without_selecting_a_later_action(self) -> None:
        self.orchestrator.advance("MISSION-0007")
        result = self.orchestrator.advance("MISSION-0007", self.receipt("action-1", "failed"))
        self.assertEqual(result.state, "WAITING_EXECUTION_FAILURE")
        self.assertEqual(result.current_action_id, "action-1")


if __name__ == "__main__":
    unittest.main()
