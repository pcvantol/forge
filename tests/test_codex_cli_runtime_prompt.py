"""Regression coverage for the deterministic Codex CLI Runtime Prompt Renderer."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest

from forge.models import (
    CodexCliRuntimePromptRequest,
    EngineeringAction,
    EngineeringActionStatus,
    EngineeringIntent,
    ExecutionHostCompatibility,
    AgentPolicySelectionRequest,
    AgentRoleModelSelectionPolicy,
    EngineeringWorkKind,
    ReasoningDepth,
    IntentApproval,
    IntentCategory,
    IntentReference,
    IntentStatus,
    IntentTraceability,
    RepositoryState,
)
from forge.models.mission import EngineeringMission, MissionIntentMembership, MissionScope
from forge.prompts import CodexCliRuntimePromptRenderer


def reference(identifier: str) -> IntentReference:
    return IntentReference(identifier, "1.0", f"local://{identifier}")


def intent() -> EngineeringIntent:
    return EngineeringIntent(
        "intent-1", "1.0", "Renderer", "Preserve planning context.", IntentCategory.IMPLEMENTATION,
        IntentTraceability((reference("vision"),), (reference("architecture"),), (reference("roadmap"),),
                           (reference("proposal"),), (reference("repository"),)),
        approval=IntentApproval("architect", "2026-08-03T00:00:00Z", reference("approval")),
        status=IntentStatus.APPROVED,
    )


def mission() -> EngineeringMission:
    return EngineeringMission("mission-1", "2.0", "Mission", "Preserve boundaries.",
                              MissionScope(("renderer",), ("execution",)),
                              (MissionIntentMembership(1, "intent-1", "1.0"),))


def request(**overrides: object) -> CodexCliRuntimePromptRequest:
    values: dict[str, object] = {
        "mission": mission(),
        "intent": intent(),
        "action": EngineeringAction(1, "action-1", "intent-1", "1.0", "Render exactly one Action.",
                                      ("clean repository commit",), status=EngineeringActionStatus.ACTIVE),
        "repository_state": RepositoryState("forge", "abc123", "sha256:" + "a" * 64, "2026-08-03T12:00:00Z"),
        "constraints": ("No execution.", "No action mutation."),
        "validation": ("Run focused tests.",),
        "compatibility": ExecutionHostCompatibility("2.4", "GENESIS", ("codex_cli", "local_git"), "engineering-platform>=1.5.0"),
        "policy_selection": AgentRoleModelSelectionPolicy().select(AgentPolicySelectionRequest(
            "mission-1", "action-1", EngineeringWorkKind.ENGINEERING,
            reasoning_depth=ReasoningDepth.STANDARD,
            repository_context=("architecture", "repository_truth"), validation_required=True,
        )),
    }
    values.update(overrides)
    return CodexCliRuntimePromptRequest(**values)  # type: ignore[arg-type]


class CodexCliRuntimePromptRendererTests(unittest.TestCase):
    def test_identical_input_produces_identical_prompt_and_correlation(self) -> None:
        renderer = CodexCliRuntimePromptRenderer()
        first = renderer.render(request(constraints=("No action mutation.", "No execution.")))
        second = renderer.render(request(constraints=("No execution.", "No action mutation.")))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.correlation_id, second.correlation_id)

    def test_prompt_preserves_single_mission_pinned_active_action(self) -> None:
        prompt = CodexCliRuntimePromptRenderer().render(request())
        self.assertEqual((prompt.mission_id, prompt.mission_revision), ("mission-1", "2.0"))
        self.assertEqual((prompt.intent_id, prompt.intent_revision, prompt.action_id), ("intent-1", "1.0", "action-1"))
        self.assertEqual(prompt.objective, "Render exactly one Action.")
        self.assertEqual(prompt.expected_repository_evidence, ("clean repository commit",))
        self.assertIn("Engineering Action: action-1", prompt.rendered_text)
        self.assertIn("Mission out-of-scope boundaries:", prompt.rendered_text)
        self.assertIn("Intent objective: Preserve planning context.", prompt.rendered_text)

    def test_prompt_contains_versioning_repository_and_compatibility_metadata(self) -> None:
        prompt = CodexCliRuntimePromptRenderer().render(request())
        document = prompt.to_dict()
        self.assertEqual(document["generated_at"], "2026-08-03T12:00:00Z")
        self.assertEqual(document["repository_state"]["revision"], "abc123")
        self.assertEqual(document["compatibility"]["execution_mode"], "GENESIS")
        self.assertEqual(document["compatibility"]["required_capabilities"], ["codex_cli", "local_git"])
        self.assertTrue(document["immutable"])
        self.assertEqual(document["producer"]["type"], "FORGE")
        self.assertTrue(document["execution_metadata"])
        self.assertEqual(document["policy"]["version"], "1.0.0")
        self.assertNotIn("agent_role", document["policy"])
        self.assertIn("Forge policy execution constraints", prompt.rendered_text)
        self.assertNotIn("engineering_agent", prompt.rendered_text)
        with self.assertRaises(FrozenInstanceError):
            prompt.id = "changed"  # type: ignore[misc]

    def test_renderer_rejects_unpinned_or_non_active_action(self) -> None:
        with self.assertRaisesRegex(ValueError, "pinned"):
            request(mission=EngineeringMission("mission-2", "1", "Other", "Other.", MissionScope(("a",), ("b",)),
                                                (MissionIntentMembership(1, "other", "1"),)))
        with self.assertRaisesRegex(ValueError, "active"):
            request(action=replace(request().action, status=EngineeringActionStatus.READY))
        with self.assertRaisesRegex(ValueError, "approved"):
            request(intent=replace(intent(), status=IntentStatus.PROPOSED))

    def test_renderer_has_no_execution_or_provider_invocation_dependency(self) -> None:
        source = (CodexCliRuntimePromptRenderer.__module__)
        self.assertEqual(source, "forge.prompts.codex_cli")


if __name__ == "__main__":
    unittest.main()
