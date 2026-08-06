"""Immutable, deterministic contracts for Architecture Review Engine 3.7.

The review model is repository-evidence-only.  It records advisory learning
after a completed Mission and deliberately contains no mission, approval,
provider, runtime, or repository-mutation operation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any


ARCHITECTURE_REVIEW_SCHEMA_VERSION = "3.7"


class ReviewInputKind(str, Enum):
    CONSTITUTION = "constitution"
    ARCHITECTURE_HANDBOOK = "architecture_handbook"
    BOOTSTRAP_COMPLETION = "bootstrap_completion"
    CAPABILITY_CATALOGUE = "capability_catalogue"
    MISSION_DOCUMENT = "mission_document"
    MISSION_STATE = "mission_state"
    REPOSITORY_TRUTH = "repository_truth"
    EXECUTION_EVIDENCE = "execution_evidence"
    EXECUTION_REPORT = "execution_report"
    HISTORICAL_INTENT = "historical_intent"
    ENGINEERING_INTENT_HISTORY = "engineering_intent_history"
    ENGINEERING_ACTION_HISTORY = "engineering_action_history"
    REPOSITORY_MATURITY = "repository_maturity"
    PORTFOLIO = "portfolio"
    MISSION_RECOMMENDATION = "mission_recommendation"
    ROADMAP = "roadmap"


class MaturityArea(str, Enum):
    ARCHITECTURE = "architecture"
    RUNTIME = "runtime"
    PLANNING = "planning"
    ENGINEERING = "engineering"
    GOVERNANCE = "governance"
    PORTFOLIO = "portfolio"
    EXECUTION_HOST = "execution_host"
    DOCUMENTATION = "documentation"
    KNOWLEDGE = "knowledge"
    QUALIFICATION = "qualification"


class MaturityClassification(str, Enum):
    NOT_EVIDENCED = "not_evidenced"
    FOUNDATION = "foundation"
    ESTABLISHED = "established"
    QUALIFIED = "qualified"


class PressureLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class ReviewSignalKind(str, Enum):
    ARCHITECTURAL_INCONSISTENCY = "architectural_inconsistency"
    DUPLICATION = "duplication"
    CAPABILITY_GAP = "capability_gap"
    IMPLEMENTATION_FAILURE = "implementation_failure"
    REPOSITORY_GROWTH = "repository_growth"
    OPERATIONAL_FAILURE = "operational_failure"
    TECHNICAL_DEBT = "technical_debt"
    DUPLICATE_IMPLEMENTATION = "duplicate_implementation"
    REFACTORING_OPPORTUNITY = "refactoring_opportunity"
    DOCUMENTATION_INCONSISTENCY = "documentation_inconsistency"
    DEPENDENCY_MAINTENANCE = "dependency_maintenance"
    REPOSITORY_HYGIENE = "repository_hygiene"
    PERFORMANCE_OBSERVATION = "performance_observation"
    ARCHITECTURE_EROSION = "architecture_erosion"


class ReviewConfidence(str, Enum):
    INSUFFICIENT = "insufficient"
    MEDIUM = "medium"
    HIGH = "high"


def _digest(document: object) -> str:
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True, order=True)
class ReviewEvidence:
    """A reproducible input pointer; the engine never retrieves its content."""

    kind: ReviewInputKind
    source_id: str
    revision: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        digest = self.content_digest.removeprefix("sha256:")
        if not all((self.source_id, self.revision, self.locator)):
            raise ValueError("review evidence identity, revision, and locator are required")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("review evidence content digest must be a sha256 digest")

    def to_dict(self) -> dict[str, str]:
        document = asdict(self)
        document["kind"] = self.kind.value
        return document


@dataclass(frozen=True, order=True)
class ReviewSignal:
    """A bounded, evidence-linked observation supplied by Repository Truth."""

    kind: ReviewSignalKind
    id: str
    description: str
    evidence: ReviewEvidence

    def __post_init__(self) -> None:
        if not self.id or not self.description:
            raise ValueError("review signal id and description are required")
        if self.evidence.kind not in {ReviewInputKind.REPOSITORY_TRUTH, ReviewInputKind.EXECUTION_EVIDENCE, ReviewInputKind.EXECUTION_REPORT}:
            raise ValueError("review signals require repository truth or execution evidence")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "id": self.id, "description": self.description, "evidence": self.evidence.to_dict()}


@dataclass(frozen=True)
class ArchitectureReviewInput:
    """The complete allow-listed, repository-only input to one deterministic review."""

    mission_id: str
    evidence: tuple[ReviewEvidence, ...]
    signals: tuple[ReviewSignal, ...] = ()
    portfolio_item_ids: tuple[str, ...] = ()
    schema_version: str = ARCHITECTURE_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ARCHITECTURE_REVIEW_SCHEMA_VERSION:
            raise ValueError("architecture review schema version is unsupported")
        if not self.mission_id or not self.evidence:
            raise ValueError("architecture review requires a completed mission id and evidence")
        if len(self.evidence) != len(set(self.evidence)) or len(self.signals) != len(set(self.signals)):
            raise ValueError("architecture review inputs must be unique")
        if len(self.portfolio_item_ids) != len(set(self.portfolio_item_ids)) or any(not item for item in self.portfolio_item_ids):
            raise ValueError("portfolio item ids must be unique and non-empty")
        object.__setattr__(self, "evidence", tuple(sorted(self.evidence, key=lambda item: (item.kind.value, item.source_id, item.revision, item.locator, item.content_digest))))
        object.__setattr__(self, "signals", tuple(sorted(self.signals, key=lambda item: (item.kind.value, item.id))))
        object.__setattr__(self, "portfolio_item_ids", tuple(sorted(self.portfolio_item_ids)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "mission_id": self.mission_id,
                "evidence": [item.to_dict() for item in self.evidence],
                "signals": [item.to_dict() for item in self.signals], "portfolio_item_ids": list(self.portfolio_item_ids)}


@dataclass(frozen=True, order=True)
class RepositoryMaturity:
    area: MaturityArea
    classification: MaturityClassification
    evidence_kinds: tuple[ReviewInputKind, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_kinds", tuple(sorted(set(self.evidence_kinds), key=lambda item: item.value)))

    def to_dict(self) -> dict[str, Any]:
        return {"area": self.area.value, "classification": self.classification.value,
                "evidence_kinds": [item.value for item in self.evidence_kinds]}


@dataclass(frozen=True)
class ArchitecturePressure:
    architecture: PressureLevel
    implementation: PressureLevel
    repository_growth: PressureLevel
    operational: PressureLevel

    def to_dict(self) -> dict[str, str]:
        return {"architecture": self.architecture.value, "implementation": self.implementation.value,
                "repository_growth": self.repository_growth.value, "operational": self.operational.value}


@dataclass(frozen=True)
class ArchitectureReview:
    """Immutable Repository Truth assessment; it never creates a recommendation or Mission."""

    id: str
    mission_id: str
    repository_maturity: tuple[RepositoryMaturity, ...]
    architectural_observations: tuple[str, ...]
    implementation_observations: tuple[str, ...]
    repository_strengths: tuple[str, ...]
    repository_weaknesses: tuple[str, ...]
    pressure: ArchitecturePressure
    detected_inconsistencies: tuple[str, ...]
    detected_duplication: tuple[str, ...]
    capability_gaps: tuple[str, ...]
    maintenance_observations: tuple[str, ...]
    recommended_mission_candidates: tuple[str, ...]
    portfolio_item_ids: tuple[str, ...]
    rationale: str
    confidence: ReviewConfidence
    input_digest: str
    schema_version: str = ARCHITECTURE_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ARCHITECTURE_REVIEW_SCHEMA_VERSION or not all((self.id, self.mission_id, self.rationale, self.input_digest)):
            raise ValueError("architecture review identity, rationale, digest, and supported schema are required")
        if len(self.repository_maturity) != len(MaturityArea) or {item.area for item in self.repository_maturity} != set(MaturityArea):
            raise ValueError("architecture review must assess every maturity area")
        object.__setattr__(self, "repository_maturity", tuple(sorted(self.repository_maturity, key=lambda item: item.area.value)))
        for field_name in ("architectural_observations", "implementation_observations", "repository_strengths", "repository_weaknesses", "detected_inconsistencies", "detected_duplication", "capability_gaps", "maintenance_observations", "recommended_mission_candidates", "portfolio_item_ids"):
            object.__setattr__(self, field_name, tuple(sorted(getattr(self, field_name))))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "id": self.id, "mission_id": self.mission_id,
                "repository_maturity": [item.to_dict() for item in self.repository_maturity],
                "architectural_observations": list(self.architectural_observations),
                "implementation_observations": list(self.implementation_observations),
                "repository_strengths": list(self.repository_strengths), "repository_weaknesses": list(self.repository_weaknesses),
                "pressure": self.pressure.to_dict(), "detected_inconsistencies": list(self.detected_inconsistencies),
                "detected_duplication": list(self.detected_duplication), "capability_gaps": list(self.capability_gaps),
                "maintenance_observations": list(self.maintenance_observations),
                "recommended_mission_candidates": list(self.recommended_mission_candidates), "portfolio_item_ids": list(self.portfolio_item_ids), "rationale": self.rationale,
                "confidence": self.confidence.value, "input_digest": self.input_digest}
