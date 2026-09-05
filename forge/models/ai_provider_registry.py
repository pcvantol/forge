"""Provider-neutral, non-executing contracts for AI Architect selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


AI_PROVIDER_REGISTRY_SCHEMA_VERSION = "1.7"


class ProviderCapability(str, Enum):
    """Capabilities a provider explicitly declares to the Forge registry."""

    ARCHITECTURE_REASONING = "architecture_reasoning"
    ENGINEERING_PROPOSAL_GENERATION = "engineering_proposal_generation"
    ENGINEERING_INTENT_DRAFTING = "engineering_intent_drafting"
    KNOWLEDGE_DISTILLATION = "knowledge_distillation"
    ARCHITECTURE_REVIEW = "architecture_review"
    ACTION_DERIVATION = "action_derivation"


class ProviderQualificationState(str, Enum):
    """Repository-owned qualification states; only QUALIFIED is selectable."""

    REGISTERED = "REGISTERED"
    QUALIFIED = "QUALIFIED"
    EXPERIMENTAL = "EXPERIMENTAL"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class ProviderStatus(str, Enum):
    """Operational availability declared independently from qualification."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


@dataclass(frozen=True, order=True)
class AIProviderMetadata:
    """Immutable registration metadata for one replaceable provider."""

    id: str
    version: str
    provider_type: str
    capabilities: tuple[ProviderCapability, ...]
    reasoning_modes: tuple[str, ...]
    qualification_state: ProviderQualificationState
    status: ProviderStatus
    schema_version: str = AI_PROVIDER_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AI_PROVIDER_REGISTRY_SCHEMA_VERSION:
            raise ValueError("AI Provider Registry schema version is unsupported")
        if not self.id or not self.version or not self.provider_type:
            raise ValueError("provider identity, version, and type are required")
        if not self.capabilities or not self.reasoning_modes:
            raise ValueError("provider capabilities and reasoning modes are required")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("provider capabilities must be unique")
        if len(self.reasoning_modes) != len(set(self.reasoning_modes)) or any(not mode for mode in self.reasoning_modes):
            raise ValueError("provider reasoning modes must be unique and non-empty")
        object.__setattr__(self, "capabilities", tuple(sorted(self.capabilities, key=lambda item: item.value)))
        object.__setattr__(self, "reasoning_modes", tuple(sorted(self.reasoning_modes)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "version": self.version,
            "provider_type": self.provider_type,
            "capabilities": [item.value for item in self.capabilities],
            "reasoning_modes": list(self.reasoning_modes),
            "qualification_state": self.qualification_state.value,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class ProviderQualification:
    """Repository-owned qualification record for registered provider metadata."""

    provider_id: str
    provider_version: str
    state: ProviderQualificationState
    repository_reference: str

    def __post_init__(self) -> None:
        if not self.provider_id or not self.provider_version or not self.repository_reference:
            raise ValueError("qualification provider identity, version, and repository reference are required")

    def to_dict(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "state": self.state.value,
            "repository_reference": self.repository_reference,
        }


@dataclass(frozen=True)
class WorkspaceProviderConfiguration:
    """Declarative workspace policy; it never invokes a provider."""

    workspace_id: str
    default_provider_id: str | None = None
    provider_preferences: tuple[str, ...] = ()
    fallback_provider_id: str | None = None

    def __post_init__(self) -> None:
        if not self.workspace_id:
            raise ValueError("workspace identity is required")
        if any(not provider_id for provider_id in self.provider_preferences):
            raise ValueError("provider preferences must be non-empty")
        if len(self.provider_preferences) != len(set(self.provider_preferences)):
            raise ValueError("provider preferences must be unique")


@dataclass(frozen=True)
class ProviderSelectionRequest:
    """A capability request for deterministic selection, never invocation."""

    workspace_id: str
    capability: ProviderCapability
    reasoning_mode: str

    def __post_init__(self) -> None:
        if not self.workspace_id or not self.reasoning_mode:
            raise ValueError("workspace identity and reasoning mode are required")


@dataclass(frozen=True)
class ProviderSelection:
    """The selected metadata and declarative reason; no provider call occurs."""

    request: ProviderSelectionRequest
    provider: AIProviderMetadata
    reason: str
