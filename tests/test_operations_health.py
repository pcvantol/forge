"""Qualification of the bounded installed-health snapshot and transports."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.request import Request, urlopen

from forge.__main__ import main
from forge.installed_health import (
    HEALTH_PROFILE_REFERENCE,
    InstalledHealthError,
    InstalledHealthRegistry,
    InstalledHealthSnapshotService,
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


class _HealthFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "forge-server"
        self.observed_at = datetime.now(UTC)
        database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        with database._connection:  # noqa: SLF001 - controlled installed fixture
            database._connection.execute(  # noqa: SLF001
                "INSERT INTO runtime_metadata(key,value) VALUES ('installation_id',?)",
                (INSTALLATION_ID,),
            )
            database._connection.execute(  # noqa: SLF001
                "UPDATE runtime_metadata SET value=? WHERE key='last_access_at'",
                (self.observed_at.isoformat(),),
            )
        self.runtime_id = database.runtime_identity.runtime_id
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
        self.assertEqual(snapshot["installation_id"], INSTALLATION_ID)
        self.assertEqual(snapshot["registry"]["profile_reference"], HEALTH_PROFILE_REFERENCE)
        self.assertRegex(snapshot["registry"]["digest"], r"^sha256:[0-9a-f]{64}$")
        provenance = snapshot["observation_provenance"]
        self.assertEqual(provenance["integrity_observation_count"], 1)
        self.assertEqual(provenance["source_snapshot"], "bounded_sidecar_copy")
        self.assertEqual(
            set(provenance["sources"]),
            {"installed_api", "runtime_state", "sqlite_integrity", "dispatcher_state"},
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
        self.assertEqual(snapshot["installation_id"], INSTALLATION_ID)

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
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
