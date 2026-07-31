"""Versioned, non-executing Engineering Prompt Artifact contracts for Forge 0.7."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .planning import EvidenceReference


PROMPT_ARTIFACT_SCHEMA_VERSION = "0.7"


class PromptArtifactStatus(str, Enum):
    """Artifact lifecycle; a ready artifact remains an instruction, not execution."""

    DRAFT = "DRAFT"
    READY = "READY"


@dataclass(frozen=True)
class SourceProposalReference:
    id: str
    version: str

    def __post_init__(self) -> None:
        if not self.id or not self.version:
            raise ValueError("source proposal identity and version are required")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True)
class PromptArtifactContext:
    workspace_id: str
    repository_id: str
    repository_reference: str
    engineering_mode: str
    governance_profile: str
    capability_references: tuple[str, ...]

    def __post_init__(self) -> None:
        if not all((self.workspace_id, self.repository_id, self.repository_reference, self.engineering_mode, self.governance_profile)):
            raise ValueError("prompt artifact context is required")
        if len(self.capability_references) != len(set(self.capability_references)):
            raise ValueError("capability references must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "repository_id": self.repository_id,
            "repository_reference": self.repository_reference,
            "engineering_mode": self.engineering_mode,
            "governance_profile": self.governance_profile,
            "capability_references": list(self.capability_references),
        }


@dataclass(frozen=True)
class PromptArtifactObjective:
    engineering_goal: str
    expected_outcome: str
    success_criteria: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.engineering_goal or not self.expected_outcome or not self.success_criteria:
            raise ValueError("prompt artifact objective and success criteria are required")

    def to_dict(self) -> dict[str, Any]:
        return {"engineering_goal": self.engineering_goal, "expected_outcome": self.expected_outcome, "success_criteria": list(self.success_criteria)}


@dataclass(frozen=True)
class PromptArtifactScope:
    included_changes: tuple[str, ...]
    excluded_changes: tuple[str, ...]
    affected_areas: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.included_changes or not self.affected_areas:
            raise ValueError("prompt artifact scope must include changes and affected areas")

    def to_dict(self) -> dict[str, Any]:
        return {"included_changes": list(self.included_changes), "excluded_changes": list(self.excluded_changes), "affected_areas": list(self.affected_areas)}


@dataclass(frozen=True)
class ExecutionInstructions:
    engineering_task_description: str
    validation_expectations: tuple[str, ...]
    constraints: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.engineering_task_description:
            raise ValueError("engineering task description is required")

    def to_dict(self) -> dict[str, Any]:
        return {"engineering_task_description": self.engineering_task_description, "validation_expectations": list(self.validation_expectations), "constraints": list(self.constraints)}


@dataclass(frozen=True)
class ValidationRequirements:
    required_checks: tuple[str, ...]
    expected_evidence: tuple[str, ...]
    completion_criteria: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.required_checks or not self.expected_evidence or not self.completion_criteria:
            raise ValueError("validation requirements are required")

    def to_dict(self) -> dict[str, Any]:
        return {"required_checks": list(self.required_checks), "expected_evidence": list(self.expected_evidence), "completion_criteria": list(self.completion_criteria)}


@dataclass(frozen=True)
class EngineeringPromptArtifact:
    """A portable versioned instruction artifact; it does not perform work."""

    id: str
    version: str
    created_at: str
    source_proposal: SourceProposalReference
    context: PromptArtifactContext
    objective: PromptArtifactObjective
    scope: PromptArtifactScope
    evidence_references: tuple[EvidenceReference, ...]
    execution_instructions: ExecutionInstructions
    validation_requirements: ValidationRequirements
    status: PromptArtifactStatus = PromptArtifactStatus.DRAFT
    schema_version: str = PROMPT_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id or not self.version or not self.created_at:
            raise ValueError("prompt artifact identity, version, and creation timestamp are required")
        if self.schema_version != PROMPT_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("prompt artifact schema version is unsupported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "version": self.version,
            "created_at": self.created_at,
            "source_proposal": self.source_proposal.to_dict(),
            "context": self.context.to_dict(),
            "objective": self.objective.to_dict(),
            "scope": self.scope.to_dict(),
            "evidence_references": [reference.to_dict() for reference in self.evidence_references],
            "execution_instructions": self.execution_instructions.to_dict(),
            "validation_requirements": self.validation_requirements.to_dict(),
            "status": self.status.value,
        }


def transition_prompt_artifact(artifact: EngineeringPromptArtifact, status: PromptArtifactStatus) -> EngineeringPromptArtifact:
    """Return an explicitly ready artifact without executing or approving work."""

    if artifact.status is not PromptArtifactStatus.DRAFT or status is not PromptArtifactStatus.READY:
        raise ValueError("prompt artifact status transition is not permitted")
    from dataclasses import replace

    return replace(artifact, status=status)
