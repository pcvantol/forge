"""Regression tests for durable, restart-safe Mission execution state."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.intent import EngineeringIntent, IntentCategory, IntentReference, IntentTraceability
from forge.models.mission import EngineeringMission, MissionIntentMembership, MissionScope
from forge.state import MissionExecutionStatus, MissionStateStore, MissionStateStoreError
from forge.runtime import RuntimeDatabase


def mission() -> EngineeringMission:
    return EngineeringMission(
        "mission-1", "1", "Mission state", "Persist one Mission safely.",
        MissionScope(("Mission state",), ("Mission Runner",)),
        (MissionIntentMembership(1, "intent-1", "1"),),
    )


def intent() -> EngineeringIntent:
    reference = IntentReference("source", "1", "docs/source.md")
    return EngineeringIntent(
        "intent-1", "1", "State store", "Persist Mission state.", IntentCategory.IMPLEMENTATION,
        IntentTraceability((reference,), (reference,), (reference,), (reference,), (reference,)),
    )


def action(status: EngineeringActionStatus = EngineeringActionStatus.READY) -> EngineeringAction:
    return EngineeringAction(1, "action-1", "intent-1", "1", "Persist the Mission.", ("state evidence",), status=status)


class MissionStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name); self.runtime = RuntimeDatabase(self.root)
        self.store = MissionStateStore(self.runtime)

    def tearDown(self) -> None:
        self.runtime.close()
        self.directory.cleanup()

    def create(self) -> None:
        self.store.create(mission(), (intent(),), (action(),), occurred_at="2026-08-01T20:00:00Z", resume={"next_action_id": "action-1"})

    def advance_to_waiting_evidence(self) -> None:
        self.create()
        self.store.transition("mission-1", MissionExecutionStatus.READY, occurred_at="2026-08-01T20:01:00Z", reason="planned")
        self.store.transition("mission-1", MissionExecutionStatus.ACTIVE, occurred_at="2026-08-01T20:02:00Z", reason="started")
        self.store.transition("mission-1", MissionExecutionStatus.WAITING_FOR_EXECUTION, occurred_at="2026-08-01T20:03:00Z", reason="action released")
        self.store.transition(
            "mission-1", MissionExecutionStatus.WAITING_FOR_EVIDENCE, occurred_at="2026-08-01T20:04:00Z", reason="host acknowledged",
            execution_correlation={"correlation_id": "correlation-1", "host_run_id": "run-1", "action_id": "action-1"},
        )

    def test_creation_persists_pinned_work_and_initial_history(self) -> None:
        self.create()
        state = self.store.get("mission-1")
        self.assertEqual(state.status, MissionExecutionStatus.CREATED)
        self.assertEqual(state.mission["id"], "mission-1")
        self.assertEqual(state.intents[0]["revision"], "1")
        self.assertEqual(state.actions[0]["id"], "action-1")
        self.assertEqual(state.resume["next_action_id"], "action-1")
        self.assertEqual([entry.to_status for entry in self.store.history("mission-1")], [MissionExecutionStatus.CREATED])
        with self.assertRaisesRegex(MissionStateStoreError, "already exists"):
            self.create()

    def test_store_requires_a_runtime_database_not_a_path_or_connection(self) -> None:
        with self.assertRaisesRegex(TypeError, "canonical RuntimeDatabase"):
            MissionStateStore(self.root / "standalone-mission-state.sqlite")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "canonical RuntimeDatabase"):
            MissionStateStore(self.runtime._connection)  # type: ignore[arg-type]  # noqa: SLF001

    def test_store_rejects_an_alternate_runtime_database(self) -> None:
        alternate = RuntimeDatabase(self.root, path=self.root / "alternate-runtime.db")
        try:
            with self.assertRaisesRegex(ValueError, "resolved canonical RuntimeDatabase"):
                MissionStateStore(alternate)
        finally:
            alternate.close()

    def test_transitions_are_closed_and_persist_every_step(self) -> None:
        self.create()
        with self.assertRaisesRegex(MissionStateStoreError, "not permitted"):
            self.store.transition("mission-1", MissionExecutionStatus.COMPLETED, occurred_at="2026-08-01T20:01:00Z", reason="skip")
        self.store.transition("mission-1", MissionExecutionStatus.READY, occurred_at="2026-08-01T20:01:00Z", reason="planned")
        self.store.transition("mission-1", MissionExecutionStatus.ACTIVE, occurred_at="2026-08-01T20:02:00Z", reason="started")
        self.store.transition("mission-1", MissionExecutionStatus.WAITING_FOR_EXECUTION, occurred_at="2026-08-01T20:03:00Z", reason="released")
        state = self.store.transition("mission-1", MissionExecutionStatus.WAITING_FOR_EVIDENCE, occurred_at="2026-08-01T20:04:00Z", reason="dispatched")
        self.assertEqual(state.revision, 5)
        self.assertEqual(len(self.store.history("mission-1")), 5)

    def test_restart_and_resume_use_persisted_state_not_process_memory(self) -> None:
        self.advance_to_waiting_evidence()
        self.store.close()
        self.runtime = RuntimeDatabase(self.root); self.store = MissionStateStore(self.runtime)
        state = self.store.resumable()[0]
        self.assertEqual(state.status, MissionExecutionStatus.WAITING_FOR_EVIDENCE)
        self.assertEqual(state.execution_correlation["host_run_id"], "run-1")  # type: ignore[index]
        self.assertEqual(state.actions[0]["id"], "action-1")

    def test_execution_policy_pause_and_approval_are_persisted(self) -> None:
        self.create()
        self.store.set_execution_policy("mission-1", {"schema_version": "1.0", "kind": "engineering_action_review", "custom_boundaries": []}, occurred_at="2026-08-01T20:00:30Z")
        self.store.transition("mission-1", MissionExecutionStatus.READY, occurred_at="2026-08-01T20:01:00Z", reason="planned")
        self.store.transition("mission-1", MissionExecutionStatus.ACTIVE, occurred_at="2026-08-01T20:02:00Z", reason="started")
        self.store.transition("mission-1", MissionExecutionStatus.WAITING_FOR_EXECUTION, occurred_at="2026-08-01T20:03:00Z", reason="released")
        self.store.transition("mission-1", MissionExecutionStatus.WAITING_FOR_EVIDENCE, occurred_at="2026-08-01T20:04:00Z", reason="acknowledged")
        paused = self.store.transition("mission-1", MissionExecutionStatus.AWAITING_APPROVAL, occurred_at="2026-08-01T20:05:00Z", reason="execution_policy_pause", pause_reason={"boundary": "engineering_action"})
        self.assertEqual(paused.execution_policy["kind"], "engineering_action_review")  # type: ignore[index]
        self.runtime.close(); self.runtime = RuntimeDatabase(self.root); self.store = MissionStateStore(self.runtime)
        restarted = self.store.get("mission-1")
        self.assertEqual(restarted.status, MissionExecutionStatus.AWAITING_APPROVAL)
        self.assertEqual(restarted.pause_reason["boundary"], "engineering_action")  # type: ignore[index]

    def test_blocked_and_failed_missions_recover_only_through_explicit_transition(self) -> None:
        self.advance_to_waiting_evidence()
        blocked = self.store.transition("mission-1", MissionExecutionStatus.BLOCKED, occurred_at="2026-08-01T20:05:00Z", reason="dependency unavailable")
        self.assertEqual(blocked.status, MissionExecutionStatus.BLOCKED)
        recovered = self.store.transition("mission-1", MissionExecutionStatus.READY, occurred_at="2026-08-01T20:06:00Z", reason="dependency recovered")
        self.assertEqual(recovered.status, MissionExecutionStatus.READY)
        active = self.store.transition("mission-1", MissionExecutionStatus.ACTIVE, occurred_at="2026-08-01T20:07:00Z", reason="retry started")
        failed = self.store.transition("mission-1", MissionExecutionStatus.FAILED, occurred_at="2026-08-01T20:08:00Z", reason="execution failed")
        self.assertEqual(active.status, MissionExecutionStatus.ACTIVE)
        self.assertEqual(failed.status, MissionExecutionStatus.FAILED)
        self.assertEqual(self.store.transition("mission-1", MissionExecutionStatus.READY, occurred_at="2026-08-01T20:09:00Z", reason="failure recovered").status, MissionExecutionStatus.READY)

    def test_completed_mission_requires_terminal_evidence_and_is_not_resumable(self) -> None:
        self.advance_to_waiting_evidence()
        with self.assertRaisesRegex(MissionStateStoreError, "requires complete host-issued execution evidence"):
            self.store.transition("mission-1", MissionExecutionStatus.COMPLETED, occurred_at="2026-08-01T20:05:00Z", reason="unproven")
        completed_action = replace(action(), status=EngineeringActionStatus.COMPLETE)
        complete = self.store.transition(
            "mission-1", MissionExecutionStatus.COMPLETED, occurred_at="2026-08-01T20:05:00Z", reason="evidence verified",
            actions=(completed_action,), execution_evidence={
                "host_id": "host-1", "receipt_id": "receipt-1", "host_run_id": "run-1", "correlation_id": "correlation-1",
                "report_id": "report-1", "outcome": "complete", "execution_started_at": "2026-08-01T20:04:00Z",
                "execution_completed_at": "2026-08-01T20:05:00Z", "execution_duration_ms": 60_000, "repository_evidence": {
                    "mission_id": "mission-1", "intent_id": "intent-1", "intent_revision": "1", "action_id": "action-1",
                    "runtime_prompt_id": "prompt-1", "correlation_id": "correlation-1", "host_run_id": "run-1", "report_id": "report-1",
                },
            },
        )
        self.assertEqual(complete.progress["percent_complete"], 100)
        self.assertEqual(complete.execution_evidence["report_id"], "report-1")  # type: ignore[index]
        self.assertEqual(self.store.resumable(), ())
        self.assertEqual(self.store.transition("mission-1", MissionExecutionStatus.ARCHIVED, occurred_at="2026-08-01T20:06:00Z", reason="retained").status, MissionExecutionStatus.ARCHIVED)

    def test_history_entries_are_frozen_and_append_only(self) -> None:
        self.create()
        first = self.store.history("mission-1")[0]
        with self.assertRaises(FrozenInstanceError):
            first.reason = "rewritten"  # type: ignore[misc]
        self.store.transition("mission-1", MissionExecutionStatus.READY, occurred_at="2026-08-01T20:01:00Z", reason="planned")
        history = self.store.history("mission-1")
        self.assertEqual([(item.sequence, item.reason) for item in history], [(1, "created"), (2, "planned")])
        self.assertFalse(hasattr(self.store, "_connection"))


if __name__ == "__main__":
    unittest.main()
