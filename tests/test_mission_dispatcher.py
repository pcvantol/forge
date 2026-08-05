"""Regression coverage for approved-Mission FIFO dispatch."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from forge.architecture import ArchitectureWorkspace
from forge.dispatcher import ApprovedMissionQueue, DispatcherStatus, MissionDispatcher, MissionDispatcherStore
from forge.intake import MissionIntake
from forge.models import EngineeringEffort, MissionCandidate, MissionCandidateMaturity, MissionCandidateStatus, RecommendationConfidenceLevel, RequiredDiscipline
from forge.state import MissionExecutionStatus, MissionStateStore


def candidate(identifier: str) -> MissionCandidate:
    return MissionCandidate(identifier, identifier, "Summary.", "Objective.", "Value.", EngineeringEffort.SMALL, RecommendationConfidenceLevel.HIGH, (RequiredDiscipline.BUSINESS,), ("none",), "review", "recommendation", 1, "Approved.", MissionCandidateMaturity.READY_FOR_ARCHITECTURE, MissionCandidateStatus.APPROVED_FOR_ARCHITECTURE)


class States:
    def __init__(self) -> None: self.status: dict[str, MissionExecutionStatus] = {}
    def get(self, mission_id: str): return SimpleNamespace(status=self.status.get(mission_id, MissionExecutionStatus.CREATED))


class MissionDispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory(); root = Path(self.directory.name)
        self.workspace = ArchitectureWorkspace(root / "architecture.sqlite")
        self.state_store = MissionStateStore(root / "state.sqlite")
        self.dispatch_store = MissionDispatcherStore(root / "dispatcher.sqlite")
        self.states, self.tick = States(), 0

    def tearDown(self) -> None:
        self.workspace.close(); self.state_store.close(); self.dispatch_store.close(); self.directory.cleanup()

    def clock(self) -> str:
        self.tick += 1; return f"2026-08-04T10:00:{self.tick:02d}Z"

    def approve(self, identifier: str) -> None:
        self.workspace.admit(candidate(identifier), actor="architect", occurred_at=self.clock(), rationale="Business approval verified.")
        self.workspace.refine(identifier, actor="architect", occurred_at=self.clock(), rationale="Ready.", scope=("scope",), engineering_constraints=("constraint",), acceptance_criteria=("criterion",), technical_assumptions=("assumption",), dependencies=("dependency",), required_capabilities=("capability",), required_disciplines=(RequiredDiscipline.PLATFORM_ARCHITECTURE,), risks=("risk",))
        self.workspace.approve_for_engineering(identifier, actor="architect", occurred_at=self.clock(), rationale="Approved.")

    def dispatcher(self, *, review=None, recommendations=None) -> MissionDispatcher:
        return MissionDispatcher(ApprovedMissionQueue(self.workspace), MissionIntake(self.state_store, self.clock), self.states, self.dispatch_store, clock=self.clock, architecture_review=review, recommendations=recommendations)

    def test_first_selection_follows_approval_fifo_not_historical_bootstrap_order(self) -> None:
        self.approve("MISSION-0002"); self.approve("MISSION-0001")
        self.assertEqual([item.id for item in ApprovedMissionQueue(self.workspace).missions()], ["MISSION-0002", "MISSION-0001"])
        self.assertEqual(self.dispatcher().dispatch().mission_id, "MISSION-0002")  # type: ignore[union-attr]

    def test_single_active_and_resume_do_not_start_a_second_mission(self) -> None:
        self.approve("MISSION-0001"); self.approve("MISSION-0002"); dispatcher = self.dispatcher(); active = dispatcher.dispatch()
        self.assertEqual(dispatcher.dispatch(), active)
        self.assertEqual(len([item for item in self.dispatch_store.records() if item.status is DispatcherStatus.ACTIVE]), 1)

    def test_restart_resumes_persisted_active_mission_identity_and_state(self) -> None:
        self.approve("MISSION-0001"); active = self.dispatcher().dispatch()
        self.dispatch_store.close()
        self.dispatch_store = MissionDispatcherStore(Path(self.directory.name) / "dispatcher.sqlite")
        resumed = self.dispatcher().resume()
        self.assertEqual(resumed, active)

    def test_completion_triggers_review_recommendations_and_next_activation(self) -> None:
        self.approve("MISSION-0001"); self.approve("MISSION-0002"); invoked: list[tuple[str, str]] = []
        dispatcher = self.dispatcher(review=lambda identifier: invoked.append(("review", identifier)), recommendations=lambda identifier: invoked.append(("recommendation", identifier)))
        dispatcher.dispatch(); self.states.status["MISSION-0001"] = MissionExecutionStatus.COMPLETED
        next_active = dispatcher.complete("MISSION-0001")
        self.assertEqual(next_active.mission_id, "MISSION-0002")  # type: ignore[union-attr]
        self.assertEqual(invoked, [("review", "MISSION-0001"), ("recommendation", "MISSION-0001")])

    def test_empty_queue_is_idle_and_recommendations_are_not_queue_members(self) -> None:
        dispatcher = self.dispatcher(); self.assertIsNone(dispatcher.dispatch()); self.assertTrue(dispatcher.is_idle)
        self.assertEqual(ApprovedMissionQueue(self.workspace).missions(), ())

    def test_only_architecture_approved_business_candidates_are_dispatched(self) -> None:
        self.workspace.admit(candidate("MISSION-0001"), actor="architect", occurred_at=self.clock(), rationale="Admitted only.")
        self.assertIsNone(self.dispatcher().dispatch()); self.approve("MISSION-0002")
        self.assertEqual(self.dispatcher().dispatch().mission_id, "MISSION-0002")  # type: ignore[union-attr]

    def test_blocked_mission_does_not_advance_queue(self) -> None:
        self.approve("MISSION-0001"); self.approve("MISSION-0002"); dispatcher = self.dispatcher(); dispatcher.dispatch()
        self.dispatch_store.transition("MISSION-0001", DispatcherStatus.BLOCKED, occurred_at=self.clock())
        self.assertIsNone(dispatcher.dispatch())


if __name__ == "__main__": unittest.main()
