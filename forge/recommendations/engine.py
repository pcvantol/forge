"""Pure deterministic transformation from Architecture Review to advisory Portfolio artefacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from forge.models.architecture_review import ArchitectureReview, PressureLevel, ReviewConfidence
from forge.models.mission_recommendation import (
    EngineeringEffort, MissionRecommendation, RecommendationCategory, RecommendationConfidence,
    RecommendationDependencies, RecommendationRepositoryContext, RequiredDiscipline,
)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class MissionRecommendationInput:
    """All declared inputs are immutable; no conversation, provider, clock, or repository retrieval is allowed."""

    review: ArchitectureReview
    repository_context: RecommendationRepositoryContext
    recommendation_timestamp: str
    available_disciplines: tuple[RequiredDiscipline, ...] = ()
    predecessor_mission_ids: tuple[str, ...] = ()
    successor_mission_ids: tuple[str, ...] = ()
    grouping: str | None = None
    sequencing: str | None = None

    def __post_init__(self) -> None:
        if not self.recommendation_timestamp:
            raise ValueError("recommendation timestamp is required as declared execution evidence")
        for name in ("available_disciplines", "predecessor_mission_ids", "successor_mission_ids"):
            values = getattr(self, name)
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError(f"recommendation input {name} must be unique and non-empty")
            object.__setattr__(self, name, tuple(sorted(values, key=lambda value: value.value if isinstance(value, RequiredDiscipline) else value)))


class MissionRecommendationEngine:
    """Generate only advisory Portfolio artefacts; never approve, prioritise, plan, or create a Mission."""

    def generate(self, recommendation_input: MissionRecommendationInput) -> tuple[MissionRecommendation, ...]:
        review = recommendation_input.review
        candidates = self._candidates(review)
        maturity_digest = "sha256:" + _digest([item.to_dict() for item in review.repository_maturity])
        dependencies = RecommendationDependencies(recommendation_input.predecessor_mission_ids, recommendation_input.successor_mission_ids,
                                                  recommendation_input.grouping, recommendation_input.sequencing)
        confidence = self._confidence(review)
        result: list[MissionRecommendation] = []
        for category, title, rationale, signals, disciplines in candidates:
            missing = tuple(item for item in disciplines if item not in recommendation_input.available_disciplines)
            identifier = "mission-recommendation-" + _digest({"review": review.id, "repository": recommendation_input.repository_context.to_dict(), "category": category.value, "signals": signals, "timestamp": recommendation_input.recommendation_timestamp})[:16]
            result.append(MissionRecommendation(identifier, recommendation_input.repository_context, review.id, maturity_digest, category, title,
                                                  rationale, "Provides an evidence-based opportunity for Business Workspace review.",
                                                  "Preserves the Architecture Review as assessment-only while recording a traceable Portfolio artefact.",
                                                  EngineeringEffort.MEDIUM, confidence, dependencies, disciplines, missing,
                                                  signals or ("repository_evidence_completeness",), recommendation_input.recommendation_timestamp,
                                                  signals or ("repository_only",), review_input_portfolio(review), True))
        return tuple(sorted(result, key=lambda item: item.id))

    @staticmethod
    def _candidates(review: ArchitectureReview) -> tuple[tuple[RecommendationCategory, str, str, tuple[str, ...], tuple[RequiredDiscipline, ...]], ...]:
        candidates: list[tuple[RecommendationCategory, str, str, tuple[str, ...], tuple[RequiredDiscipline, ...]]] = []
        if review.confidence is ReviewConfidence.INSUFFICIENT:
            candidates.append((RecommendationCategory.QUALIFICATION, "Qualify repository evidence", "Repository Truth and Execution Evidence are insufficient for Portfolio action.", (), (RequiredDiscipline.PLATFORM_ARCHITECTURE, RequiredDiscipline.ENGINEERING)))
        if review.capability_gaps:
            candidates.append((RecommendationCategory.NEW_CAPABILITY, "Consider a capability candidate", "Repository Truth identifies a capability gap for Business Workspace review.", review.capability_gaps, (RequiredDiscipline.PLATFORM_ARCHITECTURE, RequiredDiscipline.ENGINEERING, RequiredDiscipline.BUSINESS)))
        reconciliation = tuple(sorted(set(review.detected_duplication + (review.detected_inconsistencies if review.pressure.implementation is PressureLevel.HIGH else ()))))
        if reconciliation:
            candidates.append((RecommendationCategory.ARCHITECTURE_RECONCILIATION, "Consider architectural reconciliation", "Repository Truth records architectural responsibility that needs human reconciliation.", reconciliation, (RequiredDiscipline.PLATFORM_ARCHITECTURE, RequiredDiscipline.ENGINEERING)))
        if review.pressure.implementation is PressureLevel.HIGH:
            candidates.append((RecommendationCategory.TECHNICAL_DEBT, "Consider technical debt reduction", "Execution evidence records implementation pressure for Business Workspace review.", review.detected_inconsistencies or ("implementation_pressure",), (RequiredDiscipline.ENGINEERING, RequiredDiscipline.PLATFORM_ARCHITECTURE)))
        if review.pressure.operational is PressureLevel.HIGH:
            candidates.append((RecommendationCategory.RUNTIME, "Consider runtime improvement", "Operational evidence identifies a runtime opportunity for Business Workspace review.", ("operational_pressure",), (RequiredDiscipline.ENGINEERING, RequiredDiscipline.PLATFORM_ARCHITECTURE)))
        if review.pressure.repository_growth is PressureLevel.MODERATE:
            candidates.append((RecommendationCategory.PORTFOLIO, "Consider portfolio reconciliation", "Repository growth evidence identifies a Portfolio organisation opportunity.", ("repository_growth",), (RequiredDiscipline.BUSINESS, RequiredDiscipline.PLATFORM_ARCHITECTURE)))
        return tuple(sorted(candidates, key=lambda item: (item[0].value, item[1], item[3])))

    @staticmethod
    def _confidence(review: ArchitectureReview) -> RecommendationConfidence:
        maturity = sum(1 for item in review.repository_maturity if item.classification.value in {"established", "qualified"}) * 10
        pressure = 100 if review.pressure.architecture is PressureLevel.HIGH else 50 if review.pressure.architecture is PressureLevel.MODERATE else 0
        implementation = 100 if review.pressure.implementation is PressureLevel.HIGH else 0
        execution = 100 if not review.implementation_observations else 25
        completeness = min(100, len(review.repository_maturity) * 10)
        quality = {ReviewConfidence.INSUFFICIENT: 25, ReviewConfidence.MEDIUM: 60, ReviewConfidence.HIGH: 100}[review.confidence]
        return RecommendationConfidence(maturity, pressure, implementation, execution, completeness, quality)


def review_input_portfolio(review: ArchitectureReview) -> tuple[str, ...]:
    """The Architecture Review preserves the declared Portfolio reference without changing Portfolio state."""
    return review.portfolio_item_ids
