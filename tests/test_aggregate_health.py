"""Focused regressions for deterministic aggregate health and readiness."""

from datetime import datetime, timedelta, timezone
import unittest

from forge.health import (
    AggregateHealthState,
    CheckApplicability,
    HealthCheck,
    HealthObservation,
    LivenessObservation,
    LivenessState,
    ObservationFreshness,
    ObservationState,
    evaluate_health,
)


NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
MAX_AGE = timedelta(seconds=30)


def check(
    check_id: str,
    applicability: CheckApplicability,
    *capabilities: str,
) -> HealthCheck:
    return HealthCheck(check_id, check_id.split(".")[0], capabilities, applicability, MAX_AGE)


def observation(
    check_id: str,
    state: ObservationState = ObservationState.PASS,
    *,
    age: timedelta = timedelta(0),
    expires_at: datetime | None = None,
    timed_out: bool = False,
) -> HealthObservation:
    return HealthObservation(check_id, state, NOW - age, expires_at, timed_out)


class AggregateHealthTests(unittest.TestCase):
    def evaluate(self, capability_ids, checks, observations, *, liveness=True):
        live = LivenessObservation(liveness, NOW, MAX_AGE) if liveness is not None else None
        return evaluate_health(
            liveness=live,
            capability_ids=capability_ids,
            checks=checks,
            observations=observations,
            evaluated_at=NOW,
        )

    def test_healthy_readiness_is_distinct_from_liveness(self) -> None:
        checks = (check("storage.read", CheckApplicability.REQUIRED, "local"),)
        result = self.evaluate(("local",), checks, (observation("storage.read"),), liveness=False)

        self.assertEqual(result.liveness.state, LivenessState.NOT_LIVE)
        self.assertTrue(result.capabilities[0].ready)
        self.assertEqual(result.capabilities[0].state, AggregateHealthState.HEALTHY)
        self.assertEqual(result.aggregate.state, AggregateHealthState.HEALTHY)

    def test_disabled_optional_relay_does_not_block_local_readiness(self) -> None:
        checks = (
            check("storage.read", CheckApplicability.REQUIRED, "local"),
            check("relay.connect", CheckApplicability.DISABLED, "local"),
        )
        result = self.evaluate(("local",), checks, (observation("storage.read"),))

        local = result.capabilities[0]
        self.assertTrue(local.ready)
        self.assertEqual(local.state, AggregateHealthState.HEALTHY)
        self.assertEqual(local.checks[0].freshness, ObservationFreshness.DISABLED)
        self.assertEqual(result.aggregate.state, AggregateHealthState.HEALTHY)

    def test_enabled_optional_failure_degrades_without_blocking(self) -> None:
        checks = (
            check("storage.read", CheckApplicability.REQUIRED, "local"),
            check("relay.connect", CheckApplicability.OPTIONAL, "local"),
        )
        observations = (
            observation("storage.read"),
            observation("relay.connect", ObservationState.FAIL),
        )
        result = self.evaluate(("local",), checks, observations)

        self.assertTrue(result.capabilities[0].ready)
        self.assertEqual(result.capabilities[0].state, AggregateHealthState.DEGRADED)
        self.assertEqual(result.aggregate.state, AggregateHealthState.DEGRADED)

    def test_required_failure_blocks_only_dependent_capability(self) -> None:
        checks = (
            check("storage.read", CheckApplicability.REQUIRED, "dispatch", "local"),
            check("ep.execute", CheckApplicability.REQUIRED, "dispatch"),
        )
        observations = (
            observation("storage.read"),
            observation("ep.execute", ObservationState.FAIL),
        )
        result = self.evaluate(("local", "dispatch"), checks, observations)
        readiness = {item.capability_id: item for item in result.capabilities}

        self.assertTrue(readiness["local"].ready)
        self.assertFalse(readiness["dispatch"].ready)
        self.assertEqual(readiness["dispatch"].state, AggregateHealthState.UNAVAILABLE)
        self.assertEqual(result.aggregate.state, AggregateHealthState.DEGRADED)
        self.assertEqual(result.aggregate.ready_capabilities, ("local",))
        self.assertEqual(result.aggregate.blocked_capabilities, ("dispatch",))

        dispatch_only = self.evaluate(("dispatch",), checks, observations)
        self.assertEqual(dispatch_only.aggregate.state, AggregateHealthState.UNAVAILABLE)

    def test_missing_required_observation_is_unknown_and_never_ready(self) -> None:
        checks = (check("storage.read", CheckApplicability.REQUIRED, "local"),)
        result = self.evaluate(("local",), checks, ())

        self.assertFalse(result.capabilities[0].ready)
        self.assertEqual(result.capabilities[0].state, AggregateHealthState.UNKNOWN)
        self.assertEqual(result.capabilities[0].checks[0].freshness, ObservationFreshness.MISSING)
        self.assertEqual(result.aggregate.state, AggregateHealthState.UNKNOWN)

    def test_stale_expired_and_timed_out_required_passes_are_unknown(self) -> None:
        checks = (
            check("storage.stale", CheckApplicability.REQUIRED, "local"),
            check("storage.expired", CheckApplicability.REQUIRED, "local"),
            check("storage.timeout", CheckApplicability.REQUIRED, "local"),
        )
        observations = (
            observation("storage.stale", age=MAX_AGE + timedelta(microseconds=1)),
            observation("storage.expired", expires_at=NOW),
            observation("storage.timeout", timed_out=True),
        )
        result = self.evaluate(("local",), checks, observations)
        freshness = {item.check_id: item.freshness for item in result.capabilities[0].checks}

        self.assertEqual(freshness["storage.stale"], ObservationFreshness.STALE)
        self.assertEqual(freshness["storage.expired"], ObservationFreshness.EXPIRED)
        self.assertEqual(freshness["storage.timeout"], ObservationFreshness.TIMED_OUT)
        self.assertFalse(result.capabilities[0].ready)
        self.assertEqual(result.aggregate.state, AggregateHealthState.UNKNOWN)

    def test_unknown_optional_observation_is_visible_but_does_not_block_readiness(self) -> None:
        checks = (
            check("storage.read", CheckApplicability.REQUIRED, "local"),
            check("relay.connect", CheckApplicability.OPTIONAL, "local"),
        )
        result = self.evaluate(("local",), checks, (observation("storage.read"),))

        self.assertTrue(result.capabilities[0].ready)
        self.assertEqual(result.capabilities[0].state, AggregateHealthState.UNKNOWN)
        self.assertEqual(result.aggregate.state, AggregateHealthState.UNKNOWN)

    def test_known_required_failure_precedes_another_unknown_required_check(self) -> None:
        checks = (
            check("storage.read", CheckApplicability.REQUIRED, "dispatch"),
            check("ep.execute", CheckApplicability.REQUIRED, "dispatch"),
        )
        result = self.evaluate(
            ("dispatch",),
            checks,
            (observation("storage.read", ObservationState.FAIL),),
        )

        self.assertEqual(result.capabilities[0].state, AggregateHealthState.UNAVAILABLE)
        self.assertEqual(result.aggregate.state, AggregateHealthState.UNAVAILABLE)

    def test_evaluation_is_repeatable_and_does_not_mutate_domain_inputs(self) -> None:
        checks = (check("storage.read", CheckApplicability.REQUIRED, "local"),)
        observations = (observation("storage.read"),)
        inputs = (checks, observations)

        first = self.evaluate(("local",), checks, observations)
        second = self.evaluate(("local",), checks, observations)

        self.assertEqual(first, second)
        self.assertEqual(inputs, (checks, observations))
        with self.assertRaises(AttributeError):
            checks[0].check_id = "mutated"  # type: ignore[misc]

    def test_undeclared_capability_and_unknown_observation_fail_closed(self) -> None:
        checks = (check("storage.read", CheckApplicability.REQUIRED, "local"),)
        undeclared = self.evaluate(("remote",), checks, (observation("storage.read"),))
        self.assertFalse(undeclared.capabilities[0].ready)
        self.assertEqual(undeclared.aggregate.state, AggregateHealthState.UNKNOWN)

        with self.assertRaisesRegex(ValueError, "declared checks"):
            self.evaluate(("local",), checks, (observation("unknown.check"),))


if __name__ == "__main__":
    unittest.main()
