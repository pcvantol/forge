"""Focused regressions for deterministic, read-only aggregate health."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
import unittest

from forge.runtime import (
    CheckApplicability,
    CheckPurpose,
    CheckState,
    HealthCheckDefinition,
    HealthIdentity,
    HealthObservation,
    HealthState,
    LivenessState,
    ObservationFreshness,
    ObservationState,
    ReadinessState,
    evaluate_health,
)


NOW = datetime(2026, 9, 16, 19, 0, tzinfo=UTC)
MAX_AGE = timedelta(seconds=30)
IDENTITY = HealthIdentity("0.7.0", "runtime-primary", "installation-primary")


def check(
    check_id: str,
    *,
    component_id: str = "forge_server",
    purpose: CheckPurpose = CheckPurpose.READINESS,
    applicability: CheckApplicability = CheckApplicability.REQUIRED,
    capabilities: tuple[str, ...] = ("local_work",),
) -> HealthCheckDefinition:
    if purpose is CheckPurpose.LIVENESS:
        capabilities = ()
    return HealthCheckDefinition(
        component_id, check_id, purpose, applicability, MAX_AGE, capabilities,
    )


def observation(
    check_id: str,
    state: ObservationState = ObservationState.PASS,
    *,
    observed_at: datetime = NOW,
    expires_at: datetime | None = None,
    reason_code: str | None = None,
) -> HealthObservation:
    if state is not ObservationState.PASS and reason_code is None:
        reason_code = f"{state.value}_OBSERVATION"
    return HealthObservation(check_id, state, observed_at, expires_at, reason_code)


def liveness() -> HealthCheckDefinition:
    return check("process", purpose=CheckPurpose.LIVENESS)


class RuntimeHealthTests(unittest.TestCase):
    def test_healthy_keeps_liveness_and_capability_readiness_distinct(self) -> None:
        definitions = (
            liveness(),
            check("storage"),
            check("execution_peer", component_id="engineering_platform", capabilities=("dispatch",)),
        )
        result = evaluate_health(
            IDENTITY,
            definitions,
            tuple(observation(item.check_id) for item in definitions),
            evaluated_at=NOW,
        )

        self.assertEqual(result.state, HealthState.HEALTHY)
        self.assertEqual(result.liveness.state, LivenessState.ALIVE)
        self.assertTrue(result.readiness_for("local_work").ready)
        self.assertTrue(result.readiness_for("dispatch").ready)
        self.assertEqual(result.to_dict()["schema_revision"], "1.0")

    def test_required_failure_is_unavailable_without_collapsing_liveness(self) -> None:
        result = evaluate_health(
            IDENTITY,
            (liveness(), check("storage"), check("execution_peer", capabilities=("dispatch",))),
            (
                observation("process"),
                observation("storage"),
                observation("execution_peer", ObservationState.FAIL, reason_code="PEER_UNREACHABLE"),
            ),
            evaluated_at=NOW,
        )

        self.assertEqual(result.state, HealthState.UNAVAILABLE)
        self.assertEqual(result.liveness.state, LivenessState.ALIVE)
        self.assertEqual(result.readiness_for("local_work").state, ReadinessState.READY)
        self.assertEqual(result.readiness_for("dispatch").state, ReadinessState.UNAVAILABLE)

    def test_missing_stale_expired_and_timed_out_required_observations_are_unknown(self) -> None:
        cases = {
            "missing": (),
            "stale": (observation("storage", observed_at=NOW - MAX_AGE - timedelta(microseconds=1)),),
            "expired": (observation("storage", observed_at=NOW - timedelta(seconds=10), expires_at=NOW),),
            "timed_out": (observation("storage", ObservationState.TIMED_OUT, reason_code="PROBE_TIMED_OUT"),),
        }
        freshness = {
            "missing": ObservationFreshness.MISSING,
            "stale": ObservationFreshness.STALE,
            "expired": ObservationFreshness.EXPIRED,
            "timed_out": ObservationFreshness.TIMED_OUT,
        }
        for name, readiness_observations in cases.items():
            with self.subTest(name=name):
                result = evaluate_health(
                    IDENTITY,
                    (liveness(), check("storage")),
                    (observation("process"), *readiness_observations),
                    evaluated_at=NOW,
                )
                storage = next(item for item in result.checks if item.check_id == "storage")
                self.assertEqual(storage.state, CheckState.UNKNOWN)
                self.assertEqual(storage.freshness, freshness[name])
                self.assertEqual(result.state, HealthState.UNKNOWN)
                self.assertEqual(result.readiness_for("local_work").state, ReadinessState.UNKNOWN)
                self.assertFalse(result.readiness_for("local_work").ready)

    def test_optional_failure_degrades_but_does_not_block_local_readiness(self) -> None:
        result = evaluate_health(
            IDENTITY,
            (
                liveness(),
                check("storage"),
                check(
                    "relay", component_id="dashboard_relay",
                    applicability=CheckApplicability.OPTIONAL,
                ),
            ),
            (
                observation("process"),
                observation("storage"),
                observation("relay", ObservationState.FAIL, reason_code="RELAY_UNREACHABLE"),
            ),
            evaluated_at=NOW,
        )

        local = result.readiness_for("local_work")
        self.assertEqual(result.state, HealthState.DEGRADED)
        self.assertEqual(local.state, ReadinessState.READY)
        self.assertTrue(local.ready)
        self.assertTrue(local.degraded)
        self.assertEqual(local.degraded_check_ids, ("relay",))

    def test_disabled_optional_relay_needs_no_observation_and_is_not_a_failure(self) -> None:
        for disabled_observation in (
            (),
            (observation("relay", ObservationState.FAIL, reason_code="LAST_KNOWN_RELAY_FAILURE"),),
        ):
            with self.subTest(last_known_observation=bool(disabled_observation)):
                result = evaluate_health(
                    IDENTITY,
                    (
                        liveness(),
                        check("storage"),
                        check(
                            "relay", component_id="dashboard_relay",
                            applicability=CheckApplicability.DISABLED,
                        ),
                    ),
                    (observation("process"), observation("storage"), *disabled_observation),
                    evaluated_at=NOW,
                )

                relay = next(item for item in result.checks if item.check_id == "relay")
                self.assertEqual(result.state, HealthState.HEALTHY)
                self.assertTrue(result.readiness_for("local_work").ready)
                self.assertFalse(result.readiness_for("local_work").degraded)
                self.assertEqual(relay.state, CheckState.DISABLED)
                self.assertEqual(relay.freshness, ObservationFreshness.NOT_APPLICABLE)

    def test_known_required_failure_takes_precedence_over_an_unknown_required_check(self) -> None:
        result = evaluate_health(
            IDENTITY,
            (
                liveness(),
                check("storage"),
                check("runtime_dependency"),
            ),
            (
                observation("process"),
                observation("storage", ObservationState.FAIL, reason_code="STORAGE_UNAVAILABLE"),
            ),
            evaluated_at=NOW,
        )

        self.assertEqual(result.state, HealthState.UNAVAILABLE)
        readiness = result.readiness_for("local_work")
        self.assertEqual(readiness.state, ReadinessState.UNAVAILABLE)
        self.assertEqual(readiness.blocking_check_ids, ("runtime_dependency", "storage"))

    def test_unknown_optional_observation_degrades_a_ready_capability(self) -> None:
        result = evaluate_health(
            IDENTITY,
            (
                liveness(),
                check("storage"),
                check("metrics", applicability=CheckApplicability.OPTIONAL),
            ),
            (observation("process"), observation("storage")),
            evaluated_at=NOW,
        )

        self.assertEqual(result.state, HealthState.DEGRADED)
        self.assertTrue(result.readiness_for("local_work").ready)
        self.assertEqual(result.readiness_for("local_work").degraded_check_ids, ("metrics",))

    def test_liveness_failure_does_not_fabricate_readiness_results(self) -> None:
        result = evaluate_health(
            IDENTITY,
            (liveness(), check("storage")),
            (
                observation("process", ObservationState.FAIL, reason_code="PROCESS_STOPPING"),
                observation("storage"),
            ),
            evaluated_at=NOW,
        )

        self.assertEqual(result.liveness.state, LivenessState.NOT_ALIVE)
        self.assertEqual(result.state, HealthState.UNAVAILABLE)
        self.assertEqual(result.readiness_for("local_work").state, ReadinessState.READY)

    def test_evaluation_is_deterministic_and_does_not_mutate_domain_state(self) -> None:
        definitions = (check("storage"), liveness())
        observations = (observation("storage"), observation("process"))
        domain_state = {"missions": 2, "leases": 1, "generations": 0}
        before = domain_state.copy()

        first = evaluate_health(IDENTITY, definitions, observations, evaluated_at=NOW)
        second = evaluate_health(
            IDENTITY,
            tuple(reversed(definitions)),
            tuple(reversed(observations)),
            evaluated_at=NOW,
        )

        self.assertEqual(first, second)
        self.assertEqual(domain_state, before)
        self.assertEqual(tuple(item.check_id for item in first.checks), ("process", "storage"))
        with self.assertRaises(FrozenInstanceError):
            first.state = HealthState.UNKNOWN  # type: ignore[misc]

    def test_future_observations_and_capabilities_without_required_checks_fail_closed(self) -> None:
        result = evaluate_health(
            IDENTITY,
            (
                liveness(),
                check("storage", applicability=CheckApplicability.OPTIONAL),
            ),
            (
                observation("process"),
                observation("storage", observed_at=NOW + timedelta(seconds=1)),
            ),
            evaluated_at=NOW,
        )

        self.assertEqual(result.state, HealthState.UNKNOWN)
        self.assertEqual(result.readiness_for("local_work").state, ReadinessState.UNKNOWN)
        storage = next(item for item in result.checks if item.check_id == "storage")
        self.assertEqual(storage.freshness, ObservationFreshness.FUTURE)

    def test_invalid_registry_and_observation_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            evaluate_health(
                IDENTITY,
                (liveness(), check("process")),
                (observation("process"),),
                evaluated_at=NOW,
            )
        with self.assertRaisesRegex(ValueError, "declared"):
            evaluate_health(
                IDENTITY,
                (liveness(),),
                (observation("process"), observation("undeclared")),
                evaluated_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
