"""Immutable, provider-independent contracts for AI Architect reasoning.

Forge supplies all engineering knowledge as versioned references.  A provider
only returns advisory reasoning candidates; it cannot alter knowledge, create
canonical Engineering Proposals or Intents, make governance decisions, invoke
runtime providers, or execute engineering work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .intent import IntentReference


AI_ARCHITECT_PROVIDER_SCHEMA_VERSION = "1.6"


class AIArchitectInputKind(str, Enum):
    """The complete repository-held context required for provider reasoning."""

    REPOSITORY_KNOWLEDGE = "repository_knowledge"
    ARCHITECTURE_HANDBOOK = "architecture_handbook"
    CONSTITUTION = "constitution"
    ENGINEERING_HISTORY = "engineering_history"
    ENGINEERING_INTENTS = "engineering_intents"
    REPOSITORY_EVIDENCE = "repository_evidence"
    WORKSPACE_CONTEXT = "workspace_context"
    ROADMAP_CONTEXT = "roadmap_context"
    CAPABILITY_CATALOGUE = "capability_catalogue"


class AIArchitectConfidence(str, Enum):
    """Advisory confidence, never a substitute for evidence or human judgment."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class AIArchitectInput:
    """Versioned, read-only references for one mandatory input source class."""

    kind: AIArchitectInputKind
    references: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not self.references:
            raise ValueError("AI Architect input references are required")
        if len(self.references) != len(set(self.references)):
            raise ValueError("AI Architect input references must be unique")
        object.__setattr__(self, "references", tuple(sorted(self.references)))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "references": [reference.to_dict() for reference in self.references]}


@dataclass(frozen=True)
class AIArchitectRequest:
    """A complete immutable reasoning request prepared and owned by Forge."""

    id: str
    objective: str
    inputs: tuple[AIArchitectInput, ...]
    schema_version: str = AI_ARCHITECT_PROVIDER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AI_ARCHITECT_PROVIDER_SCHEMA_VERSION:
            raise ValueError("AI Architect Provider schema version is unsupported")
        if not self.id or not self.objective:
            raise ValueError("AI Architect request identity and objective are required")
        kinds = tuple(item.kind for item in self.inputs)
        if len(kinds) != len(set(kinds)):
            raise ValueError("AI Architect request input kinds must be unique")
        missing = set(AIArchitectInputKind).difference(kinds)
        if missing:
            labels = ", ".join(sorted(kind.value for kind in missing))
            raise ValueError(f"AI Architect request is missing required inputs: {labels}")
        object.__setattr__(self, "inputs", tuple(sorted(self.inputs, key=lambda item: item.kind.value)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "objective": self.objective,
            "inputs": [item.to_dict() for item in self.inputs],
        }


@dataclass(frozen=True, order=True)
class AIArchitectFindingCandidate:
    """An advisory architectural observation linked to its supporting evidence."""

    id: str
    summary: str
    evidence_references: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.summary or not self.evidence_references:
            raise ValueError("finding candidate identity, summary, and evidence are required")
        if len(self.evidence_references) != len(set(self.evidence_references)):
            raise ValueError("finding candidate evidence references must be unique")
        object.__setattr__(self, "evidence_references", tuple(sorted(self.evidence_references)))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "summary": self.summary, "evidence_references": [item.to_dict() for item in self.evidence_references]}


@dataclass(frozen=True, order=True)
class AIArchitectOpportunityCandidate:
    """An advisory opportunity, never an accepted architectural decision."""

    id: str
    title: str
    rationale: str
    finding_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.title or not self.rationale or not self.finding_ids:
            raise ValueError("opportunity candidate identity, rationale, and findings are required")
        if len(self.finding_ids) != len(set(self.finding_ids)) or any(not item for item in self.finding_ids):
            raise ValueError("opportunity candidate finding identifiers must be unique and non-empty")
        object.__setattr__(self, "finding_ids", tuple(sorted(self.finding_ids)))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "rationale": self.rationale, "finding_ids": list(self.finding_ids)}


@dataclass(frozen=True)
class EngineeringProposalDraftCandidate:
    """A proposed draft for human-governed proposal authoring, not a Proposal."""

    title: str
    objective: str
    opportunity_ids: tuple[str, ...]
    evidence_references: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not self.title or not self.objective or not self.opportunity_ids or not self.evidence_references:
            raise ValueError("proposal draft candidate title, objective, opportunities, and evidence are required")
        if len(self.opportunity_ids) != len(set(self.opportunity_ids)) or any(not item for item in self.opportunity_ids):
            raise ValueError("proposal draft candidate opportunity identifiers must be unique and non-empty")
        if len(self.evidence_references) != len(set(self.evidence_references)):
            raise ValueError("proposal draft candidate evidence references must be unique")
        object.__setattr__(self, "opportunity_ids", tuple(sorted(self.opportunity_ids)))
        object.__setattr__(self, "evidence_references", tuple(sorted(self.evidence_references)))

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "objective": self.objective, "opportunity_ids": list(self.opportunity_ids), "evidence_references": [item.to_dict() for item in self.evidence_references]}


@dataclass(frozen=True)
class EngineeringIntentDraftCandidate:
    """A proposed draft for human Intent authoring, never a canonical Intent."""

    title: str
    objective: str
    constraints: tuple[str, ...]
    expected_evidence: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not self.title or not self.objective or not self.constraints or not self.expected_evidence:
            raise ValueError("intent draft candidate title, objective, constraints, and expected evidence are required")
        if len(self.constraints) != len(set(self.constraints)) or any(not item for item in self.constraints):
            raise ValueError("intent draft candidate constraints must be unique and non-empty")
        if len(self.expected_evidence) != len(set(self.expected_evidence)):
            raise ValueError("intent draft candidate expected evidence references must be unique")
        object.__setattr__(self, "constraints", tuple(sorted(self.constraints)))
        object.__setattr__(self, "expected_evidence", tuple(sorted(self.expected_evidence)))

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "objective": self.objective, "constraints": list(self.constraints), "expected_evidence": [item.to_dict() for item in self.expected_evidence]}


@dataclass(frozen=True)
class AIArchitectResult:
    """Advisory, evidence-linked provider output with no lifecycle authority."""

    request_id: str
    provider_id: str
    findings: tuple[AIArchitectFindingCandidate, ...]
    opportunities: tuple[AIArchitectOpportunityCandidate, ...]
    proposal_draft: EngineeringProposalDraftCandidate
    intent_draft: EngineeringIntentDraftCandidate
    reasoning_evidence: tuple[IntentReference, ...]
    confidence: AIArchitectConfidence
    recommendations: tuple[str, ...]
    schema_version: str = AI_ARCHITECT_PROVIDER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AI_ARCHITECT_PROVIDER_SCHEMA_VERSION:
            raise ValueError("AI Architect Provider schema version is unsupported")
        if not self.request_id or not self.provider_id:
            raise ValueError("AI Architect result request and provider identities are required")
        if not self.findings or not self.opportunities or not self.reasoning_evidence or not self.recommendations:
            raise ValueError("AI Architect result requires findings, opportunities, evidence, and recommendations")
        for values, label, key in (
            (self.findings, "finding", lambda item: item.id),
            (self.opportunities, "opportunity", lambda item: item.id),
            (self.reasoning_evidence, "reasoning evidence", lambda item: item),
            (self.recommendations, "recommendation", lambda item: item),
        ):
            identifiers = tuple(key(item) for item in values)
            if len(identifiers) != len(set(identifiers)) or any(not item for item in identifiers):
                raise ValueError(f"AI Architect result {label} values must be unique and non-empty")
        finding_ids = {item.id for item in self.findings}
        if not set(item.finding_ids for item in self.opportunities):
            raise ValueError("AI Architect result opportunities must link to findings")
        if any(not set(item.finding_ids).issubset(finding_ids) for item in self.opportunities):
            raise ValueError("AI Architect result opportunities must reference result findings")
        opportunity_ids = {item.id for item in self.opportunities}
        if not set(self.proposal_draft.opportunity_ids).issubset(opportunity_ids):
            raise ValueError("proposal draft candidate must reference result opportunities")
        object.__setattr__(self, "findings", tuple(sorted(self.findings, key=lambda item: item.id)))
        object.__setattr__(self, "opportunities", tuple(sorted(self.opportunities, key=lambda item: item.id)))
        object.__setattr__(self, "reasoning_evidence", tuple(sorted(self.reasoning_evidence)))
        object.__setattr__(self, "recommendations", tuple(sorted(self.recommendations)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "request_id": self.request_id, "provider_id": self.provider_id,
            "findings": [item.to_dict() for item in self.findings],
            "opportunities": [item.to_dict() for item in self.opportunities],
            "proposal_draft": self.proposal_draft.to_dict(), "intent_draft": self.intent_draft.to_dict(),
            "reasoning_evidence": [item.to_dict() for item in self.reasoning_evidence],
            "confidence": self.confidence.value, "recommendations": list(self.recommendations),
        }
