"""Immutable, non-executing contracts for Forge Architecture Reasoning 1.5.

These value types capture declared, evidence-grounded architectural reasoning.
They do not retrieve knowledge, infer findings, score an opportunity, create an
Engineering Proposal or Intent, invoke an AI provider, or execute work.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from .intent import IntentReference


ARCHITECTURE_REASONING_SCHEMA_VERSION = "1.5"


class ArchitecturalFindingCategory(str, Enum):
    """Closed categories used to classify a discovered architectural gap."""

    MISSING_ARCHITECTURE = "missing_architecture"
    MISSING_CAPABILITY = "missing_capability"
    ARCHITECTURAL_INCONSISTENCY = "architectural_inconsistency"
    REPOSITORY_DRIFT = "repository_drift"
    KNOWLEDGE_GAP = "knowledge_gap"
    GOVERNANCE_GAP = "governance_gap"
    DOCUMENTATION_GAP = "documentation_gap"


class ArchitecturalEvaluationCriterion(str, Enum):
    """Evaluation lenses; the model deliberately defines no scoring."""

    CONSTITUTIONAL_COMPLIANCE = "constitutional_compliance"
    ARCHITECTURE_ALIGNMENT = "architecture_alignment"
    CAPABILITY_IMPACT = "capability_impact"
    KNOWLEDGE_IMPACT = "knowledge_impact"
    ENGINEERING_VALUE = "engineering_value"
    COMPLEXITY = "complexity"
    DEPENDENCIES = "dependencies"


class ArchitecturalOpportunityStatus(str, Enum):
    """Human-governed opportunity disposition, not engineering authority."""

    IDENTIFIED = "IDENTIFIED"
    ACCEPTED_FOR_PROPOSAL = "ACCEPTED_FOR_PROPOSAL"
    DECLINED = "DECLINED"


@dataclass(frozen=True, order=True)
class RepositoryAssessment:
    """A declared assessment of repository knowledge and observable evidence."""

    repository_id: str
    summary: str
    knowledge_references: tuple[IntentReference, ...]
    repository_evidence: tuple[IntentReference, ...]
    schema_version: str = ARCHITECTURE_REASONING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ARCHITECTURE_REASONING_SCHEMA_VERSION:
            raise ValueError("architecture reasoning schema version is unsupported")
        if not self.repository_id or not self.summary:
            raise ValueError("repository assessment identity and summary are required")
        if not self.knowledge_references or not self.repository_evidence:
            raise ValueError("repository assessment requires knowledge and repository evidence references")
        for references, label in ((self.knowledge_references, "knowledge"), (self.repository_evidence, "repository evidence")):
            if len(references) != len(set(references)):
                raise ValueError(f"repository assessment {label} references must be unique")
            object.__setattr__(self, "knowledge_references" if label == "knowledge" else "repository_evidence", tuple(sorted(references)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repository_id": self.repository_id,
            "summary": self.summary,
            "knowledge_references": [reference.to_dict() for reference in self.knowledge_references],
            "repository_evidence": [reference.to_dict() for reference in self.repository_evidence],
        }


@dataclass(frozen=True, order=True)
class ArchitecturalFinding:
    """A traceable observation from one repository assessment."""

    id: str
    assessment_repository_id: str
    category: ArchitecturalFindingCategory
    description: str
    evidence_references: tuple[IntentReference, ...]
    affected_capabilities: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not all((self.id, self.assessment_repository_id, self.description)):
            raise ValueError("architectural finding identity, assessment, and description are required")
        if not self.evidence_references or not self.affected_capabilities:
            raise ValueError("architectural finding requires evidence and affected capability references")
        for references, label in ((self.evidence_references, "evidence"), (self.affected_capabilities, "affected capability")):
            if len(references) != len(set(references)):
                raise ValueError(f"architectural finding {label} references must be unique")
            object.__setattr__(self, "evidence_references" if label == "evidence" else "affected_capabilities", tuple(sorted(references)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "assessment_repository_id": self.assessment_repository_id,
            "category": self.category.value,
            "description": self.description,
            "evidence_references": [reference.to_dict() for reference in self.evidence_references],
            "affected_capabilities": [reference.to_dict() for reference in self.affected_capabilities],
        }


@dataclass(frozen=True)
class CapabilityImpact:
    """The declared capability effect of a possible architectural improvement."""

    summary: str
    capability_references: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not self.summary or not self.capability_references:
            raise ValueError("capability impact summary and references are required")
        if len(self.capability_references) != len(set(self.capability_references)):
            raise ValueError("capability impact references must be unique")
        object.__setattr__(self, "capability_references", tuple(sorted(self.capability_references)))

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "capability_references": [reference.to_dict() for reference in self.capability_references]}


@dataclass(frozen=True)
class RoadmapImpact:
    """The declared roadmap effect; roadmap context never grants approval."""

    summary: str
    roadmap_references: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not self.summary or not self.roadmap_references:
            raise ValueError("roadmap impact summary and references are required")
        if len(self.roadmap_references) != len(set(self.roadmap_references)):
            raise ValueError("roadmap impact references must be unique")
        object.__setattr__(self, "roadmap_references", tuple(sorted(self.roadmap_references)))

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "roadmap_references": [reference.to_dict() for reference in self.roadmap_references]}


@dataclass(frozen=True)
class ArchitecturalEvaluation:
    """A human-readable evaluation with required lenses and no numeric score."""

    opportunity_id: str
    criteria: tuple[ArchitecturalEvaluationCriterion, ...]
    conclusion: str
    constitutional_references: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not self.opportunity_id or not self.conclusion or not self.constitutional_references:
            raise ValueError("architectural evaluation opportunity, conclusion, and constitutional references are required")
        if set(self.criteria) != set(ArchitecturalEvaluationCriterion) or len(self.criteria) != len(ArchitecturalEvaluationCriterion):
            raise ValueError("architectural evaluation must address every evaluation criterion exactly once")
        if len(self.constitutional_references) != len(set(self.constitutional_references)):
            raise ValueError("architectural evaluation constitutional references must be unique")
        object.__setattr__(self, "criteria", tuple(sorted(self.criteria, key=lambda criterion: criterion.value)))
        object.__setattr__(self, "constitutional_references", tuple(sorted(self.constitutional_references)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "criteria": [criterion.value for criterion in self.criteria],
            "conclusion": self.conclusion,
            "constitutional_references": [reference.to_dict() for reference in self.constitutional_references],
        }


@dataclass(frozen=True)
class ArchitecturalOpportunity:
    """An evaluated possibility; it is not an Engineering Proposal or work order."""

    id: str
    title: str
    description: str
    source_finding_ids: tuple[str, ...]
    capability_impact: CapabilityImpact
    roadmap_impact: RoadmapImpact
    status: ArchitecturalOpportunityStatus = ArchitecturalOpportunityStatus.IDENTIFIED
    decision_reference: IntentReference | None = None

    def __post_init__(self) -> None:
        if not all((self.id, self.title, self.description)) or not self.source_finding_ids:
            raise ValueError("architectural opportunity identity, description, and source findings are required")
        if len(self.source_finding_ids) != len(set(self.source_finding_ids)) or any(not identifier for identifier in self.source_finding_ids):
            raise ValueError("architectural opportunity source findings must be unique and non-empty")
        if self.status is ArchitecturalOpportunityStatus.IDENTIFIED and self.decision_reference is not None:
            raise ValueError("identified architectural opportunities cannot carry a decision reference")
        if self.status is not ArchitecturalOpportunityStatus.IDENTIFIED and self.decision_reference is None:
            raise ValueError("decided architectural opportunities require a human decision reference")
        object.__setattr__(self, "source_finding_ids", tuple(sorted(self.source_finding_ids)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "source_finding_ids": list(self.source_finding_ids),
            "capability_impact": self.capability_impact.to_dict(),
            "roadmap_impact": self.roadmap_impact.to_dict(), "status": self.status.value,
            "decision_reference": self.decision_reference.to_dict() if self.decision_reference else None,
        }


@dataclass(frozen=True)
class EngineeringProposalHandoff:
    """A traceable handoff eligible for the existing governed Proposal process."""

    opportunity_id: str
    source_finding_ids: tuple[str, ...]
    evaluation: ArchitecturalEvaluation
    capability_impact: CapabilityImpact
    roadmap_impact: RoadmapImpact
    decision_reference: IntentReference

    def __post_init__(self) -> None:
        if not self.opportunity_id or not self.source_finding_ids:
            raise ValueError("proposal handoff opportunity and source findings are required")
        if self.evaluation.opportunity_id != self.opportunity_id:
            raise ValueError("proposal handoff evaluation must belong to its opportunity")
        if len(self.source_finding_ids) != len(set(self.source_finding_ids)):
            raise ValueError("proposal handoff source findings must be unique")
        object.__setattr__(self, "source_finding_ids", tuple(sorted(self.source_finding_ids)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id, "source_finding_ids": list(self.source_finding_ids),
            "evaluation": self.evaluation.to_dict(), "capability_impact": self.capability_impact.to_dict(),
            "roadmap_impact": self.roadmap_impact.to_dict(), "decision_reference": self.decision_reference.to_dict(),
        }


def accept_for_proposal(opportunity: ArchitecturalOpportunity, evaluation: ArchitecturalEvaluation, decision_reference: IntentReference) -> ArchitecturalOpportunity:
    """Record a human architectural-review decision; it creates no proposal or Intent."""

    if opportunity.status is not ArchitecturalOpportunityStatus.IDENTIFIED:
        raise ValueError("only identified architectural opportunities may be accepted for proposal")
    if evaluation.opportunity_id != opportunity.id:
        raise ValueError("architectural evaluation must belong to the accepted opportunity")
    return replace(opportunity, status=ArchitecturalOpportunityStatus.ACCEPTED_FOR_PROPOSAL, decision_reference=decision_reference)


def hand_off_to_proposal(opportunity: ArchitecturalOpportunity, evaluation: ArchitecturalEvaluation) -> EngineeringProposalHandoff:
    """Produce proposal-process input from a human-accepted opportunity only."""

    if opportunity.status is not ArchitecturalOpportunityStatus.ACCEPTED_FOR_PROPOSAL or opportunity.decision_reference is None:
        raise ValueError("only a human-accepted architectural opportunity may enter proposal generation")
    return EngineeringProposalHandoff(opportunity.id, opportunity.source_finding_ids, evaluation, opportunity.capability_impact, opportunity.roadmap_impact, opportunity.decision_reference)
