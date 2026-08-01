import unittest
from dataclasses import FrozenInstanceError, replace

from forge.models import (
    EngineeringIntent,
    EngineeringAction,
    EngineeringActionStatus,
    IntentApproval,
    IntentCategory,
    IntentReference,
    IntentStatus,
    IntentTraceability,
    ProviderPromptDefinition,
    RuntimePromptGenerationContext,
    RuntimePromptGenerationRequest,
    RuntimePromptSectionKind,
)
from forge.prompts import RuntimePromptGenerator


def reference(identifier: str) -> IntentReference:
    return IntentReference(identifier, "1.0", f"local://{identifier}")


def approved_intent() -> EngineeringIntent:
    return EngineeringIntent(
        id="runtime-prompt-intent",
        revision="1.0",
        title="Runtime Prompt Generation",
        objective="Derive a provider-specific Runtime Prompt without execution.",
        category=IntentCategory.ARCHITECTURE_AUTHORING,
        traceability=IntentTraceability(
            (reference("vision"),),
            (reference("architecture"),),
            (reference("roadmap"),),
            (reference("proposal"),),
            (reference("repository"),),
        ),
        approval=IntentApproval("human", "2026-08-01T00:00:00Z", reference("approval")),
        status=IntentStatus.APPROVED,
    )


def request(**overrides: object) -> RuntimePromptGenerationRequest:
    values: dict[str, object] = {
        "intent": approved_intent(),
        "action": EngineeringAction(
            1, "runtime-prompt-action", "runtime-prompt-intent", "1.0",
            "Derive a Runtime Prompt.", ("Prompt provenance",),
            status=EngineeringActionStatus.ACTIVE,
        ),
        "provider_definition": ProviderPromptDefinition("provider-definition", "1.0"),
        "context": RuntimePromptGenerationContext(
            repository=(reference("forge-repository"),),
            architecture_handbook=(reference("founding-handbook"),),
            constitution=(reference("constitution"),),
            workspace=(reference("forge-workspace"),),
            capabilities=(reference("runtime-prompt-generation"),),
        ),
        "constraints": ("Do not execute the Runtime Prompt.",),
        "validation": ("Run focused Runtime Prompt tests.",),
        "deliverables": ("Runtime Prompt Generation documentation.",),
    }
    values.update(overrides)
    return RuntimePromptGenerationRequest(**values)  # type: ignore[arg-type]


class RuntimePromptGenerationTests(unittest.TestCase):
    def test_approved_engineering_intent_produces_a_transient_runtime_prompt(self) -> None:
        prompt = RuntimePromptGenerator().generate(prompt_id="runtime-prompt-1", request=request())
        self.assertEqual(prompt.source_intent_id, "runtime-prompt-intent")
        self.assertEqual(prompt.source_action_id, "runtime-prompt-action")
        self.assertTrue(prompt.to_dict()["derived"])
        self.assertTrue(prompt.to_dict()["transient"])
        self.assertEqual(prompt.provider_definition.id, "provider-definition")
        with self.assertRaises(FrozenInstanceError):
            prompt.id = "changed"  # type: ignore[misc]

    def test_prompt_contains_each_canonical_abstract_section(self) -> None:
        prompt = RuntimePromptGenerator().generate(prompt_id="runtime-prompt-1", request=request())
        self.assertEqual(
            {section.kind for section in prompt.sections},
            set(RuntimePromptSectionKind),
        )
        self.assertIn("## Validation", prompt.to_markdown())
        self.assertIn("## Deliverables", prompt.to_markdown())

    def test_generation_and_provenance_are_deterministic(self) -> None:
        first = request(
            constraints=("z constraint", "a constraint"),
            context=RuntimePromptGenerationContext(
                repository=(reference("z-repository"), reference("a-repository")),
                architecture_handbook=(reference("founding-handbook"),),
                constitution=(reference("constitution"),),
                workspace=(reference("forge-workspace"),),
                capabilities=(reference("runtime-prompt-generation"),),
            ),
        )
        second = request(
            constraints=("a constraint", "z constraint"),
            context=RuntimePromptGenerationContext(
                repository=(reference("a-repository"), reference("z-repository")),
                architecture_handbook=(reference("founding-handbook"),),
                constitution=(reference("constitution"),),
                workspace=(reference("forge-workspace"),),
                capabilities=(reference("runtime-prompt-generation"),),
            ),
        )
        generator = RuntimePromptGenerator()
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            generator.generate(prompt_id="runtime-prompt-1", request=first).to_dict(),
            generator.generate(prompt_id="runtime-prompt-1", request=second).to_dict(),
        )

    def test_generation_requires_an_approved_intent_and_complete_sections(self) -> None:
        with self.assertRaisesRegex(ValueError, "approved"):
            request(intent=replace(approved_intent(), status=IntentStatus.PROPOSED))
        with self.assertRaisesRegex(ValueError, "active"):
            request(action=replace(request().action, status=EngineeringActionStatus.READY))
        with self.assertRaisesRegex(ValueError, "deliverable"):
            request(deliverables=())
        with self.assertRaisesRegex(ValueError, "constitution"):
            request(
                context=RuntimePromptGenerationContext(
                    repository=(reference("forge-repository"),),
                    architecture_handbook=(reference("founding-handbook"),),
                    constitution=(),
                    workspace=(reference("forge-workspace"),),
                    capabilities=(reference("runtime-prompt-generation"),),
                )
            )


if __name__ == "__main__":
    unittest.main()
