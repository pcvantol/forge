"""Regression coverage for Business Workspace portfolio governance only."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path

from forge.business import BusinessAdvisor, BusinessWorkspace, BusinessWorkspaceError, render_mission_recommendation
from forge.governance import ApprovalStage, CanonicalGovernanceProfile, GovernanceRole, resolve_governance_profile
from forge.models import (
    EngineeringEffort, MissionCandidate, MissionCandidateMaturity, MissionCandidateStatus, MissionRecommendation,
    RecommendationCategory, RecommendationConfidence, RecommendationDependencies, RecommendationRepositoryContext,
    RecommendationConfidenceLevel, RequiredDiscipline,
)


def candidate(identifier: str) -> MissionCandidate:
    return MissionCandidate(
        identifier, "Business Workspace", "A governed portfolio opportunity.", "Give owners a business workspace.",
        "Makes portfolio decisions explicit.", EngineeringEffort.MEDIUM, RecommendationConfidenceLevel.HIGH,
        (RequiredDiscipline.BUSINESS, RequiredDiscipline.PLATFORM_ARCHITECTURE), ("none-confirmed",), "architecture-review-1",
        "mission-recommendation-1", 70, "Business review is needed before architecture.",
        MissionCandidateMaturity.READY_FOR_ARCHITECTURE,
    )


def recommendation() -> MissionRecommendation:
    digest = "sha256:" + sha256(b"truth").hexdigest()
    return MissionRecommendation(
        "mission-recommendation-1", RecommendationRepositoryContext("forge", "revision", digest), "architecture-review-1", digest,
        RecommendationCategory.NEW_CAPABILITY, "Business Workspace", "An evidence-based opportunity.", "Improves governance.",
        "Preserves separation.", EngineeringEffort.MEDIUM, RecommendationConfidence(80, 60, 20, 80, 70, 80),
        RecommendationDependencies(), (RequiredDiscipline.BUSINESS,), (RequiredDiscipline.BUSINESS,), ("capability-gap",),
        "2026-08-03T23:40:18Z", ("signal-1",), ("portfolio-1",),
    )


class BusinessWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace = BusinessWorkspace(Path(self.temporary_directory.name) / "business-workspace.sqlite")

    def tearDown(self) -> None:
        self.workspace.close()
        self.temporary_directory.cleanup()

    def create(self, identifier: str = "candidate-1") -> MissionCandidate:
        return self.workspace.create(candidate(identifier), actor="business-owner", occurred_at="2026-08-03T23:40:18Z")

    def test_mission_candidate_display_lists_business_fields_and_recommendation_rendering(self) -> None:
        self.create()
        displayed = self.workspace.list()
        self.assertEqual(displayed[0].title, "Business Workspace")
        self.assertEqual(displayed[0].mission_recommendation_reference, "mission-recommendation-1")
        rendered = render_mission_recommendation(recommendation())
        self.assertEqual(rendered["architecture_review_reference"], "architecture-review-1")
        self.assertTrue(rendered["advisory"])

    def test_business_approval_changes_only_candidate_state_and_is_auditable(self) -> None:
        self.create()
        approved = self.workspace.approve_for_architecture("candidate-1", actor="business-owner", occurred_at="2026-08-03T23:41:18Z", rationale="Portfolio priority confirmed.")
        self.assertEqual(approved.status, MissionCandidateStatus.APPROVED_FOR_ARCHITECTURE)
        self.assertEqual([item.event for item in self.workspace.history("candidate-1")], ["created", "approved_for_architecture"])

    def test_business_rejection_and_archive_are_terminal_business_transitions(self) -> None:
        self.create("candidate-rejected")
        rejected = self.workspace.reject("candidate-rejected", actor="business-owner", occurred_at="2026-08-03T23:41:18Z", rationale="Insufficient value.")
        self.assertEqual(rejected.status, MissionCandidateStatus.REJECTED)
        with self.assertRaises(BusinessWorkspaceError):
            self.workspace.approve_for_architecture("candidate-rejected", actor="business-owner", occurred_at="2026-08-03T23:42:18Z", rationale="Cannot reopen here.")
        self.create("candidate-archived")
        archived = self.workspace.archive("candidate-archived", actor="business-owner", occurred_at="2026-08-03T23:41:18Z", rationale="No longer strategic.")
        self.assertEqual(archived.status, MissionCandidateStatus.ARCHIVED)

    def test_business_refinement_preserves_recommendation_references(self) -> None:
        self.create()
        refined = self.workspace.refine("candidate-1", actor="business-owner", occurred_at="2026-08-03T23:41:18Z", rationale="Priority clarified.", priority=90)
        self.assertEqual(refined.priority, 90)
        self.assertEqual(refined.mission_recommendation_reference, "mission-recommendation-1")

    def test_business_advisor_is_immutable_advisory_and_never_approves(self) -> None:
        advice = BusinessAdvisor().advise(candidate("candidate-advice"))
        self.assertTrue(advice.advisory)
        self.assertIn(RequiredDiscipline.BUSINESS, advice.missing_disciplines)
        with self.assertRaises(FrozenInstanceError):
            advice.advisory = False  # type: ignore[misc]
        self.assertFalse(hasattr(BusinessAdvisor(), "approve"))

    def test_solo_governance_keeps_business_and_architecture_approvals_separate(self) -> None:
        profile = resolve_governance_profile(CanonicalGovernanceProfile.SOLO)
        self.assertEqual(profile.role_assignments[GovernanceRole.BUSINESS_OWNER], ("primary_operator",))
        self.assertEqual(profile.role_assignments[GovernanceRole.PLATFORM_ARCHITECT], ("primary_operator",))
        self.assertNotEqual(profile.approval_matrix[ApprovalStage.BUSINESS], profile.approval_matrix[ApprovalStage.ARCHITECTURE])

    def test_all_profiles_assign_roles_and_legacy_values_resolve_explicitly(self) -> None:
        for name in ("solo", "duo", "startup", "enterprise"):
            profile = resolve_governance_profile(name)
            self.assertIn(GovernanceRole.BUSINESS_OWNER, profile.role_assignments)
            self.assertIn(GovernanceRole.PLATFORM_ARCHITECT, profile.role_assignments)
        legacy = resolve_governance_profile("two_person")
        self.assertEqual(legacy.profile, CanonicalGovernanceProfile.DUO)
        self.assertIsNotNone(legacy.compatibility_note)

    def test_business_workspace_has_no_engineering_execution_or_repository_mutation_api(self) -> None:
        forbidden = {"execute", "run", "dispatch", "create_mission", "approve_for_engineering", "mutate_repository", "commit", "push"}
        self.assertTrue(forbidden.isdisjoint(set(dir(self.workspace))))
        self.create()
        self.assertEqual(len(self.workspace.list()), 1)


if __name__ == "__main__":
    unittest.main()
