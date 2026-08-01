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
from forge.models.runtime_prompt import (
    RuntimePrompt,
    RuntimePromptGenerationRequest,
    RuntimePromptSection,
    RuntimePromptSectionKind,
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
        if not proposal.evidence_references:
            raise ValueError("prompt artifact source proposal must contain evidence")
        if not all((proposal.scope.included_work, proposal.scope.excluded_work, proposal.scope.affected_capabilities)):
            raise ValueError("prompt artifact source proposal must contain a complete scope")
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


class RuntimePromptGenerator:
    """Derive the canonical abstract prompt structure without a provider template.

    Provider definitions establish provenance only.  Concrete provider wording
    belongs to a later generator implementation.
    """

    def generate(self, *, prompt_id: str, request: RuntimePromptGenerationRequest) -> RuntimePrompt:
        context = request.context
        sections = (
            RuntimePromptSection(
                RuntimePromptSectionKind.CONTEXT,
                (request.intent.title,),
                context.architecture_handbook + context.constitution + context.workspace + context.capabilities,
            ),
            RuntimePromptSection(RuntimePromptSectionKind.OBJECTIVE, (request.intent.objective,)),
            RuntimePromptSection(RuntimePromptSectionKind.REPOSITORY, ("Use the declared repository context.",), context.repository),
            RuntimePromptSection(RuntimePromptSectionKind.CONSTRAINTS, request.constraints),
            RuntimePromptSection(RuntimePromptSectionKind.VALIDATION, request.validation),
            RuntimePromptSection(RuntimePromptSectionKind.DELIVERABLES, request.deliverables),
        )
        return RuntimePrompt(
            id=prompt_id,
            source_intent_id=request.intent.id,
            source_intent_revision=request.intent.revision,
            source_action_id=request.action.id,
            provider_definition=request.provider_definition,
            generation_request_digest=request.digest(),
            sections=sections,
        )
