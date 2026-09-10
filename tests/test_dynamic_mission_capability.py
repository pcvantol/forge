"""Deterministic first-canary capability harness; no network or real provider."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from forge.execution import ExecutionLoop, ExecutionLoopError
from forge.models import (
    ApprovedScope,
    ArchitectureMission,
    ArchitectureMissionStatus,
    CanonicalExecutionEvidenceReference,
    DerivationPolicy,
    DerivedActionProposal,
    ExecutionDispatch,
    ExecutionEvidenceOutcome,
    ExecutionHostEvidence,
    ExecutionRepositoryEvidence,
    IntentReference,
    MissionCompletionEvidence,
    MissionCriterionEvidenceBinding,
    MissionGapBinding,
    MissionGapClassification,
    MissionPlannerInput,
    MissionPlanningState,
    PlannedActionDefinition,
    PlanningEvidence,
    PlanningInputKind,
    ProposalProvenance,
    ProviderPromptDefinition,
    RepositoryTruthReference,
    RequiredDiscipline,
    RuntimePrompt,
    RuntimePromptSection,
    RuntimePromptSectionKind,
    mission_criterion_id,
)
from forge.planner import AIMissionPlanner, MissionPlanner, ProposalValidationError
from forge.runtime import RuntimeDatabase
from forge.state import MissionExecutionStatus, MissionStateStore


def digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def mission() -> ArchitectureMission:
    return ArchitectureMission(
        "mission-dynamic", "candidate-dynamic", "Dynamic mission", "Derive bounded work.",
        "Prove A and its evidence-derived successor B.", "Autonomous bounded delivery.",
        "architecture-review", "mission-recommendation", ("forge-runtime",),
        ("Remain inside forge/runtime.",), ("A evidence reconciled", "B evidence reconciled"),
        ("Canonical Host evidence is available.",), ("none",), ("dynamic-runtime",),
        (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("scope drift",),
        ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
    )


def prompt(_intent: object, action: object) -> RuntimePrompt:
    return RuntimePrompt(
        f"prompt-{action.id}", action.intent_id, action.intent_revision, action.id,  # type: ignore[attr-defined]
        ProviderPromptDefinition("fixture", "1"), digest("prompt"),
        tuple(RuntimePromptSection(kind, (kind.value,)) for kind in RuntimePromptSectionKind),
    )


class Dispatcher:
    def __init__(self) -> None:
        self.completed: list[str] = []
        self.held: list[tuple[str, MissionExecutionStatus]] = []

    def dispatch(self): return SimpleNamespace(mission_id=mission().id)
    def resume(self): return SimpleNamespace(mission_id=mission().id)
    def recover(self, _mission_id: str): return None
    def complete(self, mission_id: str): self.completed.append(mission_id)
    def hold(self, mission_id: str, status: MissionExecutionStatus): self.held.append((mission_id, status))


class Host:
    def __init__(self) -> None:
        self.outcomes = {"action-a": ExecutionEvidenceOutcome.COMPLETE, "action-b": None}
        self.dispatches: dict[str, ExecutionDispatch] = {}
        self.requests: list[str] = []

    def dispatch(self, request):
        self.requests.append(request.action_id)
        result = ExecutionDispatch(request, f"run-{request.action_id}")
        self.dispatches[request.correlation_id] = result
        return result

    def recover_dispatch(self, request):
        return self.dispatches.get(request.correlation_id)

    def retrieve_evidence(self, dispatch):
        action_id = dispatch.request.action_id
        outcome = self.outcomes.get(action_id)
        if outcome is None:
            return None
        request = dispatch.request
        repository = ExecutionRepositoryEvidence(
            request.mission_id, request.intent_id, request.intent_revision, action_id,
            request.runtime_prompt.id, request.correlation_id, dispatch.host_run_id, request.repository_id,
            f"revision-{action_id}", f"report-{action_id}", digest(f"repository-{action_id}"),
        )
        return ExecutionHostEvidence(
            request.host_id, request.correlation_id, dispatch.host_run_id, f"report-{action_id}", outcome,
            repository, validation_references=(f"validation-{action_id}",),
            execution_started_at="2026-09-10T10:00:00Z", execution_completed_at="2026-09-10T10:01:00Z",
            receipt_id=f"receipt-{action_id}", execution_duration_ms=60_000,
        )


class DerivationProvider:
    def __init__(self, second: str = "successor") -> None:
        self.snapshots = []
        self.second = second

    @staticmethod
    def proposal(snapshot, action_id: str, *, dependencies: tuple[str, ...] = (), scope: str = "forge-runtime",
                 mission_gap: MissionGapBinding | None = None):
        provenance = ProposalProvenance(
            f"derivation-{action_id}", snapshot.id, snapshot.digest, "fixture-v1", "fixture-provider", "fixture-model",
            tuple(item.source_id for item in snapshot.evidence),
        )
        return DerivedActionProposal(
            action_id, scope, f"Execute {action_id}.", dependencies, ("forge/runtime",),
            (f"evidence-{action_id}",), (f"validate-{action_id}",), 1, False,
            ("architecture-review",), ("scope-drift",), provenance, mission_gap,
        )

    def successor_gap(self, snapshot, action_id: str) -> MissionGapBinding | None:
        objective = f"Execute {action_id}."
        execution_ref = next(item.source_id for item in snapshot.evidence
                             if item.kind is PlanningInputKind.EXECUTION_EVIDENCE)
        criteria = {item.criterion: item.criterion_id for item in snapshot.criteria}
        if self.second in {"missing-binding", "optional"}:
            return None
        if self.second in {"outside-criterion", "criterion-expansion"}:
            criterion_ids = ("mission-criterion-outside-approved-mission",)
        elif self.second == "proven-criterion":
            criterion_ids = (criteria["A evidence reconciled"],)
        else:
            criterion_ids = (criteria["B evidence reconciled"],)
        evidence_refs = ("stale-receipt",) if self.second == "stale-evidence" else (execution_ref,)
        if self.second == "blocker":
            return MissionGapBinding(
                MissionGapClassification.MISSION_CAUSED_BLOCKER, (), evidence_refs,
                snapshot.digest, objective, ("action-a",),
            )
        return MissionGapBinding(
            MissionGapClassification.UNPROVEN_MISSION_CRITERION, criterion_ids, evidence_refs,
            "sha256:" + "0" * 64 if self.second == "stale-binding" else snapshot.digest,
            "Unrelated objective." if self.second == "objective-mismatch" else objective,
        )

    def derive(self, snapshot):
        self.snapshots.append(snapshot)
        if len(self.snapshots) == 1:
            return (self.proposal(snapshot, "action-a"),)
        if self.second == "empty":
            return ()
        if self.second == "rewrite-a":
            return (self.proposal(snapshot, "action-a"),)
        if self.second == "stale":
            return (self.proposal(self.snapshots[0], "action-b", dependencies=("action-a",)),)
        if self.second == "outside":
            return (self.proposal(snapshot, "action-b", dependencies=("action-a",), scope="outside"),)
        return (self.proposal(snapshot, "action-b", dependencies=("action-a",),
                              mission_gap=self.successor_gap(snapshot, "action-b")),)


class DynamicMissionCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.runtime = RuntimeDatabase(self.root)
        self.runtime_identity = self.runtime.runtime_identity
        self.store = MissionStateStore(self.runtime)
        self.store.create_pending(mission(), occurred_at="2026-09-10T09:59:00Z")
        self.host, self.dispatcher, self.counter = Host(), Dispatcher(), 0

    def tearDown(self) -> None:
        self.runtime.close()
        self.directory.cleanup()

    @staticmethod
    def truth(_state, evidence):
        suffix = "initial" if evidence is None else evidence.repository_evidence.action_id
        return {
            "source_id": "forge-repository-truth", "revision": f"revision-{suffix}",
            "locator": f"repository://forge/{suffix}", "content_digest": digest(f"truth-{suffix}"),
        }

    @staticmethod
    def planning(state) -> MissionPlannerInput:
        truth = state.repository_truth or DynamicMissionCapabilityTests.truth(state, None)
        items = [
            PlanningEvidence(PlanningInputKind.MISSION_STATE, f"mission-state-{state.revision}", str(state.revision),
                             f"runtime://mission/{state.mission_id}/{state.revision}", digest({"revision": state.revision})),
            PlanningEvidence(PlanningInputKind.REPOSITORY_TRUTH, f"truth-{truth['revision']}", str(truth["revision"]),
                             str(truth["locator"]), str(truth["content_digest"])),
            PlanningEvidence(PlanningInputKind.ARCHITECTURE_REVIEW, "architecture-review", "1",
                             "repository://architecture-review", digest("architecture-review")),
            PlanningEvidence(PlanningInputKind.CAPABILITY_CATALOGUE, "capability-catalogue", "1",
                             "repository://capability-catalogue", digest("capability-catalogue")),
        ]
        if state.execution_history:
            current = state.execution_history[-1]
            items.append(PlanningEvidence(
                PlanningInputKind.EXECUTION_EVIDENCE, str(current["receipt_id"]), str(state.revision),
                f"runtime://execution/{current['receipt_id']}", str(current["repository_evidence"]["content_digest"]),
            ))
        return MissionPlannerInput(
            mission(), MissionPlanningState(mission().id, state.revision), tuple(items),
            (ApprovedScope("forge-runtime", "dynamic-runtime", (IntentReference(
                "living-mission-graph", "1", "docs/architecture/LIVING_MISSION_GRAPH_AND_CROSS_REPOSITORY_ACTION_DAG.md"
            ),), (), allow_provider_derivation=True),),
        )

    @staticmethod
    def completion_evidence(state, current, truth):
        documents = (*state.execution_history, {
            "receipt_id": current.receipt_id, "report_id": current.report_id, "outcome": current.outcome.value,
            "correlation_id": current.correlation_id, "host_run_id": current.host_run_id,
            "repository_evidence": {
                "mission_id": current.repository_evidence.mission_id,
                "action_id": current.repository_evidence.action_id,
                "repository_revision": current.repository_evidence.repository_revision,
                "content_digest": current.repository_evidence.content_digest,
            },
        })
        references = {
            item["repository_evidence"]["action_id"]: CanonicalExecutionEvidenceReference(
                item["receipt_id"], item["repository_evidence"]["action_id"], item["report_id"],
                item["repository_evidence"]["repository_revision"], item["repository_evidence"]["content_digest"],
            ) for item in documents if item.get("outcome") == "complete"
        }
        truth_reference = RepositoryTruthReference(truth["source_id"], truth["revision"], truth["locator"], truth["content_digest"])
        bindings = []
        for action_id, criterion in (("action-a", "A evidence reconciled"), ("action-b", "B evidence reconciled")):
            if action_id in references:
                bindings.append(MissionCriterionEvidenceBinding(
                    mission_criterion_id(mission().id, criterion), (references[action_id],), truth_reference,
                ))
        return MissionCompletionEvidence(mission().id, digest(mission().to_dict()), tuple(bindings))

    def loop(self, provider: DerivationProvider, *, planning=None) -> ExecutionLoop:
        def correlation():
            self.counter += 1
            return f"correlation-{self.counter}"
        return ExecutionLoop(
            self.dispatcher, self.store, MissionPlanner(), self.host, planning or self.planning, prompt, self.truth,
            host_id="host", workspace_id="forge", repository_id="forge", clock=lambda: "2026-09-10T10:00:00Z",
            correlation_id_factory=correlation, ai_planner=AIMissionPlanner(provider),
            derivation_policy=DerivationPolicy(("forge/runtime",), ("architecture-review",), ("scope-drift",)),
            completion_evidence=self.completion_evidence,
        )

    def test_initial_a_successor_b_restart_and_evidence_derived_completion(self) -> None:
        provider = DerivationProvider()
        self.assertEqual(self.store.get(mission().id).actions, ())
        waiting = self.loop(provider).run()
        assert waiting is not None
        self.assertEqual(waiting.status, MissionExecutionStatus.WAITING_FOR_EVIDENCE)
        self.assertEqual([item["id"] for item in waiting.actions], ["action-a", "action-b"])
        self.assertEqual([item["status"] for item in waiting.actions], ["COMPLETE", "WAITING_FOR_RESULT"])
        self.assertFalse(waiting.completion["all_required_criteria_proven"])
        self.assertEqual([item["derivation_id"] for item in waiting.planning_history],
                         ["derivation-action-a", "derivation-action-b"])
        self.assertTrue(all(item["validated_before_materialization"] for item in waiting.planning_history))
        self.assertEqual(waiting.planning_history[1]["completed_action_ids_at_derivation"], ["action-a"])
        gap = waiting.planning_history[1]["proposals"][0]["mission_gap"]
        self.assertEqual(gap["classification"], "UNPROVEN_MISSION_CRITERION")
        self.assertEqual(gap["criterion_ids"], [mission_criterion_id(mission().id, "B evidence reconciled")])
        self.assertTrue(any(item.kind is PlanningInputKind.EXECUTION_EVIDENCE for item in provider.snapshots[1].evidence))
        execution_input = next(item for item in provider.snapshots[1].evidence
                               if item.kind is PlanningInputKind.EXECUTION_EVIDENCE)
        truth_input = next(item for item in provider.snapshots[1].evidence
                           if item.kind is PlanningInputKind.REPOSITORY_TRUTH)
        self.assertEqual(execution_input.content_digest, digest("repository-action-a"))
        self.assertEqual(truth_input.content_digest, digest("truth-action-a"))

        before_restart = (waiting.mission_id, tuple(waiting.actions), tuple(waiting.planning_history))
        self.runtime.close()
        self.runtime = RuntimeDatabase(self.root)
        self.store = MissionStateStore(self.runtime)
        restarted = self.store.get(mission().id)
        reopened_identity = self.runtime.runtime_identity
        self.assertEqual((reopened_identity.runtime_id, reopened_identity.repository_identity,
                          reopened_identity.repository_uuid, reopened_identity.database_location),
                         (self.runtime_identity.runtime_id, self.runtime_identity.repository_identity,
                          self.runtime_identity.repository_uuid, self.runtime_identity.database_location))
        self.assertEqual((restarted.mission_id, tuple(restarted.actions), tuple(restarted.planning_history)), before_restart)

        self.host.outcomes["action-b"] = ExecutionEvidenceOutcome.COMPLETE
        complete = self.loop(provider).resume(mission().id)
        self.assertEqual(complete.status, MissionExecutionStatus.COMPLETED)
        self.assertTrue(complete.completion["all_required_criteria_proven"])
        self.assertTrue(all(item["status"] == "PROVEN" for item in complete.completion["criteria"]))
        self.assertEqual([item["id"] for item in complete.actions], ["action-a", "action-b"])
        self.assertEqual(self.host.requests, ["action-a", "action-b"])
        self.assertEqual(self.dispatcher.completed, [mission().id])
        self.assertEqual(len(provider.snapshots), 2)

    def test_unmet_criteria_and_no_successor_fail_closed(self) -> None:
        provider = DerivationProvider("empty")
        blocked = self.loop(provider).run()
        assert blocked is not None
        self.assertEqual(blocked.status, MissionExecutionStatus.BLOCKED)
        self.assertFalse(blocked.completion["all_required_criteria_proven"])
        self.assertEqual([item["id"] for item in blocked.actions], ["action-a"])
        self.assertEqual(blocked.waiting_reason, "mission_criteria_unmet_no_valid_successor")

    def test_stale_outside_and_completed_identity_reuse_are_rejected_without_rewriting_a(self) -> None:
        for mode in ("stale", "outside", "rewrite-a"):
            with self.subTest(mode=mode):
                self.runtime.close()
                scoped_root = self.root / mode
                self.runtime = RuntimeDatabase(scoped_root)
                self.store = MissionStateStore(self.runtime)
                self.store.create_pending(mission(), occurred_at="2026-09-10T09:59:00Z")
                blocked = self.loop(DerivationProvider(mode)).run()
                assert blocked is not None
                self.assertEqual(blocked.status, MissionExecutionStatus.BLOCKED)
                self.assertEqual([(item["id"], item["status"]) for item in blocked.actions], [("action-a", "COMPLETE")])
                self.assertEqual(len(blocked.execution_history), 1)

    def test_successor_relevance_failures_never_materialize_inside_scope_work(self) -> None:
        modes = (
            "proven-criterion", "missing-binding", "outside-criterion", "stale-evidence",
            "stale-binding", "optional", "objective-mismatch", "criterion-expansion",
        )
        for mode in modes:
            with self.subTest(mode=mode):
                self.runtime.close()
                scoped_root = self.root / mode
                self.runtime = RuntimeDatabase(scoped_root)
                self.store = MissionStateStore(self.runtime)
                self.store.create_pending(mission(), occurred_at="2026-09-10T09:59:00Z")
                blocked = self.loop(DerivationProvider(mode)).run()
                assert blocked is not None
                self.assertEqual(blocked.status, MissionExecutionStatus.BLOCKED)
                self.assertEqual([(item["id"], item["status"]) for item in blocked.actions],
                                 [("action-a", "COMPLETE")])
                self.assertEqual(self.host.requests[-1], "action-a")

    def test_mission_caused_blocker_with_current_causal_evidence_is_executable(self) -> None:
        waiting = self.loop(DerivationProvider("blocker")).run()
        assert waiting is not None
        self.assertEqual(waiting.status, MissionExecutionStatus.WAITING_FOR_EVIDENCE)
        self.assertEqual([item["id"] for item in waiting.actions], ["action-a", "action-b"])
        gap = waiting.planning_history[1]["proposals"][0]["mission_gap"]
        self.assertEqual(gap["classification"], "MISSION_CAUSED_BLOCKER")
        self.assertEqual(gap["mission_caused_by_action_ids"], ["action-a"])

    def test_dynamic_mode_rejects_any_preconfigured_action(self) -> None:
        def invalid_planning(state):
            source = self.planning(state)
            scope = source.approved_scopes[0]
            invalid = replace(scope, actions=(PlannedActionDefinition(
                "action-b", "Owner supplied future work.", ("evidence",), ("validation",),
            ),))
            return replace(source, approved_scopes=(invalid,))
        with self.assertRaisesRegex(ExecutionLoopError, "preconfigured"):
            self.loop(DerivationProvider(), planning=invalid_planning).run()

    def test_planning_cannot_rewrite_the_approved_mission_boundary(self) -> None:
        def changed_mission(state):
            source = self.planning(state)
            return replace(source, mission=replace(source.mission, summary="Rewritten Mission."))
        with self.assertRaisesRegex(ExecutionLoopError, "exact approved Mission"):
            self.loop(DerivationProvider(), planning=changed_mission).run()


if __name__ == "__main__":
    unittest.main()
