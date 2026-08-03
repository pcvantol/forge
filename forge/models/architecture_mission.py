"""Architecture-governed, engineering-ready Mission contract.

This is the approval boundary between a Business-approved Mission Candidate
and the future Mission Planner.  It is intentionally not the legacy
``EngineeringMission`` execution contract, which requires planned Intent
memberships that do not exist before planning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .mission_candidate import MissionCandidate
from .mission_recommendation import RequiredDiscipline


ARCHITECTURE_MISSION_SCHEMA_VERSION = "1.0"


class ArchitectureMissionStatus(str, Enum):
    ARCHITECTURE_REVIEW = "architecture_review"
    APPROVED_FOR_ENGINEERING = "approved_for_engineering"
    RETURNED_TO_BUSINESS = "returned_to_business"
    REJECTED = "rejected"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class ArchitectureMission:
    """A non-executing Mission prepared and approved by a Platform Architect."""

    id: str
    candidate_id: str
    title: str
    summary: str
    business_objective: str
    business_value: str
    architecture_review_reference: str
    mission_recommendation_reference: str
    scope: tuple[str, ...] = ()
    engineering_constraints: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    technical_assumptions: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    required_disciplines: tuple[RequiredDiscipline, ...] = ()
    risks: tuple[str, ...] = ()
    status: ArchitectureMissionStatus = ArchitectureMissionStatus.ARCHITECTURE_REVIEW
    schema_version: str = ARCHITECTURE_MISSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ARCHITECTURE_MISSION_SCHEMA_VERSION:
            raise ValueError("architecture mission schema version is unsupported")
        if not all((self.id, self.candidate_id, self.title, self.summary, self.business_objective, self.business_value,
                    self.architecture_review_reference, self.mission_recommendation_reference)):
            raise ValueError("architecture mission requires complete source Mission Candidate context")
        for values, label in (
            (self.scope, "scope"), (self.engineering_constraints, "engineering constraints"),
            (self.acceptance_criteria, "acceptance criteria"), (self.technical_assumptions, "technical assumptions"),
            (self.dependencies, "dependencies"), (self.required_capabilities, "required capabilities"), (self.risks, "risks"),
        ):
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError(f"architecture mission {label} must be unique and non-empty when supplied")
        if len(self.required_disciplines) != len(set(self.required_disciplines)):
            raise ValueError("architecture mission required disciplines must be unique")
        for values in ("scope", "engineering_constraints", "acceptance_criteria", "technical_assumptions", "dependencies", "required_capabilities", "risks"):
            object.__setattr__(self, values, tuple(sorted(getattr(self, values))))
        object.__setattr__(self, "required_disciplines", tuple(sorted(self.required_disciplines, key=lambda item: item.value)))

    @classmethod
    def from_candidate(cls, candidate: MissionCandidate) -> "ArchitectureMission":
        """Create an architectural review record without changing the Candidate."""
        return cls(
            id=candidate.id, candidate_id=candidate.id, title=candidate.title, summary=candidate.summary,
            business_objective=candidate.business_objective, business_value=candidate.business_value,
            architecture_review_reference=candidate.architecture_review_reference,
            mission_recommendation_reference=candidate.mission_recommendation_reference,
            dependencies=candidate.dependencies, required_disciplines=candidate.required_disciplines,
        )

    def is_engineering_ready(self) -> bool:
        """Require an explicit architectural contract before engineering approval."""
        return all((self.scope, self.engineering_constraints, self.acceptance_criteria, self.technical_assumptions,
                    self.dependencies, self.required_capabilities, self.required_disciplines, self.risks))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "id": self.id, "candidate_id": self.candidate_id,
            "title": self.title, "summary": self.summary, "business_objective": self.business_objective,
            "business_value": self.business_value, "architecture_review_reference": self.architecture_review_reference,
            "mission_recommendation_reference": self.mission_recommendation_reference, "scope": list(self.scope),
            "engineering_constraints": list(self.engineering_constraints), "acceptance_criteria": list(self.acceptance_criteria),
            "technical_assumptions": list(self.technical_assumptions), "dependencies": list(self.dependencies),
            "required_capabilities": list(self.required_capabilities),
            "required_disciplines": [item.value for item in self.required_disciplines], "risks": list(self.risks),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, document: dict[str, Any]) -> "ArchitectureMission":
        return cls(
            id=document["id"], candidate_id=document["candidate_id"], title=document["title"], summary=document["summary"],
            business_objective=document["business_objective"], business_value=document["business_value"],
            architecture_review_reference=document["architecture_review_reference"],
            mission_recommendation_reference=document["mission_recommendation_reference"], scope=tuple(document["scope"]),
            engineering_constraints=tuple(document["engineering_constraints"]), acceptance_criteria=tuple(document["acceptance_criteria"]),
            technical_assumptions=tuple(document["technical_assumptions"]), dependencies=tuple(document["dependencies"]),
            required_capabilities=tuple(document["required_capabilities"]),
            required_disciplines=tuple(RequiredDiscipline(item) for item in document["required_disciplines"]), risks=tuple(document["risks"]),
            status=ArchitectureMissionStatus(document["status"]), schema_version=document["schema_version"],
        )
