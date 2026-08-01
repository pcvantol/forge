import unittest
from dataclasses import FrozenInstanceError

from forge.ai_architect import AIProviderRegistry
from forge.models import (
    AIProviderMetadata,
    ProviderCapability,
    ProviderQualification,
    ProviderQualificationState,
    ProviderSelectionRequest,
    ProviderStatus,
    WorkspaceProviderConfiguration,
)


def provider(
    identifier: str,
    *,
    version: str = "1.0",
    capabilities: tuple[ProviderCapability, ...] = (ProviderCapability.ARCHITECTURE_REASONING,),
    modes: tuple[str, ...] = ("structured",),
    qualification: ProviderQualificationState = ProviderQualificationState.QUALIFIED,
    status: ProviderStatus = ProviderStatus.ACTIVE,
) -> AIProviderMetadata:
    return AIProviderMetadata(identifier, version, "future_adapter", capabilities, modes, qualification, status)


def qualification(metadata: AIProviderMetadata) -> ProviderQualification:
    return ProviderQualification(metadata.id, metadata.version, metadata.qualification_state, "docs/evidence/provider-001.md")


class AIProviderRegistryTests(unittest.TestCase):
    def test_registration_is_immutable_and_stably_ordered(self) -> None:
        registry = AIProviderRegistry()
        zulu = provider("zulu")
        alpha = provider("alpha")
        registry.register(zulu, qualification(zulu))
        registry.register(alpha, qualification(alpha))
        self.assertEqual([item.id for item in registry.list()], ["alpha", "zulu"])
        self.assertEqual(registry.qualification("alpha"), qualification(alpha))
        with self.assertRaises(FrozenInstanceError):
            alpha.version = "other"  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(alpha, qualification(alpha))

    def test_capabilities_and_reasoning_modes_are_declared_and_normalized(self) -> None:
        metadata = provider(
            "architect",
            capabilities=(ProviderCapability.ARCHITECTURE_REVIEW, ProviderCapability.ARCHITECTURE_REASONING),
            modes=("review", "structured"),
        )
        self.assertEqual(metadata.to_dict()["capabilities"], ["architecture_reasoning", "architecture_review"])
        self.assertEqual(metadata.to_dict()["reasoning_modes"], ["review", "structured"])
        with self.assertRaisesRegex(ValueError, "capabilities"):
            provider("empty", capabilities=())

    def test_qualification_is_repository_owned_and_must_match_registration(self) -> None:
        registry = AIProviderRegistry()
        metadata = provider("candidate", qualification=ProviderQualificationState.EXPERIMENTAL)
        mismatched = ProviderQualification("candidate", "1.0", ProviderQualificationState.QUALIFIED, "docs/evidence/provider.md")
        with self.assertRaisesRegex(ValueError, "qualification state"):
            registry.register(metadata, mismatched)

    def test_selection_is_deterministic_and_never_selects_ineligible_provider(self) -> None:
        registry = AIProviderRegistry()
        for metadata in (
            provider("zulu"),
            provider("alpha"),
            provider("preferred"),
            provider("experimental", qualification=ProviderQualificationState.EXPERIMENTAL),
            provider("inactive", status=ProviderStatus.INACTIVE),
        ):
            registry.register(metadata, qualification(metadata))
        request = ProviderSelectionRequest("workspace-001", ProviderCapability.ARCHITECTURE_REASONING, "structured")
        selected = registry.select(request, WorkspaceProviderConfiguration("workspace-001", provider_preferences=("experimental", "preferred"), default_provider_id="zulu"))
        self.assertEqual((selected.provider.id, selected.reason), ("preferred", "workspace_provider_preference"))
        fallback = registry.select(request, WorkspaceProviderConfiguration("workspace-001"))
        self.assertEqual((fallback.provider.id, fallback.reason), ("alpha", "stable_provider_id_version_tiebreaker"))
        with self.assertRaisesRegex(LookupError, "no qualified provider"):
            registry.select(
                ProviderSelectionRequest("workspace-001", ProviderCapability.KNOWLEDGE_DISTILLATION, "structured"),
                WorkspaceProviderConfiguration("workspace-001"),
            )


if __name__ == "__main__":
    unittest.main()
