"""End-to-end Portfolio Intelligence recommendation persistence regressions."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.business import render_persisted_mission_recommendation, render_persisted_recommendation_set
from forge.lifecycle import RecommendationLifecycleStore, RecommendationStatus
from forge.models import (
    RecommendationRepositoryContext, RequiredDiscipline, ReviewEvidence,
    ReviewInputKind, ReviewSignal, ReviewSignalKind,
)
from forge.portfolio_intelligence import PortfolioIntelligence, PortfolioIntelligenceInput


def digest(value: str) -> str:
    return "sha256:" + sha256(value.encode()).hexdigest()


def evidence(kind: ReviewInputKind, identifier: str) -> ReviewEvidence:
    return ReviewEvidence(kind, identifier, "ad6d34e", f"repository://{identifier}", digest(identifier))


class PortfolioIntelligenceOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.path = Path(self.temporary.name) / "governance" / "recommendations.sqlite"
        self.store = RecommendationLifecycleStore(self.path)
        self.operation = PortfolioIntelligence()

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def source(self) -> PortfolioIntelligenceInput:
        truth = evidence(ReviewInputKind.REPOSITORY_TRUTH, "repository-truth")
        kinds = tuple(kind for kind in ReviewInputKind if kind is not ReviewInputKind.REPOSITORY_TRUTH)
        all_evidence = (truth, *(evidence(kind, kind.value) for kind in kinds))
        signals = (
            ReviewSignal(ReviewSignalKind.CAPABILITY_GAP, "portfolio-persistence", "No persisted canonical recommendation exists.", truth),
            ReviewSignal(ReviewSignalKind.ARCHITECTURAL_INCONSISTENCY, "recommendation-contract-divergence", "Lifecycle and source recommendation context differ.", truth),
            ReviewSignal(ReviewSignalKind.TECHNICAL_DEBT, "recommendation-contract-divergence", "Governance persistence needs reconciliation.", truth),
            ReviewSignal(ReviewSignalKind.REPOSITORY_GROWTH, "generation-two-governance-surface", "Generation 2 needs an updated portfolio view.", truth),
        )
        return PortfolioIntelligenceInput(
            RecommendationRepositoryContext("forge", "ad6d34e", digest("repository-truth")), "MISSION-0006",
            all_evidence, signals, ("portfolio:forge",), "2026-08-15T20:00:00Z",
            (RequiredDiscipline.ENGINEERING, RequiredDiscipline.PLATFORM_ARCHITECTURE, RequiredDiscipline.BUSINESS),
            ("execution-receipt:MISSION-0006",),
            ("Business approval remains explicit.", "Recommendations must not create Runtime state."),
        )

    def test_persists_ranked_recommendations_and_stops_before_approval(self) -> None:
        result = self.operation.run(self.source(), self.store)
        self.assertEqual(len(result.recommendations), 4)
        self.assertEqual([item.rank for item in result.recommendations], [1, 2, 3, 4])
        self.assertEqual(result.recommended.title, "Operationalize persisted Portfolio Intelligence")
        self.assertEqual(result.recommended.status.value, "RECOMMENDED")
        self.assertEqual([item.status.value for item in result.recommendations], ["RECOMMENDED", "PROPOSED", "PROPOSED", "PROPOSED"])
        self.assertEqual(result.decision_evidence.decision_type, "MISSION_RECOMMENDATION")
        self.assertEqual(result.decision_evidence.ranked_alternatives, tuple(item.id for item in result.recommendations))
        self.assertIsNone(self.store.candidate_for_recommendation(result.recommended.id))
        self.assertIsNone(self.store.allocation_for_recommendation(result.recommended.id))
        view = render_persisted_mission_recommendation(result.recommended)
        self.assertEqual(view["approval_status"], "NOT_YET_APPROVED")
        self.assertEqual(view["recommendation_status"], "RECOMMENDED")
        workspace = render_persisted_recommendation_set(result.recommendations, result.decision_evidence)
        self.assertEqual([item["decision_evidence_reference"] for item in workspace], [result.decision_evidence.id] * 4)
        self.assertEqual(sum(item["recommendation_status"] == "RECOMMENDED" for item in workspace), 1)

    def test_reinvocation_and_restart_reuse_equivalent_recommendations(self) -> None:
        first = self.operation.run(self.source(), self.store)
        self.store.close()
        self.store = RecommendationLifecycleStore(self.path)
        second = self.operation.run(self.source(), self.store)
        self.assertEqual(first.recommendation_set_id, second.recommendation_set_id)
        self.assertEqual([item.id for item in first.recommendations], [item.id for item in second.recommendations])
        self.assertEqual([item.status for item in first.recommendations], [item.status for item in second.recommendations])
        self.assertEqual(second.decision_evidence.id, first.decision_evidence.id)
        self.assertEqual(len(self.store.list_recommendations()), 4)

    def test_ranking_is_deterministic_and_evidence_backed(self) -> None:
        first = self.operation.run(self.source(), self.store)
        second = self.operation.run(self.source(), self.store)
        self.assertEqual([(item.id, item.rank) for item in first.recommendations], [(item.id, item.rank) for item in second.recommendations])
        for item in first.recommendations:
            self.assertTrue(item.evidence_references)
            self.assertTrue(item.risk_if_deferred)
            self.assertTrue(item.required_disciplines)

    def test_reconciles_legacy_multiple_recommended_records_append_only(self) -> None:
        first = self.operation.run(self.source(), self.store)
        for recommendation in first.recommendations[1:]:
            self.store.transition(recommendation.id, RecommendationStatus.RECOMMENDED,
                                  actor="legacy-portfolio-intelligence", occurred_at="2026-08-15T20:01:00Z",
                                  rationale="Legacy defect.", references=(recommendation.id,))
        reconciled = self.operation.run(self.source(), self.store)
        self.assertEqual([item.status.value for item in reconciled.recommendations], ["RECOMMENDED", "PROPOSED", "PROPOSED", "PROPOSED"])
        self.assertEqual(reconciled.decision_evidence.id, first.decision_evidence.id)
        self.assertTrue(all(
            any(item.kind == "recommendation_selection_correction" for item in self.store.history(recommendation.id))
            for recommendation in reconciled.recommendations[1:]
        ))


if __name__ == "__main__":
    unittest.main()
