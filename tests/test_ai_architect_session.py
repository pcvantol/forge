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
    AIArchitectSession,
    AIArchitectSessionStatus,
    EngineeringIntentDraftCandidate,
    EngineeringProposalDraftCandidate,
    IntentReference,
    RepositorySnapshot,
    transition_ai_architect_session,
)


def reference(identifier: str) -> IntentReference:
    return IntentReference(identifier, "1.0", f"local://{identifier}")


def request(*, reverse: bool = False) -> AIArchitectRequest:
    inputs = tuple(AIArchitectInput(kind, (reference(kind.value),)) for kind in AIArchitectInputKind)
    return AIArchitectRequest("request-001", "Define the session boundary.", tuple(reversed(inputs)) if reverse else inputs)


def result(*, provider_id: str = "provider-001") -> AIArchitectResult:
    finding = AIArchitectFindingCandidate("finding-001", "A session boundary is needed.", (reference("evidence"),))
    opportunity = AIArchitectOpportunityCandidate("opportunity-001", "Add sessions", "Sessions bound reasoning.", (finding.id,))
    return AIArchitectResult(
        "request-001", provider_id, (finding,), (opportunity,),
        EngineeringProposalDraftCandidate("Session", "Define sessions.", (opportunity.id,), (reference("handbook"),)),
        EngineeringIntentDraftCandidate("Session", "Define sessions.", ("No execution.",), (reference("validation"),)),
        (reference("evidence"),), AIArchitectConfidence.HIGH, ("Submit to human review.",),
    )


def session(**overrides: object) -> AIArchitectSession:
    values: dict[str, object] = {
        "id": "session-001", "workspace_id": "workspace-001", "provider_id": "provider-001", "provider_version": "1.0",
        "objective": "Define the session boundary.", "request": request(),
        "repository_snapshot": RepositorySnapshot("forge", "abc123", (reference("repository-evidence"),)),
        "constitutional_context": (reference("constitution"),), "architecture_context": (reference("handbook"),),
    }
    values.update(overrides)
    return AIArchitectSession(**values)  # type: ignore[arg-type]


class AIArchitectSessionTests(unittest.TestCase):
    def test_session_creation_is_immutable_and_composes_complete_context(self) -> None:
        model = session()
        self.assertEqual(model.status, AIArchitectSessionStatus.CREATED)
        self.assertEqual({item.kind for item in model.request.inputs}, set(AIArchitectInputKind))
        self.assertIsNone(model.output)
        with self.assertRaises(FrozenInstanceError):
            model.objective = "changed"  # type: ignore[misc]

    def test_lifecycle_is_ordered_and_review_records_advisory_output_only(self) -> None:
        model = transition_ai_architect_session(session(), AIArchitectSessionStatus.PREPARED)
        model = transition_ai_architect_session(model, AIArchitectSessionStatus.REASONING)
        with self.assertRaisesRegex(ValueError, "review requires"):
            transition_ai_architect_session(model, AIArchitectSessionStatus.REVIEW)
        reviewed = transition_ai_architect_session(model, AIArchitectSessionStatus.REVIEW, output=result())
        complete = transition_ai_architect_session(reviewed, AIArchitectSessionStatus.COMPLETE)
        self.assertEqual(complete.status, AIArchitectSessionStatus.COMPLETE)
        self.assertNotIn("approval", complete.to_dict())
        with self.assertRaisesRegex(ValueError, "invalid"):
            transition_ai_architect_session(complete, AIArchitectSessionStatus.ABANDONED)

    def test_required_context_and_output_traceability_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "constitutional context"):
            session(constitutional_context=())
        with self.assertRaisesRegex(ValueError, "architecture context"):
            session(architecture_context=())
        with self.assertRaisesRegex(ValueError, "must match its complete"):
            session(objective="Different")
        reasoning = transition_ai_architect_session(
            transition_ai_architect_session(session(), AIArchitectSessionStatus.PREPARED), AIArchitectSessionStatus.REASONING
        )
        with self.assertRaisesRegex(ValueError, "selected provider"):
            transition_ai_architect_session(reasoning, AIArchitectSessionStatus.REVIEW, output=result(provider_id="other"))

    def test_structure_is_deterministic(self) -> None:
        reversed_session = session(
            request=request(reverse=True),
            constitutional_context=(reference("zulu"), reference("alpha")),
            architecture_context=(reference("zulu-architecture"), reference("alpha-architecture")),
        )
        ordered_session = session(
            constitutional_context=(reference("alpha"), reference("zulu")),
            architecture_context=(reference("alpha-architecture"), reference("zulu-architecture")),
        )
        self.assertEqual(reversed_session.to_dict(), ordered_session.to_dict())


if __name__ == "__main__":
    unittest.main()
