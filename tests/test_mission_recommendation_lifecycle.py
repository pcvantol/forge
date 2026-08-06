"""Regression coverage for the canonical recommendation governance lifecycle."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.lifecycle import (
    LifecycleError,
    MissionCandidate,
    MissionRecommendation,
    RecommendationLifecycleStore,
    RecommendationStatus,
)


def recommendation() -> MissionRecommendation:
    return MissionRecommendation(
        id="recommendation-1", title="Mission Recommendation Lifecycle", mission_origin="portfolio_intelligence",
        business_summary="Govern lifecycle before execution.", engineering_summary="Separate governance from Runtime.",
        business_value="Auditable approval.", engineering_value="Deterministic allocation.",
        architectural_value="Explicit ownership.", repository_evidence=("repository:architecture",),
        decision_evidence_reference="architecture-review:1", dependencies=("portfolio-intelligence",),
        alternatives=("Keep recommendations advisory without lifecycle.",), confidence=91,
        recommendation_timestamp="2026-08-06T14:41:17Z",
    )


class MissionRecommendationLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.store = RecommendationLifecycleStore(Path(self.directory.name) / "governance" / "lifecycle.sqlite")

    def tearDown(self) -> None:
        self.store.close(); self.directory.cleanup()

    def test_lifecycle_is_deterministic_auditable_and_allocates_only_after_both_approvals(self) -> None:
        self.store.create_recommendation(recommendation(), actor="portfolio-intelligence", rationale="Repository analysis recommends governance lifecycle.")
        self.store.transition("recommendation-1", RecommendationStatus.RECOMMENDED, actor="portfolio-intelligence", occurred_at="2026-08-06T14:42:00Z", rationale="Recommendation is ready for Business review.")
        self.store.transition("recommendation-1", RecommendationStatus.BUSINESS_APPROVED, actor="business-owner", occurred_at="2026-08-06T14:43:00Z", rationale="Business value approved.")
        self.store.transition("recommendation-1", RecommendationStatus.ARCHITECTURE_APPROVED, actor="platform-architect", occurred_at="2026-08-06T14:44:00Z", rationale="Architecture constraints approved.")
        candidate = self.store.create_candidate(MissionCandidate("candidate-1", "recommendation-1", "Mission Recommendation Lifecycle", "Implement lifecycle.", ("governance",), ("tests pass",), ("Runtime stores allocated Missions only",)))
        self.assertEqual(self.store.update_candidate(candidate.id, objective="Implement canonical lifecycle.").objective, "Implement canonical lifecycle.")
        allocation = self.store.allocate(candidate.id, actor="forge", occurred_at="2026-08-06T14:45:00Z", rationale="Both approvals are immutable and recorded.", allocate_mission_id=lambda source, _: "MISSION-0006")
        self.assertEqual(allocation.mission_id, "MISSION-0006")
        self.assertEqual(self.store.get_recommendation("recommendation-1").status, RecommendationStatus.MISSION_ALLOCATED)
        with self.assertRaises(LifecycleError):
            self.store.update_candidate(candidate.id, title="Mutable no longer")
        completion = self.store.record_completion("MISSION-0006", actor="forge", occurred_at="2026-08-06T15:00:00Z", rationale="Execution receipt validated.", references=("receipt:1",))
        self.assertEqual(completion.kind, "mission_completion")
        self.assertEqual([item.kind for item in self.store.history("recommendation-1")], ["architecture_decision", "business_decision", "mission_allocation", "mission_completion", "recommendation", "recommendation_transition"])

    def test_reject_and_invalid_transitions_remain_historical_and_fail_closed(self) -> None:
        self.store.create_recommendation(recommendation(), actor="portfolio-intelligence", rationale="Created.")
        with self.assertRaises(LifecycleError):
            self.store.transition("recommendation-1", RecommendationStatus.BUSINESS_APPROVED, actor="business-owner", occurred_at="2026-08-06T14:43:00Z", rationale="Skipping recommendation is forbidden.")
        self.store.transition("recommendation-1", RecommendationStatus.RECOMMENDED, actor="portfolio-intelligence", occurred_at="2026-08-06T14:42:00Z", rationale="Ready.")
        rejected = self.store.transition("recommendation-1", RecommendationStatus.BUSINESS_REJECTED, actor="business-owner", occurred_at="2026-08-06T14:43:00Z", rationale="Not a current priority.")
        self.assertEqual(rejected.status, RecommendationStatus.BUSINESS_REJECTED)
        self.assertGreaterEqual(len(self.store.history("recommendation-1")), 3)


if __name__ == "__main__":
    unittest.main()
