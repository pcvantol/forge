"""Deterministic Portfolio Intelligence operation and governance persistence.

This adapter accepts already-observed repository evidence. It does not read a
repository, approve work, allocate a Mission, create Runtime state, or invoke a
scheduler. Its only mutation target is the Recommendation Lifecycle store.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from forge.lifecycle import LifecycleDecisionEvidence, MissionRecommendation as LifecycleRecommendation, RecommendationLifecycleStore
from forge.models import ArchitectureReviewInput, RecommendationCategory, RecommendationRepositoryContext, RequiredDiscipline, ReviewEvidence, ReviewSignal
from forge.recommendations import MissionRecommendationEngine, MissionRecommendationInput
from forge.review import ArchitectureReviewEngine


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class PortfolioIntelligenceInput:
    """Declared, repository-observed input for one recommendation operation."""

    repository_context: RecommendationRepositoryContext
    completed_mission_id: str
    evidence: tuple[ReviewEvidence, ...]
    signals: tuple[ReviewSignal, ...]
    portfolio_item_ids: tuple[str, ...]
    recommendation_timestamp: str
    available_disciplines: tuple[RequiredDiscipline, ...]
    execution_evidence_references: tuple[str, ...]
    known_constraints: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("evidence", "signals", "portfolio_item_ids", "available_disciplines", "execution_evidence_references", "known_constraints"):
            values = getattr(self, field)
            if not values or len(values) != len(set(values)):
                raise ValueError(f"portfolio intelligence {field} must be non-empty and unique")
        if not self.completed_mission_id or not self.recommendation_timestamp:
            raise ValueError("portfolio intelligence requires mission and timestamp")


@dataclass(frozen=True)
class PersistedRecommendationSet:
    recommendation_set_id: str
    recommendations: tuple[LifecycleRecommendation, ...]
    decision_evidence: LifecycleDecisionEvidence

    @property
    def recommended(self) -> LifecycleRecommendation:
        return self.recommendations[0]


_PROFILES: dict[RecommendationCategory, tuple[str, str, str, str, str, tuple[str, ...]]] = {
    RecommendationCategory.NEW_CAPABILITY: ("Operationalize persisted Portfolio Intelligence", "Make evidence-backed recommendation generation, ranking, lifecycle persistence, and Business Workspace review a repeatable Forge governance operation.", "A Business Owner can inspect a real, ranked recommendation set before any approval or Mission allocation.", "The recommendation engine, lifecycle store, and Business Workspace expose one consistent canonical governance artefact.", "Portfolio Intelligence remains a library-only capability and future governance decisions lack durable advisory inputs.", ("No Business approval is implied.", "No Mission Runtime state may be created.")),
    RecommendationCategory.ARCHITECTURE_RECONCILIATION: ("Reconcile Generation 2 governance contracts", "Align the rich Mission Recommendation model with the lifecycle persistence and Business Workspace projection contracts.", "Business decisions retain complete, comparable recommendation context.", "Canonical governance artefacts preserve rank, risk, disciplines, constraints, and evidence provenance.", "Divergent contracts can cause incomplete governance records and undermine auditability.", ("Recommendations remain advisory.", "Runtime remains separate from recommendation history.")),
    RecommendationCategory.TECHNICAL_DEBT: ("Harden recommendation governance persistence", "Remove persistence gaps between recommendation analysis, lifecycle history, and restart-safe Business Workspace views.", "Business review remains reliable after local process restart.", "Governance state stays append-only and independently queryable from Runtime.", "Manual reconstruction may become necessary and weaken deterministic governance evidence.", ("Do not alter historical Runtime compatibility records.", "Do not allocate a Mission.")),
    RecommendationCategory.PORTFOLIO: ("Reconcile the Generation 2 portfolio view", "Update Portfolio-facing projections so completed Mission outcomes and current governance opportunities are consistently represented.", "Business can prioritize from current project maturity rather than stale transition language.", "Portfolio documentation and live projections agree on the post-MISSION-0006 state.", "Stale portfolio context can misdirect future prioritisation.", ("Historical seed Missions remain Repository Truth only.", "No automatic approval or scheduling.")),
}


class PortfolioIntelligence:
    """Generate, rank, and persist advisory recommendations without approval."""

    def run(self, source: PortfolioIntelligenceInput, lifecycle: RecommendationLifecycleStore) -> PersistedRecommendationSet:
        review = ArchitectureReviewEngine().review(ArchitectureReviewInput(source.completed_mission_id, source.evidence, source.signals, source.portfolio_item_ids))
        generated = MissionRecommendationEngine().generate(MissionRecommendationInput(review, source.repository_context, source.recommendation_timestamp, source.available_disciplines, (), (), "generation-2", "post_mission_outcome", (f"architecture-review:{review.id}", *source.execution_evidence_references)))
        # The pure engine may surface the same deterministic category/signal
        # combination through both pressure and maintenance rules. A lifecycle
        # record is content-addressed, so retain one canonical instance.
        selected = tuple({item.id: item for item in generated if item.category in _PROFILES}.values())
        if not selected:
            raise ValueError("Portfolio Intelligence found no evidence-backed recommendation candidates")
        set_id = "recommendation-set-" + _digest({"review": review.id, "recommendations": [item.id for item in selected]})[:16]
        ranked = tuple(sorted(selected, key=self._rank_key))
        for rank, recommendation in enumerate(ranked, start=1):
            projected = self._project(recommendation, set_id, rank, source.known_constraints)
            try:
                lifecycle.get_recommendation(projected.id)
            except ValueError:
                lifecycle.create_recommendation(projected, actor="portfolio-intelligence", rationale="Declared Repository Truth and completed Mission evidence produced this advisory recommendation.")
        ordered = lifecycle.recommendation_set(set_id)
        evidence_id = "decision-mission-recommendation-" + _digest({"set": set_id, "ranked": [item.id for item in ordered]})[:16]
        try:
            decision = next(item for item in lifecycle.history(ordered[0].id) if item.id == evidence_id)
        except StopIteration:
            decision = lifecycle.append_recommendation_decision(ordered[0].id, evidence_id=evidence_id, occurred_at=source.recommendation_timestamp, actor="portfolio-intelligence", confidence=ordered[0].confidence, rationale="Deterministic ranking considers declared business, architectural, engineering, deferred-risk, dependency-readiness, maturity-fit, capability-gap, and maintenance-pressure signals.", ranked_alternatives=tuple(item.id for item in ordered), references=tuple(sorted({*source.execution_evidence_references, *(reference for item in ordered for reference in item.evidence_references)})))
        reconciled = lifecycle.reconcile_recommendation_set_selection(
            set_id, selected_recommendation_id=ordered[0].id,
            decision_evidence_id=decision.id, actor="portfolio-intelligence",
            occurred_at=source.recommendation_timestamp,
            rationale="Deterministic ranking selects rank one; viable lower-ranked alternatives remain proposed.",
        )
        return PersistedRecommendationSet(set_id, reconciled, decision)

    @staticmethod
    def _rank_key(recommendation) -> tuple[int, int, str]:
        category_weight = {RecommendationCategory.NEW_CAPABILITY: 30, RecommendationCategory.ARCHITECTURE_RECONCILIATION: 24, RecommendationCategory.TECHNICAL_DEBT: 20, RecommendationCategory.PORTFOLIO: 16}.get(recommendation.category, 0)
        risk_weight = 15 if recommendation.category in {RecommendationCategory.NEW_CAPABILITY, RecommendationCategory.ARCHITECTURE_RECONCILIATION} else 10
        return (-(recommendation.confidence.score + category_weight + risk_weight), -len(recommendation.capability_impact), recommendation.id)

    @staticmethod
    def _project(recommendation, set_id: str, rank: int, known_constraints: tuple[str, ...]) -> LifecycleRecommendation:
        title, business_summary, outcome, repository_impact, deferred_risk, profile_constraints = _PROFILES[recommendation.category]
        evidence = tuple(sorted({*(item.id for item in recommendation.repository_evidence), recommendation.architecture_review_id, *recommendation.decision_evidence_references}))
        return LifecycleRecommendation(id=recommendation.id, title=title, mission_origin=recommendation.origin.value, business_summary=business_summary, engineering_summary=recommendation.expected_engineering_value, business_value=recommendation.business_value, engineering_value=recommendation.expected_engineering_value, architectural_value=recommendation.architectural_value, repository_evidence=tuple(item.id for item in recommendation.repository_evidence), decision_evidence_reference=recommendation.decision_evidence_references[0], dependencies=tuple((*recommendation.dependencies.predecessor_mission_ids, *recommendation.dependencies.successor_mission_ids)) or ("none-confirmed",), alternatives=("Defer pending later Portfolio review.",), confidence=recommendation.confidence.score, recommendation_timestamp=recommendation.recommendation_timestamp, recommendation_set_id=set_id, rank=rank, recommendation_type=recommendation.category.value, expected_outcome=outcome, expected_repository_impact=repository_impact, risk_if_deferred=deferred_risk, required_disciplines=tuple(item.value for item in recommendation.required_disciplines), known_constraints=tuple(sorted({*known_constraints, *profile_constraints})), evidence_references=evidence)
