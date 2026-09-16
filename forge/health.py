"""Deterministic, read-only Forge health and readiness evaluation.

The evaluator consumes already-collected observations.  It has no clock,
storage, provider, credential, lease, Mission, or execution-host dependency,
so evaluating health cannot generate work or mutate a domain service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable


class AggregateHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class LivenessState(str, Enum):
    LIVE = "LIVE"
    NOT_LIVE = "NOT_LIVE"
    UNKNOWN = "UNKNOWN"


class CheckApplicability(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    DISABLED = "DISABLED"


class ObservationState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class ObservationFreshness(str, Enum):
    FRESH = "FRESH"
    MISSING = "MISSING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    TIMED_OUT = "TIMED_OUT"
    INVALID = "INVALID"
    DISABLED = "DISABLED"


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class HealthCheck:
    """One declared check and the named capabilities that depend on it."""

    check_id: str
    component_id: str
    capability_ids: tuple[str, ...]
    applicability: CheckApplicability
    max_age: timedelta

    def __post_init__(self) -> None:
        if not self.check_id or not self.component_id or not self.capability_ids:
            raise ValueError("health checks require check, component, and capability identity")
        if len(self.capability_ids) != len(set(self.capability_ids)) or any(not item for item in self.capability_ids):
            raise ValueError("health check capability identities must be non-empty and unique")
        if not isinstance(self.applicability, CheckApplicability):
            raise TypeError("health check applicability must be typed")
        if self.max_age < timedelta(0):
            raise ValueError("health check max_age cannot be negative")


@dataclass(frozen=True)
class HealthObservation:
    check_id: str
    state: ObservationState
    observed_at: datetime
    expires_at: datetime | None = None
    timed_out: bool = False

    def __post_init__(self) -> None:
        if not self.check_id:
            raise ValueError("health observation requires check identity")
        if not isinstance(self.state, ObservationState):
            raise TypeError("health observation state must be typed")
        _require_aware(self.observed_at, "observed_at")
        if self.expires_at is not None:
            _require_aware(self.expires_at, "expires_at")
            if self.expires_at < self.observed_at:
                raise ValueError("health observation cannot expire before it was observed")


@dataclass(frozen=True)
class LivenessObservation:
    alive: bool | None
    observed_at: datetime
    max_age: timedelta
    expires_at: datetime | None = None
    timed_out: bool = False

    def __post_init__(self) -> None:
        if self.alive is not None and not isinstance(self.alive, bool):
            raise TypeError("liveness must be true, false, or unknown")
        _require_aware(self.observed_at, "observed_at")
        if self.max_age < timedelta(0):
            raise ValueError("liveness max_age cannot be negative")
        if self.expires_at is not None:
            _require_aware(self.expires_at, "expires_at")
            if self.expires_at < self.observed_at:
                raise ValueError("liveness cannot expire before it was observed")


@dataclass(frozen=True)
class CheckEvaluation:
    check_id: str
    component_id: str
    applicability: CheckApplicability
    observed_state: ObservationState | None
    freshness: ObservationFreshness

    @property
    def passes(self) -> bool:
        return self.freshness is ObservationFreshness.FRESH and self.observed_state is ObservationState.PASS


@dataclass(frozen=True)
class LivenessEvaluation:
    state: LivenessState
    freshness: ObservationFreshness


@dataclass(frozen=True)
class CapabilityReadiness:
    capability_id: str
    ready: bool
    state: AggregateHealthState
    checks: tuple[CheckEvaluation, ...]
    contributing_check_ids: tuple[str, ...]


@dataclass(frozen=True)
class AggregateHealth:
    state: AggregateHealthState
    ready: bool
    ready_capabilities: tuple[str, ...]
    blocked_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class HealthEvaluation:
    """Liveness is deliberately independent from readiness and aggregate health."""

    liveness: LivenessEvaluation
    capabilities: tuple[CapabilityReadiness, ...]
    aggregate: AggregateHealth


def _freshness(
    *,
    observed_at: datetime,
    expires_at: datetime | None,
    max_age: timedelta,
    timed_out: bool,
    evaluated_at: datetime,
) -> ObservationFreshness:
    if timed_out:
        return ObservationFreshness.TIMED_OUT
    if observed_at > evaluated_at:
        return ObservationFreshness.INVALID
    if expires_at is not None and expires_at <= evaluated_at:
        return ObservationFreshness.EXPIRED
    if evaluated_at - observed_at > max_age:
        return ObservationFreshness.STALE
    return ObservationFreshness.FRESH


def evaluate_liveness(
    observation: LivenessObservation | None,
    *,
    evaluated_at: datetime,
) -> LivenessEvaluation:
    """Evaluate process liveness without implying capability readiness."""

    _require_aware(evaluated_at, "evaluated_at")
    if observation is None:
        return LivenessEvaluation(LivenessState.UNKNOWN, ObservationFreshness.MISSING)
    freshness = _freshness(
        observed_at=observation.observed_at,
        expires_at=observation.expires_at,
        max_age=observation.max_age,
        timed_out=observation.timed_out,
        evaluated_at=evaluated_at,
    )
    if freshness is not ObservationFreshness.FRESH or observation.alive is None:
        return LivenessEvaluation(LivenessState.UNKNOWN, freshness)
    return LivenessEvaluation(
        LivenessState.LIVE if observation.alive else LivenessState.NOT_LIVE,
        freshness,
    )


def _validated_inputs(
    checks: Iterable[HealthCheck], observations: Iterable[HealthObservation]
) -> tuple[dict[str, HealthCheck], dict[str, HealthObservation]]:
    check_items = tuple(checks)
    observation_items = tuple(observations)
    check_map = {item.check_id: item for item in check_items}
    observation_map = {item.check_id: item for item in observation_items}
    if len(check_map) != len(check_items):
        raise ValueError("health check identities must be unique")
    if len(observation_map) != len(observation_items):
        raise ValueError("health observation identities must be unique")
    unknown = set(observation_map) - set(check_map)
    if unknown:
        raise ValueError("health observations must reference declared checks")
    return check_map, observation_map


def _evaluate_check(
    check: HealthCheck,
    observation: HealthObservation | None,
    evaluated_at: datetime,
) -> CheckEvaluation:
    if check.applicability is CheckApplicability.DISABLED:
        return CheckEvaluation(
            check.check_id,
            check.component_id,
            check.applicability,
            None,
            ObservationFreshness.DISABLED,
        )
    if observation is None:
        return CheckEvaluation(
            check.check_id,
            check.component_id,
            check.applicability,
            None,
            ObservationFreshness.MISSING,
        )
    return CheckEvaluation(
        check.check_id,
        check.component_id,
        check.applicability,
        observation.state,
        _freshness(
            observed_at=observation.observed_at,
            expires_at=observation.expires_at,
            max_age=check.max_age,
            timed_out=observation.timed_out,
            evaluated_at=evaluated_at,
        ),
    )


def evaluate_capability_readiness(
    capability_id: str,
    checks: Iterable[HealthCheck],
    observations: Iterable[HealthObservation],
    *,
    evaluated_at: datetime,
) -> CapabilityReadiness:
    """Evaluate one named capability using explicit applicability semantics."""

    if not capability_id:
        raise ValueError("capability identity is required")
    _require_aware(evaluated_at, "evaluated_at")
    check_map, observation_map = _validated_inputs(checks, observations)
    declared = tuple(sorted(
        (item for item in check_map.values() if capability_id in item.capability_ids),
        key=lambda item: item.check_id,
    ))
    if not declared:
        return CapabilityReadiness(capability_id, False, AggregateHealthState.UNKNOWN, (), ())

    evaluated = tuple(_evaluate_check(item, observation_map.get(item.check_id), evaluated_at) for item in declared)
    applicable = tuple(item for item in evaluated if item.applicability is not CheckApplicability.DISABLED)
    if not applicable:
        return CapabilityReadiness(
            capability_id,
            False,
            AggregateHealthState.UNKNOWN,
            evaluated,
            (),
        )
    required = tuple(item for item in applicable if item.applicability is CheckApplicability.REQUIRED)
    optional = tuple(item for item in applicable if item.applicability is CheckApplicability.OPTIONAL)

    required_failures = tuple(item for item in required if item.freshness is ObservationFreshness.FRESH
                              and item.observed_state is ObservationState.FAIL)
    required_unknown = tuple(item for item in required if not item.passes and item not in required_failures)
    optional_unknown = tuple(item for item in optional if item.freshness is not ObservationFreshness.FRESH
                             or item.observed_state is ObservationState.UNKNOWN)
    optional_failures = tuple(item for item in optional if item.freshness is ObservationFreshness.FRESH
                              and item.observed_state is ObservationState.FAIL)

    if required_failures:
        state, ready, contributors = AggregateHealthState.UNAVAILABLE, False, required_failures
    elif required_unknown:
        state, ready, contributors = AggregateHealthState.UNKNOWN, False, required_unknown
    elif optional_unknown:
        state, ready, contributors = AggregateHealthState.UNKNOWN, True, optional_unknown
    elif optional_failures:
        state, ready, contributors = AggregateHealthState.DEGRADED, True, optional_failures
    else:
        state, ready, contributors = AggregateHealthState.HEALTHY, True, ()
    return CapabilityReadiness(
        capability_id,
        ready,
        state,
        evaluated,
        tuple(item.check_id for item in contributors),
    )


def evaluate_aggregate_health(capabilities: Iterable[CapabilityReadiness]) -> AggregateHealth:
    """Combine named readiness scopes without collapsing partial availability."""

    items = tuple(sorted(capabilities, key=lambda item: item.capability_id))
    identities = tuple(item.capability_id for item in items)
    if len(identities) != len(set(identities)):
        raise ValueError("capability readiness identities must be unique")
    if not items:
        return AggregateHealth(AggregateHealthState.UNKNOWN, False, (), ())

    ready = tuple(item.capability_id for item in items if item.ready)
    blocked = tuple(item.capability_id for item in items if not item.ready)
    unavailable = tuple(item for item in items if item.state is AggregateHealthState.UNAVAILABLE)
    unknown = tuple(item for item in items if item.state is AggregateHealthState.UNKNOWN)
    degraded = tuple(item for item in items if item.state is AggregateHealthState.DEGRADED)

    if unavailable:
        state = AggregateHealthState.DEGRADED if ready else AggregateHealthState.UNAVAILABLE
    elif unknown:
        state = AggregateHealthState.UNKNOWN
    elif degraded:
        state = AggregateHealthState.DEGRADED
    else:
        state = AggregateHealthState.HEALTHY
    return AggregateHealth(state, not blocked, ready, blocked)


def evaluate_health(
    *,
    liveness: LivenessObservation | None,
    capability_ids: Iterable[str],
    checks: Iterable[HealthCheck],
    observations: Iterable[HealthObservation],
    evaluated_at: datetime,
) -> HealthEvaluation:
    """Evaluate a complete immutable snapshot at a caller-supplied instant."""

    check_items = tuple(checks)
    observation_items = tuple(observations)
    requested = tuple(sorted(capability_ids))
    if not requested or len(requested) != len(set(requested)) or any(not item for item in requested):
        raise ValueError("health evaluation requires unique named capabilities")
    _validated_inputs(check_items, observation_items)
    capabilities = tuple(
        evaluate_capability_readiness(
            capability_id,
            check_items,
            observation_items,
            evaluated_at=evaluated_at,
        )
        for capability_id in requested
    )
    return HealthEvaluation(
        evaluate_liveness(liveness, evaluated_at=evaluated_at),
        capabilities,
        evaluate_aggregate_health(capabilities),
    )
