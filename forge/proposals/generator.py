"""Local-only deterministic Engineering Proposal generation for Forge 0.6."""

from __future__ import annotations

from collections.abc import Iterable

from forge.models import (
    EngineeringGoal,
    EngineeringIncrementProposal,
    EngineeringPlan,
    EngineeringProposal,
    EvidenceReference,
    ProposalCreationMetadata,
    ProposalDependencies,
    ProposalRationale,
    ProposalRisk,
    ProposalScope,
    ProposalStatus,
    RiskAssessment,
    RiskLevel,
    Workspace,
)


GENERATOR_NAME = "forge.engineering_proposal_generator"
GENERATOR_VERSION = "0.6"


class EngineeringProposalGenerator:
    """Transform validated planning declarations into one non-executing draft."""

    def generate(
        self,
        *,
        proposal_id: str,
        workspace: Workspace,
        plan: EngineeringPlan,
        goals: Iterable[EngineeringGoal],
        increment_proposals: Iterable[EngineeringIncrementProposal],
        increment_id: str,
        knowledge_references: Iterable[EvidenceReference] = (),
    ) -> EngineeringProposal:
        goals_by_id = {goal.id: goal for goal in goals}
        increments_by_id = {increment.id: increment for increment in increment_proposals}
        if increment_id not in plan.ordered_increment_ids:
            raise ValueError("proposal increment must be ordered by the engineering plan")
        increment = increments_by_id.get(increment_id)
        if increment is None:
            raise ValueError("proposal increment is required")
        if increment.goal_id not in goals_by_id:
            raise ValueError("proposal goal is required")
        goal = goals_by_id[increment.goal_id]
        if plan.workspace_id != workspace.id or goal.workspace_id != workspace.id:
            raise ValueError("proposal workspace, plan, and goal must share an identity")

        position = plan.ordered_increment_ids.index(increment_id)
        previous = plan.ordered_increment_ids[:position]
        evidence = self._unique_evidence(
            (*goal.evidence_references, *increment.evidence_references, *plan.evidence_references, *tuple(knowledge_references))
        )
        return EngineeringProposal(
            id=proposal_id,
            title=f"Engineering proposal: {increment.id}",
            objective=goal.description,
            expected_outcome=increment.expected_outcome,
            creation_metadata=ProposalCreationMetadata(GENERATOR_NAME, GENERATOR_VERSION, workspace.id, plan.id, increment.id),
            scope=ProposalScope((increment.scope,), ("Repository execution, tool invocation, commits, and approval are excluded.",), increment.affected_capabilities),
            rationale=ProposalRationale(increment.rationale, f"Advances engineering goal {goal.id} through plan {plan.id}.", "Preserves the planning and supplied knowledge evidence references."),
            dependencies=ProposalDependencies(increment.dependencies, previous, plan.assumptions),
            risk=ProposalRisk(
                RiskAssessment(increment.risk_level, "Derived from the planned increment risk classification."),
                RiskAssessment(RiskLevel.LOW, "The artifact remains governed intention and does not approve or execute work."),
                RiskAssessment(increment.risk_level, "Scope is bounded to the declared increment and its affected capabilities."),
            ),
            evidence_references=evidence,
            status=ProposalStatus.DRAFT,
        )

    @staticmethod
    def _unique_evidence(references: tuple[EvidenceReference, ...]) -> tuple[EvidenceReference, ...]:
        seen: set[tuple[str, str, str, str, str]] = set()
        unique: list[EvidenceReference] = []
        for reference in references:
            key = (reference.kind.value, reference.source_id, reference.source_version, reference.reference, reference.location)
            if key not in seen:
                seen.add(key)
                unique.append(reference)
        return tuple(unique)
