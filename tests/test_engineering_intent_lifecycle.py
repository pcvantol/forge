import unittest
from dataclasses import FrozenInstanceError, replace

from forge.models import (
    EngineeringIntent,
    IntentApproval,
    IntentCategory,
    IntentEvidence,
    IntentEvidenceKind,
    IntentReference,
    IntentRelationship,
    IntentRelationshipKind,
    IntentStatus,
    IntentTraceability,
    transition_intent,
    validate_intent_relationships,
)


def reference(identifier: str) -> IntentReference:
    return IntentReference(identifier, "1.0", f"local://{identifier}")


def evidence(kind: IntentEvidenceKind) -> IntentEvidence:
    return IntentEvidence(kind, f"{kind.value}-source", "1.0", f"local://{kind.value}", "sha256:" + "a" * 64)


def traceability() -> IntentTraceability:
    return IntentTraceability(
        (reference("vision"),),
        (reference("architecture"),),
        (reference("roadmap"),),
        (reference("proposal"),),
        (reference("repository"),),
    )


def intent(**overrides: object) -> EngineeringIntent:
    values: dict[str, object] = {
        "id": "intent-1",
        "revision": "1.0",
        "title": "Intent lifecycle",
        "objective": "Establish a governed lifecycle.",
        "category": IntentCategory.ARCHITECTURE_AUTHORING,
        "traceability": traceability(),
    }
    values.update(overrides)
    return EngineeringIntent(**values)  # type: ignore[arg-type]


class EngineeringIntentLifecycleTests(unittest.TestCase):
    def test_all_lifecycle_states_are_declared(self) -> None:
        self.assertEqual(
            {state.value for state in IntentStatus},
            {"DRAFT", "PROPOSED", "APPROVED", "IMPLEMENTED", "VERIFIED", "SUPERSEDED", "ARCHIVED"},
        )

    def test_categories_relationships_and_evidence_kinds_are_closed(self) -> None:
        self.assertEqual(
            {category.value for category in IntentCategory},
            {"Assessment", "Implementation", "Repair", "Migration", "Knowledge Capture", "Architecture Authoring", "Reconciliation"},
        )
        self.assertEqual(
            {kind.value for kind in IntentRelationshipKind},
            {"replaces", "depends_on", "supersedes", "implements", "derived_from"},
        )
        self.assertEqual(
            {kind.value for kind in IntentEvidenceKind},
            {"implementation", "validation", "repository", "architectural"},
        )

    def test_allowed_ordered_transitions_preserve_immutable_content(self) -> None:
        draft = intent(approval=IntentApproval("human", "2026-08-01T00:00:00Z", reference("approval")))
        proposed = transition_intent(draft, IntentStatus.PROPOSED)
        approved = transition_intent(proposed, IntentStatus.APPROVED)
        implemented = transition_intent(replace(approved, evidence=(evidence(IntentEvidenceKind.IMPLEMENTATION),)), IntentStatus.IMPLEMENTED)
        verified = transition_intent(replace(implemented, evidence=(evidence(IntentEvidenceKind.IMPLEMENTATION), evidence(IntentEvidenceKind.VALIDATION), evidence(IntentEvidenceKind.REPOSITORY))), IntentStatus.VERIFIED)
        archived = transition_intent(verified, IntentStatus.ARCHIVED)
        self.assertEqual(archived.status, IntentStatus.ARCHIVED)
        self.assertEqual(archived.traceability, draft.traceability)
        with self.assertRaises(FrozenInstanceError):
            archived.title = "changed"  # type: ignore[misc]

    def test_transition_rejects_skips_terminal_states_and_missing_approval(self) -> None:
        with self.assertRaisesRegex(ValueError, "not permitted"):
            transition_intent(intent(), IntentStatus.APPROVED)
        proposed = transition_intent(intent(), IntentStatus.PROPOSED)
        with self.assertRaisesRegex(ValueError, "approval"):
            transition_intent(proposed, IntentStatus.APPROVED)
        archived = intent(
            status=IntentStatus.ARCHIVED,
            approval=IntentApproval("human", "2026-08-01T00:00:00Z", reference("approval")),
            evidence=(evidence(IntentEvidenceKind.IMPLEMENTATION), evidence(IntentEvidenceKind.VALIDATION), evidence(IntentEvidenceKind.REPOSITORY)),
        )
        with self.assertRaisesRegex(ValueError, "not permitted"):
            transition_intent(archived, IntentStatus.PROPOSED)
        with self.assertRaisesRegex(ValueError, "replaces"):
            transition_intent(intent(), IntentStatus.SUPERSEDED)

    def test_verified_requires_implementation_validation_and_repository_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "implementation"):
            intent(status=IntentStatus.VERIFIED, approval=IntentApproval("human", "2026-08-01T00:00:00Z", reference("approval")))
        with self.assertRaisesRegex(ValueError, "validation"):
            intent(status=IntentStatus.VERIFIED, approval=IntentApproval("human", "2026-08-01T00:00:00Z", reference("approval")), evidence=(evidence(IntentEvidenceKind.IMPLEMENTATION),))
        with self.assertRaisesRegex(ValueError, "repository"):
            intent(status=IntentStatus.VERIFIED, approval=IntentApproval("human", "2026-08-01T00:00:00Z", reference("approval")), evidence=(evidence(IntentEvidenceKind.IMPLEMENTATION), evidence(IntentEvidenceKind.VALIDATION)))

    def test_relationships_reject_self_duplicate_and_missing_targets(self) -> None:
        with self.assertRaisesRegex(ValueError, "itself"):
            intent(relationships=(IntentRelationship(IntentRelationshipKind.DEPENDS_ON, "intent-1"),))
        relationship = IntentRelationship(IntentRelationshipKind.DEPENDS_ON, "other")
        with self.assertRaisesRegex(ValueError, "unique"):
            intent(relationships=(relationship, relationship))
        with self.assertRaisesRegex(ValueError, "present"):
            validate_intent_relationships((intent(relationships=(relationship,)),))

    def test_supersession_requires_explicit_reciprocal_relationships(self) -> None:
        predecessor = intent(
            id="intent-old",
            status=IntentStatus.SUPERSEDED,
            relationships=(IntentRelationship(IntentRelationshipKind.REPLACES, "intent-new"),),
        )
        successor = intent(
            id="intent-new",
            relationships=(IntentRelationship(IntentRelationshipKind.SUPERSEDES, "intent-old"),),
        )
        validate_intent_relationships((predecessor, successor))
        with self.assertRaisesRegex(ValueError, "reciprocal"):
            validate_intent_relationships((predecessor, replace(successor, relationships=())))

    def test_traceability_requires_the_complete_canonical_chain(self) -> None:
        with self.assertRaisesRegex(ValueError, "traceability"):
            IntentTraceability((), reference("architecture"), reference("roadmap"), reference("proposal"), reference("repository"))


if __name__ == "__main__":
    unittest.main()
