"""Deterministic, read-only aggregate-health evaluation.

The evaluator deliberately accepts observations as values.  It never probes a
peer, initializes a runtime, or invokes a provider: collecting observations is
owned by the caller and is separate from deciding their meaning.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable


class AggregateHealth(str, Enum):
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
    TIMED_OUT = "TIMED_OUT"


class EvaluatedCheckState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    DISABLED = "DISABLED"


LIVENESS_SCOPE = "liveness"


@dataclass(frozen=True)
class HealthCheck:
    """One stable health check and the readiness scope it contributes to."""

    check_id: str
    scope: str
    requirement: CheckRequirement

    def __post_init__(self) -> None:
        if not self.check_id or not self.scope:
            raise ValueError("health checks require stable check and scope identifiers")


@dataclass(frozen=True)
class HealthObservation:
    """A caller-collected observation with an explicit freshness lifetime."""

    check_id: str
    state: ObservationState
    observed_at: datetime
    valid_for: timedelta

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("health observation timestamps must be timezone-aware")
        if self.valid_for < timedelta(0):
            raise ValueError("health observation validity cannot be negative")

    def is_fresh_at(self, now: datetime) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("health evaluation timestamps must be timezone-aware")
        return now <= self.observed_at + self.valid_for


@dataclass(frozen=True)
class EvaluatedCheck:
    check: HealthCheck
    state: EvaluatedCheckState


@dataclass(frozen=True)
class HealthReport:
    """A pure projection for liveness, a named readiness scope, or all checks."""

    status: AggregateHealth
    ready: bool
    checks: tuple[EvaluatedCheck, ...]


def evaluate_health(checks: Iterable[HealthCheck], observations: Iterable[HealthObservation], *,
                    now: datetime, scope: str | None = None) -> HealthReport:
    """Evaluate supplied values without collecting observations or mutating state.

    A missing, stale, timed-out, or explicitly unknown required observation is
    always ``UNKNOWN`` and therefore cannot make a scope ready.  An enabled
    optional problem degrades an otherwise ready scope; disabled optional
    checks are shown but do not participate in the outcome.
    """
    selected_checks = tuple(check for check in checks if scope is None or check.scope == scope)
    if not selected_checks:
        return HealthReport(AggregateHealth.UNKNOWN, False, ())

    by_id: dict[str, HealthObservation] = {}
    for observation in observations:
        if observation.check_id in by_id:
            raise ValueError(f"duplicate observation for check {observation.check_id!r}")
        by_id[observation.check_id] = observation

    evaluated = tuple(
        EvaluatedCheck(check, _evaluate_check(check, by_id.get(check.check_id), now))
        for check in selected_checks
    )
    required = tuple(item for item in evaluated if item.check.requirement is CheckRequirement.REQUIRED)
    optional = tuple(item for item in evaluated if item.check.requirement is CheckRequirement.OPTIONAL)

    if any(item.state is EvaluatedCheckState.FAIL for item in required):
        return HealthReport(AggregateHealth.UNAVAILABLE, False, evaluated)
    if any(item.state is EvaluatedCheckState.UNKNOWN for item in required):
        return HealthReport(AggregateHealth.UNKNOWN, False, evaluated)
    if any(item.state is not EvaluatedCheckState.PASS for item in optional):
        return HealthReport(AggregateHealth.DEGRADED, True, evaluated)
    return HealthReport(AggregateHealth.HEALTHY, True, evaluated)


def evaluate_liveness(checks: Iterable[HealthCheck], observations: Iterable[HealthObservation], *,
                      now: datetime) -> HealthReport:
    """Evaluate process liveness independently from named capability readiness."""
    return evaluate_health(checks, observations, now=now, scope=LIVENESS_SCOPE)


def evaluate_readiness(checks: Iterable[HealthCheck], observations: Iterable[HealthObservation], *,
                       now: datetime, capability: str) -> HealthReport:
    """Evaluate one named capability without collapsing it into liveness."""
    return evaluate_health(checks, observations, now=now, scope=capability)


def _evaluate_check(check: HealthCheck, observation: HealthObservation | None,
                    now: datetime) -> EvaluatedCheckState:
    if check.requirement is CheckRequirement.DISABLED:
        return EvaluatedCheckState.DISABLED
    if observation is None or not observation.is_fresh_at(now):
        return EvaluatedCheckState.UNKNOWN
    if observation.state is ObservationState.PASS:
        return EvaluatedCheckState.PASS
    if observation.state is ObservationState.FAIL:
        return EvaluatedCheckState.FAIL
    return EvaluatedCheckState.UNKNOWN
