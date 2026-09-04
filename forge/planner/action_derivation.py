"""Bounded Action Derivation stage of the one canonical AI Mission Planner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from forge.models.action_derivation import (
    DerivationPolicy, DerivedActionProposal, GovernanceRefinementRequired,
    PlanningSnapshot, ProposalValidationStatus, ValidatedDerivation,
)
from forge.models.mission_planner import ApprovedScope, MissionPlan, MissionPlannerInput, PlannedActionDefinition
from forge.planner.engine import MissionPlanner


class ActionDerivationProvider(Protocol):
    """Replaceable reasoning boundary. Its output is untrusted proposal data."""

    def derive(self, snapshot: PlanningSnapshot) -> tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired: ...


class ProposalValidationError(ValueError):
    """A provider proposal did not meet deterministic approved-Mission rules."""


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
