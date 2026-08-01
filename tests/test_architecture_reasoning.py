import unittest
from dataclasses import FrozenInstanceError

from forge.models import (
    ArchitecturalEvaluation,
    ArchitecturalEvaluationCriterion,
    ArchitecturalFinding,
    ArchitecturalFindingCategory,
    ArchitecturalOpportunity,
    ArchitecturalOpportunityStatus,
    CapabilityImpact,
    IntentReference,
    RepositoryAssessment,
    RoadmapImpact,
    accept_for_proposal,
    hand_off_to_proposal,
)


def reference(identifier: str) -> IntentReference:
    return IntentReference(identifier, "1.0", f"local://{identifier}")


def opportunity() -> ArchitecturalOpportunity:
    return ArchitecturalOpportunity(
        "architecture-reasoning", "Architecture Reasoning", "Make the pre-authoring decision model explicit.",
        ("finding-knowledge-gap",), CapabilityImpact("Introduces an architecture reasoning capability.", (reference("capability-reasoning"),)),
        RoadmapImpact("Precedes the AI Architect Provider abstraction.", (reference("roadmap-phase-b"),)),
    )


def evaluation() -> ArchitecturalEvaluation:
    return ArchitecturalEvaluation(
        "architecture-reasoning", tuple(reversed(tuple(ArchitecturalEvaluationCriterion))),
        "The opportunity is constitutionally aligned and ready for human review.", (reference("constitution-article-5"),),
    )


class ArchitectureReasoningModelTests(unittest.TestCase):
    def test_reasoning_model_is_immutable_and_deterministically_serialized(self) -> None:
        assessment = RepositoryAssessment(
            "forge", "Repository knowledge shows an explicit pre-authoring reasoning gap.",
            (reference("knowledge-model"), reference("constitution")), (reference("repository-head"),),
        )
        self.assertEqual([item["id"] for item in assessment.to_dict()["knowledge_references"]], ["constitution", "knowledge-model"])
        with self.assertRaises(FrozenInstanceError):
            assessment.summary = "changed"  # type: ignore[misc]

    def test_architectural_finding_categories_are_closed_and_traceable(self) -> None:
        self.assertEqual(
            {category.value for category in ArchitecturalFindingCategory},
            {"missing_architecture", "missing_capability", "architectural_inconsistency", "repository_drift", "knowledge_gap", "governance_gap", "documentation_gap"},
        )
        finding = ArchitecturalFinding(
            "finding-knowledge-gap", "forge", ArchitecturalFindingCategory.KNOWLEDGE_GAP,
            "The reasoning path is not represented as repository knowledge.", (reference("repository-head"),), (reference("capability-reasoning"),),
        )
        self.assertEqual(finding.to_dict()["category"], "knowledge_gap")

    def test_opportunity_requires_evaluation_of_all_declared_criteria(self) -> None:
        model = evaluation()
        self.assertEqual(set(model.criteria), set(ArchitecturalEvaluationCriterion))
        with self.assertRaisesRegex(ValueError, "every evaluation criterion"):
            ArchitecturalEvaluation("architecture-reasoning", (ArchitecturalEvaluationCriterion.COMPLEXITY,), "Incomplete.", (reference("constitution"),))

    def test_human_acceptance_enables_a_traceable_proposal_handoff_without_creating_a_proposal(self) -> None:
        candidate = opportunity()
        with self.assertRaisesRegex(ValueError, "human-accepted"):
            hand_off_to_proposal(candidate, evaluation())
        accepted = accept_for_proposal(candidate, evaluation(), reference("architectural-review-001"))
        self.assertEqual(accepted.status, ArchitecturalOpportunityStatus.ACCEPTED_FOR_PROPOSAL)
        handoff = hand_off_to_proposal(accepted, evaluation())
        self.assertEqual(handoff.opportunity_id, candidate.id)
        self.assertEqual(handoff.decision_reference.id, "architectural-review-001")
        with self.assertRaisesRegex(ValueError, "only identified"):
            accept_for_proposal(accepted, evaluation(), reference("second-decision"))


if __name__ == "__main__":
    unittest.main()
