"""Installed health qualification: authority, safety, and transport parity."""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
from datetime import UTC, datetime
from io import StringIO
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.request import Request, urlopen

try:
    import fcntl
except ImportError:  # pragma: no cover - production support is macOS/Linux
    fcntl = None  # type: ignore[assignment]

from forge.__main__ import main
from forge.operations_health import InstalledHealthError, InstalledHealthSnapshotService
from forge.operations_read_api import InstalledOperationsReadService, OperationsReadAPI, make_server
from forge.runtime import (
    CANONICAL_COMPONENT_REGISTRY,
    ComponentRegistry,
    HealthIdentity,
    HealthObservation,
    ObservationState,
    RuntimeBootstrap,
    evaluate_health,
)


NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
CREDENTIAL = "synthetic-health-credential"
INSTALLATION_ID = "installation-health-primary"


@contextmanager
def _running_mission_controller(root: Path):
    if fcntl is None:
        raise unittest.SkipTest("foreground controller locking is unavailable")
    lease = root / "forge-mission-controller.lock"
    lease.touch()
    with lease.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class _InstalledHealthFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "forge-server"
        database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        with database._connection:  # noqa: SLF001 - establish the pre-existing installation fixture
            database._set_metadata({"installation_id": INSTALLATION_ID})  # noqa: SLF001
        self.runtime_id = database.metadata["runtime_id"]
        database.close()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def files(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def domain_counts(self) -> dict[str, int]:
        connection = sqlite3.connect(
            (self.root / "forge.db").resolve().as_uri() + "?mode=ro",
            uri=True,
        )
        try:
            tables = (
                "mission_state",
                "execution_receipts",
                "planning_provider_generation_permits",
                "planning_provider_external_session_audit",
            )
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }
        finally:
            connection.close()


class HealthSnapshotTests(_InstalledHealthFixture):
    def test_live_wal_observation_is_current_and_read_only(self) -> None:
        database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        try:
            database._connection.execute("PRAGMA wal_autocheckpoint=0")  # noqa: SLF001
            database._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # noqa: SLF001
            with database._connection:  # noqa: SLF001 - commit a current runtime observation to WAL
                database._set_metadata({"status": "maintenance"})  # noqa: SLF001

            wal = self.root / "forge.db-wal"
            shm = self.root / "forge.db-shm"
            self.assertTrue(wal.is_file())
            self.assertGreater(wal.stat().st_size, 0)
            self.assertTrue(shm.is_file())
            before_domain = self.domain_counts()
            before_files = self.files()

            snapshot = InstalledHealthSnapshotService(
                self.root,
                clock=lambda: NOW,
            ).snapshot().to_dict()

            storage = next(
                item for item in snapshot["checks"] if item["check_id"] == "runtime_storage"
            )
            self.assertEqual(storage["observation_state"], ObservationState.FAIL.value)
            self.assertEqual(storage["reason_code"], "RUNTIME_NOT_ACTIVE")
            self.assertEqual(self.domain_counts(), before_domain)
            self.assertEqual(self.files(), before_files)
        finally:
            database.close()

    def test_authoritative_bounded_snapshot(self) -> None:
        before_domain = self.domain_counts()
        before_files = self.files()

        snapshot = InstalledHealthSnapshotService(
            self.root,
            clock=lambda: NOW,
        ).snapshot().to_dict()

        self.assertEqual(snapshot["schema_revision"], "1.0")
        self.assertEqual(snapshot["component_registry_revision"], "1.0")
        self.assertEqual(snapshot["runtime_id"], self.runtime_id)
        self.assertEqual(snapshot["installation_id"], INSTALLATION_ID)
        self.assertEqual(snapshot["source_observed_at"], NOW.isoformat())
        self.assertTrue(snapshot["read_only"])
        self.assertEqual(snapshot["bounds"]["observation_limit"], 4)
        self.assertEqual(snapshot["bounds"]["integrity_observations"], 1)
        self.assertLessEqual(snapshot["bounds"]["deadline_seconds"], 2.0)
        self.assertEqual(
            set(snapshot["component_ids"]),
            {
                "forge_server", "operations_console", "dashboard_relay", "platform_database",
                "mission_dispatcher", "planning_provider", "codex_runtime", "python_runtime",
                "ep_peer", "http_ingress", "cli_ingress", "operational_logging", "tailscale_access",
            },
        )
        self.assertEqual(tuple(snapshot["component_ids"]), CANONICAL_COMPONENT_REGISTRY.component_ids)
        checks = {item["check_id"]: item for item in snapshot["checks"]}
        self.assertEqual(
            set(checks),
            {"dispatcher_state", "execution_peer_binding", "relay_access", "runtime_storage", "server_process"},
        )
        self.assertEqual(checks["server_process"]["observation_state"], ObservationState.FAIL.value)
        self.assertEqual(checks["server_process"]["reason_code"], "SERVER_PROCESS_NOT_RUNNING")
        self.assertEqual(snapshot["liveness"]["state"], "NOT_ALIVE")
        self.assertEqual(snapshot["availability"], "UNAVAILABLE")
        self.assertEqual(checks["execution_peer_binding"]["observation_state"], ObservationState.FAIL.value)
        self.assertEqual(checks["relay_access"]["state"], "DISABLED")
        self.assertEqual(self.domain_counts(), before_domain)
        self.assertEqual(self.files(), before_files)

        with self.assertRaisesRegex(ValueError, "schema revision"):
            ComponentRegistry("2.0", CANONICAL_COMPONENT_REGISTRY.components)

        identity = HealthIdentity(snapshot["product_version"], self.runtime_id, INSTALLATION_ID)
        definitions = {
            item.check_id: item for item in CANONICAL_COMPONENT_REGISTRY.health_definitions
        }
        for peer_state in ObservationState:
            observations = []
            for check_id in ("server_process", "runtime_storage", "dispatcher_state", "execution_peer_binding"):
                definition = definitions[check_id]
                state = peer_state if check_id == "execution_peer_binding" else ObservationState.PASS
                observations.append(HealthObservation(
                    identity,
                    definition.component_id,
                    definition.check_id,
                    definition.purpose,
                    definition.capabilities,
                    state,
                    NOW,
                    reason_code=None if state is ObservationState.PASS else f"{state.value}_ASSESSMENT",
                ))
            assessed = evaluate_health(
                identity,
                CANONICAL_COMPONENT_REGISTRY.health_definitions,
                observations,
                capability_scope=("dispatch", "local_work"),
                evaluated_at=NOW,
            )
            peer = next(item for item in assessed.checks if item.check_id == "execution_peer_binding")
            self.assertEqual(peer.observation_state, peer_state)

        ticks = iter((0.0, 3.0, 3.0, 3.0))
        with self.assertRaises(InstalledHealthError) as timeout:
            InstalledHealthSnapshotService(
                self.root,
                clock=lambda: NOW,
                monotonic=lambda: next(ticks, 3.0),
            ).snapshot()
        self.assertEqual(timeout.exception.code, "HEALTH_SNAPSHOT_TIMEOUT")
        self.assertEqual(self.files(), before_files)

    def test_current_schema_is_required_without_snapshot_mutation(self) -> None:
        for unsupported in (38, 40):
            with self.subTest(schema=unsupported), TemporaryDirectory() as temporary:
                root = Path(temporary) / "forge-server"
                database = RuntimeBootstrap(data_root=root, forge_version="test").open()
                with database._connection:  # noqa: SLF001 - controlled compatibility fixture
                    database._set_metadata({  # noqa: SLF001
                        "installation_id": INSTALLATION_ID,
                        "schema_version": str(unsupported),
                        "migration_version": str(unsupported),
                    })
                    database._connection.execute(f"PRAGMA user_version={unsupported}")  # noqa: SLF001
                database.close()
                before = {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*") if path.is_file()
                }

                with self.assertRaises(InstalledHealthError) as rejected:
                    InstalledHealthSnapshotService(root, clock=lambda: NOW).snapshot()

                self.assertEqual(rejected.exception.code, "RUNTIME_SCHEMA_UNSUPPORTED")
                self.assertEqual(
                    {
                        path.relative_to(root).as_posix(): path.read_bytes()
                        for path in root.rglob("*") if path.is_file()
                    },
                    before,
                )

    def test_stopped_installation_is_not_reported_alive_by_cli_or_service(self) -> None:
        before_domain = self.domain_counts()
        before_files = self.files()

        api = OperationsReadAPI(
            InstalledOperationsReadService(self.root, clock=lambda: NOW),
            CREDENTIAL,
        )
        response = api.handle("GET", "/v1/health", "Bearer " + CREDENTIAL)
        output = StringIO()
        with redirect_stdout(output):
            cli_status = main(["--data-root", str(self.root), "health"])
        cli_document = json.loads(output.getvalue())

        self.assertEqual(response.status, 503)
        self.assertEqual(response.body["liveness"]["state"], "NOT_ALIVE")
        self.assertEqual(cli_status, 0)
        self.assertEqual(cli_document["liveness"]["state"], "NOT_ALIVE")
        self.assertEqual(cli_document["availability"], "UNAVAILABLE")
        self.assertEqual(self.domain_counts(), before_domain)
        self.assertEqual(self.files(), before_files)

    def test_mission_controller_is_not_reported_as_the_forge_server(self) -> None:
        with _running_mission_controller(self.root):
            before_domain = self.domain_counts()
            before_files = self.files()

            snapshot = InstalledHealthSnapshotService(
                self.root,
                clock=lambda: NOW,
            ).snapshot().to_dict()

            self.assertEqual(snapshot["liveness"]["state"], "NOT_ALIVE")
            self.assertEqual(snapshot["availability"], "UNAVAILABLE")
            self.assertEqual(self.domain_counts(), before_domain)
            self.assertEqual(self.files(), before_files)


class HealthSecurityTests(unittest.TestCase):
    def test_noninteractive_redacted_failure_modes(self) -> None:
        with TemporaryDirectory() as temporary:
            secret = "ghp_synthetic_health_secret"
            root = Path(temporary) / secret
            output = StringIO()
            with redirect_stdout(output):
                status = main(["--data-root", str(root), "health"])
            rendered = output.getvalue()
            self.assertEqual(status, 1)
            self.assertNotIn(secret, rendered)
            self.assertIn("INSTALLED_HEALTH_UNAVAILABLE", rendered)
            self.assertFalse(root.exists())

            api = OperationsReadAPI(InstalledOperationsReadService(root), CREDENTIAL)
            response = api.handle("GET", "/v1/health", "Bearer " + CREDENTIAL)
            self.assertEqual(response.status, 503)
            encoded = json.dumps(response.body, sort_keys=True)
            self.assertNotIn(secret, encoded)
            self.assertNotIn(CREDENTIAL, encoded)
            self.assertEqual(response.body["error"]["code"], "INSTALLED_HEALTH_UNAVAILABLE")
            self.assertFalse(root.exists())

        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "forge-server"
            database = RuntimeBootstrap(data_root=root, forge_version="test").open()
            database.close()
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            output = StringIO()
            with redirect_stdout(output):
                status = main(["--data-root", str(root), "health"])
            self.assertEqual(status, 1)
            self.assertIn("INSTALLATION_IDENTITY_UNAVAILABLE", output.getvalue())
            self.assertEqual(
                {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                },
                before,
            )


class HealthTransportTests(_InstalledHealthFixture):
    def test_installed_http_cli_contract(self) -> None:
        api = OperationsReadAPI(
            InstalledOperationsReadService(self.root, clock=lambda: NOW),
            CREDENTIAL,
        )
        server = make_server("127.0.0.1", 0, api)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            before_domain = self.domain_counts()
            before_files = self.files()
            request = Request(
                f"http://127.0.0.1:{server.server_port}/v1/health",
                headers={"Authorization": "Bearer " + CREDENTIAL},
            )
            with urlopen(request, timeout=2) as response:
                http_status = response.status
                http_document = json.load(response)
            output = StringIO()
            with redirect_stdout(output):
                cli_status = main(["--data-root", str(self.root), "health"])
            cli_document = json.loads(output.getvalue())
            self.assertEqual(self.domain_counts(), before_domain)
            self.assertEqual(self.files(), before_files)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

        self.assertEqual((http_status, cli_status), (200, 0))
        self.assertEqual(http_document["liveness"]["state"], "ALIVE")
        self.assertEqual(cli_document["liveness"]["state"], "ALIVE")
        for field in (
            "api_version",
            "schema_revision",
            "component_registry_revision",
            "product",
            "product_version",
            "runtime_id",
            "installation_id",
            "capability_scope",
            "state",
            "availability",
            "component_ids",
            "read_only",
            "bounds",
        ):
            self.assertEqual(http_document[field], cli_document[field])
        self.assertEqual(
            [(item["check_id"], item["state"]) for item in http_document["checks"]],
            [(item["check_id"], item["state"]) for item in cli_document["checks"]],
        )

        root = Path(__file__).parents[1]
        openapi = json.loads((root / "forge/api/operations-read-openapi-v1.json").read_text(encoding="utf-8"))
        postman = json.loads((root / "forge/api/operations-read-postman-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(
            openapi["paths"]["/v1/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/HealthResponse",
        )
        self.assertTrue(any(item["request"]["url"].endswith("/v1/health") for item in postman["item"]))


if __name__ == "__main__":
    unittest.main()
