"""Local-only deterministic Engineering Prompt Artifact generation for Forge 0.7."""

from __future__ import annotations

from collections.abc import Iterable

from forge.models import (
    EngineeringPromptArtifact,
    EngineeringProposal,
    ExecutionInstructions,
    PromptArtifactContext,
    PromptArtifactObjective,
    PromptArtifactScope,
    ProposalStatus,
    Repository,
    SourceProposalReference,
    ValidationRequirements,
    Workspace,
)


class EngineeringPromptArtifactGenerator:
    """Transform an approved proposal into a portable instruction draft."""

    def generate(
        self,
        *,
        artifact_id: str,
        artifact_version: str,
        created_at: str,
        proposal: EngineeringProposal,
        workspace: Workspace,
        repository: Repository,
        success_criteria: Iterable[str],
        engineering_task_description: str,
        validation_expectations: Iterable[str],
        constraints: Iterable[str],
        required_checks: Iterable[str],
        expected_evidence: Iterable[str],
        completion_criteria: Iterable[str],
    ) -> EngineeringPromptArtifact:
        if proposal.status is not ProposalStatus.APPROVED:
            raise ValueError("prompt artifact source proposal must be approved")
        if proposal.creation_metadata.workspace_id != workspace.id:
            raise ValueError("prompt artifact proposal and workspace must share an identity")
        return EngineeringPromptArtifact(
            id=artifact_id,
            version=artifact_version,
            created_at=created_at,
            source_proposal=SourceProposalReference(proposal.id, proposal.schema_version),
            context=PromptArtifactContext(
                workspace.id,
                repository.id,
                repository.repository,
                workspace.engineering_mode.value,
                workspace.governance_profile.value,
                proposal.scope.affected_capabilities,
            ),
            objective=PromptArtifactObjective(proposal.objective, proposal.expected_outcome, tuple(success_criteria)),
            scope=PromptArtifactScope(proposal.scope.included_work, proposal.scope.excluded_work, proposal.scope.affected_capabilities),
            evidence_references=proposal.evidence_references,
            execution_instructions=ExecutionInstructions(engineering_task_description, tuple(validation_expectations), tuple(constraints)),
            validation_requirements=ValidationRequirements(tuple(required_checks), tuple(expected_evidence), tuple(completion_criteria)),
        )
