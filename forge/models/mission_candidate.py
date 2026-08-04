"""Versioned, business-governed Mission Candidate contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .mission_recommendation import EngineeringEffort, RecommendationConfidenceLevel, RequiredDiscipline


MISSION_CANDIDATE_SCHEMA_VERSION = "1.1"


class MissionCandidateStatus(str, Enum):
    BUSINESS_REVIEW = "business_review"
    APPROVED_FOR_ARCHITECTURE = "approved_for_architecture"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class MissionCandidateMaturity(str, Enum):
    IDEA = "idea"
    RESEARCH = "research"
    FEASIBILITY = "feasibility"
    PROPOSAL = "proposal"
    READY_FOR_ARCHITECTURE = "ready_for_architecture"


@dataclass(frozen=True)
class MissionCandidate:
    """A Portfolio opportunity; deliberately not a Mission or an execution request."""

    id: str
    title: str
    summary: str
    business_objective: str
    business_value: str
    estimated_engineering_effort: EngineeringEffort
    confidence: RecommendationConfidenceLevel
    required_disciplines: tuple[RequiredDiscipline, ...]
    dependencies: tuple[str, ...]
    architecture_review_reference: str | None
    mission_recommendation_reference: str | None
    priority: int
    business_rationale: str
    maturity: MissionCandidateMaturity = MissionCandidateMaturity.IDEA
    status: MissionCandidateStatus = MissionCandidateStatus.BUSINESS_REVIEW
    schema_version: str = MISSION_CANDIDATE_SCHEMA_VERSION
    solution_template_reference: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != MISSION_CANDIDATE_SCHEMA_VERSION:
            raise ValueError("mission candidate schema version is unsupported")
        if not all((self.id, self.title, self.summary, self.business_objective, self.business_value,
                    self.business_rationale)):
            raise ValueError("mission candidate requires complete business context")
        if self.solution_template_reference:
            if self.architecture_review_reference or self.mission_recommendation_reference:
                raise ValueError("template candidates must not claim Architecture Review or Mission Recommendation provenance")
        elif not all((self.architecture_review_reference, self.mission_recommendation_reference)):
            raise ValueError("non-template candidates require complete recommendation provenance")
        if not 0 <= self.priority <= 100:
            raise ValueError("mission candidate priority must be between 0 and 100")
        for values, label in ((self.required_disciplines, "required disciplines"), (self.dependencies, "dependencies")):
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError(f"mission candidate {label} must be unique and non-empty")
        object.__setattr__(self, "required_disciplines", tuple(sorted(self.required_disciplines, key=lambda item: item.value)))
        object.__setattr__(self, "dependencies", tuple(sorted(self.dependencies)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "business_objective": self.business_objective,
            "business_value": self.business_value,
            "estimated_engineering_effort": self.estimated_engineering_effort.value,
            "confidence": self.confidence.value,
            "required_disciplines": [item.value for item in self.required_disciplines],
            "dependencies": list(self.dependencies),
            "architecture_review_reference": self.architecture_review_reference,
            "mission_recommendation_reference": self.mission_recommendation_reference,
            "priority": self.priority,
            "business_rationale": self.business_rationale,
            "maturity": self.maturity.value,
            "status": self.status.value,
            "solution_template_reference": self.solution_template_reference,
        }

    @classmethod
    def from_dict(cls, document: dict[str, Any]) -> "MissionCandidate":
        schema_version = document["schema_version"]
        if schema_version == "1.0":
            schema_version = MISSION_CANDIDATE_SCHEMA_VERSION
        return cls(
            id=document["id"], title=document["title"], summary=document["summary"],
            business_objective=document["business_objective"], business_value=document["business_value"],
            estimated_engineering_effort=EngineeringEffort(document["estimated_engineering_effort"]),
            confidence=RecommendationConfidenceLevel(document["confidence"]),
            required_disciplines=tuple(RequiredDiscipline(item) for item in document["required_disciplines"]),
            dependencies=tuple(document["dependencies"]), architecture_review_reference=document.get("architecture_review_reference"),
            mission_recommendation_reference=document.get("mission_recommendation_reference"), priority=document["priority"],
            business_rationale=document["business_rationale"], maturity=MissionCandidateMaturity(document["maturity"]),
            status=MissionCandidateStatus(document["status"]), schema_version=schema_version,
            solution_template_reference=document.get("solution_template_reference"),
        )
