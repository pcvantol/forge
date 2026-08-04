"""Regression coverage for Forge's autonomous single-Mission execution loop."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from forge.execution import ApprovalRecord, ExecutionLoop, ExecutionLoopError, ExecutionPolicy, ExecutionPolicyKind, RecoveryAuthorization
from forge.governance import execution_policy_for_profile
from forge.models import (
    ApprovedScope, ArchitectureMission, ArchitectureMissionStatus, EngineeringActionStatus,
    ExecutionDispatch, ExecutionEvidenceOutcome, ExecutionHostEvidence, ExecutionRepositoryEvidence,
    IntentReference, MissionPlannerInput, MissionPlanningState, PlannedActionDefinition,
    PlanningEvidence, PlanningInputKind, RequiredDiscipline, ProviderPromptDefinition,
    RuntimePrompt, RuntimePromptSection, RuntimePromptSectionKind,
)
from forge.planner import MissionPlanner
from forge.state import MissionExecutionStatus, MissionStateStore


def digest(letter: str) -> str:
    return "sha256:" + letter * 64


def mission() -> ArchitectureMission:
    return ArchitectureMission(
        "mission-loop", "candidate-loop", "Loop", "Run work.", "Complete bounded work.", "Evidence.",
        "review-source", "recommendation-source", ("contract", "docs"), ("bounded",), ("complete",),
        ("local",), ("none",), ("capability-contract", "capability-docs"),
        (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("none",), ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
    )


def planning(state: object) -> MissionPlannerInput:
    revision = getattr(state, "revision")
    evidence = tuple(PlanningEvidence(kind, kind.value, str(revision), f"local://{kind.value}", digest("a")) for kind in (
        PlanningInputKind.MISSION_STATE, PlanningInputKind.REPOSITORY_TRUTH,
        PlanningInputKind.ARCHITECTURE_REVIEW, PlanningInputKind.CAPABILITY_CATALOGUE,
    ))
    reference = IntentReference("architecture", "1", "local://architecture")
    return MissionPlannerInput(
        mission(), MissionPlanningState("mission-loop", revision), evidence,
        (ApprovedScope("contract", "capability-contract", (reference,), (
            PlannedActionDefinition("contract-action", "Implement contract.", ("contract evidence",), ("contract test",), 10),
        )), ApprovedScope("docs", "capability-docs", (reference,), (
            PlannedActionDefinition("docs-action", "Document contract.", ("docs evidence",), ("docs test",), 20),
        ))),
    )


def prompt(_intent: object, action: object) -> RuntimePrompt:
    return RuntimePrompt(f"prompt-{action.id}", action.intent_id, action.intent_revision, action.id,  # type: ignore[attr-defined]
                         ProviderPromptDefinition("test", "1"), digest("b"),
                         tuple(RuntimePromptSection(kind, (kind.value,)) for kind in RuntimePromptSectionKind))


class Dispatcher:
    def __init__(self) -> None:
        self.held: list[tuple[str, MissionExecutionStatus]] = []
        self.completed: list[str] = []
        self.recovered: list[str] = []

    def dispatch(self): return SimpleNamespace(mission_id="mission-loop")
    def resume(self): return SimpleNamespace(mission_id="mission-loop")
    def hold(self, mission_id: str, status: MissionExecutionStatus) -> None: self.held.append((mission_id, status))
    def complete(self, mission_id: str) -> None: self.completed.append(mission_id)
    def recover(self, mission_id: str) -> None: self.recovered.append(mission_id)


class Host:
    def __init__(self, outcomes: dict[str, ExecutionEvidenceOutcome | None]) -> None:
        self.outcomes, self.dispatches, self.requests = outcomes, {}, []

    def dispatch(self, request):
        self.requests.append(request.action_id)
        dispatch = ExecutionDispatch(request, f"run-{request.correlation_id}")
        self.dispatches[request.correlation_id] = dispatch
        return dispatch

    def recover_dispatch(self, request): return self.dispatches.get(request.correlation_id)

    def retrieve_evidence(self, dispatch):
        outcome = self.outcomes.get(dispatch.request.action_id)
        if outcome is None: return None
        request = dispatch.request
        repository = ExecutionRepositoryEvidence(request.mission_id, request.intent_id, request.intent_revision,
            request.action_id, request.runtime_prompt.id, request.correlation_id, dispatch.host_run_id,
            request.repository_id, "revision", f"report-{request.action_id}", digest("c"))
        return ExecutionHostEvidence(request.host_id, request.correlation_id, dispatch.host_run_id,
                                     f"report-{request.action_id}", outcome, repository)


class ExecutionLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory(); self.path = Path(self.directory.name) / "state.sqlite"
        self.store = MissionStateStore(self.path); self.store.create_pending(mission(), occurred_at="2026-08-04T10:00:00Z")
        self.dispatcher, self.counter, self.planning_calls = Dispatcher(), 0, 0

    def tearDown(self) -> None:
        self.store.close(); self.directory.cleanup()

    def loop(self, host: Host, policy: ExecutionPolicy | None = None, profile: str = "solo") -> ExecutionLoop:
        def correlation() -> str:
            self.counter += 1
            return f"correlation-{self.counter}"
        def planning_input(state: object) -> MissionPlannerInput:
            self.planning_calls += 1
            return planning(state)
        return ExecutionLoop(self.dispatcher, self.store, MissionPlanner(), host, planning_input, prompt,
                             lambda _state, _evidence: {"source_id": "repository", "revision": "revision", "content_digest": digest("d")},
                             host_id="host", workspace_id="workspace", repository_id="forge",
                             clock=lambda: "2026-08-04T10:00:00Z", correlation_id_factory=correlation,
                             execution_policy=policy, governance_profile=profile)

    def test_multiple_actions_progress_completion_evidence_and_completion_notifications(self) -> None:
        state = self.loop(Host({"contract-action": ExecutionEvidenceOutcome.COMPLETE, "docs-action": ExecutionEvidenceOutcome.COMPLETE})).run()
        assert state is not None
        self.assertEqual(state.status, MissionExecutionStatus.COMPLETED)
        self.assertEqual(state.progress["percent_complete"], 100)
        self.assertEqual(len(state.execution_history), 2)
        self.assertEqual(self.planning_calls, 2)  # Initial plan plus deterministic remaining-work replan.
        self.assertEqual(state.completion["repository_truth_updated"], True)  # type: ignore[index]
        self.assertEqual(self.dispatcher.completed, ["mission-loop"])

    def test_blocking_resume_requires_authorization_and_never_repeats_completed_actions(self) -> None:
        host = Host({"contract-action": ExecutionEvidenceOutcome.COMPLETE, "docs-action": ExecutionEvidenceOutcome.BLOCKED})
        loop = self.loop(host); blocked = loop.run()
        assert blocked is not None
        self.assertEqual(blocked.status, MissionExecutionStatus.BLOCKED)
        self.assertEqual(self.dispatcher.held, [("mission-loop", MissionExecutionStatus.BLOCKED)])
        with self.assertRaisesRegex(ExecutionLoopError, "explicit recovery"):
            loop.resume("mission-loop")
        host.outcomes["docs-action"] = ExecutionEvidenceOutcome.COMPLETE
        resumed = loop.resume("mission-loop", RecoveryAuthorization("mission-loop", "docs-action", "operator-1", "Dependency resolved."))
        self.assertEqual(resumed.status, MissionExecutionStatus.COMPLETED)
        self.assertEqual(host.requests, ["contract-action", "docs-action", "docs-action"])

    def test_persisted_waiting_state_and_observability_are_restart_safe_and_deterministic(self) -> None:
        host = Host({"contract-action": None, "docs-action": ExecutionEvidenceOutcome.COMPLETE})
        first = self.loop(host).run(); assert first is not None
        self.assertEqual(first.status, MissionExecutionStatus.WAITING_FOR_EVIDENCE)
        projection = self.loop(host).observability("mission-loop")
        self.assertEqual((projection.current_action_id, projection.percent_complete), ("contract-action", 0))
        self.store.close(); self.store = MissionStateStore(self.path)
        host.outcomes["contract-action"] = ExecutionEvidenceOutcome.COMPLETE
        state = self.loop(host).resume("mission-loop")
        self.assertEqual(state.status, MissionExecutionStatus.COMPLETED)
        self.assertEqual(host.requests, ["contract-action", "docs-action"])

    def test_action_review_pauses_after_exact_evidence_and_resumes_after_approval(self) -> None:
        host = Host({"contract-action": ExecutionEvidenceOutcome.COMPLETE, "docs-action": ExecutionEvidenceOutcome.COMPLETE})
        loop = self.loop(host, ExecutionPolicy(ExecutionPolicyKind.ENGINEERING_ACTION_REVIEW))
        paused = loop.run(); assert paused is not None
        self.assertEqual(paused.status, MissionExecutionStatus.AWAITING_APPROVAL)
        self.assertEqual(paused.pause_reason["boundary"], "engineering_action")  # type: ignore[index]
        self.store.close(); self.store = MissionStateStore(self.path)
        resumed = self.loop(host, ExecutionPolicy(ExecutionPolicyKind.ENGINEERING_ACTION_REVIEW)).resume(
            "mission-loop", approval=ApprovalRecord("approval-1", "architect", "2026-08-04T10:01:00Z", "review-1"))
        self.assertEqual(resumed.status, MissionExecutionStatus.AWAITING_APPROVAL)
        self.assertEqual(resumed.approval_record["approval_id"], "approval-1")  # type: ignore[index]
        self.assertEqual(host.requests, ["contract-action", "docs-action"])

    def test_intent_capability_and_mission_reviews_pause_only_at_their_boundary(self) -> None:
        outcomes = {"contract-action": ExecutionEvidenceOutcome.COMPLETE, "docs-action": ExecutionEvidenceOutcome.COMPLETE}
        expectations = ((ExecutionPolicyKind.ENGINEERING_INTENT_REVIEW, "engineering_intent"),
                        (ExecutionPolicyKind.CAPABILITY_REVIEW, "capability"),
                        (ExecutionPolicyKind.MISSION_REVIEW, "mission"))
        for policy_kind, boundary in expectations:
            with self.subTest(policy=policy_kind):
                self.store.close(); self.path.unlink(); self.store = MissionStateStore(self.path)
                self.store.create_pending(mission(), occurred_at="2026-08-04T10:00:00Z")
                paused = self.loop(Host(outcomes), ExecutionPolicy(policy_kind)).run(); assert paused is not None
                self.assertEqual(paused.status, MissionExecutionStatus.AWAITING_APPROVAL)
                self.assertEqual(paused.pause_reason["boundary"], boundary)  # type: ignore[index]

    def test_continuous_policy_and_profile_defaults_preserve_identical_host_sequence(self) -> None:
        self.assertEqual(execution_policy_for_profile("solo").kind, ExecutionPolicyKind.CONTINUOUS)
        self.assertEqual(execution_policy_for_profile("duo").kind, ExecutionPolicyKind.ENGINEERING_INTENT_REVIEW)
        self.assertEqual(execution_policy_for_profile("professional").kind, ExecutionPolicyKind.ENGINEERING_ACTION_REVIEW)
        self.assertEqual(execution_policy_for_profile("enterprise").kind, ExecutionPolicyKind.CUSTOM)
        host = Host({"contract-action": ExecutionEvidenceOutcome.COMPLETE, "docs-action": ExecutionEvidenceOutcome.COMPLETE})
        state = self.loop(host, ExecutionPolicy(ExecutionPolicyKind.CONTINUOUS)).run(); assert state is not None
        self.assertEqual(state.status, MissionExecutionStatus.COMPLETED)
        self.assertEqual(host.requests, ["contract-action", "docs-action"])


if __name__ == "__main__":
    unittest.main()
