import unittest
from dataclasses import FrozenInstanceError

from forge.models import (
    AuthoringSource,
    AuthoringSourceKind,
    EngineeringIntentAuthoringContext,
    IntentReference,
)


def reference(identifier: str) -> IntentReference:
    return IntentReference(identifier, "1.0", f"local://{identifier}")


def sources(*, omit: AuthoringSourceKind | None = None, reverse: bool = False) -> tuple[AuthoringSource, ...]:
    records = tuple(
        AuthoringSource(kind, (reference(kind.value),))
        for kind in AuthoringSourceKind
        if kind is not omit
    )
    return tuple(reversed(records)) if reverse else records


def context(**overrides: object) -> EngineeringIntentAuthoringContext:
    values: dict[str, object] = {
        "objective": "Establish a provider-independent contract.",
        "rationale": "Future Intents require repository-grounded provenance.",
        "sources": sources(),
        "affected_capabilities": (reference("engineering-intent-authoring"),),
        "architecture_references": (reference("architecture-handbook"),),
        "constitutional_articles": (reference("article-3"),),
        "expected_evidence": (reference("authoring-report"),),
        "validation": (reference("unit-tests"),),
    }
    values.update(overrides)
    return EngineeringIntentAuthoringContext(**values)  # type: ignore[arg-type]


class EngineeringIntentAuthoringTests(unittest.TestCase):
    def test_valid_authoring_context_captures_every_required_source(self) -> None:
        model = context()
        self.assertEqual(
            {source.kind for source in model.sources},
            set(AuthoringSourceKind),
        )
        self.assertEqual(model.to_dict()["objective"], "Establish a provider-independent contract.")
        with self.assertRaises(FrozenInstanceError):
            model.objective = "changed"  # type: ignore[misc]

    def test_each_required_repository_source_class_is_mandatory(self) -> None:
        for kind in AuthoringSourceKind:
            with self.subTest(source=kind.value):
                with self.assertRaisesRegex(ValueError, kind.value):
                    context(sources=sources(omit=kind))

    def test_required_intent_fields_and_architectural_references_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "objective"):
            context(objective="")
        with self.assertRaisesRegex(ValueError, "affected capability"):
            context(affected_capabilities=())
        with self.assertRaisesRegex(ValueError, "architecture"):
            context(architecture_references=())
        with self.assertRaisesRegex(ValueError, "expected evidence"):
            context(expected_evidence=())
        with self.assertRaisesRegex(ValueError, "validation"):
            context(validation=())

    def test_authoring_model_serialization_is_deterministic(self) -> None:
        first = context(sources=sources(reverse=True), affected_capabilities=(reference("z"), reference("a")))
        second = context(sources=sources(), affected_capabilities=(reference("a"), reference("z")))
        self.assertEqual(first.to_dict(), second.to_dict())


if __name__ == "__main__":
    unittest.main()
