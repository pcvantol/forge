"""Focused regressions for deterministic, read-only aggregate health."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path
import unittest

import forge.runtime.health as health_module
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
LOCAL_SCOPE = ("local_work",)
FULL_SCOPE = ("dispatch", "local_work")


def check(
    check_id: str,
    *,
    component_id: str = "forge_server",
    purpose: CheckPurpose = CheckPurpose.READINESS,
    applicability: CheckApplicability = CheckApplicability.REQUIRED,
    capabilities: tuple[str, ...] = ("local_work",),
    enabled: bool = True,
) -> HealthCheckDefinition:
    if purpose is CheckPurpose.LIVENESS:
        capabilities = ()
    return HealthCheckDefinition(
        component_id, check_id, purpose, applicability, MAX_AGE, capabilities, enabled,
    )


def observation(
    check_id: str,
    state: ObservationState = ObservationState.PASS,
    *,
    identity: HealthIdentity = IDENTITY,
    component_id: str = "forge_server",
    purpose: CheckPurpose = CheckPurpose.READINESS,
    capabilities: tuple[str, ...] = ("local_work",),
    observed_at: datetime = NOW,
    expires_at: datetime | None = None,
    reason_code: str | None = None,
) -> HealthObservation:
    if check_id == "process":
        purpose = CheckPurpose.LIVENESS
        capabilities = ()
    if state is not ObservationState.PASS and reason_code is None:
        reason_code = f"{state.value}_OBSERVATION"
    return HealthObservation(
        identity, component_id, check_id, purpose, capabilities,
        state, observed_at, expires_at, reason_code,
    )


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
            (
                observation("process"),
                observation("storage"),
                observation(
                    "execution_peer",
                    component_id="engineering_platform",
                    capabilities=("dispatch",),
                ),
            ),
            capability_scope=FULL_SCOPE,
            evaluated_at=NOW,
        )

        self.assertEqual(result.state, HealthState.HEALTHY)
        self.assertEqual(result.liveness.state, LivenessState.ALIVE)
        self.assertTrue(result.readiness_for("local_work").ready)
        self.assertTrue(result.readiness_for("dispatch").ready)
        self.assertEqual(result.to_dict()["schema_revision"], "1.0")
        self.assertEqual(result.to_dict()["capability_scope"], ["dispatch", "local_work"])

    def test_required_peer_failure_degrades_otherwise_ready_runtime(self) -> None:
        result = evaluate_health(
            IDENTITY,
            (
                liveness(),
                check("storage"),
                check(
                    "execution_peer",
                    component_id="engineering_platform",
                    capabilities=("dispatch",),
                ),
            ),
            (
                observation("process"),
                observation("storage"),
                observation(
                    "execution_peer", ObservationState.FAIL,
                    component_id="engineering_platform", capabilities=("dispatch",),
                    reason_code="PEER_UNREACHABLE",
                ),
            ),
            capability_scope=FULL_SCOPE,
            evaluated_at=NOW,
        )

        self.assertEqual(result.state, HealthState.DEGRADED)
        self.assertEqual(result.liveness.state, LivenessState.ALIVE)
        self.assertEqual(result.readiness_for("local_work").state, ReadinessState.READY)
        self.assertEqual(result.readiness_for("dispatch").state, ReadinessState.UNAVAILABLE)

        local_result = evaluate_health(
            IDENTITY,
            (
                liveness(),
                check("storage"),
                check(
                    "execution_peer",
                    component_id="engineering_platform",
                    capabilities=("dispatch",),
                ),
            ),
            (
                observation("process"),
                observation("storage"),
                observation(
                    "execution_peer", ObservationState.FAIL,
                    component_id="engineering_platform", capabilities=("dispatch",),
                    reason_code="PEER_UNREACHABLE",
                ),
            ),
            capability_scope=LOCAL_SCOPE,
            evaluated_at=NOW,
        )
        self.assertEqual(local_result.state, HealthState.HEALTHY)
        self.assertTrue(local_result.readiness_for("local_work").ready)

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
                    capability_scope=LOCAL_SCOPE,
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
                observation(
                    "relay", ObservationState.FAIL,
                    component_id="dashboard_relay", reason_code="RELAY_UNREACHABLE",
                ),
            ),
            capability_scope=LOCAL_SCOPE,
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
            (
                observation(
                    "relay", ObservationState.FAIL,
                    component_id="dashboard_relay",
                    capabilities=("remote_access",),
                    reason_code="LAST_KNOWN_RELAY_FAILURE",
                ),
            ),
        ):
            with self.subTest(last_known_observation=bool(disabled_observation)):
                result = evaluate_health(
                    IDENTITY,
                    (
                        liveness(),
                        check("storage"),
                        check(
                            "relay", component_id="dashboard_relay",
                            applicability=CheckApplicability.OPTIONAL,
                            capabilities=("remote_access",),
                            enabled=False,
                        ),
                    ),
                    (observation("process"), observation("storage"), *disabled_observation),
                    capability_scope=LOCAL_SCOPE,
                    evaluated_at=NOW,
                )

                relay = next(item for item in result.checks if item.check_id == "relay")
                self.assertEqual(result.state, HealthState.HEALTHY)
                self.assertTrue(result.readiness_for("local_work").ready)
                self.assertFalse(result.readiness_for("local_work").degraded)
                self.assertEqual(
                    result.readiness_for("remote_access").state,
                    ReadinessState.UNKNOWN,
                )
                self.assertEqual(relay.state, CheckState.DISABLED)
                self.assertEqual(relay.freshness, ObservationFreshness.NOT_APPLICABLE)
                self.assertEqual(relay.applicability, CheckApplicability.OPTIONAL)
                self.assertFalse(relay.enabled)

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
            capability_scope=LOCAL_SCOPE,
            evaluated_at=NOW,
        )

        self.assertEqual(result.state, HealthState.UNAVAILABLE)
        readiness = result.readiness_for("local_work")
        self.assertEqual(readiness.state, ReadinessState.UNAVAILABLE)
        self.assertEqual(readiness.blocking_check_ids, ("runtime_dependency", "storage"))

        mixed_capabilities = evaluate_health(
            IDENTITY,
            (
                liveness(),
                check("storage"),
                check(
                    "execution_peer",
                    component_id="engineering_platform",
                    capabilities=("dispatch",),
                ),
            ),
            (
                observation("process"),
                observation("storage", ObservationState.FAIL, reason_code="STORAGE_UNAVAILABLE"),
            ),
            capability_scope=FULL_SCOPE,
            evaluated_at=NOW,
        )
        self.assertEqual(mixed_capabilities.state, HealthState.UNAVAILABLE)

        unknown_liveness = evaluate_health(
            IDENTITY,
            (liveness(), check("storage")),
            (
                observation("storage", ObservationState.FAIL, reason_code="STORAGE_UNAVAILABLE"),
            ),
            capability_scope=LOCAL_SCOPE,
            evaluated_at=NOW,
        )
        self.assertEqual(unknown_liveness.state, HealthState.UNAVAILABLE)

    def test_unknown_optional_observation_degrades_a_ready_capability(self) -> None:
        result = evaluate_health(
            IDENTITY,
            (
                liveness(),
                check("storage"),
                check("metrics", applicability=CheckApplicability.OPTIONAL),
            ),
            (observation("process"), observation("storage")),
            capability_scope=LOCAL_SCOPE,
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
            capability_scope=LOCAL_SCOPE,
            evaluated_at=NOW,
        )

        self.assertEqual(result.liveness.state, LivenessState.NOT_ALIVE)
        self.assertEqual(result.state, HealthState.UNAVAILABLE)
        self.assertEqual(result.readiness_for("local_work").state, ReadinessState.READY)

    def test_evaluation_is_deterministic_and_does_not_mutate_domain_state(self) -> None:
        definitions = (check("storage"), liveness())
        observations = (observation("storage"), observation("process"))
        definitions_before = tuple(definitions)
        observations_before = tuple(observations)

        first = evaluate_health(
            IDENTITY,
            definitions,
            observations,
            capability_scope=LOCAL_SCOPE,
            evaluated_at=NOW,
        )
        second = evaluate_health(
            IDENTITY,
            tuple(reversed(definitions)),
            tuple(reversed(observations)),
            capability_scope=LOCAL_SCOPE,
            evaluated_at=NOW,
        )

        self.assertEqual(first, second)
        self.assertEqual(definitions, definitions_before)
        self.assertEqual(observations, observations_before)
        self.assertEqual(tuple(item.check_id for item in first.checks), ("process", "storage"))
        with self.assertRaises(FrozenInstanceError):
            first.state = HealthState.UNKNOWN  # type: ignore[misc]

    def test_evaluator_has_no_domain_mutation_or_provider_dependency(self) -> None:
        source = Path(health_module.__file__).read_text()
        imported_roots: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

        self.assertEqual(
            imported_roots,
            {"__future__", "dataclasses", "datetime", "enum", "re", "typing"},
        )

    def test_unknown_optional_observation_degrades_without_becoming_required(self) -> None:
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
                observation(
                    "relay", component_id="dashboard_relay",
                    observed_at=NOW + timedelta(seconds=1),
                ),
            ),
            capability_scope=LOCAL_SCOPE,
            evaluated_at=NOW,
        )

        self.assertEqual(result.state, HealthState.DEGRADED)
        self.assertEqual(result.readiness_for("local_work").state, ReadinessState.READY)
        relay = next(item for item in result.checks if item.check_id == "relay")
        self.assertEqual(relay.freshness, ObservationFreshness.FUTURE)

    def test_observations_are_bound_to_runtime_installation_and_check_scope(self) -> None:
        definitions = (liveness(), check("storage"))
        wrong_identities = (
            HealthIdentity("0.7.1", "runtime-primary", "installation-primary"),
            HealthIdentity("0.7.0", "runtime-other", "installation-primary"),
            HealthIdentity("0.7.0", "runtime-primary", "installation-other"),
        )
        for wrong_identity in wrong_identities:
            with self.subTest(identity=wrong_identity):
                with self.assertRaisesRegex(ValueError, "identity"):
                    evaluate_health(
                        IDENTITY,
                        definitions,
                        (observation("process"), observation("storage", identity=wrong_identity)),
                        capability_scope=LOCAL_SCOPE,
                        evaluated_at=NOW,
                    )
        with self.assertRaisesRegex(ValueError, "scope"):
            evaluate_health(
                IDENTITY,
                definitions,
                (
                    observation("process"),
                    observation("storage", capabilities=("dispatch",)),
                ),
                capability_scope=LOCAL_SCOPE,
                evaluated_at=NOW,
            )

    def test_invalid_registry_and_observation_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            evaluate_health(
                IDENTITY,
                (liveness(), check("process")),
                (observation("process"),),
                capability_scope=LOCAL_SCOPE,
                evaluated_at=NOW,
            )
        with self.assertRaisesRegex(ValueError, "declared"):
            evaluate_health(
                IDENTITY,
                (liveness(), check("storage")),
                (observation("process"), observation("undeclared")),
                capability_scope=LOCAL_SCOPE,
                evaluated_at=NOW,
            )

    def test_aggregate_requires_explicit_scope_with_mandatory_readiness(self) -> None:
        with self.assertRaisesRegex(TypeError, "capability_scope"):
            evaluate_health(  # type: ignore[call-arg]
                IDENTITY,
                (liveness(), check("storage")),
                (observation("process"), observation("storage")),
                evaluated_at=NOW,
            )
        for definitions in (
            (liveness(),),
            (
                liveness(),
                check("relay", applicability=CheckApplicability.OPTIONAL),
            ),
            (
                liveness(),
                check(
                    "relay",
                    applicability=CheckApplicability.OPTIONAL,
                    enabled=False,
                ),
            ),
        ):
            with self.subTest(definitions=definitions):
                with self.assertRaisesRegex(ValueError, "enabled required readiness"):
                    evaluate_health(
                        IDENTITY,
                        definitions,
                        (observation("process"),),
                        capability_scope=LOCAL_SCOPE,
                        evaluated_at=NOW,
                    )

    def test_required_readiness_cannot_be_disabled(self) -> None:
        with self.assertRaisesRegex(ValueError, "only optional"):
            check("storage", enabled=False)


if __name__ == "__main__":
    unittest.main()
