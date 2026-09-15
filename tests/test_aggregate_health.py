"""Regression coverage for the pure aggregate-health service layer."""
from datetime import UTC, datetime, timedelta
import unittest

from forge.health import (
    AggregateHealthEvaluator,
    AggregateHealthOutcome,
    CheckRequirement,
    EffectiveCheckState,
    HealthCheck,
    HealthObservation,
    ObservationState,
)


NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)


def observed(state: ObservationState = ObservationState.PASS, **changes: object) -> HealthObservation:
    values: dict[str, object] = {"state": state, "observed_at": NOW, "max_age": timedelta(minutes=1)}
    values.update(changes)
    return HealthObservation(**values)  # type: ignore[arg-type]


def check(capability: str, requirement: CheckRequirement, observation: HealthObservation | None = None,
          check_id: str | None = None) -> HealthCheck:
    return HealthCheck("runtime", check_id or capability, capability, requirement, observation)


class AggregateHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = AggregateHealthEvaluator()

    def evaluate(self, *checks: HealthCheck, liveness: bool = True, capabilities: tuple[str, ...] = ("local",)):
        return self.evaluator.evaluate(liveness=liveness, requested_capabilities=capabilities, checks=checks, evaluated_at=NOW)

    def test_healthy_requires_fresh_passing_required_observations(self) -> None:
        result = self.evaluate(check("local", CheckRequirement.REQUIRED, observed()))
        self.assertEqual(result.outcome, AggregateHealthOutcome.HEALTHY)
        self.assertTrue(result.liveness)
        self.assertEqual(dict(result.capability_readiness), {"local": True})

    def test_optional_failure_degrades_without_blocking_ready_capability(self) -> None:
        result = self.evaluate(
            check("local", CheckRequirement.REQUIRED, observed()),
            check("remote", CheckRequirement.OPTIONAL, observed(ObservationState.FAIL)),
        )
        self.assertEqual(result.outcome, AggregateHealthOutcome.DEGRADED)
        self.assertEqual(dict(result.capability_readiness), {"local": True})

    def test_disabled_optional_relay_does_not_block_local_readiness(self) -> None:
        result = self.evaluate(
            check("local", CheckRequirement.REQUIRED, observed()),
            check("relay", CheckRequirement.DISABLED, observed(ObservationState.FAIL)),
        )
        self.assertEqual(result.outcome, AggregateHealthOutcome.HEALTHY)
        self.assertTrue(result.capability_readiness["local"])
        self.assertEqual(result.checks[1].state, EffectiveCheckState.DISABLED)

    def test_required_failure_is_unavailable_while_liveness_is_still_true(self) -> None:
        result = self.evaluate(check("dispatch", CheckRequirement.REQUIRED, observed(ObservationState.FAIL)),
                               capabilities=("dispatch",))
        self.assertEqual(result.outcome, AggregateHealthOutcome.UNAVAILABLE)
        self.assertTrue(result.liveness)
        self.assertFalse(result.capability_readiness["dispatch"])

    def test_required_missing_stale_expired_and_timed_out_observations_are_unknown_never_pass(self) -> None:
        cases = (
            ("missing", None),
            ("stale", observed(observed_at=NOW - timedelta(minutes=2))),
            ("expired", observed(expires_at=NOW)),
            ("timed-out", observed(timed_out=True)),
        )
        for label, observation in cases:
            with self.subTest(label=label):
                result = self.evaluate(check("local", CheckRequirement.REQUIRED, observation))
                self.assertEqual(result.outcome, AggregateHealthOutcome.UNKNOWN)
                self.assertFalse(result.capability_readiness["local"])
                self.assertEqual(result.checks[0].state, EffectiveCheckState.UNKNOWN)

    def test_dead_process_is_not_healthy_even_when_capability_observation_passes(self) -> None:
        result = self.evaluate(check("local", CheckRequirement.REQUIRED, observed()), liveness=False)
        self.assertEqual(result.outcome, AggregateHealthOutcome.UNAVAILABLE)
        self.assertFalse(result.liveness)
        self.assertFalse(result.capability_readiness["local"])

    def test_evaluation_is_read_only_for_its_input_observations(self) -> None:
        observation = observed()
        source = check("local", CheckRequirement.REQUIRED, observation)
        before = (source, observation)
        result = self.evaluate(source)
        self.assertEqual((source, observation), before)
        self.assertEqual(result.outcome, AggregateHealthOutcome.HEALTHY)


if __name__ == "__main__":
    unittest.main()
