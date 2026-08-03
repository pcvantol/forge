"""Regression coverage for Architecture Workspace governance only."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from forge.architecture import ArchitectureAdvisor, ArchitectureWorkspace, ArchitectureWorkspaceError, render_architecture_mission
from forge.governance import ApprovalStage, CanonicalGovernanceProfile, GovernanceRole, resolve_governance_profile
from forge.models import (
    ArchitectureMissionStatus, EngineeringEffort, MissionCandidate, MissionCandidateMaturity, MissionCandidateStatus,
    RecommendationConfidenceLevel, RequiredDiscipline,
)


def candidate(identifier: str = "candidate-1") -> MissionCandidate:
    return MissionCandidate(
        identifier, "Architecture Workspace", "A governed engineering opportunity.", "Prepare a bounded Mission.",
        "Keeps engineering governance explicit.", EngineeringEffort.MEDIUM, RecommendationConfidenceLevel.HIGH,
        (RequiredDiscipline.BUSINESS, RequiredDiscipline.PLATFORM_ARCHITECTURE), ("none-confirmed",), "architecture-review-1",
        "mission-recommendation-1", 70, "Business approval recorded.", MissionCandidateMaturity.READY_FOR_ARCHITECTURE,
        MissionCandidateStatus.APPROVED_FOR_ARCHITECTURE,
    )


class ArchitectureWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace = ArchitectureWorkspace(Path(self.temporary_directory.name) / "architecture-workspace.sqlite")

    def tearDown(self) -> None:
        self.workspace.close()
        self.temporary_directory.cleanup()

    def admit(self, identifier: str = "candidate-1"):
        return self.workspace.admit(candidate(identifier), actor="platform-architect", occurred_at="2026-08-04T10:00:00Z", rationale="Business approval verified.")

    def refine_to_ready(self, identifier: str = "candidate-1"):
        return self.workspace.refine(
            identifier, actor="platform-architect", occurred_at="2026-08-04T10:01:00Z", rationale="Architecture contract prepared.",
            scope=("Architecture Workspace governance.",), engineering_constraints=("No engineering execution.",),
            acceptance_criteria=("Approval remains auditable.",), technical_assumptions=("Local persistence is sufficient.",),
            dependencies=("business-approval-record",), required_capabilities=("architecture-workspace",),
            required_disciplines=(RequiredDiscipline.PLATFORM_ARCHITECTURE,), risks=("Scope expansion must be rejected.",),
        )

    def test_admission_accepts_only_business_approved_candidates_and_preserves_business_context(self) -> None:
        admitted = self.admit()
        self.assertEqual(admitted.status, ArchitectureMissionStatus.ARCHITECTURE_REVIEW)
        self.assertEqual(admitted.business_objective, candidate().business_objective)
        self.assertEqual(self.workspace.list()[0].candidate_id, "candidate-1")
        with self.assertRaises(ArchitectureWorkspaceError):
            self.workspace.admit(
                MissionCandidate(
                    "unapproved", "Unapproved", "Summary.", "Business objective.", "Business value.",
                    EngineeringEffort.SMALL, RecommendationConfidenceLevel.HIGH,
                    (RequiredDiscipline.BUSINESS,), ("none-confirmed",), "review-1", "recommendation-1", 1,
                    "Rationale.", MissionCandidateMaturity.READY_FOR_ARCHITECTURE, MissionCandidateStatus.BUSINESS_REVIEW,
                ), actor="platform-architect", occurred_at="2026-08-04T10:00:00Z", rationale="Invalid admission."
            )

    def test_architectural_refinement_changes_only_architecture_owned_fields_and_is_auditable(self) -> None:
        self.admit()
        refined = self.refine_to_ready()
        self.assertTrue(refined.is_engineering_ready())
        self.assertEqual([item.event for item in self.workspace.history("candidate-1")], ["admitted_from_business", "refined"])
        with self.assertRaises(ArchitectureWorkspaceError):
            self.workspace.refine("candidate-1", actor="platform-architect", occurred_at="2026-08-04T10:02:00Z", rationale="Invalid.", business_objective="Changed")

    def test_engineering_approval_changes_only_architecture_mission_state(self) -> None:
        self.admit()
        with self.assertRaises(ArchitectureWorkspaceError):
            self.workspace.approve_for_engineering("candidate-1", actor="platform-architect", occurred_at="2026-08-04T10:02:00Z", rationale="Incomplete.")
        self.refine_to_ready()
        approved = self.workspace.approve_for_engineering("candidate-1", actor="platform-architect", occurred_at="2026-08-04T10:03:00Z", rationale="Ready for bounded engineering.")
        self.assertEqual(approved.status, ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING)
        self.assertEqual(approved.business_objective, candidate().business_objective)
        self.assertEqual(self.workspace.history("candidate-1")[-1].event, "approved_for_engineering")

    def test_return_reject_and_archive_are_recorded_non_executing_transitions(self) -> None:
        for identifier, method, expected in (
            ("returned", "return_to_business", ArchitectureMissionStatus.RETURNED_TO_BUSINESS),
            ("rejected", "reject", ArchitectureMissionStatus.REJECTED),
            ("archived", "archive", ArchitectureMissionStatus.ARCHIVED),
        ):
            self.admit(identifier)
            result = getattr(self.workspace, method)(identifier, actor="platform-architect", occurred_at="2026-08-04T10:01:00Z", rationale="Governance decision.")
            self.assertEqual(result.status, expected)

    def test_advisor_is_immutable_advisory_and_cannot_approve(self) -> None:
        mission = self.admit()
        advice = ArchitectureAdvisor().advise(mission)
        self.assertTrue(advice.advisory)
        self.assertIn("requires architectural refinement", advice.technical_feasibility)
        with self.assertRaises(FrozenInstanceError):
            advice.advisory = False  # type: ignore[misc]
        self.assertFalse(hasattr(ArchitectureAdvisor(), "approve"))
        rendered = render_architecture_mission(mission)
        self.assertFalse(rendered["execution_available"])

    def test_solo_profile_keeps_architecture_approval_distinct_and_assigns_platform_architect(self) -> None:
        profile = resolve_governance_profile(CanonicalGovernanceProfile.SOLO)
        self.assertEqual(profile.role_assignments[GovernanceRole.PLATFORM_ARCHITECT], ("primary_operator",))
        self.assertNotEqual(profile.approval_matrix[ApprovalStage.BUSINESS], profile.approval_matrix[ApprovalStage.ARCHITECTURE])

    def test_workspace_has_no_engineering_execution_or_repository_mutation_api(self) -> None:
        forbidden = {"execute", "run", "dispatch", "plan", "mutate_repository", "commit", "push"}
        self.assertTrue(forbidden.isdisjoint(set(dir(self.workspace))))


if __name__ == "__main__":
    unittest.main()
