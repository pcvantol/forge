"""Installed-health snapshot qualification at the read-only operations boundary."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from forge.__main__ import main
from forge.health import InstalledHealthError, InstalledHealthSnapshotService
from forge.operator_identity import InstallationOperatorService
from forge.operations_read_api import InstalledOperationsReadService, OperationsReadAPI
from forge.runtime import (
    CheckApplicability,
    CheckPurpose,
    HealthCheckDefinition,
    HealthIdentity,
    HealthObservation,
    ObservationFreshness,
    ObservationState,
    RuntimeBootstrap,
    evaluate_health,
)


NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
CREDENTIAL = "synthetic-installed-health-credential"


class _HealthFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "forge-server"
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        with self.database._connection:  # noqa: SLF001 - controlled installed fixture
            self.database._set_metadata({"installation_id": "installation-primary"})  # noqa: SLF001
        self.installation_id = self.database.metadata["installation_id"]

    def tearDown(self) -> None:
        self.database.close()
        self.temporary.cleanup()

    def _state(self) -> dict[str, object]:
        tables = (
            "planning_provider_security_config",
            "planning_provider_external_session_config",
            "mission_state",
            "execution_receipts",
            "scheduler_submissions",
        )
        rows = {
            table: tuple(tuple(row) for row in self.database._connection.execute(  # noqa: SLF001
                f"SELECT * FROM {table} ORDER BY 1"
            ))
            for table in tables
        }
        files = {
            path.name: (path.stat().st_size, sha256(path.read_bytes()).hexdigest())
            for path in (self.root / "forge.db", self.root / "forge.db-wal", self.root / "forge.db-shm")
            if path.exists()
        }
        return {"rows": rows, "files": files}


class HealthSnapshotTests(_HealthFixture):
    def test_authoritative_bounded_snapshot(self) -> None:
        before = self._state()
        statements: list[str] = []
        original_connect = __import__("sqlite3").connect

        def observed_connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        with patch("forge.health.sqlite3.connect", side_effect=observed_connect):
            snapshot = InstalledHealthSnapshotService(self.root, clock=lambda: NOW).snapshot()

        self.assertEqual(snapshot["schema_version"], "1.0")
        self.assertEqual(snapshot["assessment"], "installed_health_snapshot")
        self.assertEqual(snapshot["profile"], "FULL@1.0")
        self.assertEqual(snapshot["evaluation"]["state"], "HEALTHY")
        self.assertEqual(snapshot["identity"]["installation_id"], self.installation_id)
        self.assertEqual(
            InstallationOperatorService(self.database, lambda: None).installation_id(),
            self.installation_id,
        )
        self.assertEqual(snapshot["identity"]["runtime_id"], self.database.runtime_identity.runtime_id)
        self.assertEqual(snapshot["registry"]["schema_version"], "1.0")
        self.assertEqual(
            {item["component_id"] for item in snapshot["registry"]["components"]},
            {
                "forge_server", "operations_console", "dashboard_relay", "platform_database",
                "mission_dispatcher", "planning_provider", "codex_runtime", "python_runtime",
                "ep_peer", "http_ingress", "cli_ingress", "operational_logging", "tailscale_access",
            },
        )
        self.assertEqual(snapshot["observation_policy"], {
            "integrity_observations": 1,
            "provider_invocations": 0,
            "peer_invocations": 0,
            "mutations": 0,
        })
        self.assertEqual(
            sum("integrity_check" in statement.lower() for statement in statements), 1,
        )
        self.assertEqual(self._state(), before)

    def test_missing_installation_identity_is_not_fabricated(self) -> None:
        with self.database._connection:  # noqa: SLF001 - controlled invalid fixture
            self.database._connection.execute(  # noqa: SLF001
                "DELETE FROM runtime_metadata WHERE key='installation_id'"
            )
        with self.assertRaises(InstalledHealthError) as rejected:
            InstalledHealthSnapshotService(self.root, clock=lambda: NOW).snapshot()
        self.assertEqual(rejected.exception.code, "INSTALLATION_IDENTITY_INVALID")

    def test_integrity_observation_has_enforceable_deadline(self) -> None:
        statements: list[str] = []
        original_connect = __import__("sqlite3").connect

        def observed_connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        monotonic_calls = 0

        def expired_clock() -> float:
            nonlocal monotonic_calls
            monotonic_calls += 1
            return 100.0 if monotonic_calls == 1 else 102.0

        service = InstalledHealthSnapshotService(
            self.root, clock=lambda: NOW, monotonic_clock=expired_clock,
        )
        with patch("forge.health.sqlite3.connect", side_effect=observed_connect):
            with self.assertRaises(InstalledHealthError) as rejected:
                service.snapshot()
        self.assertEqual(rejected.exception.code, "HEALTH_OBSERVATION_TIMED_OUT")
        self.assertLessEqual(
            sum("integrity_check" in statement.lower() for statement in statements), 1,
        )
        for invalid in (0, -1, 1.1, float("inf"), float("nan"), True):
            with self.subTest(maximum_seconds=invalid):
                with self.assertRaises(ValueError):
                    InstalledHealthSnapshotService(self.root, maximum_seconds=invalid)

    def test_failed_dispatcher_and_newer_schema_fail_closed(self) -> None:
        with self.database._connection:  # noqa: SLF001 - controlled invalid fixture
            self.database._connection.execute(  # noqa: SLF001
                "INSERT INTO dispatcher_state VALUES (1, 'INVALID', NULL, '[]', '{}')"
            )
        snapshot = InstalledHealthSnapshotService(self.root, clock=lambda: NOW).snapshot()
        self.assertEqual(snapshot["evaluation"]["state"], "UNAVAILABLE")
        dispatcher = next(
            item for item in snapshot["evaluation"]["checks"] if item["check_id"] == "dispatcher_state"
        )
        self.assertEqual((dispatcher["state"], dispatcher["reason_code"]), (
            "FAIL", "DISPATCHER_STATE_INVALID",
        ))

        with self.database._connection:  # noqa: SLF001 - future-schema fixture
            self.database._set_metadata({  # noqa: SLF001
                "schema_version": "40", "migration_version": "40",
            })
            self.database._connection.execute("PRAGMA user_version=40")  # noqa: SLF001
        with self.assertRaisesRegex(InstalledHealthError, "newer than this Forge version") as rejected:
            InstalledHealthSnapshotService(self.root, clock=lambda: NOW).snapshot()
        self.assertEqual(rejected.exception.code, "STORAGE_SCHEMA_NEWER")


class HealthObservationTests(unittest.TestCase):
    def test_healthy_failed_stale_expired_missing_timed_out_future_and_unknown(self) -> None:
        identity = HealthIdentity("1.0.0", "runtime-primary", "installation-primary")
        definitions = (
            HealthCheckDefinition(
                "forge_server", "reader", CheckPurpose.LIVENESS,
                CheckApplicability.REQUIRED, timedelta(seconds=30),
            ),
            HealthCheckDefinition(
                "platform_database", "storage", CheckPurpose.READINESS,
                CheckApplicability.REQUIRED, timedelta(seconds=30), ("snapshot",),
            ),
        )

        def observation(
            state: ObservationState = ObservationState.PASS,
            *, observed_at: datetime = NOW, expires_at: datetime | None = None,
        ) -> HealthObservation:
            return HealthObservation(
                identity, "platform_database", "storage", CheckPurpose.READINESS,
                ("snapshot",), state, observed_at, expires_at,
                None if state is ObservationState.PASS else "OBSERVATION_FAILED",
            )

        reader = HealthObservation(
            identity, "forge_server", "reader", CheckPurpose.LIVENESS,
            (), ObservationState.PASS, NOW,
        )
        cases = {
            "healthy": (observation(), "FRESH", "PASS"),
            "failed": (observation(ObservationState.FAIL), "FRESH", "FAIL"),
            "stale": (observation(observed_at=NOW - timedelta(seconds=30)), "STALE", "UNKNOWN"),
            "expired": (
                observation(observed_at=NOW - timedelta(seconds=2), expires_at=NOW),
                "EXPIRED", "UNKNOWN",
            ),
            "missing": (None, "MISSING", "UNKNOWN"),
            "timed_out": (observation(ObservationState.TIMED_OUT), "TIMED_OUT", "UNKNOWN"),
            "future": (observation(observed_at=NOW + timedelta(seconds=1)), "FUTURE", "UNKNOWN"),
            "unknown": (observation(ObservationState.UNKNOWN), "FRESH", "UNKNOWN"),
        }
        for name, (storage, freshness, state) in cases.items():
            with self.subTest(name=name):
                evaluated = evaluate_health(
                    identity, definitions, (reader,) if storage is None else (reader, storage),
                    capability_scope=("snapshot",), evaluated_at=NOW,
                )
                check = next(item for item in evaluated.checks if item.check_id == "storage")
                self.assertEqual(check.freshness, ObservationFreshness(freshness))
                self.assertEqual(check.state.value, state)


class HealthSecurityTests(_HealthFixture):
    def test_noninteractive_redacted_failure_modes(self) -> None:
        secret = "ghp_" + "syntheticvalue"
        absent = Path(self.temporary.name) / secret
        with patch("builtins.input", side_effect=AssertionError("interactive input forbidden")):
            with self.assertRaises(InstalledHealthError) as missing:
                InstalledHealthSnapshotService(absent, clock=lambda: NOW).snapshot()
        self.assertEqual(missing.exception.code, "INSTALLATION_MISSING")
        self.assertNotIn(secret, str(missing.exception))
        self.assertFalse(absent.exists())

        marker = self.root / "instance" / "runtime-instance.json"
        marker.write_text(secret + "\n", encoding="utf-8")
        api = OperationsReadAPI(InstalledOperationsReadService(self.root, clock=lambda: NOW), CREDENTIAL)
        response = api.handle("GET", "/v1/health", "Bearer " + CREDENTIAL)
        rendered = json.dumps(response.body, sort_keys=True)
        self.assertEqual(response.status, 503)
        self.assertEqual(response.body["error"]["code"], "INSTALLATION_IDENTITY_MISMATCH")
        self.assertNotIn(secret, rendered)
        self.assertNotIn(str(self.root), rendered)


class HealthTransportTests(_HealthFixture):
    def test_installed_http_cli_contract(self) -> None:
        api = OperationsReadAPI(
            InstalledOperationsReadService(self.root, clock=lambda: NOW), CREDENTIAL,
        )
        denied = api.handle("GET", "/v1/health", None)
        accepted = api.handle("GET", "/v1/health", "Bearer " + CREDENTIAL)
        self.assertEqual((denied.status, accepted.status), (401, 200))
        self.assertEqual(accepted.body["assessment"], "installed_health_snapshot")
        self.assertTrue(accepted.body["read_only"])

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["--data-root", str(self.root), "health"])
        cli = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(cli["schema_version"], accepted.body["schema_version"])
        self.assertEqual(cli["registry"]["digest"], accepted.body["registry"]["digest"])
        self.assertEqual(cli["identity"]["installation_id"], self.installation_id)

        server_output = StringIO()
        with redirect_stdout(server_output):
            server_exit = main(["--data-root", str(self.root), "server", "health"])
        self.assertEqual(server_exit, 0)
        self.assertEqual(json.loads(server_output.getvalue())["registry"]["digest"], cli["registry"]["digest"])
