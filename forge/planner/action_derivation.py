"""Bounded Action Derivation stage of the one canonical AI Mission Planner."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Protocol

from forge.models.action_derivation import (
    DerivationLifecycle, DerivationPolicy, DerivationRecord, DerivedActionProposal, GovernanceRefinementRequired,
    PlanningSnapshot, ProposalValidationStatus, ValidatedDerivation,
)
from forge.models.mission_planner import ApprovedScope, MissionPlan, MissionPlannerInput, PlannedActionDefinition
from forge.planner.engine import MissionPlanner


class ActionDerivationProvider(Protocol):
    """Replaceable reasoning boundary. Its output is untrusted proposal data."""

    def derive(self, snapshot: PlanningSnapshot) -> tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired: ...


class ProposalValidationError(ValueError):
    """A provider proposal did not meet deterministic approved-Mission rules."""


_VALIDATION_FAILURE_CODES = {
    ProposalValidationStatus.STALE_REDERIVE_REQUIRED.value: "STALE_SNAPSHOT",
    "at least one derived proposal is required": "EMPTY_PROPOSALS",
    "derived action identities must be unique": "DUPLICATE_ACTION_ID",
    "derived proposal scope is outside approved Mission": "SCOPE_OUTSIDE_MISSION",
    "derived proposal provenance does not bind the current planning snapshot": "STALE_PROVENANCE",
    "derived proposal write scope exceeds approved authority": "WRITE_SCOPE_EXCEEDED",
    "derived proposal weakens required human gates": "HUMAN_GATES_WEAKENED",
    "derived proposal omits required risk inputs": "RISK_INPUTS_OMITTED",
    "derived proposal dependency target is unknown": "UNKNOWN_DEPENDENCY",
    "derived proposal dependency graph contains a cycle": "CYCLIC_DEPENDENCY",
}


def deterministic_validation_failure_code(error: ProposalValidationError) -> str:
    """Classify a deterministic rejection without retaining provider data."""
    return _VALIDATION_FAILURE_CODES.get(error.args[0] if error.args else None, "DETERMINISTIC_VALIDATION_REJECTED")


def _is_sha256_digest(value: object) -> bool:
    return (isinstance(value, str) and value.startswith("sha256:") and len(value) == 71
            and all(character in "0123456789abcdef" for character in value[7:]))


def _record_deterministic_validation_failure(database, request, *, policy_digest: str,
                                             evidence_digest: str, effective_contract_digest: str,
                                             provider_result_digest: str, preflight_receipt: dict[str, object],
                                             error: ProposalValidationError,
                                             reattempt_lineage: dict[str, object] | None = None) -> dict[str, object]:
    """Persist bounded FAILED lifecycle evidence through the canonical store only."""
    if not all(_is_sha256_digest(value) for value in
               (policy_digest, evidence_digest, effective_contract_digest,
                provider_result_digest, request.snapshot.digest,
                preflight_receipt.get("request_digest"))):
        raise ValueError("complete canonical validation-failure bindings are required")
    receipt_id, main_head = preflight_receipt.get("receipt_id"), preflight_receipt.get("main_head")
    if (not isinstance(receipt_id, str) or not receipt_id
            or not isinstance(main_head, str) or len(main_head) != 40
            or any(character not in "0123456789abcdef" for character in main_head)):
        raise ValueError("complete canonical token-preflight provenance is required")
    code = deterministic_validation_failure_code(error)
    lineage = _validated_reattempt_lineage(reattempt_lineage, request, policy_digest, evidence_digest,
                                           effective_contract_digest, preflight_receipt["request_digest"])
    validation_digest = "sha256:" + sha256(json.dumps({
        "code": code, "snapshot_digest": request.snapshot.digest, "policy_digest": policy_digest,
        "evidence_digest": evidence_digest, "effective_contract_digest": effective_contract_digest,
        "provider_result_digest": provider_result_digest,
        "generation_request_digest": preflight_receipt["request_digest"],
        "preflight_receipt_id": receipt_id, "main_head": main_head,
        "reattempt_lineage": lineage,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    document = DerivationRecord(request.derivation_id, request.snapshot.mission_id, request.snapshot.digest,
                                "1.0", policy_digest, DerivationLifecycle.FAILED,
                                proposal_digest=provider_result_digest,
                                validation_digest=validation_digest).to_dict()
    document.update({"validation_failure_code": code, "evidence_digest": evidence_digest,
                     "effective_contract_digest": effective_contract_digest,
                     "provider_result_digest": provider_result_digest,
                     "generation_request_digest": preflight_receipt["request_digest"],
                     "preflight_receipt_id": receipt_id, "main_head": main_head,
                     "provider_output_untrusted": True, "runtime_action_executed": False,
                     **lineage})
    return database.save_action_derivation(document)


def _record_deterministic_validation_success(database, request, *, policy_digest: str,
                                             evidence_digest: str, effective_contract_digest: str,
                                             provider_result_digest: str,
                                             preflight_receipt: dict[str, object],
                                             validated: "ValidatedDerivation",
                                             reattempt_lineage: dict[str, object] | None = None) -> dict[str, object]:
    """Persist a bounded, non-materializing successful validation result.

    The validated proposals remain provider data and are deliberately not
    stored here. The result digest and canonical authority bindings make the
    pass auditable without turning provider output into execution authority.
    """
    if not isinstance(validated, ValidatedDerivation):
        raise ValueError("a successful derivation record requires deterministic validation")
    if not all(_is_sha256_digest(value) for value in
               (policy_digest, evidence_digest, effective_contract_digest,
                provider_result_digest, request.snapshot.digest,
                preflight_receipt.get("request_digest"))):
        raise ValueError("complete canonical validation-success bindings are required")
    receipt_id, main_head = preflight_receipt.get("receipt_id"), preflight_receipt.get("main_head")
    if (not isinstance(receipt_id, str) or not receipt_id
            or not isinstance(main_head, str) or len(main_head) != 40
            or any(character not in "0123456789abcdef" for character in main_head)):
        raise ValueError("complete canonical token-preflight provenance is required")
    lineage = _validated_reattempt_lineage(reattempt_lineage, request, policy_digest, evidence_digest,
                                           effective_contract_digest, preflight_receipt["request_digest"])
    validation_digest = "sha256:" + sha256(json.dumps({
        "result": "PASS", "snapshot_digest": request.snapshot.digest, "policy_digest": policy_digest,
        "evidence_digest": evidence_digest, "effective_contract_digest": effective_contract_digest,
        "provider_result_digest": provider_result_digest,
        "generation_request_digest": preflight_receipt["request_digest"],
        "preflight_receipt_id": receipt_id, "main_head": main_head,
        "reattempt_lineage": lineage,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    document = DerivationRecord(request.derivation_id, request.snapshot.mission_id, request.snapshot.digest,
                                "1.0", policy_digest, DerivationLifecycle.VALIDATED,
                                proposal_digest=provider_result_digest,
                                validation_digest=validation_digest).to_dict()
    document.update({"validation_result": "PASS", "evidence_digest": evidence_digest,
                     "effective_contract_digest": effective_contract_digest,
                     "provider_result_digest": provider_result_digest,
                     "generation_request_digest": preflight_receipt["request_digest"],
                     "preflight_receipt_id": receipt_id, "main_head": main_head,
                     "provider_output_untrusted": True, "runtime_action_executed": False,
                     "action_materialized": False, **lineage})
    return database.save_action_derivation(document)


def _validated_reattempt_lineage(lineage: dict[str, object] | None, request, policy_digest: str,
                                 evidence_digest: str, effective_contract_digest: str,
                                 request_digest: object) -> dict[str, object]:
    """Copy only canonically consumed successor lineage into a terminal record."""
    if lineage is None:
        return {}
    required = ("authorization_id", "predecessor_attempt_id", "reattempt_reason", "attempt_sequence",
                "successor_attempt_id", "planning_snapshot_digest", "g011_policy_digest",
                "evidence_digest", "effective_contract_digest", "provider_request_digest")
    if any(field not in lineage for field in required):
        raise ValueError("complete consumed reattempt lineage is required")
    if (lineage["successor_attempt_id"] != request.derivation_id
            or lineage["planning_snapshot_digest"] != request.snapshot.digest
            or lineage["g011_policy_digest"] != policy_digest
            or lineage["evidence_digest"] != evidence_digest
            or lineage["effective_contract_digest"] != effective_contract_digest
            or lineage["provider_request_digest"] != request_digest):
        raise ValueError("consumed reattempt lineage does not bind terminal derivation")
    return {field: lineage[field] for field in ("authorization_id", "predecessor_attempt_id",
                                                 "reattempt_reason", "attempt_sequence")}


class ActionDerivationValidator:
    """Pure, fail-closed validation before deterministic graph materialization."""

    def validate(
        self,
        proposals: tuple[DerivedActionProposal, ...],
        snapshot: PlanningSnapshot,
        planning_input: MissionPlannerInput,
        policy: DerivationPolicy,
    ) -> ValidatedDerivation:
        if not snapshot.is_current_for(planning_input):
            raise ProposalValidationError(ProposalValidationStatus.STALE_REDERIVE_REQUIRED.value)
        if not proposals:
            raise ProposalValidationError("at least one derived proposal is required")
        ids = {proposal.logical_action_id for proposal in proposals}
        if len(ids) != len(proposals):
            raise ProposalValidationError("derived action identities must be unique")
        mission_scopes = set(planning_input.mission.scope)
        for proposal in proposals:
            if proposal.scope not in mission_scopes:
                raise ProposalValidationError("derived proposal scope is outside approved Mission")
            if proposal.provenance.planning_snapshot_id != snapshot.id or proposal.provenance.planning_snapshot_digest != snapshot.digest:
                raise ProposalValidationError("derived proposal provenance does not bind the current planning snapshot")
            if not set(proposal.write_scopes) <= set(policy.allowed_write_scopes):
                raise ProposalValidationError("derived proposal write scope exceeds approved authority")
            if not set(policy.required_human_gates) <= set(proposal.human_gates):
                raise ProposalValidationError("derived proposal weakens required human gates")
            if not set(policy.required_risk_inputs) <= set(proposal.risk_inputs):
                raise ProposalValidationError("derived proposal omits required risk inputs")
            unknown = set(proposal.dependencies) - ids
            if unknown:
                raise ProposalValidationError("derived proposal dependency target is unknown")
        self._assert_acyclic(proposals)
        return ValidatedDerivation(snapshot, proposals)

    @staticmethod
    def _assert_acyclic(proposals: tuple[DerivedActionProposal, ...]) -> None:
        graph = {proposal.logical_action_id: set(proposal.dependencies) for proposal in proposals}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ProposalValidationError("derived proposal dependency graph contains a cycle")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in sorted(graph):
            visit(node)


def planner_input_from_derivation(
    planning_input: MissionPlannerInput, validated: ValidatedDerivation,
) -> MissionPlannerInput:
    """Deterministically project validated rich data into the existing planner input."""
    if not validated.snapshot.is_current_for(planning_input):
        raise ProposalValidationError(ProposalValidationStatus.STALE_REDERIVE_REQUIRED.value)
    by_scope: dict[str, list[PlannedActionDefinition]] = {scope.scope: [] for scope in planning_input.approved_scopes}
    for proposal in validated.proposals:
        by_scope[proposal.scope].append(PlannedActionDefinition(
            proposal.logical_action_id, proposal.objective, proposal.expected_evidence,
            proposal.validation_strategy, proposal.priority, proposal.postponed,
            dependencies=proposal.dependencies,
        ))
    scopes = tuple(ApprovedScope(scope.scope, scope.capability_id, scope.architecture_references, tuple(by_scope[scope.scope]))
                   for scope in planning_input.approved_scopes if by_scope[scope.scope])
    # An approved Mission must still be fully represented. A provider cannot omit a scope.
    if {scope.scope for scope in scopes} != set(planning_input.mission.scope):
        raise ProposalValidationError("derived proposals do not cover every approved Mission scope")
    return MissionPlannerInput(planning_input.mission, planning_input.mission_state,
                               planning_input.evidence, scopes)


@dataclass(frozen=True)
class DerivationResult:
    snapshot: PlanningSnapshot
    validated: ValidatedDerivation | None
    governance_refinement: GovernanceRefinementRequired | None
    plan: MissionPlan | None


class AIMissionPlanner:
    """One canonical planner pipeline: derive, validate, then materialize."""

    def __init__(self, provider: ActionDerivationProvider, validator: ActionDerivationValidator | None = None,
                 materializer: MissionPlanner | None = None) -> None:
        self._provider = provider
        self._validator = validator or ActionDerivationValidator()
        self._materializer = materializer or MissionPlanner()

    def plan(self, planning_input: MissionPlannerInput, policy: DerivationPolicy) -> DerivationResult:
        snapshot = PlanningSnapshot.from_planner_input(planning_input)
        proposed = self._provider.derive(snapshot)
        if isinstance(proposed, GovernanceRefinementRequired):
            return DerivationResult(snapshot, None, proposed, None)
        validated = self._validator.validate(proposed, snapshot, planning_input, policy)
        return DerivationResult(snapshot, validated, None,
                                self._materializer.plan(planner_input_from_derivation(planning_input, validated)))
