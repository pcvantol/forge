"""Immutable, deterministic advisory Portfolio artefacts derived from Architecture Reviews."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


MISSION_RECOMMENDATION_SCHEMA_VERSION = "1.1"


class MissionOrigin(str, Enum):
    """Extensible, advisory provenance for a Mission Recommendation."""

    BUSINESS = "business"
    ARCHITECTURE = "architecture"
    MAINTENANCE = "maintenance"
    SECURITY = "security"
    PERFORMANCE = "performance"
    OPERATIONS = "operations"
    DOCUMENTATION = "documentation"
    USER_FEEDBACK = "user_feedback"


class RecommendationCategory(str, Enum):
    NEW_CAPABILITY = "new_capability"
    ARCHITECTURE_RECONCILIATION = "architecture_reconciliation"
    QUALIFICATION = "qualification"
    TECHNICAL_DEBT = "technical_debt"
    DOCUMENTATION = "documentation"
    GOVERNANCE = "governance"
    EXECUTION_HOST = "execution_host"
    RUNTIME = "runtime"
    PORTFOLIO = "portfolio"
    DEVELOPER_EXPERIENCE = "developer_experience"
    INFRASTRUCTURE = "infrastructure"


class EngineeringEffort(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class RecommendationConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RequiredDiscipline(str, Enum):
    PLATFORM_ARCHITECTURE = "platform_architecture"
    ENGINEERING = "engineering"
    BUSINESS = "business"
    UX = "ux"
    SECURITY = "security"
    PRIVACY = "privacy"
    LEGAL = "legal"
    COMMERCIAL = "commercial"
    MARKET_RESEARCH = "market_research"
    COMPLIANCE = "compliance"


@dataclass(frozen=True, order=True)
class RecommendationRepositoryContext:
    repository_id: str
    repository_revision: str
    repository_truth_digest: str

    def __post_init__(self) -> None:
        digest = self.repository_truth_digest.removeprefix("sha256:")
        if not self.repository_id or not self.repository_revision or not self.repository_truth_digest.startswith("sha256:") or len(digest) != 64:
            raise ValueError("recommendation repository context requires identity, revision, and sha256 Repository Truth")

    def to_dict(self) -> dict[str, str]:
        return {"repository_id": self.repository_id, "repository_revision": self.repository_revision,
                "repository_truth_digest": self.repository_truth_digest}


@dataclass(frozen=True, order=True)
class RecommendationEvidenceReference:
    """Revision- and digest-pinned Repository Truth evidence for one recommendation."""

    id: str
    kind: str
    revision: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        digest = self.content_digest.removeprefix("sha256:")
        if not all((self.id, self.kind, self.revision, self.locator)):
            raise ValueError("recommendation repository evidence requires identity, kind, revision, and locator")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("recommendation repository evidence requires a sha256 digest")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "kind": self.kind, "revision": self.revision,
                "locator": self.locator, "content_digest": self.content_digest}


@dataclass(frozen=True)
class RecommendationConfidence:
    """Deterministic factors, all derived from declared Repository Truth and review evidence."""

    repository_maturity: int
    architecture_pressure: int
    implementation_pressure: int
    execution_evidence: int
    capability_completeness: int
    evidence_quality: int

    def __post_init__(self) -> None:
        if any(not 0 <= value <= 100 for value in self._values()):
            raise ValueError("recommendation confidence factors must be between 0 and 100")

    def _values(self) -> tuple[int, ...]:
        return (self.repository_maturity, self.architecture_pressure, self.implementation_pressure,
                self.execution_evidence, self.capability_completeness, self.evidence_quality)

    @property
    def score(self) -> int:
        return sum(self._values()) // len(self._values())

    @property
    def level(self) -> RecommendationConfidenceLevel:
        return (RecommendationConfidenceLevel.HIGH if self.score >= 75 else
                RecommendationConfidenceLevel.MEDIUM if self.score >= 45 else RecommendationConfidenceLevel.LOW)

    def to_dict(self) -> dict[str, Any]:
        return {"repository_maturity": self.repository_maturity, "architecture_pressure": self.architecture_pressure,
                "implementation_pressure": self.implementation_pressure, "execution_evidence": self.execution_evidence,
                "capability_completeness": self.capability_completeness, "evidence_quality": self.evidence_quality,
                "score": self.score, "level": self.level.value}


@dataclass(frozen=True)
class RecommendationDependencies:
    predecessor_mission_ids: tuple[str, ...] = ()
    successor_mission_ids: tuple[str, ...] = ()
    grouping: str | None = None
    sequencing: str | None = None

    def __post_init__(self) -> None:
        for values in (self.predecessor_mission_ids, self.successor_mission_ids):
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError("recommendation dependency mission ids must be unique and non-empty")
        object.__setattr__(self, "predecessor_mission_ids", tuple(sorted(self.predecessor_mission_ids)))
        object.__setattr__(self, "successor_mission_ids", tuple(sorted(self.successor_mission_ids)))

    def to_dict(self) -> dict[str, Any]:
        return {"predecessor_mission_ids": list(self.predecessor_mission_ids), "successor_mission_ids": list(self.successor_mission_ids),
                "grouping": self.grouping, "sequencing": self.sequencing, "advisory": True}


@dataclass(frozen=True)
class MissionRecommendation:
    """A Portfolio artefact; it has no approval, state transition, planner, or execution authority."""

    id: str
    repository_context: RecommendationRepositoryContext
    architecture_review_id: str
    repository_maturity_digest: str
    category: RecommendationCategory
    title: str
    rationale: str
    business_value: str
    architectural_value: str
    estimated_effort: EngineeringEffort
    confidence: RecommendationConfidence
    dependencies: RecommendationDependencies
    required_disciplines: tuple[RequiredDiscipline, ...]
    missing_disciplines: tuple[RequiredDiscipline, ...]
    capability_impact: tuple[str, ...]
    recommendation_timestamp: str
    source_signal_ids: tuple[str, ...]
    portfolio_item_ids: tuple[str, ...]
    origin: MissionOrigin
    repository_evidence: tuple[RecommendationEvidenceReference, ...]
    expected_engineering_value: str
    risk_if_deferred: str
    recommendation_source: str
    decision_evidence_references: tuple[str, ...]
    advisory: bool = True
    schema_version: str = MISSION_RECOMMENDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MISSION_RECOMMENDATION_SCHEMA_VERSION or not all((self.id, self.architecture_review_id, self.repository_maturity_digest, self.title, self.rationale, self.business_value, self.architectural_value, self.expected_engineering_value, self.risk_if_deferred, self.recommendation_source, self.recommendation_timestamp)):
            raise ValueError("mission recommendation requires complete immutable evidence and value context")
        if not self.repository_maturity_digest.startswith("sha256:") or len(self.repository_maturity_digest.removeprefix("sha256:")) != 64:
            raise ValueError("recommendation maturity reference must be a sha256 digest")
        if not self.advisory:
            raise ValueError("mission recommendations must remain advisory")
        if not self.repository_evidence or len(self.repository_evidence) != len(set(self.repository_evidence)):
            raise ValueError("mission recommendations require unique Repository Truth evidence")
        for values, label in ((self.required_disciplines, "required disciplines"), (self.missing_disciplines, "missing disciplines"), (self.capability_impact, "capability impact"), (self.source_signal_ids, "source signals")):
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError(f"mission recommendation {label} must be unique and non-empty")
        if len(self.portfolio_item_ids) != len(set(self.portfolio_item_ids)) or any(not value for value in self.portfolio_item_ids):
            raise ValueError("mission recommendation portfolio items must be unique and non-empty when declared")
        if len(self.decision_evidence_references) != len(set(self.decision_evidence_references)) or any(not value for value in self.decision_evidence_references):
            raise ValueError("mission recommendation decision evidence references must be unique and non-empty")
        if not set(self.missing_disciplines).issubset(self.required_disciplines):
            raise ValueError("missing disciplines must be required disciplines")
        for name in ("required_disciplines", "missing_disciplines", "capability_impact", "source_signal_ids", "portfolio_item_ids", "decision_evidence_references"):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name), key=lambda value: value.value if isinstance(value, Enum) else value)))
        object.__setattr__(self, "repository_evidence", tuple(sorted(self.repository_evidence)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "id": self.id, "repository_context": self.repository_context.to_dict(),
                "architecture_review_id": self.architecture_review_id, "repository_maturity_digest": self.repository_maturity_digest,
                "category": self.category.value, "title": self.title, "rationale": self.rationale, "business_value": self.business_value,
                "architectural_value": self.architectural_value, "estimated_effort": self.estimated_effort.value,
                "confidence": self.confidence.to_dict(), "dependencies": self.dependencies.to_dict(),
                "required_disciplines": [item.value for item in self.required_disciplines], "missing_disciplines": [item.value for item in self.missing_disciplines],
                "capability_impact": list(self.capability_impact), "recommendation_timestamp": self.recommendation_timestamp,
                "source_signal_ids": list(self.source_signal_ids), "portfolio_item_ids": list(self.portfolio_item_ids),
                "origin": self.origin.value, "repository_evidence": [item.to_dict() for item in self.repository_evidence],
                "expected_engineering_value": self.expected_engineering_value, "risk_if_deferred": self.risk_if_deferred,
                "recommendation_source": self.recommendation_source,
                "decision_evidence_references": list(self.decision_evidence_references), "advisory": True}
