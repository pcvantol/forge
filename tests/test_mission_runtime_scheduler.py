from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.mission_scheduler import ExecutionReceipt, MissionRuntimeScheduler, SubmissionAcceptance
from forge.runtime import RuntimeDatabase


class Inbox:
    def __init__(self): self.envelopes = []
    def submit(self, envelope):
        self.envelopes.append(envelope)
        return SubmissionAcceptance(envelope["submission_id"], f"run-{len(self.envelopes)}")


class MissionRuntimeSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); root = Path(self.temp.name); (root / "missions").mkdir()
        self.runtime = RuntimeDatabase(root, forge_version="test"); self.addCleanup(self.runtime.close); self.addCleanup(self.temp.cleanup)
        self.runtime.save_dispatcher_state(status="ACTIVE", mission_sequence=("MISSION-0042",), active_mission_id="MISSION-0042")
        self.runtime.save_mission_state({"mission_id": "MISSION-0042", "mission_title": "Scheduler qualification", "lifecycle": "ACTIVE", "status": "ACTIVE",
            "progress": {"percent_complete": 0}, "resume": {"phase": "scheduler"}, "execution_policy": {"mode": "bounded"},
            "governance": {"business_approval": "approved", "architecture_approval": "approved"},
            "engineering_intents": [{"id": "intent-1", "status": "APPROVED"}],
            "engineering_actions": [{"id": "action-1", "intent_id": "intent-1", "objective": "First safe action", "status": "READY", "dependencies": []},
                {"id": "action-2", "intent_id": "intent-1", "objective": "Second safe action", "status": "READY", "dependencies": ["action-1"]}],
            "current_engineering_intent": None, "current_engineering_action": None, "runtime_prompts": [], "decision_evidence_ids": [], "execution_receipt_references": []})
        self.inbox = Inbox(); self.scheduler = MissionRuntimeScheduler(self.runtime, self.inbox, timestamp="2026-08-08T12:00:00Z")

    def receipt(self, envelope, outcome="COMPLETE"):
        mission = envelope["mission"]
        values = {"receipt_id": f"receipt-{mission['action_id']}", "submission_id": envelope["submission_id"], "run_id": f"run-{len(self.inbox.envelopes)}",
            "mission_id": mission["id"], "intent_id": mission["intent_id"], "action_id": mission["action_id"], "outcome": outcome, "executed_at": "2026-08-08T12:01:00Z"}
        return ExecutionReceipt(**values, integrity=ExecutionReceipt.integrity_for(**values))

    def test_qualification_automatically_dispatches_two_iterations_and_completes(self):
        first = self.scheduler.evaluate("MISSION-0042")
        self.assertEqual(first.state, "WAITING_EXECUTION"); self.assertEqual(len(self.inbox.envelopes), 1)
        self.assertIn("execution_context", self.inbox.envelopes[0]); self.assertEqual(self.inbox.envelopes[0]["execution_context"], self.runtime.execution_context("MISSION-0042"))
        second = self.scheduler.evaluate("MISSION-0042", self.receipt(self.inbox.envelopes[0]))
        self.assertEqual(second.state, "WAITING_EXECUTION"); self.assertEqual(len(self.inbox.envelopes), 2)
        complete = self.scheduler.evaluate("MISSION-0042", self.receipt(self.inbox.envelopes[1]))
        self.assertEqual(complete.state, "COMPLETE")
        self.assertEqual(self.runtime.get_document("mission_state", "MISSION-0042")["lifecycle"], "COMPLETE")
        self.assertEqual(self.runtime.get_document("planning_state", "1")["current_queue"], [])
        self.assertEqual(self.runtime._connection.execute("SELECT COUNT(*) FROM scheduler_submissions").fetchone()[0], 2)

    def test_duplicate_evaluation_and_restart_recover_the_single_outstanding_submission(self):
        first = self.scheduler.evaluate("MISSION-0042")
        again = self.scheduler.evaluate("MISSION-0042")
        restarted = MissionRuntimeScheduler(self.runtime, self.inbox, timestamp="2026-08-08T12:00:01Z").evaluate("MISSION-0042")
        self.assertEqual((again.submission_id, restarted.submission_id), (first.submission_id, first.submission_id))
        self.assertEqual(len(self.inbox.envelopes), 1)

    def test_invalid_receipt_fails_closed_without_next_submission(self):
        self.scheduler.evaluate("MISSION-0042")
        invalid = self.receipt(self.inbox.envelopes[0]); invalid = ExecutionReceipt(**{**invalid.__dict__, "integrity": "sha256:bad"})
        self.assertEqual(self.scheduler.evaluate("MISSION-0042", invalid).state, "WAITING_OPERATOR")
        self.assertEqual(len(self.inbox.envelopes), 1)

    def test_blocked_host_is_retained_without_replacement_work(self):
        self.scheduler.evaluate("MISSION-0042")
        self.assertEqual(self.scheduler.evaluate("MISSION-0042", self.receipt(self.inbox.envelopes[0], "BLOCKED")).state, "BLOCKED")
        self.assertEqual(len(self.inbox.envelopes), 1)

    def test_governance_capability_and_ambiguous_graph_pause(self):
        state = self.runtime.get_document("mission_state", "MISSION-0042"); state["governance"]["business_approval"] = "revoked"; self.runtime.save_mission_state(state)
        self.assertEqual(self.scheduler.evaluate("MISSION-0042").state, "WAITING_GOVERNANCE")
        state["governance"]["business_approval"] = "approved"; state["external_capability_pending"] = True; self.runtime.save_mission_state(state)
        self.assertEqual(self.scheduler.evaluate("MISSION-0042").state, "WAITING_CAPABILITY")


if __name__ == "__main__": unittest.main()
