"""Deterministic capability assessment and delegated-work records.

The registry describes available execution capabilities.  It never invokes a
provider: Forge retains the Mission and records only the bounded Engineering
Action it asks another provider to complete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping


CAPABILITY_REGISTRY_SCHEMA_VERSION = "1.0"
DELEGATION_SCHEMA_VERSION = "1.0"


class CapabilityAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class CapabilityOwner(str, Enum):
    FORGE = "internal_forge"
    HUMAN = "human"
    EXTERNAL_FORGE_RUNNER = "external_forge_runner"
    EXTERNAL_AI_AGENT = "external_ai_agent"
    EXTERNAL_APPLICATION = "external_application"
    PROFESSIONAL_SERVICE = "professional_service"


class CapabilityExecutionMode(str, Enum):
    INTERNAL = "internal"
    DELEGATED = "delegated"


class DelegationApprovalState(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DelegationResultState(str, Enum):
    PENDING = "pending"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ADDITIONAL_WORK_REQUIRED = "additional_work_required"


@dataclass(frozen=True)
class CapabilityRegistration:
    id: str
    name: str
    owner: CapabilityOwner
    availability: CapabilityAvailability
    execution_mode: CapabilityExecutionMode
    preferred_provider: CapabilityOwner
    trust_level: str
    approval_required: bool = False
    schema_version: str = CAPABILITY_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CAPABILITY_REGISTRY_SCHEMA_VERSION or not all((self.id, self.name, self.trust_level)):
            raise ValueError("capability registration requires supported version, identity, name, and trust level")
        if self.execution_mode is CapabilityExecutionMode.INTERNAL and self.owner is not CapabilityOwner.FORGE:
            raise ValueError("internal execution must be owned by Forge")

    def to_dict(self) -> dict[str, object]:
        document = asdict(self)
        for name in ("owner", "availability", "execution_mode", "preferred_provider"):
            document[name] = document[name].value  # type: ignore[union-attr]
        return document


@dataclass(frozen=True)
class CapabilityAssessment:
    capability_id: str
    available: bool
    execution_mode: CapabilityExecutionMode
    selected_provider: CapabilityOwner
    alternatives_considered: tuple[CapabilityOwner, ...]
    rationale: str
    confidence: int
    approval_required: bool

    def to_dict(self) -> dict[str, object]:
        return {"capability_id": self.capability_id, "available": self.available,
                "execution_mode": self.execution_mode.value, "selected_provider": self.selected_provider.value,
                "alternatives_considered": [item.value for item in self.alternatives_considered],
                "rationale": self.rationale, "confidence": self.confidence,
                "approval_required": self.approval_required}


class CapabilityRegistry:
    """Immutable, deterministically ordered capability configuration."""

    def __init__(self, registrations: tuple[CapabilityRegistration, ...]) -> None:
        identifiers = [item.id for item in registrations]
        if not registrations or len(identifiers) != len(set(identifiers)):
            raise ValueError("capability registry requires uniquely identified registrations")
        self._registrations = {item.id: item for item in registrations}

    def assess(self, capability_id: str) -> CapabilityAssessment:
        registration = self._registrations.get(capability_id)
        if registration is None:
            raise ValueError("required capability is not registered")
        available = registration.availability is CapabilityAvailability.AVAILABLE and registration.execution_mode is CapabilityExecutionMode.INTERNAL
        alternatives = tuple(sorted((owner for owner in CapabilityOwner if owner is not registration.preferred_provider), key=lambda item: item.value))
        return CapabilityAssessment(
            capability_id, available, registration.execution_mode,
            CapabilityOwner.FORGE if available else registration.preferred_provider,
            alternatives,
            "internal capability available" if available else "required capability is unavailable for internal execution",
            100 if available else 90, registration.approval_required,
        )


@dataclass(frozen=True)
class DelegationRequest:
    id: str
    mission_id: str
    action_id: str
    capability_id: str
    provider: CapabilityOwner
    reason: str
    decision_evidence: tuple[str, ...]
    requested_at: str
    approval_state: DelegationApprovalState
    alternatives_considered: tuple[CapabilityOwner, ...]
    confidence: int
    result_state: DelegationResultState = DelegationResultState.PENDING
    verification: Mapping[str, object] | None = None
    schema_version: str = DELEGATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DELEGATION_SCHEMA_VERSION or not all((self.id, self.mission_id, self.action_id, self.capability_id, self.reason, self.requested_at)):
            raise ValueError("delegation request requires complete identity, rationale, and timestamp")
        if not 0 <= self.confidence <= 100:
            raise ValueError("delegation confidence must be between 0 and 100")

    def to_dict(self) -> dict[str, object]:
        document = asdict(self)
        document["provider"] = self.provider.value
        document["approval_state"] = self.approval_state.value
        document["result_state"] = self.result_state.value
        document["alternatives_considered"] = [item.value for item in self.alternatives_considered]
        return document
