"""Local deterministic registry for AI Architect Provider declarations only."""

from __future__ import annotations

from forge.models import (
    AIProviderMetadata,
    ProviderQualification,
    ProviderQualificationState,
    ProviderSelection,
    ProviderSelectionRequest,
    ProviderStatus,
    WorkspaceProviderConfiguration,
)


class AIProviderRegistry:
    """Register and select declared providers without loading or invoking one."""

    def __init__(self) -> None:
        self._providers: dict[str, AIProviderMetadata] = {}
        self._qualifications: dict[str, ProviderQualification] = {}

    def register(self, provider: AIProviderMetadata, qualification: ProviderQualification) -> AIProviderMetadata:
        """Register one repository-qualified declaration, rejecting duplicate ids."""
        if provider.id in self._providers:
            raise ValueError("provider id is already registered")
        if qualification.provider_id != provider.id or qualification.provider_version != provider.version:
            raise ValueError("provider qualification must match provider identity and version")
        if qualification.state is not provider.qualification_state:
            raise ValueError("provider qualification must match provider qualification state")
        self._providers[provider.id] = provider
        self._qualifications[provider.id] = qualification
        return provider

    def list(self) -> tuple[AIProviderMetadata, ...]:
        """Return all declarations in stable provider-id and version order."""
        return tuple(sorted(self._providers.values(), key=lambda item: (item.id, item.version)))

    def qualification(self, provider_id: str) -> ProviderQualification | None:
        """Return the repository-owned qualification record, if registered."""
        return self._qualifications.get(provider_id)

    def select(
        self,
        request: ProviderSelectionRequest,
        configuration: WorkspaceProviderConfiguration,
    ) -> ProviderSelection:
        """Select an active qualified declaration by policy, never invoke it."""
        if configuration.workspace_id != request.workspace_id:
            raise ValueError("workspace provider configuration must match selection request")
        qualified = tuple(
            provider
            for provider in self.list()
            if provider.qualification_state is ProviderQualificationState.QUALIFIED
            and provider.status is ProviderStatus.ACTIVE
            and request.capability in provider.capabilities
            and request.reasoning_mode in provider.reasoning_modes
        )
        if not qualified:
            raise LookupError("no qualified provider supports the requested capability and reasoning mode")
        by_id = {provider.id: provider for provider in qualified}
        configured = self._ordered_configured_ids(configuration)
        for provider_id, reason in configured:
            provider = by_id.get(provider_id)
            if provider is not None:
                return ProviderSelection(request, provider, reason)
        return ProviderSelection(request, qualified[0], "stable_provider_id_version_tiebreaker")

    @staticmethod
    def _ordered_configured_ids(configuration: WorkspaceProviderConfiguration) -> tuple[tuple[str, str], ...]:
        candidates = [(provider_id, "workspace_provider_preference") for provider_id in configuration.provider_preferences]
        if configuration.default_provider_id:
            candidates.append((configuration.default_provider_id, "workspace_default_provider"))
        if configuration.fallback_provider_id:
            candidates.append((configuration.fallback_provider_id, "workspace_fallback_provider"))
        seen: set[str] = set()
        ordered: list[tuple[str, str]] = []
        for provider_id, reason in candidates:
            if provider_id not in seen:
                seen.add(provider_id)
                ordered.append((provider_id, reason))
        return tuple(ordered)
