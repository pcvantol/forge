"""Regression coverage for deterministic, advisory Mission Recommendations."""

from __future__ import annotations

import unittest
from hashlib import sha256

from forge.models import (
    ArchitectureReviewInput, MissionOrigin, RecommendationCategory, RecommendationRepositoryContext,
    RequiredDiscipline, ReviewEvidence, ReviewInputKind, ReviewSignal, ReviewSignalKind,
)
from forge.recommendations import MissionRecommendationEngine, MissionRecommendationInput
from forge.review import ArchitectureReviewEngine


def evidence(kind: ReviewInputKind, name: str) -> ReviewEvidence:
    return ReviewEvidence(kind, name, "1", f"local://{name}", "sha256:" + sha256(name.encode()).hexdigest())


class MissionRecommendationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.truth = evidence(ReviewInputKind.REPOSITORY_TRUTH, "truth")
        self.execution = evidence(ReviewInputKind.EXECUTION_EVIDENCE, "execution")
        self.review_engine = ArchitectureReviewEngine()
        self.engine = MissionRecommendationEngine()
        self.context = RecommendationRepositoryContext("forge", "abc123", self.truth.content_digest)

    def review(self, signals: tuple[ReviewSignal, ...] = ()):
        items = (self.truth, self.execution, evidence(ReviewInputKind.CONSTITUTION, "constitution"),
                 evidence(ReviewInputKind.ARCHITECTURE_HANDBOOK, "handbook"), evidence(ReviewInputKind.BOOTSTRAP_COMPLETION, "bootstrap"),
                 evidence(ReviewInputKind.CAPABILITY_CATALOGUE, "catalogue"), evidence(ReviewInputKind.MISSION_DOCUMENT, "mission"),
                 evidence(ReviewInputKind.MISSION_STATE, "state"), evidence(ReviewInputKind.EXECUTION_REPORT, "report"),
                 evidence(ReviewInputKind.HISTORICAL_INTENT, "history"), evidence(ReviewInputKind.ENGINEERING_INTENT_HISTORY, "intents"),
                 evidence(ReviewInputKind.PORTFOLIO, "portfolio"))
        return self.review_engine.review(ArchitectureReviewInput("completed-mission", items, signals, ("portfolio-1",)))

    def generate(self, review):
        return self.engine.generate(MissionRecommendationInput(review, self.context, "2026-08-03T23:39:43Z", (RequiredDiscipline.ENGINEERING,), ("mission-a",), ("mission-b",), "phase-c", "after_qualification"))

    def test_generates_evidence_based_capability_recommendation(self) -> None:
        review = self.review((ReviewSignal(ReviewSignalKind.CAPABILITY_GAP, "gap-1", "Gap.", self.truth),))
        recommendation = next(item for item in self.generate(review) if item.category is RecommendationCategory.NEW_CAPABILITY)
        self.assertEqual(recommendation.architecture_review_id, review.id)
        self.assertEqual(recommendation.repository_context, self.context)
        self.assertEqual(recommendation.dependencies.predecessor_mission_ids, ("mission-a",))
        self.assertTrue(recommendation.advisory)

    def test_insufficient_review_generates_qualification_recommendation(self) -> None:
        review = self.review_engine.review(ArchitectureReviewInput("completed-mission", (evidence(ReviewInputKind.MISSION_DOCUMENT, "only-mission"),)))
        recommendations = self.engine.generate(MissionRecommendationInput(review, self.context, "2026-08-03T23:39:43Z"))
        self.assertEqual(recommendations[0].category, RecommendationCategory.QUALIFICATION)

    def test_required_discipline_detection_names_missing_expertise(self) -> None:
        review = self.review((ReviewSignal(ReviewSignalKind.CAPABILITY_GAP, "gap-1", "Gap.", self.truth),))
        recommendation = next(item for item in self.generate(review) if item.category is RecommendationCategory.NEW_CAPABILITY)
        self.assertIn(RequiredDiscipline.BUSINESS, recommendation.missing_disciplines)
        self.assertNotIn(RequiredDiscipline.ENGINEERING, recommendation.missing_disciplines)

    def test_categories_and_dependency_generation(self) -> None:
        signals = (ReviewSignal(ReviewSignalKind.DUPLICATION, "duplicate-1", "Duplicate.", self.truth),
                   ReviewSignal(ReviewSignalKind.IMPLEMENTATION_FAILURE, "failure-1", "Failure.", self.execution),
                   ReviewSignal(ReviewSignalKind.ARCHITECTURAL_INCONSISTENCY, "architecture-1", "Mismatch.", self.truth),
                   ReviewSignal(ReviewSignalKind.OPERATIONAL_FAILURE, "operation-1", "Failure.", self.execution),
                   ReviewSignal(ReviewSignalKind.REPOSITORY_GROWTH, "growth-1", "Growth.", self.truth))
        categories = {item.category for item in self.generate(self.review(signals))}
        self.assertTrue({RecommendationCategory.ARCHITECTURE_RECONCILIATION, RecommendationCategory.TECHNICAL_DEBT,
                         RecommendationCategory.RUNTIME, RecommendationCategory.PORTFOLIO}.issubset(categories))

    def test_repository_only_recommendation_and_confidence_are_deterministic(self) -> None:
        review = self.review((ReviewSignal(ReviewSignalKind.CAPABILITY_GAP, "gap-1", "Gap.", self.truth),))
        first = self.generate(review)
        second = self.generate(review)
        self.assertEqual(first, second)
        self.assertEqual(first[0].confidence.score, second[0].confidence.score)
        self.assertNotIn("conversation", repr(first))

    def test_portfolio_integration_is_reference_only_and_recommendations_are_immutable(self) -> None:
        review = self.review((ReviewSignal(ReviewSignalKind.CAPABILITY_GAP, "gap-1", "Gap.", self.truth),))
        recommendation = self.generate(review)[0]
        self.assertEqual(recommendation.portfolio_item_ids, ("portfolio-1",))
        with self.assertRaises(Exception):
            recommendation.title = "mutated"  # type: ignore[misc]

    def test_maintenance_signals_produce_an_advisory_maintenance_recommendation_with_provenance(self) -> None:
        maintenance_kinds = (
            ReviewSignalKind.TECHNICAL_DEBT, ReviewSignalKind.DUPLICATE_IMPLEMENTATION,
            ReviewSignalKind.REFACTORING_OPPORTUNITY, ReviewSignalKind.DOCUMENTATION_INCONSISTENCY,
            ReviewSignalKind.DEPENDENCY_MAINTENANCE, ReviewSignalKind.REPOSITORY_HYGIENE,
            ReviewSignalKind.PERFORMANCE_OBSERVATION, ReviewSignalKind.ARCHITECTURE_EROSION,
        )
        review = self.review(tuple(
            ReviewSignal(kind, f"maintenance-{kind.value}", "Observed Repository Truth.", self.truth)
            for kind in maintenance_kinds
        ))
        recommendation = next(item for item in self.generate(review) if item.origin is MissionOrigin.MAINTENANCE)
        self.assertTrue(recommendation.advisory)
        self.assertEqual(recommendation.recommendation_source, "architecture_review")
        self.assertTrue(recommendation.repository_evidence)
        self.assertEqual(recommendation.decision_evidence_references, (f"architecture-review:{review.id}",))
        self.assertEqual(set(review.maintenance_observations), {f"maintenance-{kind.value}" for kind in maintenance_kinds})

    def test_supported_origins_are_extensible_machine_values(self) -> None:
        self.assertEqual(
            {origin.value for origin in MissionOrigin},
            {"business", "architecture", "maintenance", "security", "performance", "operations", "documentation", "user_feedback"},
        )


if __name__ == "__main__":
    unittest.main()
