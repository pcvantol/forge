"""Deterministic, read-only aggregate health and readiness evaluation.

The evaluator consumes an already-declared check registry and already-collected
observations.  It performs no probing, persistence, generation, submission, or
other domain operation.  Liveness, named-capability readiness, and aggregate
health remain separate results so that one cannot be used as evidence for
another.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


AGGREGATE_HEALTH_SCHEMA_VERSION = "1.0"


class CheckApplicability(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    DISABLED = "DISABLED"


class ObservedCheckState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class EvaluatedCheckState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    DISABLED = "DISABLED"


class ObservationFreshness(str, Enum):
    CURRENT = "CURRENT"
    MISSING = "MISSING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    TIMED_OUT = "TIMED_OUT"
    FUTURE = "FUTURE"
    DISABLED = "DISABLED"


class LivenessState(str, Enum):
    LIVE = "LIVE"
    NOT_LIVE = "NOT_LIVE"
    UNKNOWN = "UNKNOWN"


class CapabilityReadinessState(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    UNKNOWN = "UNKNOWN"


class AggregateHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_aware(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


@dataclass(frozen=True)
class HealthCheck:
    """One stable registry declaration used by the pure evaluator.

    ``capabilities`` declares only the named readiness scopes to which the
    check contributes.  ``liveness`` separately declares whether it is a
    process-liveness observation; it does not make any capability ready.
    """

    check_id: str
    component_id: str
    applicability: CheckApplicability
    maximum_age: timedelta
    capabilities: tuple[str, ...] = ()
    liveness: bool = False

    def __post_init__(self) -> None:
        _require_identifier(self.check_id, "health check ID")
        _require_identifier(self.component_id, "health component ID")
        if not isinstance(self.applicability, CheckApplicability):
            raise ValueError("health check applicability is invalid")
        if not isinstance(self.maximum_age, timedelta) or self.maximum_age <= timedelta(0):
            raise ValueError("health check maximum age must be positive")
        if not isinstance(self.liveness, bool):
            raise ValueError("health check liveness flag is invalid")
        capabilities = tuple(self.capabilities)
        for capability in capabilities:
            _require_identifier(capability, "health capability")
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("health check capabilities must be unique")
        if not capabilities and not self.liveness:
            raise ValueError("health check must contribute to liveness or a named capability")
        object.__setattr__(self, "capabilities", tuple(sorted(capabilities)))


@dataclass(frozen=True)
class HealthObservation:
    """One bounded observation supplied to the evaluator by an owning source."""

    check_id: str
    state: ObservedCheckState
    observed_at: datetime
    expires_at: datetime | None = None
    timed_out: bool = False

    def __post_init__(self) -> None:
        _require_identifier(self.check_id, "health observation check ID")
        if not isinstance(self.state, ObservedCheckState):
            raise ValueError("health observation state is invalid")
        _require_aware(self.observed_at, "health observation time")
        if self.expires_at is not None:
            _require_aware(self.expires_at, "health observation expiry")
            if self.expires_at < self.observed_at:
                raise ValueError("health observation cannot expire before it was observed")
        if not isinstance(self.timed_out, bool):
            raise ValueError("health observation timeout flag is invalid")


@dataclass(frozen=True)
class HealthCheckEvaluation:
    check_id: str
    component_id: str
    applicability: CheckApplicability
    capabilities: tuple[str, ...]
    liveness: bool
    state: EvaluatedCheckState
    freshness: ObservationFreshness
    observed_at: datetime | None
    age: timedelta | None
    timed_out: bool
    reason: str


@dataclass(frozen=True)
class CapabilityReadiness:
    capability: str
    state: CapabilityReadinessState
    required_checks: tuple[str, ...]
    blocking_checks: tuple[str, ...]
    unknown_checks: tuple[str, ...]


@dataclass(frozen=True)
class AggregateHealthEvaluation:
    evaluated_at: datetime
    requested_capabilities: tuple[str, ...]
    liveness: LivenessState
    aggregate: AggregateHealthState
    capabilities: tuple[CapabilityReadiness, ...]
    checks: tuple[HealthCheckEvaluation, ...]
    schema_version: str = AGGREGATE_HEALTH_SCHEMA_VERSION

    def readiness_for(self, capability: str) -> CapabilityReadiness:
        """Return the exact requested capability result, failing on ambiguity."""
        for readiness in self.capabilities:
            if readiness.capability == capability:
                return readiness
        raise KeyError(capability)


class AggregateHealthEvaluator:
    """Evaluate supplied facts only; never collect facts or mutate a domain."""

    def evaluate(
        self,
        checks: Iterable[HealthCheck],
        observations: Iterable[HealthObservation],
        *,
        capabilities: Iterable[str],
        evaluated_at: datetime,
    ) -> AggregateHealthEvaluation:
        _require_aware(evaluated_at, "health evaluation time")
        declared_checks = tuple(checks)
        declared_observations = tuple(observations)
        if any(not isinstance(check, HealthCheck) for check in declared_checks):
            raise ValueError("health check declaration is invalid")
        if any(not isinstance(observation, HealthObservation) for observation in declared_observations):
            raise ValueError("health observation is invalid")
        requested_capabilities = tuple(capabilities)
        for capability in requested_capabilities:
            _require_identifier(capability, "requested health capability")
        if not requested_capabilities:
            raise ValueError("health evaluation requires at least one named capability")
        if len(requested_capabilities) != len(set(requested_capabilities)):
            raise ValueError("requested health capabilities must be unique")
        requested_capabilities = tuple(sorted(requested_capabilities))

        checks_by_id = self._unique_by_id(declared_checks, "check")
        observations_by_id = self._unique_by_id(declared_observations, "observation")
        unknown_observations = set(observations_by_id) - set(checks_by_id)
        if unknown_observations:
            raise ValueError("health observations reference undeclared checks")

        evaluations = tuple(
            self._evaluate_check(check, observations_by_id.get(check.check_id), evaluated_at)
            for check in sorted(declared_checks, key=lambda item: item.check_id)
        )
        evaluations_by_id = {item.check_id: item for item in evaluations}
        readiness = tuple(
            self._evaluate_capability(capability, declared_checks, evaluations_by_id)
            for capability in requested_capabilities
        )
        liveness = self._evaluate_liveness(declared_checks, evaluations_by_id)
        aggregate = self._evaluate_aggregate(
            declared_checks, evaluations_by_id, requested_capabilities, readiness, liveness,
        )
        return AggregateHealthEvaluation(
            evaluated_at=evaluated_at,
            requested_capabilities=requested_capabilities,
            liveness=liveness,
            aggregate=aggregate,
            capabilities=readiness,
            checks=evaluations,
        )

    @staticmethod
    def _unique_by_id(items, label: str) -> dict[str, object]:
        indexed: dict[str, object] = {}
        for item in items:
            item_id = getattr(item, "check_id", None)
            if not isinstance(item_id, str):
                raise ValueError(f"health {label} is invalid")
            if item_id in indexed:
                raise ValueError(f"health {label} IDs must be unique")
            indexed[item_id] = item
        return indexed

    @staticmethod
    def _evaluate_check(
        check: HealthCheck,
        observation: HealthObservation | None,
        evaluated_at: datetime,
    ) -> HealthCheckEvaluation:
        if check.applicability is CheckApplicability.DISABLED:
            return HealthCheckEvaluation(
                check.check_id, check.component_id, check.applicability, check.capabilities, check.liveness,
                EvaluatedCheckState.DISABLED, ObservationFreshness.DISABLED, None, None, False,
                "CHECK_DISABLED",
            )
        if observation is None:
            return HealthCheckEvaluation(
                check.check_id, check.component_id, check.applicability, check.capabilities, check.liveness,
                EvaluatedCheckState.UNKNOWN, ObservationFreshness.MISSING, None, None, False,
                "OBSERVATION_MISSING",
            )

        age = evaluated_at - observation.observed_at
        if observation.timed_out:
            freshness, reason = ObservationFreshness.TIMED_OUT, "OBSERVATION_TIMED_OUT"
        elif age < timedelta(0):
            freshness, reason = ObservationFreshness.FUTURE, "OBSERVATION_FROM_FUTURE"
        elif observation.expires_at is not None and evaluated_at >= observation.expires_at:
            freshness, reason = ObservationFreshness.EXPIRED, "OBSERVATION_EXPIRED"
        elif age > check.maximum_age:
            freshness, reason = ObservationFreshness.STALE, "OBSERVATION_STALE"
        else:
            freshness, reason = ObservationFreshness.CURRENT, "OBSERVATION_CURRENT"

        if freshness is not ObservationFreshness.CURRENT:
            state = EvaluatedCheckState.UNKNOWN
        elif observation.state is ObservedCheckState.PASS:
            state, reason = EvaluatedCheckState.PASS, "OBSERVATION_PASSED"
        elif observation.state is ObservedCheckState.FAIL:
            state, reason = EvaluatedCheckState.FAIL, "OBSERVATION_FAILED"
        else:
            state, reason = EvaluatedCheckState.UNKNOWN, "OBSERVATION_INSUFFICIENT"
        return HealthCheckEvaluation(
            check.check_id, check.component_id, check.applicability, check.capabilities, check.liveness,
            state, freshness, observation.observed_at, age, observation.timed_out, reason,
        )

    @staticmethod
    def _evaluate_capability(
        capability: str,
        checks: tuple[HealthCheck, ...],
        evaluations: dict[str, HealthCheckEvaluation],
    ) -> CapabilityReadiness:
        required = tuple(sorted(
            check.check_id for check in checks
            if check.applicability is CheckApplicability.REQUIRED and capability in check.capabilities
        ))
        blocking = tuple(check_id for check_id in required
                         if evaluations[check_id].state is EvaluatedCheckState.FAIL)
        unknown = tuple(check_id for check_id in required
                        if evaluations[check_id].state is EvaluatedCheckState.UNKNOWN)
        if blocking:
            state = CapabilityReadinessState.NOT_READY
        elif unknown or not required:
            state = CapabilityReadinessState.UNKNOWN
        else:
            state = CapabilityReadinessState.READY
        return CapabilityReadiness(capability, state, required, blocking, unknown)

    @staticmethod
    def _evaluate_liveness(
        checks: tuple[HealthCheck, ...],
        evaluations: dict[str, HealthCheckEvaluation],
    ) -> LivenessState:
        required = tuple(
            evaluations[check.check_id] for check in checks
            if check.liveness and check.applicability is CheckApplicability.REQUIRED
        )
        if any(item.state is EvaluatedCheckState.FAIL for item in required):
            return LivenessState.NOT_LIVE
        if not required or any(item.state is EvaluatedCheckState.UNKNOWN for item in required):
            return LivenessState.UNKNOWN
        return LivenessState.LIVE

    @staticmethod
    def _evaluate_aggregate(
        checks: tuple[HealthCheck, ...],
        evaluations: dict[str, HealthCheckEvaluation],
        requested_capabilities: tuple[str, ...],
        readiness: tuple[CapabilityReadiness, ...],
        liveness: LivenessState,
    ) -> AggregateHealthState:
        relevant = tuple(
            evaluations[check.check_id] for check in checks
            if check.liveness or set(check.capabilities).intersection(requested_capabilities)
        )
        required = tuple(item for item in relevant if item.applicability is CheckApplicability.REQUIRED)
        optional = tuple(item for item in relevant if item.applicability is CheckApplicability.OPTIONAL)

        # A current, known required failure outranks uncertain required facts.
        if any(item.state is EvaluatedCheckState.FAIL for item in required):
            return AggregateHealthState.UNAVAILABLE
        if (
            not required
            or liveness is LivenessState.UNKNOWN
            or any(item.state is EvaluatedCheckState.UNKNOWN for item in required)
            or any(item.state is CapabilityReadinessState.UNKNOWN for item in readiness)
        ):
            return AggregateHealthState.UNKNOWN
        if any(item.state in {EvaluatedCheckState.FAIL, EvaluatedCheckState.UNKNOWN} for item in optional):
            return AggregateHealthState.DEGRADED
        return AggregateHealthState.HEALTHY
