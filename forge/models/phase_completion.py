"""Versioned, evidence-only contracts for Forge Phase Completion 1.0.

These types describe and assess completion; they never retrieve evidence,
operate a repository, or authorize execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


PHASE_COMPLETION_SCHEMA_VERSION = "1.0"


class EvidenceKind(str, Enum):
    """Supported reference-only evidence categories."""

    DOCUMENTATION = "documentation"
    VALIDATION = "validation"
    TEST = "test"
    ENGINEERING_ARTIFACT = "engineering_artifact"
    REPAIR_REPORT = "repair_report"


class CriterionOutcome(str, Enum):
    """A declared result for evidence scoped to one criterion."""

    PASS = "PASS"
    FAIL = "FAIL"


class AssessmentStatus(str, Enum):
    """Evidence-derived phase status; COMPLETE additionally needs closure evidence."""

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class ReproducibleEvidenceReference:
    """An immutable pointer to evidence, without embedding or fetching it."""

    kind: EvidenceKind
    source_id: str
    source_version: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.source_id, self.source_version, self.locator, self.content_digest)):
            raise ValueError("evidence source identity, version, locator, and digest are required")
        if not self.content_digest.startswith("sha256:") or len(self.content_digest) != 71 or any(character not in "0123456789abcdef" for character in self.content_digest[7:]):
            raise ValueError("evidence content digest must be a sha256 digest")

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["kind"] = self.kind.value
        return document


@dataclass(frozen=True)
class CompletionCriterion:
    """A single declarative requirement for completing an engineering phase."""

    id: str
    description: str
    required: bool = True

    def __post_init__(self) -> None:
        if not self.id or not self.description:
            raise ValueError("criterion id and description are required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompletionEvidence:
    """A criterion-scoped PASS or FAIL result backed by one immutable reference."""

    criterion_id: str
    outcome: CriterionOutcome
    reference: ReproducibleEvidenceReference

    def __post_init__(self) -> None:
        if not self.criterion_id:
            raise ValueError("completion evidence must identify a criterion")

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "outcome": self.outcome.value,
            "reference": self.reference.to_dict(),
        }


@dataclass(frozen=True)
class CompletionDeclaration:
    """An explicit closure declaration that is meaningful only after readiness."""

    reference: ReproducibleEvidenceReference

    def to_dict(self) -> dict[str, Any]:
        return {"reference": self.reference.to_dict()}


@dataclass(frozen=True)
class EngineeringPhase:
    """A bounded phase with declarative completion criteria and optional closure evidence."""

    id: str
    name: str
    objective: str
    criteria: tuple[CompletionCriterion, ...]
    completion_declaration: CompletionDeclaration | None = None
    schema_version: str = PHASE_COMPLETION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.objective or not self.criteria:
            raise ValueError("phase id, name, objective, and criteria are required")
        criterion_ids = [criterion.id for criterion in self.criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("phase criterion ids must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "objective": self.objective,
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "completion_declaration": None if self.completion_declaration is None else self.completion_declaration.to_dict(),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, order=True)
class AssessmentFinding:
    """A stable explanation of why a phase is not yet complete."""

    criterion_id: str
    code: str
    message: str


@dataclass(frozen=True)
class PhaseAssessment:
    """The deterministic assessment output, derived solely from declared input."""

    phase_id: str
    status: AssessmentStatus
    findings: tuple[AssessmentFinding, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "status": self.status.value,
            "findings": [asdict(finding) for finding in self.findings],
        }
