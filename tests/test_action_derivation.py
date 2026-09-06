"""Contract tests for the untrusted derivation stage of the AI Mission Planner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from forge.models import (
    ArchitectureMission, ArchitectureMissionStatus, DerivationLifecycle, DerivationPolicy, DerivationRecord, DerivedActionProposal, DerivedActionIdentityState,
    EngineeringEffort, IntentReference, MissionPlannerInput, MissionPlanningState,
    PlanningEvidence, PlanningInputKind, PlanningSnapshot, ProposalProvenance, ProviderInvocationEvidence, ProviderSideEffectState,
    RequiredDiscipline, ApprovedScope, classify_replan_identity,
)
from forge.planner import (AIMissionPlanner, ActionDerivationValidator, BoundedActionDerivationProvider,
                           ProposalValidationError, ProviderDerivationRequest, ProviderDerivationResponse,
                           deterministic_validation_failure_code, record_deterministic_validation_failure)
from forge.runtime.database import RuntimeDatabase


def _digest(char: str) -> str:
    return f"sha256:{char * 64}"


def input_model(**overrides: object) -> MissionPlannerInput:
    mission = ArchitectureMission(
        "mission-1", "candidate-1", "Planner", "Plan only.", "Build a bounded planner.", "Safe engineering.",
        "architecture-review-1", "recommendation-1", ("planner-contract", "planner-docs"),
        ("Planning never executes.",), ("Deterministic plans are generated.",), ("Local data only.",),
        ("architecture-approved",), ("mission-planner", "documentation"),
        (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("Scope drift.",), ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
    )
    evidence = tuple(PlanningEvidence(kind, kind.value, "1", f"local://{kind.value}", _digest("a")) for kind in (
        PlanningInputKind.MISSION_STATE, PlanningInputKind.REPOSITORY_TRUTH,
        PlanningInputKind.ARCHITECTURE_REVIEW, PlanningInputKind.CAPABILITY_CATALOGUE,
    ))
    reference = IntentReference("architecture", "1", "local://architecture")
    # Existing definitions are present only to construct an approved Mission envelope;
    # they are replaced by validated derived definitions before materialization.
    from forge.models import PlannedActionDefinition
    scopes = (
        ApprovedScope("planner-contract", "mission-planner", (reference,), (PlannedActionDefinition("legacy-contract", "Legacy envelope.", ("evidence",), ("tests",)),)),
        ApprovedScope("planner-docs", "documentation", (reference,), (PlannedActionDefinition("legacy-docs", "Legacy envelope.", ("evidence",), ("tests",)),)),
    )
    values: dict[str, object] = {"mission": mission, "mission_state": MissionPlanningState("mission-1", 1), "evidence": evidence, "approved_scopes": scopes}
    values.update(overrides)
    return MissionPlannerInput(**values)  # type: ignore[arg-type]


def proposal(*, action_id: str = "derive-contract", scope: str = "planner-contract", dependencies: tuple[str, ...] = (),
             write_scopes: tuple[str, ...] = ("forge/planner",), gates: tuple[str, ...] = ("architecture-review",),
             risks: tuple[str, ...] = ("scope-drift",), snapshot: PlanningSnapshot | None = None) -> DerivedActionProposal:
    current = snapshot or PlanningSnapshot.from_planner_input(input_model())
    provenance = ProposalProvenance("derivation-1", current.id, current.digest, "1.0", "fixture-provider", "fixture-1",
                                    tuple(item.source_id for item in current.evidence))
    return DerivedActionProposal(action_id, scope, "Implement bounded derived planning.", dependencies, write_scopes,
                                 (f"{action_id} evidence",), (f"{action_id} tests",), 10, False, gates, risks, provenance)


class FixtureProvider:
    def __init__(self, response: tuple[DerivedActionProposal, ...]) -> None:
        self.response = response
        self.calls = 0

    def derive(self, snapshot: PlanningSnapshot) -> tuple[DerivedActionProposal, ...]:
        self.calls += 1
        return self.response


class FixtureExecutor:
    def __init__(self, response: ProviderDerivationResponse | ProviderSideEffectState) -> None:
        self.response = response
        self.invocations = 0

    def invoke(self, request: ProviderDerivationRequest) -> ProviderDerivationResponse:
        self.invocations += 1
        if not isinstance(self.response, ProviderDerivationResponse):
            raise RuntimeError("fixture cannot return ambiguity from invocation")
        return self.response

    def reconcile(self, request: ProviderDerivationRequest) -> ProviderDerivationResponse | ProviderSideEffectState:
        return self.response


class ActionDerivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.input = input_model()
        self.snapshot = PlanningSnapshot.from_planner_input(self.input)
        self.policy = DerivationPolicy(("forge/planner",), ("architecture-review",), ("scope-drift",))

    def test_valid_untrusted_proposals_are_validated_then_materialized(self) -> None:
        first = proposal(snapshot=self.snapshot)
        second = proposal(action_id="derive-docs", scope="planner-docs", dependencies=(first.logical_action_id,), snapshot=self.snapshot)
        result = AIMissionPlanner(FixtureProvider((first, second))).plan(self.input, self.policy)
        self.assertIsNone(result.governance_refinement)
        self.assertEqual([action.id for intent in result.plan.intents for action in intent.actions], ["derive-contract", "derive-docs"])
        self.assertEqual(result.plan.intents[1].actions[0].dependencies, ("derive-contract",))

    def test_stale_snapshot_cannot_materialize(self) -> None:
        stale = PlanningSnapshot.from_planner_input(input_model(mission_state=self.input.mission_state.__class__("mission-1", 2)))
        with self.assertRaisesRegex(ProposalValidationError, "STALE_REDERIVE_REQUIRED"):
            ActionDerivationValidator().validate((proposal(snapshot=stale), proposal(action_id="derive-docs", scope="planner-docs", snapshot=stale)), stale, self.input, self.policy)

    def test_scope_authority_gates_and_risk_fail_closed(self) -> None:
        validator = ActionDerivationValidator()
        cases = (
            (proposal(scope="outside", snapshot=self.snapshot), "outside approved Mission"),
            (proposal(write_scopes=("outside",), snapshot=self.snapshot), "write scope"),
            (proposal(gates=(), snapshot=self.snapshot), "human gates"),
            (proposal(risks=(), snapshot=self.snapshot), "risk inputs"),
        )
        for first, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ProposalValidationError, message):
                validator.validate((first, proposal(action_id="derive-docs", scope="planner-docs", snapshot=self.snapshot)), self.snapshot, self.input, self.policy)

    def test_unknown_and_cyclic_dependencies_fail_closed(self) -> None:
        validator = ActionDerivationValidator()
        unknown = proposal(dependencies=("missing",), snapshot=self.snapshot)
        with self.assertRaisesRegex(ProposalValidationError, "unknown"):
            validator.validate((unknown, proposal(action_id="derive-docs", scope="planner-docs", snapshot=self.snapshot)), self.snapshot, self.input, self.policy)
        first = proposal(dependencies=("derive-docs",), snapshot=self.snapshot)
        second = proposal(action_id="derive-docs", scope="planner-docs", dependencies=("derive-contract",), snapshot=self.snapshot)
        with self.assertRaisesRegex(ProposalValidationError, "cycle"):
            validator.validate((first, second), self.snapshot, self.input, self.policy)

    def test_provider_cannot_omit_an_approved_scope(self) -> None:
        provider = FixtureProvider((proposal(snapshot=self.snapshot),))
        with self.assertRaisesRegex(ProposalValidationError, "cover every approved Mission scope"):
            AIMissionPlanner(provider).plan(self.input, self.policy)
        self.assertEqual(provider.calls, 1)

    def test_lifecycle_is_ordered_and_terminal_states_fail_closed(self) -> None:
        record = DerivationRecord("derivation-1", "mission-1", self.snapshot.digest, "1.0", "fixture-v1", DerivationLifecycle.SNAPSHOT_CREATED)
        running = record.transition(DerivationLifecycle.DERIVATION_REQUESTED).transition(DerivationLifecycle.PROVIDER_RUNNING)
        self.assertEqual(running.lifecycle, DerivationLifecycle.PROVIDER_RUNNING)
        with self.assertRaisesRegex(ValueError, "invalid"):
            record.transition(DerivationLifecycle.MATERIALIZED)

    def test_provider_adapter_binds_bounded_evidence_and_never_retries_ambiguity(self) -> None:
        request = ProviderDerivationRequest("derivation-1", self.snapshot, "fixture-provider", "fixture-1")
        evidence = ProviderInvocationEvidence("fixture-provider", "fixture-1", "1.0", request.digest, self.snapshot.digest,
                                              _digest("b"), ProviderSideEffectState.HAPPENED_AND_CONFIRMED)
        response = ProviderDerivationResponse(evidence, proposals=(proposal(snapshot=self.snapshot),))
        executor = FixtureExecutor(response)
        adapter = BoundedActionDerivationProvider(executor)
        self.assertEqual(adapter.invoke(request), response)
        self.assertEqual(executor.invocations, 1)
        ambiguous = BoundedActionDerivationProvider(FixtureExecutor(ProviderSideEffectState.MAY_HAVE_HAPPENED))
        self.assertEqual(ambiguous.reconcile(request), ProviderSideEffectState.MAY_HAVE_HAPPENED)

    def test_replan_identity_preserves_completed_history_and_avoids_churn(self) -> None:
        current = proposal(snapshot=self.snapshot)
        self.assertEqual(classify_replan_identity(current, current), DerivedActionIdentityState.UNCHANGED)
        modified = DerivedActionProposal(**{**current.__dict__, "objective": "Changed implementation."})
        self.assertEqual(classify_replan_identity(current, modified), DerivedActionIdentityState.MODIFIED_UNEXECUTED)
        self.assertEqual(classify_replan_identity(current, modified, completed=True), DerivedActionIdentityState.SUPERSEDED)
        deferred = DerivedActionProposal(**{**current.__dict__, "postponed": True})
        self.assertEqual(classify_replan_identity(current, deferred), DerivedActionIdentityState.DEFERRED)

    def test_validation_failure_is_persisted_as_closed_canonical_evidence(self) -> None:
        request = ProviderDerivationRequest("derivation-validation-failure", self.snapshot,
                                            "fixture-provider", "fixture-1")
        failure = ProposalValidationError("derived proposal write scope exceeds approved authority")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = RuntimeDatabase(root, path=root / "runtime.db")
            self.addCleanup(database.close)
            database.create_mission_state({
                "mission_id": "mission-1", "status": "APPROVED_PLANNABLE",
                "lifecycle": "APPROVED_PLANNABLE", "progress": {}, "resume": {},
                "execution_policy": {"write_scope": "NONE"}, "revision": 1,
                "admission_contract": {"mission": {"id": "mission-1"}},
            })
            saved = record_deterministic_validation_failure(
                database, request, policy_digest=_digest("b"), evidence_digest=_digest("c"),
                effective_contract_digest=_digest("d"), error=failure,
            )
            self.assertEqual(saved["lifecycle"], DerivationLifecycle.FAILED.value)
            self.assertEqual(saved["validation_failure_code"], "WRITE_SCOPE_EXCEEDED")
            self.assertNotIn(str(failure), str(saved))
            self.assertEqual(database.get_document("action_derivations", request.derivation_id), saved)
        self.assertEqual(deterministic_validation_failure_code(ProposalValidationError("untrusted sk-proj-value")),
                         "DETERMINISTIC_VALIDATION_REJECTED")


if __name__ == "__main__":
    unittest.main()
