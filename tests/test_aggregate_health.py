from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from forge.qualification.aggregate_health import (
    AggregateHealthEvaluator,
    AggregateHealthState,
    CheckRequirement,
    HealthCheck,
    HealthObservation,
    ObservationState,
    OptionalUnknownImpact,
)


NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


def observed(state: ObservationState = ObservationState.PASS, *, age: timedelta = timedelta(),
             expires_at: datetime | None = None) -> HealthObservation:
    return HealthObservation(state, NOW - age, expires_at)


def check(check_id: str, requirement: CheckRequirement, observation: HealthObservation | None, *,
          capability: str | None = "local", maximum_age: timedelta = timedelta(minutes=5),
          unknown_impact: OptionalUnknownImpact = OptionalUnknownImpact.UNKNOWN) -> HealthCheck:
    return HealthCheck(check_id, capability, requirement, maximum_age, observation, unknown_impact)


class AggregateHealthEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = AggregateHealthEvaluator()

    def test_disabled_optional_relay_does_not_block_local_readiness(self) -> None:
        checks = (
            check("storage", CheckRequirement.REQUIRED, observed()),
            check("relay", CheckRequirement.DISABLED, None, capability="local"),
        )
        aggregate = self.evaluator.evaluate_aggregate(checks, now=NOW)
        local = self.evaluator.evaluate_capability("local", checks, now=NOW)
        self.assertEqual(aggregate.state, AggregateHealthState.HEALTHY)
        self.assertTrue(local.ready)

    def test_enabled_optional_failure_is_degraded_but_local_readiness_remains_ready(self) -> None:
        checks = (
            check("storage", CheckRequirement.REQUIRED, observed()),
            check("relay", CheckRequirement.OPTIONAL, observed(ObservationState.FAIL), capability="remote"),
        )
        aggregate = self.evaluator.evaluate_aggregate(checks, now=NOW)
        local = self.evaluator.evaluate_capability("local", checks, now=NOW)
        self.assertEqual(aggregate.state, AggregateHealthState.DEGRADED)
        self.assertTrue(local.ready)
        self.assertEqual(local.state, AggregateHealthState.HEALTHY)

    def test_required_failure_is_unavailable_without_changing_liveness(self) -> None:
        checks = (check("execution-peer", CheckRequirement.REQUIRED, observed(ObservationState.FAIL), capability="dispatch"),)
        readiness = self.evaluator.evaluate_capability("dispatch", checks, now=NOW)
        liveness = self.evaluator.evaluate_liveness(observed(), now=NOW)
        self.assertEqual(readiness.state, AggregateHealthState.UNAVAILABLE)
        self.assertFalse(readiness.ready)
        self.assertTrue(liveness.live)

    def test_missing_stale_expired_and_timed_out_required_checks_never_pass(self) -> None:
        cases = (
            check("missing", CheckRequirement.REQUIRED, None),
            check("stale", CheckRequirement.REQUIRED, observed(age=timedelta(minutes=6))),
            check("expired", CheckRequirement.REQUIRED, observed(expires_at=NOW - timedelta(seconds=1))),
            check("timed-out", CheckRequirement.REQUIRED, observed(ObservationState.TIMEOUT)),
        )
        for required_check in cases:
            with self.subTest(check=required_check.check_id):
                result = self.evaluator.evaluate_capability("local", (required_check,), now=NOW)
                self.assertEqual(result.state, AggregateHealthState.UNKNOWN)
                self.assertFalse(result.ready)

    def test_declared_optional_unknown_policy_is_deterministic_and_visible(self) -> None:
        unknown = check("relay", CheckRequirement.OPTIONAL, None, unknown_impact=OptionalUnknownImpact.UNKNOWN)
        degraded = check("metrics", CheckRequirement.OPTIONAL, None, unknown_impact=OptionalUnknownImpact.DEGRADED)
        self.assertEqual(self.evaluator.evaluate_aggregate((unknown,), now=NOW).state, AggregateHealthState.UNKNOWN)
        self.assertEqual(self.evaluator.evaluate_aggregate((degraded,), now=NOW).state, AggregateHealthState.DEGRADED)

    def test_evaluation_is_a_pure_read_only_operation(self) -> None:
        checks = (check("storage", CheckRequirement.REQUIRED, observed()),)
        before = checks
        result = self.evaluator.evaluate_aggregate(checks, now=NOW)
        self.assertEqual(result.state, AggregateHealthState.HEALTHY)
        self.assertIs(checks, before)
        self.assertEqual(checks[0].observation, observed())


if __name__ == "__main__":
    unittest.main()
