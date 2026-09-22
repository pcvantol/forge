"""The production provider snapshot carries safe, current continuation facts."""

from dataclasses import replace
from hashlib import sha256
import json
import unittest

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.action_derivation import DerivationPolicy, PlanningSnapshot
from forge.models.criterion_assessment import (
    ApprovedRepositoryEvidenceSource, CriterionAssessmentContract, CriterionEvidenceRequirement,
)
from forge.models.criterion_observation import CriterionObservation
from forge.models.mission_completion import MissionCriterionEvaluationStatus, mission_criterion_id
from forge.models.mission_planner import (
    ApprovedScope, MAX_CONTINUATION_CONTEXT_BYTES, MissionContinuationContext, MissionCriterionPlanningState,
    MissionPlannerInput, MissionPlanningState, PlanningEvidence, PlanningInputKind, planning_digest,
)
from forge.planner.action_derivation import AIMissionPlanner
from forge.planner.codex_cli_session import _parse_response, _prompt
from forge.planner.durable_derivation import _replay_boundary_digest
from forge.planner.provider_adapter import ProviderDerivationRequest
from tests.test_action_derivation import input_model


def digest(value):
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def fixture():
    base = input_model()
    contracts = tuple(CriterionAssessmentContract(f"K{number}", (
        CriterionEvidenceRequirement(f"requirement-{number}", kind="repository_json",
                                     artifact_path=f"evidence/k{number}.json", json_pointer="/delivered", expected_json="true"),
    )) for number in (1, 2))
    mission = replace(base.mission, scope=(base.mission.scope[0],), acceptance_criteria=("K1", "K2"),
                      criterion_assessment_contracts=contracts, maximum_actions=4,
                      maximum_consecutive_no_progress_actions=2,
                      repository_evidence_source=ApprovedRepositoryEvidenceSource("repository-synthetic", "example/fixture"))
    planning = {"scope": list(mission.scope), "write_scopes": ["evidence"], "non_goals": ["unrelated work"],
                "risk_inputs": ["scope-drift"], "human_gates": ["protected delivery"], "dependencies": ["host"],
                "context_input_bound": 16000, "context_output_bound": 4000, "provenance_revision": "approved-r1",
                "criterion_assessment_contracts": [item.to_dict() for item in contracts],
                "maximum_actions": 4, "maximum_consecutive_no_progress_actions": 2,
                "repository_evidence_source": mission.repository_evidence_source.to_dict()}
    action = EngineeringAction(1, "action-a", "intent-a", "1", "Deliver only K1.", ("K1 realization",),
                               status=EngineeringActionStatus.COMPLETE).to_dict()
    repository = {"mission_id": mission.id, "intent_id": "intent-a", "intent_revision": "1", "action_id": "action-a",
                  "runtime_prompt_id": "prompt-a", "correlation_id": "correlation-a", "host_run_id": "run-a",
                  "repository_id": "repository-synthetic", "repository_revision": "a" * 40,
                  "report_id": "report-a", "content_digest": "sha256:" + "b" * 64}
    terminal = {"host_id": "host-synthetic", "correlation_id": "correlation-a", "host_run_id": "run-a",
                "receipt_id": "receipt-a", "report_id": "report-a", "outcome": "complete", "repository_evidence": repository}
    truth = {"source_id": "truth-a", "revision": "a" * 40, "locator": "repository://synthetic/a",
             "content_digest": "sha256:" + "c" * 64}
    assessments = []
    states = []
    for index, contract in enumerate(contracts):
        criterion_id = mission_criterion_id(mission.id, contract.criterion)
        status = "PROVEN" if index == 0 else "UNSATISFIED"
        observation = CriterionObservation(
            mission.id, digest(mission.to_dict()), criterion_id, contract.digest,
            contract.requirements[0].requirement_id, "receipt-a", "action-a", "report-a", "a" * 40,
            "sha256:" + "b" * 64, "repository_json", "example/fixture", contract.requirements[0].artifact_path,
            "sha256:" + "d" * 64, "true" if index == 0 else '"PRIVATE_OBSERVED_VALUE"',
            "PASS" if index == 0 else "FAIL", "MATCHED" if index == 0 else "ASSERTION_MISMATCH",
            requirement_digest=contract.requirements[0].digest, json_pointer="/delivered", candidate_revision="a" * 40)
        assessments.append({"criterion_id": criterion_id, "criterion": contract.criterion,
                            "status": status, "reason": observation.reason, "contract_digest": contract.digest,
                            "requirement_results": [{"requirement_id": observation.requirement_id,
                                "requirement_digest": contract.requirements[0].digest, "status": status,
                                "reason": observation.reason, "observation_ids": [observation.id]}],
                            "observations": [observation.to_dict()]})
        states.append(MissionCriterionPlanningState(criterion_id, MissionCriterionEvaluationStatus(status)))
    values = {"planning": planning, "actions": (action,), "execution_history": (terminal,),
              "completion": {"criteria": assessments}, "repository_truth": truth}
    context = MissionContinuationContext.from_runtime(mission, **values)
    evidence = (*base.evidence, PlanningEvidence(PlanningInputKind.EXECUTION_EVIDENCE, "receipt-a", "2", "runtime://receipt-a", repository["content_digest"]))
    scopes = (ApprovedScope(mission.scope[0], base.approved_scopes[0].capability_id,
                            base.approved_scopes[0].architecture_references, (), allow_provider_derivation=True),)
    source = MissionPlannerInput(mission, MissionPlanningState(mission.id, 2, ("action-a",), (), tuple(states), context), evidence, scopes)
    return source, values


class CriterionPlanningContextTests(unittest.TestCase):
    def test_local_host_failure_is_retained_without_inventing_a_successful_receipt(self):
        source, values = fixture()
        failed = {"outcome": "failed", "diagnostic_references": ["runner:host_evidence_failed"],
                  "failure_code": "PRIVATE_EXCEPTION_CODE"}
        context = MissionContinuationContext.from_runtime(
            source.mission, **{**values, "execution_history": (failed, *values["execution_history"])})
        projected = context.to_dict()["terminal_evidence"]
        self.assertEqual(projected[0], {"outcome": "failed", "receipt_id": None,
            "repository_evidence": None, "reason": "HOST_EVIDENCE_UNAVAILABLE"})
        self.assertEqual(projected[1]["outcome"], "complete")
        self.assertNotIn("PRIVATE_EXCEPTION_CODE", context.document_json)

    def test_legacy_input_and_snapshot_keep_prechange_digest(self):
        source = input_model()
        snapshot = PlanningSnapshot.from_planner_input(source)
        self.assertEqual(planning_digest(source), "sha256:76f94ba71d6298cfd60d0bf1bef094842d414fc5ae7c68f4fda0866446eeec22")
        self.assertEqual(snapshot.digest, "sha256:d2b14483f6108ee20c62f2c4702563bbfa81efd5d88169372cc3228db5078017")
        self.assertNotIn("continuation_context", source.mission_state.to_dict())
        self.assertNotIn("approved_mission", snapshot.to_dict())
        self.assertNotIn("continuation_context", snapshot.to_dict())

    def test_actual_codex_prompt_receives_authority_realization_remaining_work_and_history(self):
        source, _ = fixture()
        snapshot = PlanningSnapshot.from_planner_input(source)
        prompt = _prompt(ProviderDerivationRequest("synthetic-attempt", snapshot, "synthetic-provider", None))
        self.assertEqual(prompt["snapshot"]["approved_mission"], source.mission.to_dict())
        context = prompt["snapshot"]["continuation_context"]
        self.assertEqual(context["approved_planning"]["provenance_revision"], "approved-r1")
        self.assertEqual(context["approved_planning"]["maximum_actions"], 4)
        self.assertEqual(context["criterion_assessments"][0]["status"], "PROVEN")
        self.assertEqual(context["criterion_assessments"][1]["status"], "UNSATISFIED")
        self.assertEqual(context["criterion_assessments"][1]["requirement_results"][0]["reason"], "ASSERTION_MISMATCH")
        self.assertEqual(context["prior_actions"][0]["objective"], "Deliver only K1.")
        self.assertEqual(context["prior_actions"][0]["observed_contributions"][0]["observation_result"], "PASS")
        self.assertEqual(context["terminal_evidence"][0]["receipt_id"], "receipt-a")
        self.assertEqual(context["repository_truth"]["revision"], "a" * 40)
        self.assertNotIn("observed_json", json.dumps(prompt))
        self.assertNotIn("PRIVATE_OBSERVED_VALUE", json.dumps(prompt))

    def test_context_is_immutable_and_bound_in_snapshot_and_replay(self):
        source, values = fixture()
        snapshot = PlanningSnapshot.from_planner_input(source)
        context_copy = source.mission_state.continuation_context.to_dict()
        context_copy["prior_actions"][0]["objective"] = "tampered copy"
        self.assertEqual(snapshot, PlanningSnapshot.from_planner_input(source))
        values["actions"] = ({**values["actions"][0], "objective": "A different realized contribution"},)
        context = MissionContinuationContext.from_runtime(source.mission, **values)
        changed = replace(source, mission_state=replace(source.mission_state, continuation_context=context))
        successor = PlanningSnapshot.from_planner_input(changed)
        self.assertNotEqual(snapshot.digest, successor.digest)
        self.assertNotEqual(_replay_boundary_digest(snapshot), _replay_boundary_digest(successor))
        self.assertFalse(snapshot.is_current_for(changed))

    def test_contract_snapshot_cannot_drop_contracts_criteria_actions_or_receipts(self):
        source, _ = fixture()
        with self.assertRaisesRegex(ValueError, "requires continuation context"):
            replace(source, mission_state=replace(source.mission_state, continuation_context=None))
        for key in ("criterion_assessments", "prior_actions", "terminal_evidence"):
            document = source.mission_state.continuation_context.to_dict()
            document[key] = []
            context = MissionContinuationContext(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            with self.subTest(key=key), self.assertRaises(ValueError):
                replace(source, mission_state=replace(source.mission_state, continuation_context=context))
        document = source.mission_state.continuation_context.to_dict()
        document["approved_planning"]["maximum_actions"] = 99
        context = MissionContinuationContext(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, "differs from the approved"):
            replace(source, mission_state=replace(source.mission_state, continuation_context=context))

    def test_candidate_identity_is_preserved_separately_from_delivery_in_terminal_summary(self):
        source, values = fixture()
        values["execution_history"][0]["repository_evidence"]["candidate_revision"] = "d" * 40
        context = MissionContinuationContext.from_runtime(source.mission, **values)
        repository = context.to_dict()["terminal_evidence"][0]["repository_evidence"]
        self.assertEqual(repository["candidate_revision"], "d" * 40)
        self.assertEqual(repository["repository_revision"], "a" * 40)
        self.assertNotEqual(source.mission_state.continuation_context, context)

    def test_verified_delegation_preserves_lineage_without_fabricating_host_receipt(self):
        source, values = fixture()
        values["execution_history"] = ({"delegation_id": "delegation-a", "outcome": "verified_external_completion"},)
        values["delegations"] = ({"id": "delegation-a", "action_id": "action-a", "result_state": "accepted",
                                   "verification": {"verified": True, "private_report": "OMIT_FROM_PROVIDER"}},)
        context = MissionContinuationContext.from_runtime(source.mission, **values)
        changed = replace(source, mission_state=replace(source.mission_state, continuation_context=context))
        document = PlanningSnapshot.from_planner_input(changed).to_dict()["continuation_context"]
        self.assertEqual(document["terminal_evidence"], [])
        self.assertEqual(document["verified_delegations"], [{"delegation_id": "delegation-a",
                         "action_id": "action-a", "outcome": "verified_external_completion"}])
        self.assertNotIn("OMIT_FROM_PROVIDER", json.dumps(document))
        self.assertNotEqual(PlanningSnapshot.from_planner_input(source).digest,
                            PlanningSnapshot.from_planner_input(changed).digest)
        values["delegations"] = ()
        with self.assertRaisesRegex(ValueError, "verified Action lineage"):
            MissionContinuationContext.from_runtime(source.mission, **values)

    def test_context_growth_fails_closed_before_provider_transport(self):
        source, values = fixture()
        values["actions"] = ({**values["actions"][0], "objective": "x" * MAX_CONTINUATION_CONTEXT_BYTES},)
        with self.assertRaisesRegex(ValueError, "byte bound"):
            MissionContinuationContext.from_runtime(source.mission, **values)

    def test_context_cannot_omit_authority_or_include_observed_values(self):
        source, values = fixture()
        values["planning"] = {key: value for key, value in values["planning"].items() if key != "write_scopes"}
        with self.assertRaisesRegex(ValueError, "lacks approved planning authority"):
            MissionContinuationContext.from_runtime(source.mission, **values)
        document = source.mission_state.continuation_context.to_dict()
        document["criterion_assessments"][0]["observation_summaries"][0]["observed_json"] = "true"
        with self.assertRaisesRegex(ValueError, "provenance only"):
            MissionContinuationContext(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False))

    def test_same_production_output_parser_and_materializer_accept_a_remaining_criterion_proposal(self):
        source, _ = fixture()
        snapshot = PlanningSnapshot.from_planner_input(source)
        request = ProviderDerivationRequest("synthetic-attempt", snapshot, "synthetic-provider", None)
        remaining = next(item for item in snapshot.criteria if item.criterion == "K2")
        response = {"result": {"kind": "proposals", "proposals": [{
            "logical_action_id": "action-b", "scope": source.mission.scope[0], "objective": "Realize K2 from the missing artifact assertion.",
            "dependencies": [], "write_scopes": ["evidence"], "expected_evidence": ["K2 artifact assertion"],
            "validation_strategy": ["observe K2"], "priority": 1, "postponed": False,
            "human_gates": ["protected delivery"], "risk_inputs": ["scope-drift"],
            "source_evidence_refs": [item.source_id for item in snapshot.evidence],
            "mission_gap": {"classification": "UNPROVEN_MISSION_CRITERION", "criterion_ids": [remaining.criterion_id],
                "triggering_evidence_refs": ["receipt-a"], "planning_snapshot_digest": snapshot.digest,
                "causal_objective": "Realize K2 from the missing artifact assertion.", "mission_caused_by_action_ids": []},
        }]}}
        proposals, refinement = _parse_response(
            request, response, "1.0",
            DerivationPolicy(("evidence",), ("protected delivery",), ("scope-drift",)),
        )
        self.assertIsNone(refinement)
        class ParsedProvider:
            def derive(self, actual_snapshot):
                if actual_snapshot != snapshot:
                    raise AssertionError("provider snapshot changed")
                return proposals
        result = AIMissionPlanner(ParsedProvider()).plan(source, DerivationPolicy(("evidence",), ("protected delivery",), ("scope-drift",)))
        self.assertIsNone(result.governance_refinement)
        self.assertEqual(result.plan.intents[0].actions[0].id, "action-b")


if __name__ == "__main__":
    unittest.main()
