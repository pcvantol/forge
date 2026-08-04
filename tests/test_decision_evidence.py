"""Regression coverage for immutable, Repository Truth-rooted Decision Evidence."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from forge.architecture import render_architecture_decision_evidence
from forge.business import render_business_decision_evidence
from forge.decision_evidence import DecisionEvidenceRepository, DecisionEvidenceRepositoryError
from forge.execution import render_execution_decision_evidence_reference
from forge.models import (
    ApprovalState, DecisionAlternative, DecisionConfidence, DecisionEvidence, DecisionOutcome, DecisionReference,
    DecisionReferenceKind, DecisionType,
)


def reference(kind: DecisionReferenceKind, identifier: str) -> DecisionReference:
    return DecisionReference(kind, identifier, f"repository://{identifier}", "r1", "sha256:" + sha256(identifier.encode()).hexdigest())


def decision() -> DecisionEvidence:
    repository_truth = reference(DecisionReferenceKind.REPOSITORY_TRUTH, "repository-truth-1")
    review = reference(DecisionReferenceKind.ARCHITECTURE_REVIEW, "architecture-review-1")
    execution = reference(DecisionReferenceKind.EXECUTION_EVIDENCE, "execution-evidence-1")
    mission_state = reference(DecisionReferenceKind.MISSION_STATE, "mission-state-1")
    traceability = (reference(DecisionReferenceKind.MISSION_RECOMMENDATION, "recommendation-1"), review,
                    reference(DecisionReferenceKind.SOLUTION_TEMPLATE, "template-1"),
                    reference(DecisionReferenceKind.ENGINEERING_INTENT, "intent-1"),
                    reference(DecisionReferenceKind.ENGINEERING_ACTION, "action-1"))
    return DecisionEvidence(
        "decision-1", DecisionType.ENGINEERING_ACTION_SELECTION, "2026-08-04T12:00:00Z", repository_truth,
        reference(DecisionReferenceKind.MISSION, "mission-1"), "Select the evidence-gated action.",
        "Repository maturity, review, mission state, and execution evidence favour the bounded action.", traceability,
        DecisionConfidence(82, repository_truth, review, execution, mission_state),
        (DecisionAlternative("alternative-a", "Run an unbounded action.", "Violates the bounded Mission constraint."),
         DecisionAlternative("alternative-b", "Defer the action.", "Evidence shows the required preconditions are present."),
         DecisionAlternative("alternative-c", "Select the evidence-gated action.", "Selected; it satisfies all declared constraints.")),
        "alternative-c", ("engineering", "platform_architecture"), ("One active action only.",),
        ("Human approval remains required.",), reference(DecisionReferenceKind.REPOSITORY_EVIDENCE, "maturity-1"),
        (execution,), ApprovalState.PENDING_HUMAN_APPROVAL, DecisionOutcome.SELECTED,
    )


class DecisionEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = DecisionEvidenceRepository(Path(self.temporary_directory.name) / "repository-truth" / "decision-evidence.sqlite", reference_resolver=lambda _: True)

    def tearDown(self) -> None:
        self.repository.close()
        self.temporary_directory.cleanup()

    def test_creation_records_required_decision_fields_and_alternatives(self) -> None:
        evidence = decision()
        self.assertEqual(evidence.decision_type, DecisionType.ENGINEERING_ACTION_SELECTION)
        self.assertEqual(evidence.chosen_alternative, "alternative-c")
        self.assertEqual(len(evidence.alternatives_considered), 3)
        self.assertEqual(evidence.to_dict()["approval_state"], "pending_human_approval")

    def test_confidence_requires_all_non_opaque_provenance(self) -> None:
        evidence = decision()
        self.assertEqual(evidence.confidence.level, "high")
        with self.assertRaises(ValueError):
            DecisionConfidence(50, evidence.repository_context, evidence.repository_context,
                               evidence.execution_evidence_references[0], reference(DecisionReferenceKind.MISSION_STATE, "state-2"))

    def test_traceability_covers_canonical_artefacts_without_duplication(self) -> None:
        evidence = decision()
        kinds = {item.kind for item in evidence.evidence_references}
        self.assertTrue({DecisionReferenceKind.MISSION_RECOMMENDATION, DecisionReferenceKind.ARCHITECTURE_REVIEW,
                         DecisionReferenceKind.SOLUTION_TEMPLATE, DecisionReferenceKind.ENGINEERING_INTENT,
                         DecisionReferenceKind.ENGINEERING_ACTION}.issubset(kinds))
        self.assertNotIn("reasoning", evidence.to_dict()["evidence_references"][0])

    def test_repository_rejects_unresolved_references(self) -> None:
        unresolved = DecisionEvidenceRepository(Path(self.temporary_directory.name) / "unresolved.sqlite", reference_resolver=lambda _: False)
        self.addCleanup(unresolved.close)
        with self.assertRaises(DecisionEvidenceRepositoryError):
            unresolved.append(decision())

    def test_repository_is_append_only_and_rejects_duplicate_ids(self) -> None:
        stored = self.repository.append(decision())
        self.assertEqual(self.repository.get(stored.id), stored)
        with self.assertRaises(DecisionEvidenceRepositoryError):
            self.repository.append(stored)
        with self.assertRaises(Exception):
            self.repository._connection.execute("DELETE FROM decision_evidence WHERE decision_id = ?", (stored.id,))

    def test_immutable_and_deterministic(self) -> None:
        first, second = decision(), decision()
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.content_digest, second.content_digest)
        with self.assertRaises(FrozenInstanceError):
            first.reasoning_summary = "changed"  # type: ignore[misc]

    def test_workspace_projections_preserve_ownership_boundaries(self) -> None:
        evidence = decision()
        business = render_business_decision_evidence(evidence)
        architecture = render_architecture_decision_evidence(evidence)
        execution = render_execution_decision_evidence_reference(evidence)
        self.assertEqual(business["chosen_alternative"], "alternative-c")
        self.assertIn("traceability", architecture)
        self.assertNotIn("reasoning_summary", execution)
        self.assertEqual(execution["decision_evidence_id"], evidence.id)

    def test_reasoning_references_mission_recommendation_and_architecture_review(self) -> None:
        evidence = decision()
        references = {item.kind for item in evidence.evidence_references}
        self.assertIn(DecisionReferenceKind.MISSION_RECOMMENDATION, references)
        self.assertIn(DecisionReferenceKind.ARCHITECTURE_REVIEW, references)


if __name__ == "__main__":
    unittest.main()
