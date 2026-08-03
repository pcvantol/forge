"""Regression coverage for deterministic, repository-only Architecture Review 3.6."""

from __future__ import annotations

import unittest
from hashlib import sha256

from forge.models import (
    ArchitectureReviewInput, MaturityArea, MaturityClassification, PressureLevel,
    RecommendationKind, ReviewConfidence, ReviewEvidence, ReviewInputKind,
    ReviewSignal, ReviewSignalKind,
)
from forge.review import ArchitectureReviewEngine


def evidence(kind: ReviewInputKind, name: str) -> ReviewEvidence:
    return ReviewEvidence(kind, name, "1", f"local://{name}", "sha256:" + sha256(name.encode()).hexdigest())


class ArchitectureReviewEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ArchitectureReviewEngine()
        self.truth = evidence(ReviewInputKind.REPOSITORY_TRUTH, "truth")
        self.execution = evidence(ReviewInputKind.EXECUTION_EVIDENCE, "execution")

    def complete_input(self, signals: tuple[ReviewSignal, ...] = ()) -> ArchitectureReviewInput:
        return ArchitectureReviewInput("mission-1", (
            self.truth, self.execution, evidence(ReviewInputKind.CONSTITUTION, "constitution"),
            evidence(ReviewInputKind.ARCHITECTURE_HANDBOOK, "handbook"), evidence(ReviewInputKind.BOOTSTRAP_COMPLETION, "bootstrap"),
            evidence(ReviewInputKind.CAPABILITY_CATALOGUE, "capability"), evidence(ReviewInputKind.MISSION_DOCUMENT, "mission"),
            evidence(ReviewInputKind.MISSION_STATE, "state"), evidence(ReviewInputKind.EXECUTION_REPORT, "report"),
            evidence(ReviewInputKind.HISTORICAL_INTENT, "history"), evidence(ReviewInputKind.ENGINEERING_INTENT_HISTORY, "intents"),
            evidence(ReviewInputKind.PORTFOLIO, "portfolio"),
        ), signals, ("candidate-1",))

    def test_generates_immutable_architecture_review_and_maturity(self) -> None:
        review = self.engine.review(self.complete_input())
        self.assertEqual(review.confidence, ReviewConfidence.HIGH)
        self.assertEqual(len(review.repository_maturity), len(MaturityArea))
        self.assertEqual(dict((item.area, item.classification) for item in review.repository_maturity)[MaturityArea.ARCHITECTURE], MaturityClassification.QUALIFIED)
        self.assertTrue(review.input_digest.startswith("sha256:"))

    def test_repository_only_review_rejects_non_allow_list_by_construction(self) -> None:
        self.assertNotIn("conversation", {kind.value for kind in ReviewInputKind})
        self.assertNotIn("runtime_prompt", {kind.value for kind in ReviewInputKind})

    def test_insufficient_evidence_generates_qualification_recommendation(self) -> None:
        review = self.engine.review(ArchitectureReviewInput("mission-1", (evidence(ReviewInputKind.MISSION_DOCUMENT, "mission"),)))
        self.assertEqual(review.confidence, ReviewConfidence.INSUFFICIENT)
        self.assertEqual(review.recommendations[0].kind, RecommendationKind.QUALIFICATION)

    def test_recommendations_are_deterministic_for_input_order(self) -> None:
        signal = ReviewSignal(ReviewSignalKind.CAPABILITY_GAP, "gap-1", "Gap.", self.truth)
        first = self.complete_input((signal,))
        second = ArchitectureReviewInput(first.mission_id, tuple(reversed(first.evidence)), tuple(reversed(first.signals)), first.portfolio_item_ids)
        self.assertEqual(self.engine.review(first), self.engine.review(second))

    def test_architecture_pressure_needs_implementation_pressure(self) -> None:
        architecture = ReviewSignal(ReviewSignalKind.ARCHITECTURAL_INCONSISTENCY, "architecture-1", "Mismatch.", self.truth)
        no_need = self.engine.review(self.complete_input((architecture,)))
        self.assertEqual(no_need.pressure.architecture, PressureLevel.NONE)
        self.assertFalse(any(item.title == "Consider architectural reconciliation" for item in no_need.recommendations))
        implementation = ReviewSignal(ReviewSignalKind.IMPLEMENTATION_FAILURE, "implementation-1", "Failure.", self.execution)
        needed = self.engine.review(self.complete_input((architecture, implementation)))
        self.assertEqual(needed.pressure.implementation, PressureLevel.HIGH)
        self.assertEqual(needed.pressure.architecture, PressureLevel.HIGH)
        self.assertTrue(any(item.title == "Consider architectural reconciliation" for item in needed.recommendations))

    def test_portfolio_recommendation_is_advisory(self) -> None:
        gap = ReviewSignal(ReviewSignalKind.CAPABILITY_GAP, "gap-1", "Gap.", self.truth)
        review = self.engine.review(self.complete_input((gap,)))
        recommendation = next(item for item in review.recommendations if item.kind is RecommendationKind.NEW_CAPABILITY)
        self.assertTrue(recommendation.advisory)
        self.assertEqual(recommendation.review_id, review.id)


if __name__ == "__main__":
    unittest.main()
