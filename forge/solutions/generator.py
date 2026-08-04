"""Pure deterministic draft generation from a Solution Template and declared context."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from forge.models import MissionCandidate, MissionCandidateMaturity, MissionCandidateStatus, RecommendationConfidenceLevel, RequiredDiscipline, SolutionTemplate


ADVISOR_QUESTIONS = ("users", "customers", "delivery_model", "deployment", "mobile_required", "offline_support", "compliance_requirements", "expected_scale", "existing_systems")


@dataclass(frozen=True)
class BusinessAdvisorAnswers:
    """Declared answers only; blanks are retained so the Business Owner can decide what to refine."""

    values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if len(self.values) != len({key for key, _ in self.values}) or any(key not in ADVISOR_QUESTIONS for key, _ in self.values):
            raise ValueError("business advisor answers require unique canonical questions")
        object.__setattr__(self, "values", tuple(sorted((key, value.strip()) for key, value in self.values)))

    @classmethod
    def from_dict(cls, values: dict[str, str]) -> "BusinessAdvisorAnswers":
        return cls(tuple(values.items()))

    def answer(self, key: str) -> str:
        return dict(self.values).get(key, "")

    @property
    def unanswered(self) -> tuple[str, ...]:
        return tuple(key for key in ADVISOR_QUESTIONS if not self.answer(key))


@dataclass(frozen=True)
class SolutionTemplateDraft:
    candidates: tuple[MissionCandidate, ...]
    architecture_recommendations: tuple[str, ...]
    missing_disciplines: tuple[RequiredDiscipline, ...]
    advisory: bool = True


class SolutionTemplateMissionCandidateGenerator:
    """Generates editable business-review drafts and has no approval, Mission, or execution authority."""

    def generate(self, template: SolutionTemplate, answers: BusinessAdvisorAnswers, repository_context: dict[str, str], *, available_disciplines: tuple[RequiredDiscipline, ...] = ()) -> SolutionTemplateDraft:
        context = tuple(sorted(repository_context.items()))
        candidates = []
        for definition in template.recommended_mission_candidates:
            digest = sha256(json.dumps({"template": template.reference, "candidate": definition.key, "answers": answers.values, "repository": context}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
            candidates.append(MissionCandidate(
                f"template-candidate-{digest}", definition.title,
                f"{definition.objective} Template: {template.name}.", definition.objective, definition.value,
                definition.effort, RecommendationConfidenceLevel.MEDIUM, definition.disciplines, definition.dependencies,
                None, None, 50, f"Draft generated from {template.reference}; Business Owner refinement remains required.",
                MissionCandidateMaturity.PROPOSAL, MissionCandidateStatus.BUSINESS_REVIEW,
                solution_template_reference=template.reference,
            ))
        missing = tuple(item for item in template.engineering_disciplines if item not in available_disciplines)
        recommendations = tuple(sorted(template.architecture_patterns + template.compliance_considerations))
        return SolutionTemplateDraft(tuple(sorted(candidates, key=lambda item: item.id)), recommendations, missing)
