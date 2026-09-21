"""Deterministic, read-only Forge health and readiness evaluation.

The evaluator consumes a projection from the owning component registry.  It
does not discover components, run probes, invoke providers, or mutate runtime
state.  Callers collect bounded observations separately and provide the exact
time at which those observations must be assessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re
from typing import Iterable


HEALTH_SCHEMA_REVISION = "1.0"

_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class CheckPurpose(str, Enum):
    LIVENESS = "LIVENESS"
    READINESS = "READINESS"


class CheckApplicability(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class ObservationState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    TIMED_OUT = "TIMED_OUT"


class ObservationFreshness(str, Enum):
    FRESH = "FRESH"
    MISSING = "MISSING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    TIMED_OUT = "TIMED_OUT"
    FUTURE = "FUTURE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CheckState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    DISABLED = "DISABLED"


class LivenessState(str, Enum):
    ALIVE = "ALIVE"
    NOT_ALIVE = "NOT_ALIVE"
    UNKNOWN = "UNKNOWN"


class ReadinessState(str, Enum):
    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


def _require_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a stable identifier")
    return value


def _require_aware(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


def _timestamp(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


@dataclass(frozen=True)
class HealthIdentity:
    """Non-secret identity bound to one health evaluation."""

    product_version: str
    runtime_id: str
    installation_id: str
    product: str = "forge"
    schema_revision: str = HEALTH_SCHEMA_REVISION

    def __post_init__(self) -> None:
        if self.product != "forge" or self.schema_revision != HEALTH_SCHEMA_REVISION:
            raise ValueError("health product or schema revision is unsupported")
        if not isinstance(self.product_version, str) or not _VERSION.fullmatch(self.product_version):
            raise ValueError("product version must be bounded text")
        _require_identifier(self.runtime_id, "runtime id")
        _require_identifier(self.installation_id, "installation id")


@dataclass(frozen=True)
class HealthCheckDefinition:
    """One check projected from the canonical component registry.

    Applicability records whether a check is required or optional. Enabled
    state is separate so only an optional check may be disabled; a mandatory
    readiness obligation cannot disappear by being relabelled disabled.
    """

    component_id: str
    check_id: str
    purpose: CheckPurpose
    applicability: CheckApplicability
    freshness_timeout: timedelta
    capabilities: tuple[str, ...] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        _require_identifier(self.component_id, "component id")
        _require_identifier(self.check_id, "check id")
        if not isinstance(self.purpose, CheckPurpose):
            raise ValueError("check purpose is invalid")
        if not isinstance(self.applicability, CheckApplicability):
            raise ValueError("check applicability is invalid")
        if not isinstance(self.enabled, bool):
            raise ValueError("check enabled state must be boolean")
        if not isinstance(self.freshness_timeout, timedelta) or self.freshness_timeout <= timedelta(0):
            raise ValueError("freshness timeout must be positive")
        if not isinstance(self.capabilities, tuple):
            raise ValueError("capabilities must be an immutable tuple")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("capabilities must be unique")
        for capability in self.capabilities:
            _require_identifier(capability, "capability id")
        if self.purpose is CheckPurpose.LIVENESS:
            if (
                self.applicability is not CheckApplicability.REQUIRED
                or not self.enabled
                or self.capabilities
            ):
                raise ValueError("liveness checks must be enabled, required, and capability-independent")
        elif not self.capabilities:
            raise ValueError("readiness checks must name at least one capability")
        elif not self.enabled and self.applicability is not CheckApplicability.OPTIONAL:
            raise ValueError("only optional readiness checks may be disabled")


@dataclass(frozen=True)
class HealthObservation:
    """A bounded observation collected for one runtime and check scope."""

    identity: HealthIdentity
    component_id: str
    check_id: str
    purpose: CheckPurpose
    capabilities: tuple[str, ...]
    state: ObservationState
    observed_at: datetime
    expires_at: datetime | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HealthIdentity):
            raise ValueError("observation identity is required")
        _require_identifier(self.component_id, "component id")
        _require_identifier(self.check_id, "check id")
        if not isinstance(self.purpose, CheckPurpose):
            raise ValueError("observation purpose is invalid")
        if not isinstance(self.capabilities, tuple):
            raise ValueError("observation capabilities must be an immutable tuple")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("observation capabilities must be unique")
        for capability in self.capabilities:
            _require_identifier(capability, "capability id")
        if self.purpose is CheckPurpose.LIVENESS and self.capabilities:
            raise ValueError("liveness observations must be capability-independent")
        if self.purpose is CheckPurpose.READINESS and not self.capabilities:
            raise ValueError("readiness observations must name at least one capability")
        if not isinstance(self.state, ObservationState):
            raise ValueError("observation state is invalid")
        observed_at = _require_aware(self.observed_at, "observation time")
        if self.expires_at is not None:
            expires_at = _require_aware(self.expires_at, "observation expiry")
            if expires_at <= observed_at:
                raise ValueError("observation expiry must follow its observation time")
        if self.reason_code is not None and not _REASON_CODE.fullmatch(self.reason_code):
            raise ValueError("observation reason must be a bounded safe code")
        if self.state is not ObservationState.PASS and self.reason_code is None:
            raise ValueError("non-passing observations require a safe reason code")


@dataclass(frozen=True)
class CheckEvaluation:
    component_id: str
    check_id: str
    purpose: CheckPurpose
    applicability: CheckApplicability
    enabled: bool
    capabilities: tuple[str, ...]
    state: CheckState
    freshness: ObservationFreshness
    observation_state: ObservationState | None
    observed_at: datetime | None
    expires_at: datetime | None
    age_seconds: float | None
    timeout_seconds: float
    reason_code: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "check_id": self.check_id,
            "purpose": self.purpose.value,
            "applicability": self.applicability.value,
            "enabled": self.enabled,
            "capabilities": list(self.capabilities),
            "state": self.state.value,
            "freshness": self.freshness.value,
            "observation_state": None if self.observation_state is None else self.observation_state.value,
            "observed_at": _timestamp(self.observed_at),
            "expires_at": _timestamp(self.expires_at),
            "age_seconds": self.age_seconds,
            "timeout_seconds": self.timeout_seconds,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class LivenessEvaluation:
    state: LivenessState
    check_ids: tuple[str, ...]

    @property
    def alive(self) -> bool:
        return self.state is LivenessState.ALIVE

    def to_dict(self) -> dict[str, object]:
        return {"state": self.state.value, "alive": self.alive, "check_ids": list(self.check_ids)}


@dataclass(frozen=True)
class CapabilityReadiness:
    capability_id: str
    state: ReadinessState
    required_check_ids: tuple[str, ...]
    blocking_check_ids: tuple[str, ...]
    degraded_check_ids: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.state is ReadinessState.READY

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_check_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "state": self.state.value,
            "ready": self.ready,
            "degraded": self.degraded,
            "required_check_ids": list(self.required_check_ids),
            "blocking_check_ids": list(self.blocking_check_ids),
            "degraded_check_ids": list(self.degraded_check_ids),
        }


@dataclass(frozen=True)
class HealthEvaluation:
    identity: HealthIdentity
    evaluated_at: datetime
    capability_scope: tuple[str, ...]
    state: HealthState
    liveness: LivenessEvaluation
    capabilities: tuple[CapabilityReadiness, ...]
    checks: tuple[CheckEvaluation, ...]

    def readiness_for(self, capability_id: str) -> CapabilityReadiness:
        _require_identifier(capability_id, "capability id")
        for readiness in self.capabilities:
            if readiness.capability_id == capability_id:
                return readiness
        raise KeyError(capability_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_revision": self.identity.schema_revision,
            "product": self.identity.product,
            "product_version": self.identity.product_version,
            "runtime_id": self.identity.runtime_id,
            "installation_id": self.identity.installation_id,
            "evaluated_at": _timestamp(self.evaluated_at),
            "capability_scope": list(self.capability_scope),
            "state": self.state.value,
            "liveness": self.liveness.to_dict(),
            "capabilities": [item.to_dict() for item in self.capabilities],
            "checks": [item.to_dict() for item in self.checks],
        }


def evaluate_health(
    identity: HealthIdentity,
    definitions: Iterable[HealthCheckDefinition],
    observations: Iterable[HealthObservation],
    *,
    capability_scope: Iterable[str],
    evaluated_at: datetime,
) -> HealthEvaluation:
    """Evaluate one immutable snapshot for an explicit readiness scope.

    The caller supplies the canonical registry projection and must name every
    capability advertised by this aggregate. Each requested capability needs
    an enabled required readiness definition, so a liveness-only or optional-
    only projection cannot become a green aggregate.
    """

    if not isinstance(identity, HealthIdentity):
        raise TypeError("health identity is required")
    evaluated_at = _require_aware(evaluated_at, "evaluation time")
    if isinstance(capability_scope, (str, bytes)):
        raise ValueError("requested capabilities must be an iterable of identifiers")
    capability_items = tuple(capability_scope)
    if not capability_items:
        raise ValueError("at least one requested capability is required")
    if len(capability_items) != len(set(capability_items)):
        raise ValueError("requested capabilities must be unique")
    for capability_id in capability_items:
        _require_identifier(capability_id, "requested capability id")
    ordered_capability_scope = tuple(sorted(capability_items))
    definition_items = tuple(definitions)
    if not definition_items or not all(isinstance(item, HealthCheckDefinition) for item in definition_items):
        raise ValueError("at least one typed health check definition is required")
    ordered_definitions = tuple(sorted(definition_items, key=lambda item: (item.component_id, item.check_id)))
    definition_ids = tuple(item.check_id for item in ordered_definitions)
    if len(definition_ids) != len(set(definition_ids)):
        raise ValueError("health check ids must be unique")
    if not any(item.purpose is CheckPurpose.LIVENESS for item in ordered_definitions):
        raise ValueError("at least one liveness check is required")
    for capability_id in ordered_capability_scope:
        required_definitions = tuple(
            item for item in ordered_definitions
            if item.purpose is CheckPurpose.READINESS
            and item.enabled
            and item.applicability is CheckApplicability.REQUIRED
            and capability_id in item.capabilities
        )
        if not required_definitions:
            raise ValueError(
                "each requested capability must have an enabled required readiness check"
            )

    observation_items = tuple(observations)
    if not all(isinstance(item, HealthObservation) for item in observation_items):
        raise ValueError("typed health observations are required")
    observation_ids = tuple(item.check_id for item in observation_items)
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("health observation check ids must be unique")
    unknown_ids = set(observation_ids).difference(definition_ids)
    if unknown_ids:
        raise ValueError("observations must reference declared health checks")
    definition_by_id = {item.check_id: item for item in ordered_definitions}
    if any(item.identity != identity for item in observation_items):
        raise ValueError("observation identity must match the health evaluation")
    if any(not _observation_matches_definition(item, definition_by_id[item.check_id])
           for item in observation_items):
        raise ValueError("observation scope must match its declared health check")
    observation_by_id = {item.check_id: item for item in observation_items}

    checks = tuple(
        _evaluate_check(definition, observation_by_id.get(definition.check_id), evaluated_at)
        for definition in ordered_definitions
    )
    liveness = _evaluate_liveness(checks)
    capabilities = _evaluate_capabilities(checks)
    state = _aggregate_state(checks, capabilities, ordered_capability_scope)
    return HealthEvaluation(
        identity,
        evaluated_at,
        ordered_capability_scope,
        state,
        liveness,
        capabilities,
        checks,
    )


def _observation_matches_definition(
    observation: HealthObservation,
    definition: HealthCheckDefinition,
) -> bool:
    return (
        observation.component_id == definition.component_id
        and observation.purpose is definition.purpose
        and tuple(sorted(observation.capabilities)) == tuple(sorted(definition.capabilities))
    )


def _evaluate_check(
    definition: HealthCheckDefinition,
    observation: HealthObservation | None,
    evaluated_at: datetime,
) -> CheckEvaluation:
    timeout_seconds = definition.freshness_timeout.total_seconds()
    common = (
        definition.component_id,
        definition.check_id,
        definition.purpose,
        definition.applicability,
        definition.enabled,
        tuple(sorted(definition.capabilities)),
    )
    if not definition.enabled:
        return CheckEvaluation(
            *common, CheckState.DISABLED, ObservationFreshness.NOT_APPLICABLE,
            None, None, None, None, timeout_seconds, "CHECK_DISABLED",
        )
    if observation is None:
        return CheckEvaluation(
            *common, CheckState.UNKNOWN, ObservationFreshness.MISSING,
            None, None, None, None, timeout_seconds, "OBSERVATION_MISSING",
        )

    age_seconds = (evaluated_at - observation.observed_at).total_seconds()
    observed = (observation.state, observation.observed_at, observation.expires_at, age_seconds, timeout_seconds)
    if age_seconds < 0:
        return CheckEvaluation(
            *common, CheckState.UNKNOWN, ObservationFreshness.FUTURE,
            *observed, "OBSERVATION_IN_FUTURE",
        )
    if observation.state is ObservationState.TIMED_OUT:
        return CheckEvaluation(
            *common, CheckState.UNKNOWN, ObservationFreshness.TIMED_OUT,
            *observed, observation.reason_code or "OBSERVATION_TIMED_OUT",
        )
    if observation.expires_at is not None and observation.expires_at <= evaluated_at:
        return CheckEvaluation(
            *common, CheckState.UNKNOWN, ObservationFreshness.EXPIRED,
            *observed, "OBSERVATION_EXPIRED",
        )
    if age_seconds >= timeout_seconds:
        return CheckEvaluation(
            *common, CheckState.UNKNOWN, ObservationFreshness.STALE,
            *observed, "OBSERVATION_STALE",
        )
    if observation.state is ObservationState.PASS:
        state = CheckState.PASS
    elif observation.state is ObservationState.FAIL:
        state = CheckState.FAIL
    else:
        state = CheckState.UNKNOWN
    return CheckEvaluation(
        *common, state, ObservationFreshness.FRESH,
        *observed, observation.reason_code,
    )


def _evaluate_liveness(checks: tuple[CheckEvaluation, ...]) -> LivenessEvaluation:
    liveness = tuple(item for item in checks if item.purpose is CheckPurpose.LIVENESS)
    if any(item.state is CheckState.FAIL for item in liveness):
        state = LivenessState.NOT_ALIVE
    elif any(item.state is CheckState.UNKNOWN for item in liveness):
        state = LivenessState.UNKNOWN
    else:
        state = LivenessState.ALIVE
    return LivenessEvaluation(state, tuple(item.check_id for item in liveness))


def _evaluate_capabilities(checks: tuple[CheckEvaluation, ...]) -> tuple[CapabilityReadiness, ...]:
    capability_ids = sorted({capability for item in checks for capability in item.capabilities})
    results: list[CapabilityReadiness] = []
    for capability_id in capability_ids:
        relevant = tuple(item for item in checks if capability_id in item.capabilities)
        required = tuple(
            item for item in relevant
            if item.enabled and item.applicability is CheckApplicability.REQUIRED
        )
        failed = tuple(item.check_id for item in required if item.state is CheckState.FAIL)
        unresolved = tuple(item.check_id for item in required if item.state is CheckState.UNKNOWN)
        optional_issues = tuple(
            item.check_id for item in relevant
            if item.enabled
            and item.applicability is CheckApplicability.OPTIONAL
            and item.state is not CheckState.PASS
        )
        if failed:
            state = ReadinessState.UNAVAILABLE
        elif unresolved or not required:
            state = ReadinessState.UNKNOWN
        else:
            state = ReadinessState.READY
        results.append(CapabilityReadiness(
            capability_id,
            state,
            tuple(item.check_id for item in required),
            tuple(sorted((*failed, *unresolved))),
            tuple(sorted(optional_issues)),
        ))
    return tuple(results)


def _aggregate_state(
    checks: tuple[CheckEvaluation, ...],
    capabilities: tuple[CapabilityReadiness, ...],
    capability_scope: tuple[str, ...],
) -> HealthState:
    required_liveness = tuple(
        item for item in checks
        if item.purpose is CheckPurpose.LIVENESS
        and item.enabled
        and item.applicability is CheckApplicability.REQUIRED
    )
    if any(item.state is CheckState.FAIL for item in required_liveness):
        return HealthState.UNAVAILABLE
    liveness_unknown = any(item.state is CheckState.UNKNOWN for item in required_liveness)

    required_capabilities = tuple(
        item for item in capabilities if item.capability_id in capability_scope
    )
    unavailable = tuple(
        item for item in required_capabilities
        if item.state is ReadinessState.UNAVAILABLE
    )
    if unavailable:
        if liveness_unknown:
            return HealthState.UNAVAILABLE
        if any(item.state is ReadinessState.READY for item in required_capabilities):
            return HealthState.DEGRADED
        return HealthState.UNAVAILABLE
    if liveness_unknown or any(
        item.state is ReadinessState.UNKNOWN for item in required_capabilities
    ):
        return HealthState.UNKNOWN

    optional = tuple(
        item for item in checks
        if item.enabled
        and item.applicability is CheckApplicability.OPTIONAL
        and any(capability_id in capability_scope for capability_id in item.capabilities)
    )
    if any(item.state is not CheckState.PASS for item in optional):
        return HealthState.DEGRADED
    return HealthState.HEALTHY
