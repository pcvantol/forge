"""Qualification of the bounded installed-health snapshot and transports."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
import json
import os
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic
import unittest
from urllib.request import Request, urlopen

from forge.__main__ import main
from forge.installed_health import (
    HEALTH_PROFILE_REFERENCE,
    InstalledHealthError,
    InstalledHealthRegistry,
    InstalledHealthSnapshotService,
    _bounded_copy,
    _outcome,
)
from forge.operations_read_api import InstalledOperationsReadService, OperationsReadAPI, make_server
from forge.runtime import RuntimeBootstrap
from forge.runtime.health import (
    CheckPurpose,
    HealthIdentity,
    HealthObservation,
    ObservationState,
    evaluate_health,
)


CREDENTIAL = "synthetic-health-credential"
INSTALLATION_ID = "99ede979-e8b8-48ca-9174-3257778c680f"
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)


def _assert_contract_schema(testcase: unittest.TestCase, value: object, schema: dict[str, object]) -> None:
    if "const" in schema:
        testcase.assertEqual(value, schema["const"])
    if "enum" in schema:
        testcase.assertIn(value, schema["enum"])
    kind = schema.get("type")
    kinds = (kind,) if isinstance(kind, str) else tuple(kind or ())
    if kinds:
        matches = {
            "array": lambda item: isinstance(item, list),
            "boolean": lambda item: isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "null": lambda item: item is None,
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "object": lambda item: isinstance(item, dict),
            "string": lambda item: isinstance(item, str),
        }
        testcase.assertTrue(any(matches[name](value) for name in kinds))
    if value is None:
        return
    if kind == "object":
        properties = schema["properties"]
        required = schema["required"]
        testcase.assertFalse(schema["additionalProperties"])
        testcase.assertEqual(set(value), set(required))
        testcase.assertEqual(set(required), set(properties))
        for key, child_schema in properties.items():
            _assert_contract_schema(testcase, value[key], child_schema)
    elif kind == "array":
        testcase.assertGreaterEqual(len(value), schema.get("minItems", 0))
        if schema.get("uniqueItems"):
            testcase.assertEqual(
                len(value), len({json.dumps(item, sort_keys=True) for item in value}),
            )
        for item in value:
            _assert_contract_schema(testcase, item, schema["items"])
    elif isinstance(value, str):
        testcase.assertGreaterEqual(len(value), schema.get("minLength", 0))
        if "pattern" in schema:
            testcase.assertIsNotNone(re.fullmatch(schema["pattern"], value))
        if schema.get("format") == "date-time":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            testcase.assertIsNotNone(parsed.utcoffset())
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema:
            testcase.assertGreaterEqual(value, schema["minimum"])
        if "maximum" in schema:
            testcase.assertLessEqual(value, schema["maximum"])
        if "exclusiveMinimum" in schema:
            testcase.assertGreater(value, schema["exclusiveMinimum"])


class _HealthFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "forge-server"
        self.observed_at = datetime.now(UTC)
        database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        with database._connection:  # noqa: SLF001 - controlled installed fixture
            database._connection.execute(  # noqa: SLF001
                "UPDATE runtime_metadata SET value=? WHERE key='last_access_at'",
                (self.observed_at.isoformat(),),
            )
            database._connection.execute(  # noqa: SLF001
                "INSERT INTO dispatcher_state VALUES (1, 'IDLE', NULL, '[]', '{}')"
            )
        self.runtime_id = database.runtime_identity.runtime_id
        self.installation_id = database.metadata["installation_id"]
        database.close()

    def files(self) -> dict[Path, bytes]:
        return {
            path.relative_to(self.root): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }


class HealthSnapshotTests(_HealthFixture):
    def test_authoritative_bounded_snapshot(self) -> None:
        statements: list[str] = []
        active = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.addCleanup(active.close)
        before = self.files()

        snapshot = InstalledHealthSnapshotService(
            self.root, statement_observer=statements.append,
        ).installed_health_snapshot()

        self.assertEqual(snapshot["outcome"], "HEALTHY")
        self.assertEqual(snapshot["runtime_id"], self.runtime_id)
        self.assertEqual(snapshot["installation_id"], self.installation_id)
        self.assertEqual(snapshot["registry"]["profile_reference"], HEALTH_PROFILE_REFERENCE)
        self.assertRegex(snapshot["registry"]["digest"], r"^sha256:[0-9a-f]{64}$")
        provenance = snapshot["observation_provenance"]
        self.assertEqual(provenance["integrity_observation_count"], 1)
        self.assertEqual(provenance["timeout_seconds"], 2.0)
        self.assertEqual(provenance["registry_byte_limit"], 64 * 1024)
        self.assertEqual(provenance["snapshot_byte_limit"], 128 * 1024 * 1024)
        self.assertEqual(provenance["runtime_marker_byte_limit"], 1024)
        self.assertEqual(provenance["source_snapshot"], "bounded_sidecar_copy")
        self.assertEqual(
            set(provenance["sources"]),
            {
                "installed_api", "runtime_state", "operational_reset_maintenance",
                "sqlite_integrity", "dispatcher_state",
            },
        )
        normalized = tuple(statement.upper() for statement in statements)
        self.assertEqual(sum("PRAGMA INTEGRITY_CHECK" in item for item in normalized), 1)
        self.assertFalse(any(
            token in item for item in normalized
            for token in ("INSERT ", "UPDATE ", "DELETE ", "MISSION_STATE", "EXECUTION_RECEIPTS")
        ))
        self.assertEqual(self.files(), before)

    def test_registry_provenance_forward_schema_and_installation_identity(self) -> None:
        registry_document = json.loads(
            (Path(__file__).parents[1] / "forge" / "api" / "installed-health-component-registry-1.0.json")
            .read_text(encoding="utf-8")
        )
        registry_document["schema_version"] = "2.0"
        with self.assertRaisesRegex(InstalledHealthError, "schema is unsupported"):
            InstalledHealthRegistry.load(registry_document)

        snapshot = InstalledHealthSnapshotService(
            self.root, clock=lambda: self.observed_at,
        ).installed_health_snapshot()
        self.assertEqual(snapshot["installation_id"], self.installation_id)

        second_root = Path(self.temporary.name) / "second-forge-server"
        second = RuntimeBootstrap(data_root=second_root, forge_version="test").open()
        try:
            self.assertNotEqual(second.metadata["installation_id"], self.installation_id)
        finally:
            second.close()

        connection = sqlite3.connect(self.root / "forge.db")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE runtime_metadata SET value='forged-installation' WHERE key='installation_id'"
            )
        connection.rollback()
        with connection:
            connection.execute("DROP TRIGGER runtime_identity_immutable")
            connection.execute("DROP TRIGGER runtime_identity_immutable_delete")
            connection.execute(
                "INSERT INTO installation_operator_binding VALUES (?,?,?,?,?,?)",
                ("different-installation", "operator", 1, 1, "ACTIVE", self.observed_at.isoformat()),
            )
        connection.close()
        with self.assertRaises(InstalledHealthError) as inconsistent:
            InstalledHealthSnapshotService(self.root).installed_health_snapshot()
        self.assertEqual(inconsistent.exception.code, "HEALTH_IDENTITY_INCONSISTENT")

    def test_existing_operator_binding_restores_and_protects_installation_identity(self) -> None:
        connection = sqlite3.connect(self.root / "forge.db")
        with connection:
            connection.execute("DROP TRIGGER runtime_identity_immutable")
            connection.execute("DROP TRIGGER runtime_identity_immutable_delete")
            connection.execute(
                "CREATE TRIGGER runtime_identity_immutable BEFORE UPDATE ON runtime_metadata "
                "WHEN OLD.key IN ('runtime_id', 'repository_identity', 'repository_root', 'created_at') "
                "AND NEW.value <> OLD.value "
                "BEGIN SELECT RAISE(ABORT, 'runtime identity is immutable'); END"
            )
            connection.execute(
                "INSERT INTO installation_operator_binding VALUES (?,?,?,?,?,?)",
                (self.installation_id, "operator", 1, 1, "ACTIVE", self.observed_at.isoformat()),
            )
            connection.execute("DELETE FROM runtime_metadata WHERE key='installation_id'")
        connection.close()

        reopened = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        try:
            self.assertEqual(reopened.metadata["installation_id"], self.installation_id)
            with self.assertRaises(sqlite3.IntegrityError):
                reopened._connection.execute(  # noqa: SLF001 - controlled persistence assertion
                    "UPDATE runtime_metadata SET value='forged-installation' WHERE key='installation_id'"
                )
            reopened._connection.rollback()  # noqa: SLF001 - controlled persistence assertion
            with self.assertRaises(sqlite3.IntegrityError):
                reopened._connection.execute(  # noqa: SLF001 - controlled persistence assertion
                    "DELETE FROM runtime_metadata WHERE key='installation_id'"
                )
            reopened._connection.rollback()  # noqa: SLF001 - controlled persistence assertion
            with self.assertRaises(sqlite3.IntegrityError):
                reopened._connection.execute(  # noqa: SLF001 - controlled persistence assertion
                    "INSERT OR REPLACE INTO runtime_metadata(key, value) "
                    "VALUES ('installation_id', 'forged-installation')"
                )
        finally:
            reopened.close()

    def test_timeout_and_file_limits_cover_pre_database_reads_and_copy_chunks(self) -> None:
        started = monotonic()
        marker = self.root / "instance" / "runtime-instance.json"
        saved_marker = marker.with_suffix(".saved")
        marker.rename(saved_marker)
        os.mkfifo(marker)
        try:
            with self.assertRaises(InstalledHealthError) as timed_out:
                InstalledHealthSnapshotService(
                    self.root,
                    timeout_seconds=0.25,
                    integrity_timeout_seconds=0.05,
                ).installed_health_snapshot()
        finally:
            marker.unlink()
            saved_marker.rename(marker)
        self.assertEqual(timed_out.exception.code, "HEALTH_SNAPSHOT_TIMED_OUT")
        self.assertLess(monotonic() - started, 1.5)

        marker.write_bytes(b"x" * 1025)
        with self.assertRaises(InstalledHealthError) as marker_limit:
            InstalledHealthSnapshotService(self.root).installed_health_snapshot()
        self.assertEqual(marker_limit.exception.code, "HEALTH_IDENTITY_LIMIT")

        source = Path(self.temporary.name) / "bounded-copy-source"
        target = Path(self.temporary.name) / "bounded-copy-target"
        source.write_bytes(b"must-not-be-copied")
        with self.assertRaises(InstalledHealthError) as copy_timeout:
            _bounded_copy(source, target, 1.0, iter((0.0, 2.0)).__next__)
        self.assertEqual(copy_timeout.exception.code, "HEALTH_SNAPSHOT_TIMED_OUT")
        self.assertEqual(target.read_bytes(), b"")

    def test_operational_reset_maintenance_blocks_readiness_without_snapshot_mutation(self) -> None:
        connection = sqlite3.connect(self.root / "forge.db")
        connection.create_function("forge_maintenance_write_permitted", 0, lambda: 1)
        with connection:
            connection.execute(
                "UPDATE operational_reset_state "
                "SET active_operation_id='forge-reset-health-test',state='PREPARED',updated_at=? "
                "WHERE singleton=1",
                (self.observed_at.isoformat(),),
            )
        connection.close()
        before = self.files()

        snapshot = InstalledHealthSnapshotService(
            self.root, clock=lambda: self.observed_at,
        ).installed_health_snapshot()

        self.assertEqual(snapshot["outcome"], "FAILED")
        self.assertTrue(snapshot["liveness"]["alive"])
        self.assertFalse(snapshot["capabilities"][0]["ready"])
        maintenance = next(
            item for item in snapshot["checks"]
            if item["check_id"] == "operational_reset_maintenance"
        )
        self.assertEqual(maintenance["state"], "FAIL")
        self.assertEqual(maintenance["reason_code"], "OPERATIONAL_RESET_MAINTENANCE_ACTIVE")
        self.assertEqual(self.files(), before)

        api = OperationsReadAPI(InstalledOperationsReadService(self.root), CREDENTIAL)
        response = api.handle("GET", "/v1/health", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 503)
        output = StringIO()
        with redirect_stdout(output):
            result = main(["--data-root", str(self.root), "health", "snapshot"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "FAILED")

    def test_forward_runtime_schema_is_rejected(self) -> None:
        import sqlite3
        from forge.runtime.database import RUNTIME_SCHEMA_VERSION

        connection = sqlite3.connect(self.root / "forge.db")
        with connection:
            connection.execute(
                "UPDATE runtime_metadata SET value=? WHERE key IN ('schema_version','migration_version')",
                (str(RUNTIME_SCHEMA_VERSION + 1),),
            )
            connection.execute(f"PRAGMA user_version={RUNTIME_SCHEMA_VERSION + 1}")
        connection.close()

        with self.assertRaises(InstalledHealthError) as raised:
            InstalledHealthSnapshotService(self.root, clock=lambda: NOW).installed_health_snapshot()
        self.assertEqual(raised.exception.code, "HEALTH_SCHEMA_FORWARD")

    def test_distinct_health_outcomes(self) -> None:
        registry = InstalledHealthRegistry.load()
        identity = HealthIdentity("2.7.25", "forge-runtime-test", INSTALLATION_ID)
        definitions = registry.definitions

        def outcome(state: ObservationState | None, *, observed_at: datetime = NOW,
                    expires_at: datetime | None = None) -> str:
            observations = [
                HealthObservation(identity, "forge_server", "installed_api", CheckPurpose.LIVENESS,
                                  (), ObservationState.PASS, NOW),
                HealthObservation(identity, "forge_storage", "sqlite_integrity", CheckPurpose.READINESS,
                                  ("installed_health",), ObservationState.PASS, NOW),
                HealthObservation(identity, "forge_runtime", "operational_reset_maintenance",
                                  CheckPurpose.READINESS, ("installed_health",),
                                  ObservationState.PASS, NOW),
                HealthObservation(identity, "forge_dispatcher", "dispatcher_state", CheckPurpose.READINESS,
                                  ("installed_health",), ObservationState.PASS, NOW),
            ]
            if state is not None:
                observations.append(HealthObservation(
                    identity, "forge_runtime", "runtime_state", CheckPurpose.READINESS,
                    ("installed_health",), state, observed_at, expires_at,
                    None if state is ObservationState.PASS else "RUNTIME_OBSERVATION_NONPASSING",
                ))
            evaluation = evaluate_health(
                identity, definitions, observations,
                capability_scope=("installed_health",), evaluated_at=NOW,
            )
            return _outcome(evaluation.checks)

        cases = {
            "HEALTHY": outcome(ObservationState.PASS),
            "FAILED": outcome(ObservationState.FAIL),
            "STALE": outcome(ObservationState.PASS, observed_at=NOW - timedelta(seconds=300)),
            "EXPIRED": outcome(
                ObservationState.PASS,
                observed_at=NOW - timedelta(seconds=2),
                expires_at=NOW - timedelta(seconds=1),
            ),
            "MISSING": outcome(None),
            "TIMED_OUT": outcome(ObservationState.TIMED_OUT),
            "FUTURE": outcome(ObservationState.PASS, observed_at=NOW + timedelta(seconds=1)),
            "UNKNOWN": outcome(ObservationState.UNKNOWN),
        }
        self.assertEqual(cases, {name: name for name in cases})

    def test_collector_reaches_every_advertised_outcome(self) -> None:
        cases = {
            "HEALTHY": (NOW, "active", "IDLE", 0.25),
            "FAILED": (NOW, "inactive", "IDLE", 0.25),
            "STALE": (NOW - timedelta(seconds=301), "active", "IDLE", 0.25),
            "EXPIRED": (NOW - timedelta(seconds=601), "active", "IDLE", 0.25),
            "MISSING": (NOW, "active", None, 0.25),
            "TIMED_OUT": (NOW, "active", "IDLE", 1e-9),
            "FUTURE": (NOW + timedelta(seconds=1), "active", "IDLE", 0.25),
            "UNKNOWN": (NOW, "active", "UNRECOGNIZED", 0.25),
        }
        for expected, (observed_at, runtime_status, dispatcher_status, integrity_timeout) in cases.items():
            with self.subTest(expected=expected):
                connection = sqlite3.connect(self.root / "forge.db")
                with connection:
                    connection.execute(
                        "UPDATE runtime_metadata SET value=? WHERE key='last_access_at'",
                        (observed_at.isoformat(),),
                    )
                    connection.execute(
                        "UPDATE runtime_metadata SET value=? WHERE key='status'",
                        (runtime_status,),
                    )
                    connection.execute("DELETE FROM dispatcher_state WHERE singleton=1")
                    if dispatcher_status is not None:
                        connection.execute(
                            "INSERT INTO dispatcher_state VALUES (1, ?, NULL, '[]', '{}')",
                            (dispatcher_status,),
                        )
                connection.close()

                snapshot = InstalledHealthSnapshotService(
                    self.root,
                    clock=lambda: NOW,
                    integrity_timeout_seconds=integrity_timeout,
                ).installed_health_snapshot()
                self.assertEqual(snapshot["outcome"], expected)
                if expected == "MISSING":
                    dispatcher = next(
                        item for item in snapshot["checks"]
                        if item["check_id"] == "dispatcher_state"
                    )
                    self.assertEqual(dispatcher["freshness"], "MISSING")


class HealthSecurityTests(_HealthFixture):
    def test_noninteractive_redacted_failure_modes(self) -> None:
        secret = "ghp_" + "synthetic-health-secret"
        missing_root = Path(self.temporary.name) / secret
        output = StringIO()
        with redirect_stdout(output):
            result = main(["--data-root", str(missing_root), "health", "snapshot"])
        self.assertEqual(result, 1)
        self.assertNotIn(secret, output.getvalue())
        self.assertIn("HEALTH_RUNTIME_MISSING", output.getvalue())
        self.assertFalse(missing_root.exists())

        api = OperationsReadAPI(InstalledOperationsReadService(missing_root), CREDENTIAL)
        response = api.handle("GET", "/v1/health", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 503)
        rendered = json.dumps(response.body, sort_keys=True)
        self.assertNotIn(secret, rendered)
        self.assertNotIn(CREDENTIAL, rendered)
        self.assertFalse(missing_root.exists())


class HealthTransportTests(_HealthFixture):
    def test_installed_http_cli_contract(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            result = main(["--data-root", str(self.root), "health", "snapshot"])
        self.assertEqual(result, 0)
        cli = json.loads(output.getvalue())
        self.assertEqual(cli["outcome"], "HEALTHY")
        self.assertEqual(cli["registry"]["profile_reference"], HEALTH_PROFILE_REFERENCE)

        api = OperationsReadAPI(InstalledOperationsReadService(self.root), CREDENTIAL)
        server = make_server("127.0.0.1", 0, api)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/v1/health",
                headers={"Authorization": "Bearer " + CREDENTIAL},
            )
            with urlopen(request, timeout=2) as response:
                http = json.load(response)
            self.assertEqual(http["outcome"], cli["outcome"])
            self.assertEqual(http["runtime_id"], cli["runtime_id"])
            self.assertEqual(http["installation_id"], cli["installation_id"])
            self.assertEqual(http["registry"], cli["registry"])
            self.assertEqual(http["observation_provenance"], cli["observation_provenance"])
            schema = json.loads(
                (Path(__file__).parents[1] / "forge" / "api" / "operations-read-openapi-v1.json")
                .read_text(encoding="utf-8")
            )["components"]["schemas"]["HealthResponse"]
            _assert_contract_schema(self, http, schema)

            invalid = json.loads(json.dumps(http))
            invalid["outcome"] = "NOT_AN_OUTCOME"
            with self.assertRaises(AssertionError):
                _assert_contract_schema(self, invalid, schema)
            invalid = json.loads(json.dumps(http))
            invalid["evaluated_at"] = "not-a-date"
            with self.assertRaises((AssertionError, ValueError)):
                _assert_contract_schema(self, invalid, schema)
            invalid = json.loads(json.dumps(http))
            invalid["observation_provenance"]["bounded"] = False
            with self.assertRaises(AssertionError):
                _assert_contract_schema(self, invalid, schema)
            invalid = json.loads(json.dumps(http))
            invalid["unexpected"] = True
            with self.assertRaises(AssertionError):
                _assert_contract_schema(self, invalid, schema)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
