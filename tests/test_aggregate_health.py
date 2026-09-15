from datetime import datetime, timedelta, timezone
import unittest

from forge.aggregate_health import (
    AggregateHealth,
    CheckRequirement,
    EvaluatedCheckState,
    HealthCheck,
    HealthObservation,
    LIVENESS_SCOPE,
    ObservationState,
    evaluate_health,
    evaluate_liveness,
    evaluate_readiness,
)


NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


def observation(check_id, state=ObservationState.PASS, *, observed_at=NOW, valid_for=timedelta(minutes=1)):
    return HealthObservation(check_id, state, observed_at, valid_for)


class AggregateHealthTests(unittest.TestCase):
    def test_healthy_when_every_required_check_is_fresh_and_passing(self):
        report = evaluate_health(
            [HealthCheck("storage", "local", CheckRequirement.REQUIRED)],
            [observation("storage")], now=NOW,
        )
        self.assertEqual(report.status, AggregateHealth.HEALTHY)
        self.assertTrue(report.ready)

    def test_enabled_optional_failure_degrades_but_preserves_readiness(self):
        report = evaluate_health(
            [HealthCheck("storage", "local", CheckRequirement.REQUIRED),
             HealthCheck("relay", "local", CheckRequirement.OPTIONAL)],
            [observation("storage"), observation("relay", ObservationState.FAIL)], now=NOW,
        )
        self.assertEqual(report.status, AggregateHealth.DEGRADED)
        self.assertTrue(report.ready)

    def test_required_failure_is_unavailable(self):
        report = evaluate_health(
            [HealthCheck("execution-host", "dispatch", CheckRequirement.REQUIRED)],
            [observation("execution-host", ObservationState.FAIL)], now=NOW,
        )
        self.assertEqual(report.status, AggregateHealth.UNAVAILABLE)
        self.assertFalse(report.ready)

    def test_missing_stale_expired_and_timed_out_required_checks_are_never_ready(self):
        check = HealthCheck("storage", "local", CheckRequirement.REQUIRED)
        cases = (
            (),
            (observation("storage", observed_at=NOW - timedelta(seconds=1), valid_for=timedelta(0)),),
            (observation("storage", observed_at=NOW - timedelta(minutes=2), valid_for=timedelta(minutes=1)),),
            (observation("storage", ObservationState.TIMED_OUT),),
            (observation("storage", ObservationState.UNKNOWN),),
        )
        for observations in cases:
            with self.subTest(observations=observations):
                report = evaluate_health([check], observations, now=NOW)
                self.assertEqual(report.status, AggregateHealth.UNKNOWN)
                self.assertFalse(report.ready)

    def test_disabled_optional_relay_does_not_block_local_readiness(self):
        report = evaluate_health(
            [HealthCheck("storage", "local", CheckRequirement.REQUIRED),
             HealthCheck("relay", "local", CheckRequirement.DISABLED)],
            [observation("storage")], now=NOW,
        )
        self.assertEqual(report.status, AggregateHealth.HEALTHY)
        self.assertTrue(report.ready)
        self.assertEqual(report.checks[1].state, EvaluatedCheckState.DISABLED)

    def test_liveness_capability_readiness_and_aggregate_health_are_distinct(self):
        checks = [
            HealthCheck("process", LIVENESS_SCOPE, CheckRequirement.REQUIRED),
            HealthCheck("storage", "local", CheckRequirement.REQUIRED),
            HealthCheck("execution-host", "dispatch", CheckRequirement.REQUIRED),
        ]
        observations = [observation("process"), observation("storage"),
                        observation("execution-host", ObservationState.FAIL)]
        self.assertEqual(evaluate_liveness(checks, observations, now=NOW).status, AggregateHealth.HEALTHY)
        self.assertEqual(evaluate_readiness(checks, observations, now=NOW, capability="local").status,
                         AggregateHealth.HEALTHY)
        self.assertEqual(evaluate_readiness(checks, observations, now=NOW, capability="dispatch").status,
                         AggregateHealth.UNAVAILABLE)
        self.assertEqual(evaluate_health(checks, observations, now=NOW).status, AggregateHealth.UNAVAILABLE)

    def test_evaluation_does_not_mutate_supplied_values(self):
        checks = (HealthCheck("storage", "local", CheckRequirement.REQUIRED),)
        observations = (observation("storage"),)
        before = (checks, observations)
        report = evaluate_health(checks, observations, now=NOW)
        self.assertEqual((checks, observations), before)
        self.assertEqual(report.status, AggregateHealth.HEALTHY)


if __name__ == "__main__":
    unittest.main()
