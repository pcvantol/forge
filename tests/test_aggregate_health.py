"""Focused regressions for deterministic aggregate health and readiness."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import unittest

from forge.health import (
    AggregateHealthEvaluator,
    AggregateHealthState,
    CapabilityReadinessState,
    CheckApplicability,
    EvaluatedCheckState,
    HealthCheck,
    HealthObservation,
    LivenessState,
    ObservationFreshness,
    ObservedCheckState,
)


NOW = datetime(2026, 9, 16, 18, 0, tzinfo=timezone.utc)
MAXIMUM_AGE = timedelta(seconds=30)


def check(
    check_id: str,
    *,
    applicability: CheckApplicability = CheckApplicability.REQUIRED,
    capabilities: tuple[str, ...] = ("local",),
    liveness: bool = False,
) -> HealthCheck:
    return HealthCheck(
        check_id=check_id,
        component_id=f"component-{check_id}",
        applicability=applicability,
        maximum_age=MAXIMUM_AGE,
        capabilities=capabilities,
        liveness=liveness,
    )


def observation(
    check_id: str,
    state: ObservedCheckState = ObservedCheckState.PASS,
    *,
    observed_at: datetime = NOW,
    expires_at: datetime | None = None,
    timed_out: bool = False,
) -> HealthObservation:
    return HealthObservation(check_id, state, observed_at, expires_at, timed_out)


class AggregateHealthEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = AggregateHealthEvaluator()
        self.liveness = check("process", capabilities=(), liveness=True)
        self.storage = check("storage")

    def evaluate(self, checks, observations, *capabilities: str):
        return self.evaluator.evaluate(
            checks, observations, capabilities=capabilities or ("local",), evaluated_at=NOW,
        )

    def test_liveness_readiness_and_aggregate_are_distinct_results(self) -> None:
        result = self.evaluate(
            (self.liveness, self.storage),
            (observation("process"), observation("storage", ObservedCheckState.FAIL)),
        )

        self.assertEqual(result.liveness, LivenessState.LIVE)
        self.assertEqual(result.readiness_for("local").state, CapabilityReadinessState.NOT_READY)
        self.assertEqual(result.aggregate, AggregateHealthState.UNAVAILABLE)

        dead_but_capable = self.evaluate(
            (self.liveness, self.storage),
            (observation("process", ObservedCheckState.FAIL), observation("storage")),
        )
        self.assertEqual(dead_but_capable.liveness, LivenessState.NOT_LIVE)
        self.assertEqual(dead_but_capable.readiness_for("local").state, CapabilityReadinessState.READY)
        self.assertEqual(dead_but_capable.aggregate, AggregateHealthState.UNAVAILABLE)

    def test_healthy_degraded_unavailable_and_unknown_truth_table(self) -> None:
        optional = check("relay", applicability=CheckApplicability.OPTIONAL)
        cases = (
            ((observation("process"), observation("storage"), observation("relay")), AggregateHealthState.HEALTHY),
            ((observation("process"), observation("storage"), observation("relay", ObservedCheckState.FAIL)), AggregateHealthState.DEGRADED),
            ((observation("process"), observation("storage", ObservedCheckState.FAIL), observation("relay")), AggregateHealthState.UNAVAILABLE),
            ((observation("process"), observation("relay")), AggregateHealthState.UNKNOWN),
        )
        for observations, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    self.evaluate((self.liveness, self.storage, optional), observations).aggregate,
                    expected,
                )

    def test_missing_stale_expired_and_timed_out_required_observations_never_pass(self) -> None:
        stale = observation("storage", observed_at=NOW - MAXIMUM_AGE - timedelta(microseconds=1))
        expired = observation("storage", observed_at=NOW, expires_at=NOW)
        timed_out = observation("storage", timed_out=True)
        cases = (
            ((), ObservationFreshness.MISSING),
            ((stale,), ObservationFreshness.STALE),
            ((expired,), ObservationFreshness.EXPIRED),
            ((timed_out,), ObservationFreshness.TIMED_OUT),
        )
        for supplied, freshness in cases:
            with self.subTest(freshness=freshness):
                result = self.evaluate(
                    (self.liveness, self.storage),
                    (observation("process"), *supplied),
                )
                storage = next(item for item in result.checks if item.check_id == "storage")
                self.assertEqual(storage.state, EvaluatedCheckState.UNKNOWN)
                self.assertEqual(storage.freshness, freshness)
                self.assertEqual(result.readiness_for("local").state, CapabilityReadinessState.UNKNOWN)
                self.assertEqual(result.aggregate, AggregateHealthState.UNKNOWN)

    def test_known_required_failure_precedes_an_unknown_required_check(self) -> None:
        peer = check("execution-peer")
        result = self.evaluate(
            (self.liveness, self.storage, peer),
            (observation("process"), observation("storage", ObservedCheckState.FAIL)),
        )

        self.assertEqual(result.readiness_for("local").state, CapabilityReadinessState.NOT_READY)
        self.assertEqual(result.aggregate, AggregateHealthState.UNAVAILABLE)

    def test_required_optional_and_disabled_checks_are_scoped(self) -> None:
        execution_peer = check("execution-peer", capabilities=("dispatch",))
        disabled_relay = check(
            "relay", applicability=CheckApplicability.DISABLED, capabilities=("local", "remote-access"),
        )
        checks = (self.liveness, self.storage, execution_peer, disabled_relay)
        observations = (
            observation("process"), observation("storage"),
            observation("execution-peer", ObservedCheckState.FAIL),
        )

        local = self.evaluate(checks, observations, "local")
        self.assertEqual(local.readiness_for("local").state, CapabilityReadinessState.READY)
        self.assertEqual(local.aggregate, AggregateHealthState.HEALTHY)
        relay = next(item for item in local.checks if item.check_id == "relay")
        self.assertEqual(relay.state, EvaluatedCheckState.DISABLED)
        self.assertEqual(relay.freshness, ObservationFreshness.DISABLED)

        dispatch = self.evaluate(checks, observations, "dispatch")
        self.assertEqual(dispatch.readiness_for("dispatch").state, CapabilityReadinessState.NOT_READY)
        self.assertEqual(dispatch.aggregate, AggregateHealthState.UNAVAILABLE)

    def test_enabled_optional_failure_degrades_without_blocking_readiness(self) -> None:
        relay = check(
            "relay", applicability=CheckApplicability.OPTIONAL, capabilities=("remote-access",),
        )
        remote_core = check("remote-core", capabilities=("remote-access",))
        result = self.evaluate(
            (self.liveness, relay, remote_core),
            (observation("process"), observation("relay", ObservedCheckState.FAIL), observation("remote-core")),
            "remote-access",
        )

        self.assertEqual(result.readiness_for("remote-access").state, CapabilityReadinessState.READY)
        self.assertEqual(result.aggregate, AggregateHealthState.DEGRADED)

        missing_optional = self.evaluate(
            (self.liveness, relay, remote_core),
            (observation("process"), observation("remote-core")),
            "remote-access",
        )
        self.assertEqual(missing_optional.readiness_for("remote-access").state, CapabilityReadinessState.READY)
        self.assertEqual(missing_optional.aggregate, AggregateHealthState.DEGRADED)

    def test_unknown_liveness_prevents_a_healthy_aggregate_without_changing_readiness(self) -> None:
        result = self.evaluate((self.storage,), (observation("storage"),))

        self.assertEqual(result.liveness, LivenessState.UNKNOWN)
        self.assertEqual(result.readiness_for("local").state, CapabilityReadinessState.READY)
        self.assertEqual(result.aggregate, AggregateHealthState.UNKNOWN)

    def test_evaluation_is_pure_and_inputs_and_results_are_immutable(self) -> None:
        checks = [self.liveness, self.storage]
        observations = [observation("process"), observation("storage")]
        before = (tuple(checks), tuple(observations))

        result = self.evaluate(checks, observations)

        self.assertEqual((tuple(checks), tuple(observations)), before)
        self.assertEqual(result.aggregate, AggregateHealthState.HEALTHY)
        with self.assertRaises(FrozenInstanceError):
            result.aggregate = AggregateHealthState.UNKNOWN  # type: ignore[misc]

    def test_duplicate_or_undeclared_observation_identity_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "observation IDs"):
            self.evaluate(
                (self.liveness, self.storage),
                (observation("process"), observation("storage"), observation("storage")),
            )
        with self.assertRaisesRegex(ValueError, "undeclared"):
            self.evaluate(
                (self.liveness, self.storage),
                (observation("process"), observation("storage"), observation("unknown")),
            )


if __name__ == "__main__":
    unittest.main()
