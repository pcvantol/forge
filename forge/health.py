"""Deterministic, read-only aggregation of liveness and capability observations.

This module deliberately accepts already collected observations.  It neither
probes components nor has access to Forge's generation, submission, lease, or
credential services.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Sequence


class AggregateHealthOutcome(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class CheckRequirement(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    DISABLED = "DISABLED"


class ObservationState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class EffectiveCheckState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class HealthObservation:
    """One externally collected, bounded observation.

    ``expires_at`` and ``timed_out`` are authoritative validity signals.  A
    stale, expired, missing, or timed-out observation is always effective
    ``UNKNOWN`` and is never promoted to a pass.
    """

    state: ObservationState
    observed_at: datetime
    max_age: timedelta
    expires_at: datetime | None = None
    timed_out: bool = False

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("health observation timestamp must include a timezone")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("health observation expiry must include a timezone")
        if self.max_age < timedelta(0):
            raise ValueError("health observation maximum age cannot be negative")

    def effective_state(self, *, evaluated_at: datetime) -> EffectiveCheckState:
        if evaluated_at.tzinfo is None:
            raise ValueError("health evaluation timestamp must include a timezone")
        if (self.timed_out or self.expires_at is not None and self.expires_at <= evaluated_at
                or evaluated_at - self.observed_at > self.max_age):
            return EffectiveCheckState.UNKNOWN
        return EffectiveCheckState(self.state.value)


@dataclass(frozen=True)
class HealthCheck:
    """A check belonging to one named capability readiness scope."""

    component_id: str
    check_id: str
    capability: str
    requirement: CheckRequirement
    observation: HealthObservation | None = None

    def __post_init__(self) -> None:
        if not all((self.component_id, self.check_id, self.capability)):
            raise ValueError("health checks require component, check, and capability identities")

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.component_id, self.check_id, self.capability


@dataclass(frozen=True)
class EvaluatedHealthCheck:
    component_id: str
    check_id: str
    capability: str
    requirement: CheckRequirement
    state: EffectiveCheckState


@dataclass(frozen=True)
class AggregateHealth:
    """A pure projection; ``liveness`` and capability readiness are separate."""

    outcome: AggregateHealthOutcome
    liveness: bool
    capability_readiness: Mapping[str, bool]
    checks: tuple[EvaluatedHealthCheck, ...]


class AggregateHealthEvaluator:
    """Evaluate supplied observations without probing or mutating any domain state."""

    def evaluate(self, *, liveness: bool, requested_capabilities: Sequence[str],
                 checks: Sequence[HealthCheck], evaluated_at: datetime) -> AggregateHealth:
        if evaluated_at.tzinfo is None:
            raise ValueError("health evaluation timestamp must include a timezone")
        capabilities = tuple(sorted(set(requested_capabilities)))
        if not capabilities or any(not capability for capability in capabilities):
            raise ValueError("at least one named capability is required")
        identities = [check.identity for check in checks]
        if len(identities) != len(set(identities)):
            raise ValueError("health checks must have unique component, check, and capability identities")

        evaluated = tuple(self._evaluate_check(check, evaluated_at)
                          for check in sorted(checks, key=lambda check: check.identity))
        readiness = {
            capability: liveness and self._capability_ready(capability, evaluated)
            for capability in capabilities
        }
        outcome = self._outcome(liveness, capabilities, evaluated)
        return AggregateHealth(outcome, liveness, MappingProxyType(readiness), evaluated)

    @staticmethod
    def _evaluate_check(check: HealthCheck, evaluated_at: datetime) -> EvaluatedHealthCheck:
        state = (EffectiveCheckState.DISABLED if check.requirement is CheckRequirement.DISABLED
                 else EffectiveCheckState.UNKNOWN if check.observation is None
                 else check.observation.effective_state(evaluated_at=evaluated_at))
        return EvaluatedHealthCheck(check.component_id, check.check_id, check.capability, check.requirement, state)

    @staticmethod
    def _capability_ready(capability: str, checks: Sequence[EvaluatedHealthCheck]) -> bool:
        applicable = [check for check in checks if check.capability == capability
                      and check.requirement is CheckRequirement.REQUIRED]
        return bool(applicable) and all(check.state is EffectiveCheckState.PASS for check in applicable)

    @staticmethod
    def _outcome(liveness: bool, capabilities: Sequence[str], checks: Sequence[EvaluatedHealthCheck]) -> AggregateHealthOutcome:
        if not liveness:
            return AggregateHealthOutcome.UNAVAILABLE
        required = [check for check in checks if check.requirement is CheckRequirement.REQUIRED]
        present_capabilities = {check.capability for check in required}
        if any(capability not in present_capabilities for capability in capabilities):
            return AggregateHealthOutcome.UNKNOWN
        if any(check.state is EffectiveCheckState.FAIL for check in required):
            return AggregateHealthOutcome.UNAVAILABLE
        if any(check.state is EffectiveCheckState.UNKNOWN for check in required):
            return AggregateHealthOutcome.UNKNOWN
        optional = [check for check in checks if check.requirement is CheckRequirement.OPTIONAL]
        if any(check.state is not EffectiveCheckState.PASS for check in optional):
            return AggregateHealthOutcome.DEGRADED
        return AggregateHealthOutcome.HEALTHY
