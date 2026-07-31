"""Versioned, declarative contracts for Forge Engineering Planning 0.5.

Planning records intended work only.  These models deliberately have no
repository, tool, approval, execution, or mutation behaviour.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


PLANNING_SCHEMA_VERSION = "0.5"


class EvidenceKind(str, Enum):
    """The governed external record to which a plan may refer."""

    KNOWLEDGE_SOURCE = "knowledge_source"
    EVIDENCE_RECORD = "evidence_record"
    ARCHITECTURE_DOCUMENT = "architecture_document"
    FOUNDATION_DOCUMENT = "foundation_document"


class RiskLevel(str, Enum):
    """A human-declared proposal risk classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanStatus(str, Enum):
    """Planning lifecycle state; it never grants execution authority."""

    DRAFT = "draft"
    PROPOSED = "proposed"


@dataclass(frozen=True)
class EvidenceReference:
    """A traceable pointer to evidence without copying its content."""

    kind: EvidenceKind
    source_id: str
    source_version: str
    reference: str
    location: str

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_version or not self.reference or not self.location:
            raise ValueError("evidence reference source, version, reference, and location are required")

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["kind"] = self.kind.value
        return document


@dataclass(frozen=True)
class EngineeringGoal:
    """A desired engineering outcome scoped to one workspace."""

    id: str
    description: str
    desired_outcome: str
    workspace_id: str
    evidence_references: tuple[EvidenceReference, ...] = ()
    schema_version: str = PLANNING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id or not self.description or not self.desired_outcome or not self.workspace_id:
            raise ValueError("goal id, description, desired outcome, and workspace id are required")

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["evidence_references"] = [reference.to_dict() for reference in self.evidence_references]
        return document


@dataclass(frozen=True)
class EngineeringIncrementProposal:
    """A bounded, non-executing proposal that advances an Engineering Goal."""

    id: str
    goal_id: str
    scope: str
    expected_outcome: str
    affected_capabilities: tuple[str, ...]
    dependencies: tuple[str, ...]
    risk_level: RiskLevel
    rationale: str
    evidence_references: tuple[EvidenceReference, ...] = ()
    schema_version: str = PLANNING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not all((self.id, self.goal_id, self.scope, self.expected_outcome, self.rationale)):
            raise ValueError("proposal identity, goal, scope, outcome, and rationale are required")
        if not self.affected_capabilities:
            raise ValueError("proposal must identify affected capabilities")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("proposal dependencies must be unique")
        if self.id in self.dependencies:
            raise ValueError("proposal must not depend on itself")

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["affected_capabilities"] = list(self.affected_capabilities)
        document["dependencies"] = list(self.dependencies)
        document["risk_level"] = self.risk_level.value
        document["evidence_references"] = [reference.to_dict() for reference in self.evidence_references]
        return document


@dataclass(frozen=True)
class IncrementDependency:
    """Dependencies for one ordered plan increment."""

    increment_id: str
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.increment_id or self.increment_id in self.depends_on:
            raise ValueError("dependency must identify an increment and cannot depend on itself")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("dependency targets must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {"increment_id": self.increment_id, "depends_on": list(self.depends_on)}


@dataclass(frozen=True)
class EngineeringPlan:
    """An ordered, declarative plan pending future approval and execution."""

    id: str
    workspace_id: str
    ordered_increment_ids: tuple[str, ...]
    dependencies: tuple[IncrementDependency, ...]
    assumptions: tuple[str, ...]
    status: PlanStatus = PlanStatus.DRAFT
    evidence_references: tuple[EvidenceReference, ...] = ()
    schema_version: str = PLANNING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id or not self.workspace_id or not self.ordered_increment_ids:
            raise ValueError("plan id, workspace id, and ordered increments are required")
        if len(self.ordered_increment_ids) != len(set(self.ordered_increment_ids)):
            raise ValueError("plan increments must be unique")
        dependency_ids = [item.increment_id for item in self.dependencies]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("plan dependency declarations must be unique")

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["ordered_increment_ids"] = list(self.ordered_increment_ids)
        document["assumptions"] = list(self.assumptions)
        document["dependencies"] = [dependency.to_dict() for dependency in self.dependencies]
        document["status"] = self.status.value
        document["evidence_references"] = [reference.to_dict() for reference in self.evidence_references]
        return document
