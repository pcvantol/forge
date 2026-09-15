"""Deterministic, read-only Forge aggregate-health evaluation.

The evaluator deliberately accepts observations as immutable values.  It never
opens storage, invokes a provider, resolves credentials, creates a lease, or
submits work; adapters remain responsible for collecting bounded observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class AggregateHealthState(str, Enum):
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
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class OptionalUnknownImpact(str, Enum):
    """Declared aggregate impact of an unknown configured optional check."""

    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HealthObservation:
    state: ObservationState
    observed_at: datetime
    expires_at: datetime | None = None
    safe_reason: str | None = None

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("health observations require a timezone-aware timestamp")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("health observation expiry requires a timezone-aware timestamp")


@dataclass(frozen=True)
class HealthCheck:
    check_id: str
    capability: str | None
    requirement: CheckRequirement
    maximum_age: timedelta
    observation: HealthObservation | None
    optional_unknown_impact: OptionalUnknownImpact = OptionalUnknownImpact.UNKNOWN

    def __post_init__(self) -> None:
        if not self.check_id:
            raise ValueError("health checks require a stable check ID")
        if self.capability == "":
            raise ValueError("health check capability must be absent or non-empty")
        if self.maximum_age <= timedelta():
            raise ValueError("health checks require a positive maximum age")


@dataclass(frozen=True)
class LivenessReport:
    state: AggregateHealthState
    live: bool


@dataclass(frozen=True)
class CapabilityReadinessReport:
    capability: str
    state: AggregateHealthState
    ready: bool
    check_ids: tuple[str, ...]


@dataclass(frozen=True)
class AggregateHealthReport:
    state: AggregateHealthState
    check_ids: tuple[str, ...]


class AggregateHealthEvaluator:
    """Evaluate supplied observations without collecting or changing them."""

    def evaluate_liveness(self, observation: HealthObservation | None, *, now: datetime) -> LivenessReport:
        state = self._observation_state(observation, timedelta.max, now)
        return LivenessReport(state=state, live=state is AggregateHealthState.HEALTHY)

    def evaluate_capability(self, capability: str, checks: tuple[HealthCheck, ...], *, now: datetime) -> CapabilityReadinessReport:
        if not capability:
            raise ValueError("capability readiness requires a capability")
        applicable = tuple(check for check in checks if check.capability in (None, capability))
        state = self._evaluate(applicable, now, empty_is_unknown=True)
        required = tuple(check for check in applicable if check.requirement is CheckRequirement.REQUIRED)
        ready = bool(required) and all(
            self._observation_state(check.observation, check.maximum_age, now) is AggregateHealthState.HEALTHY
            for check in required
        )
        return CapabilityReadinessReport(capability, state, ready, tuple(check.check_id for check in applicable))

    def evaluate_aggregate(self, checks: tuple[HealthCheck, ...], *, now: datetime) -> AggregateHealthReport:
        return AggregateHealthReport(self._evaluate(checks, now, empty_is_unknown=True), tuple(check.check_id for check in checks))

    def _evaluate(self, checks: tuple[HealthCheck, ...], now: datetime, *, empty_is_unknown: bool) -> AggregateHealthState:
        if now.tzinfo is None:
            raise ValueError("health evaluation requires a timezone-aware current time")
        applicable = tuple(check for check in checks if check.requirement is not CheckRequirement.DISABLED)
        if not applicable:
            return AggregateHealthState.UNKNOWN if empty_is_unknown else AggregateHealthState.HEALTHY
        states = tuple((check, self._observation_state(check.observation, check.maximum_age, now)) for check in applicable)
        if any(check.requirement is CheckRequirement.REQUIRED and state is AggregateHealthState.UNAVAILABLE
               for check, state in states):
            return AggregateHealthState.UNAVAILABLE
        if any(check.requirement is CheckRequirement.REQUIRED and state is AggregateHealthState.UNKNOWN
               for check, state in states):
            return AggregateHealthState.UNKNOWN
        if any(check.requirement is CheckRequirement.OPTIONAL and state is AggregateHealthState.UNAVAILABLE
               for check, state in states):
            return AggregateHealthState.DEGRADED
        if any(check.requirement is CheckRequirement.OPTIONAL and state is AggregateHealthState.UNKNOWN
               and check.optional_unknown_impact is OptionalUnknownImpact.UNKNOWN for check, state in states):
            return AggregateHealthState.UNKNOWN
        if any(check.requirement is CheckRequirement.OPTIONAL and state is AggregateHealthState.UNKNOWN
               for check, state in states):
            return AggregateHealthState.DEGRADED
        return AggregateHealthState.HEALTHY

    @staticmethod
    def _observation_state(observation: HealthObservation | None, maximum_age: timedelta, now: datetime) -> AggregateHealthState:
        if observation is None or observation.state in {ObservationState.UNKNOWN, ObservationState.TIMEOUT}:
            return AggregateHealthState.UNKNOWN
        if observation.expires_at is not None and observation.expires_at < now:
            return AggregateHealthState.UNKNOWN
        if now - observation.observed_at > maximum_age:
            return AggregateHealthState.UNKNOWN
        if observation.state is ObservationState.FAIL:
            return AggregateHealthState.UNAVAILABLE
        return AggregateHealthState.HEALTHY
