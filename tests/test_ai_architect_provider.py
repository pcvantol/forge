import unittest
from dataclasses import FrozenInstanceError

from forge.models import (
    AIArchitectConfidence,
    AIArchitectFindingCandidate,
    AIArchitectInput,
    AIArchitectInputKind,
    AIArchitectOpportunityCandidate,
    AIArchitectRequest,
    AIArchitectResult,
    EngineeringIntentDraftCandidate,
    EngineeringProposalDraftCandidate,
    IntentReference,
)


def reference(identifier: str) -> IntentReference:
    return IntentReference(identifier, "1.0", f"local://{identifier}")


def inputs(*, omit: AIArchitectInputKind | None = None, reverse: bool = False) -> tuple[AIArchitectInput, ...]:
    records = tuple(AIArchitectInput(kind, (reference(kind.value),)) for kind in AIArchitectInputKind if kind is not omit)
    return tuple(reversed(records)) if reverse else records


def request(**overrides: object) -> AIArchitectRequest:
    values: dict[str, object] = {"id": "reasoning-001", "objective": "Identify a provider contract.", "inputs": inputs()}
    values.update(overrides)
    return AIArchitectRequest(**values)  # type: ignore[arg-type]


def result(**overrides: object) -> AIArchitectResult:
    finding = AIArchitectFindingCandidate("finding-001", "A provider boundary is missing.", (reference("repository-evidence"),))
    opportunity = AIArchitectOpportunityCandidate("opportunity-001", "Define the boundary", "The gap is architectural.", (finding.id,))
    values: dict[str, object] = {
        "request_id": "reasoning-001", "provider_id": "candidate-provider", "findings": (finding,), "opportunities": (opportunity,),
        "proposal_draft": EngineeringProposalDraftCandidate("Provider contract", "Define it.", (opportunity.id,), (reference("handbook"),)),
        "intent_draft": EngineeringIntentDraftCandidate("Provider contract", "Define it.", ("No execution.",), (reference("tests"),)),
        "reasoning_evidence": (reference("repository-evidence"),), "confidence": AIArchitectConfidence.MEDIUM,
        "recommendations": ("Submit the candidate to human review.",),
    }
    values.update(overrides)
    return AIArchitectResult(**values)  # type: ignore[arg-type]


class AIArchitectProviderContractTests(unittest.TestCase):
    def test_request_requires_all_nine_read_only_source_classes(self) -> None:
        model = request(inputs=inputs(reverse=True))
        self.assertEqual({item.kind for item in model.inputs}, set(AIArchitectInputKind))
        self.assertEqual(model.to_dict(), request().to_dict())
        with self.assertRaises(FrozenInstanceError):
            model.objective = "changed"  # type: ignore[misc]
        for kind in AIArchitectInputKind:
            with self.subTest(source=kind.value):
                with self.assertRaisesRegex(ValueError, kind.value):
                    request(inputs=inputs(omit=kind))

    def test_result_is_evidence_linked_advisory_candidates_without_status(self) -> None:
        model = result()
        document = model.to_dict()
        self.assertEqual(document["confidence"], "medium")
        self.assertNotIn("status", document)
        self.assertNotIn("approval", document)
        self.assertEqual(document["proposal_draft"]["opportunity_ids"], ["opportunity-001"])
        with self.assertRaisesRegex(ValueError, "reference result findings"):
            result(opportunities=(AIArchitectOpportunityCandidate("other", "Other", "Other", ("unknown",)),))

    def test_result_rejects_empty_or_unlinked_advisory_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "findings"):
            result(findings=())
        with self.assertRaisesRegex(ValueError, "must reference result opportunities"):
            result(proposal_draft=EngineeringProposalDraftCandidate("Draft", "Draft", ("unknown",), (reference("evidence"),)))


if __name__ == "__main__":
    unittest.main()
