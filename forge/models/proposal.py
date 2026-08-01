"""Governed, non-executing contracts for Forge Engineering Proposals 0.6."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any

from .planning import EvidenceReference, RiskLevel


PROPOSAL_SCHEMA_VERSION = "0.6"


class ProposalStatus(str, Enum):
    """Proposal lifecycle state; none of these states performs execution."""

    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"


@dataclass(frozen=True)
class ProposalCreationMetadata:
    """Deterministic provenance of a generated proposal artifact."""

    generator: str
    generator_version: str
    workspace_id: str
    source_plan_id: str
    source_increment_id: str

    def __post_init__(self) -> None:
        if not all((self.generator, self.generator_version, self.workspace_id, self.source_plan_id, self.source_increment_id)):
            raise ValueError("proposal creation metadata is required")


@dataclass(frozen=True)
class ProposalScope:
    included_work: tuple[str, ...]
    excluded_work: tuple[str, ...]
    affected_capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.included_work or not self.affected_capabilities:
            raise ValueError("proposal scope must include work and affected capabilities")
        if any(not item for item in (*self.included_work, *self.excluded_work, *self.affected_capabilities)):
            raise ValueError("proposal scope entries must not be empty")
        if len(self.affected_capabilities) != len(set(self.affected_capabilities)):
            raise ValueError("proposal affected capabilities must be unique")


@dataclass(frozen=True)
class ProposalRationale:
    why_this_increment_exists: str
    roadmap_relationship: str
    evidence_relationship: str

    def __post_init__(self) -> None:
        if not all((self.why_this_increment_exists, self.roadmap_relationship, self.evidence_relationship)):
            raise ValueError("proposal rationale is required")


@dataclass(frozen=True)
class ProposalDependencies:
    required_capabilities: tuple[str, ...]
    required_previous_increments: tuple[str, ...]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    rationale: str

    def __post_init__(self) -> None:
        if not self.rationale:
            raise ValueError("risk rationale is required")


@dataclass(frozen=True)
class ProposalRisk:
    technical_risk: RiskAssessment
    governance_risk: RiskAssessment
    scope_risk: RiskAssessment


@dataclass(frozen=True)
class EngineeringProposal:
    """A traceable governed intention, never an execution instruction."""

    id: str
    title: str
    objective: str
    expected_outcome: str
    creation_metadata: ProposalCreationMetadata
    scope: ProposalScope
    rationale: ProposalRationale
    dependencies: ProposalDependencies
    risk: ProposalRisk
    evidence_references: tuple[EvidenceReference, ...]
    status: ProposalStatus = ProposalStatus.DRAFT
    schema_version: str = PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not all((self.id, self.title, self.objective, self.expected_outcome)):
            raise ValueError("proposal identity, title, objective, and expected outcome are required")
        if self.schema_version != PROPOSAL_SCHEMA_VERSION:
            raise ValueError("proposal schema version is unsupported")
        if not self.evidence_references:
            raise ValueError("proposal evidence references are required")

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["status"] = self.status.value
        document["risk"] = {
            "technical_risk": {"level": self.risk.technical_risk.level.value, "rationale": self.risk.technical_risk.rationale},
            "governance_risk": {"level": self.risk.governance_risk.level.value, "rationale": self.risk.governance_risk.rationale},
            "scope_risk": {"level": self.risk.scope_risk.level.value, "rationale": self.risk.scope_risk.rationale},
        }
        document["scope"] = {
            "included_work": list(self.scope.included_work),
            "excluded_work": list(self.scope.excluded_work),
            "affected_capabilities": list(self.scope.affected_capabilities),
        }
        document["dependencies"] = {
            "required_capabilities": list(self.dependencies.required_capabilities),
            "required_previous_increments": list(self.dependencies.required_previous_increments),
            "assumptions": list(self.dependencies.assumptions),
        }
        document["evidence_references"] = [reference.to_dict() for reference in self.evidence_references]
        return document


_NEXT_STATUS = {
    ProposalStatus.DRAFT: ProposalStatus.PROPOSED,
    ProposalStatus.PROPOSED: ProposalStatus.APPROVED,
    ProposalStatus.APPROVED: ProposalStatus.EXECUTED,
}


def transition_proposal(proposal: EngineeringProposal, status: ProposalStatus) -> EngineeringProposal:
    """Return an explicitly transitioned proposal without performing its work."""

    if _NEXT_STATUS.get(proposal.status) != status:
        raise ValueError("proposal status transition is not permitted")
    return replace(proposal, status=status)
