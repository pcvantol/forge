"""Aggregate-health composition and installed-service qualification."""
from __future__ import annotations

from base64 import urlsafe_b64encode
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import venv
import zipfile

from forge.__main__ import main
from forge.component_registry import COMPONENT_REGISTRY_VERSION, component_registry
from forge.execution_host_configuration import (
    EngineeringPlatformExecutionHostFactory,
    EngineeringPlatformPeerConfigurationStore,
)
from forge.operations_read_api import InstalledOperationsReadService, OperationsReadAPI, make_server
from forge.runtime import (
    CheckPurpose,
    HealthObservation,
    ObservationState,
    RUNTIME_SCHEMA_VERSION,
    RuntimeBootstrap,
    installed_health_registry,
)
from forge.secure_store import SecretReference


NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
CREDENTIAL = "synthetic-health-credential"


def _write_candidate_wheel(repository: Path, destination: Path) -> tuple[Path, str]:
    """Create one valid wheel from the checked-out candidate using only stdlib.

    The production workflow separately qualifies the normal build backend. This
    helper keeps the repository suite offline while still crossing a real wheel
    installation and generated console-script boundary.
    """
    version = json.loads(
        (repository / "product-version.json").read_text(encoding="utf-8"),
    )["version"]
    distribution = "forge_autonomy"
    wheel = destination / f"{distribution}-{version}-py3-none-any.whl"
    dist_info = f"{distribution}-{version}.dist-info"
    entries = {
        path.relative_to(repository).as_posix(): path.read_bytes()
        for path in sorted((repository / "forge").rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    entries.update({
        f"{dist_info}/METADATA": (
            "Metadata-Version: 2.4\n"
            "Name: forge-autonomy\n"
            f"Version: {version}\n"
            "Requires-Python: >=3.11\n"
        ).encode(),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: forge-installed-health-qualification\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n"
        ).encode(),
        f"{dist_info}/entry_points.txt": b"[console_scripts]\nforge = forge.__main__:main\n",
    })
    records = []
    for name, content in sorted(entries.items()):
        digest = urlsafe_b64encode(sha256(content).digest()).rstrip(b"=").decode()
        records.append(f"{name},sha256={digest},{len(content)}")
    record_name = f"{dist_info}/RECORD"
    entries[record_name] = ("\n".join(records) + f"\n{record_name},,\n").encode()
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            archive.writestr(name, content)
    return wheel, version


def _logical_runtime_snapshot(root: Path) -> dict[str, object]:
    """Hash domain state, including transactions that still reside in WAL."""
    database = root / "forge.db"
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        logical_database = "\n".join(connection.iterdump()).encode()
    finally:
        connection.close()
    files = {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in {"forge.db", "forge.db-wal", "forge.db-shm"}
    }
    return {"database": sha256(logical_database).hexdigest(), "files": files}


class _InstalledHealthFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "forge-server"
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self._metadata(status="active", last_access_at=NOW.isoformat())
        self.service = InstalledOperationsReadService(self.root, clock=lambda: NOW)
        self.api = OperationsReadAPI(self.service, CREDENTIAL)

    def tearDown(self) -> None:
        self.database.close()
        self.temporary.cleanup()

    def _metadata(self, **values: str | None) -> None:
        with self.database._connection:  # noqa: SLF001 - controlled installed fixture
            for key, value in values.items():
                if value is None:
                    self.database._connection.execute(  # noqa: SLF001
                        "DELETE FROM runtime_metadata WHERE key = ?", (key,),
                    )
                else:
                    self.database._connection.execute(  # noqa: SLF001
                        "INSERT INTO runtime_metadata(key,value) VALUES (?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value),
                    )

    def snapshot(self) -> dict[Path, bytes]:
        return {
            path.relative_to(self.root): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file() and not path.name.endswith(("-shm", "-wal"))
        }

    def configure_peer(self) -> None:
        EngineeringPlatformPeerConfigurationStore(
            self.database._connection, self.database.runtime_identity.runtime_id, writable=True,
        ).configure(
            binding_id="ep-primary",
            endpoint="https://ep.test",
            expected_ep_instance_id="ep-instance-1",
            ep_consumer_id="forge-consumer-1",
            execution_host_id="engineering-platform",
            ep_project_id="forge-project",
            ep_repository_id="forge-repository",
            repository_identity="forge-source",
            credential_reference=SecretReference.parse("keychain://forge.ep/consumer"),
            operator_id="local-admin",
            occurred_at="2026-09-21T09:00:00Z",
        )

    @staticmethod
    def peer_observer(state: ObservationState, *, observed_at: datetime = NOW):
        def observe(identity, _configuration, _requested_at, _timeout):
            return HealthObservation(
                identity,
                "ep_peer",
                "execution_peer",
                CheckPurpose.READINESS,
                ("dispatch",),
                state,
                observed_at,
                reason_code=None if state is ObservationState.PASS else "PEER_OBSERVATION_FAILED",
            )
        return observe


class HealthServiceTests(_InstalledHealthFixture):
    def test_installed_truth_table_and_no_mutation(self) -> None:
        runtime_id = self.database.runtime_identity.runtime_id
        before = self.snapshot()
        with patch(
            "forge.planner.openai_responses.OpenAIResponsesPlanningProvider.invoke",
            side_effect=AssertionError("health must not invoke a provider"),
        ), patch(
            "forge.planner.codex_cli_session.CodexCliChatGPTSessionPlanningProvider.invoke",
            side_effect=AssertionError("health must not invoke a provider"),
        ):
            healthy = self.service.installed_health(("local_work",))
            degraded = self.service.installed_health(("dispatch", "local_work"))

        self.assertEqual(healthy["state"], "HEALTHY")
        self.assertEqual(degraded["state"], "DEGRADED")
        self.assertEqual(healthy["runtime_id"], runtime_id)
        self.assertEqual(healthy["installation_id"], runtime_id)
        self.assertEqual(self.snapshot(), before)

        self._metadata(status="maintenance")
        unavailable = self.service.installed_health(("local_work",))
        self.assertEqual(unavailable["state"], "UNAVAILABLE")

        self._metadata(status="active", last_access_at=(NOW - timedelta(days=1)).isoformat())
        current = self.service.installed_health(("local_work",))
        storage = next(item for item in current["checks"] if item["check_id"] == "storage")
        self.assertEqual((current["state"], storage["freshness"], storage["observed_at"]), (
            "HEALTHY", "FRESH", NOW.isoformat(),
        ))
        self._metadata(last_access_at=None)
        self.assertEqual(self.service.installed_health(("local_work",))["state"], "HEALTHY")

        self.configure_peer()
        passing = InstalledOperationsReadService(
            self.root, clock=lambda: NOW,
            peer_observer=self.peer_observer(ObservationState.PASS),
        ).installed_health(("dispatch", "local_work"))
        failed = InstalledOperationsReadService(
            self.root, clock=lambda: NOW,
            peer_observer=self.peer_observer(ObservationState.FAIL),
        ).installed_health(("dispatch", "local_work"))
        unknown = InstalledOperationsReadService(
            self.root, clock=lambda: NOW,
            peer_observer=self.peer_observer(ObservationState.UNKNOWN),
        ).installed_health(("dispatch", "local_work"))
        self.assertEqual((passing["state"], failed["state"], unknown["state"]), (
            "HEALTHY", "DEGRADED", "UNKNOWN",
        ))

    def test_dispatch_consumes_fresh_stale_and_timed_out_peer_observations(self) -> None:
        self.configure_peer()
        stale = InstalledOperationsReadService(
            self.root, clock=lambda: NOW,
            peer_observer=self.peer_observer(
                ObservationState.PASS, observed_at=NOW - timedelta(seconds=30),
            ),
        ).installed_health(("dispatch",))
        timed_out = InstalledOperationsReadService(
            self.root, clock=lambda: NOW,
            peer_observer=self.peer_observer(ObservationState.TIMED_OUT),
        ).installed_health(("dispatch",))
        stale_check = next(item for item in stale["checks"] if item["check_id"] == "execution_peer")
        timeout_check = next(
            item for item in timed_out["checks"] if item["check_id"] == "execution_peer"
        )
        self.assertEqual((stale["state"], stale_check["freshness"]), ("UNKNOWN", "STALE"))
        self.assertEqual(
            (timed_out["state"], timeout_check["freshness"]), ("UNKNOWN", "TIMED_OUT"),
        )

    def test_dispatch_runs_existing_bounded_authoritative_peer_preflight(self) -> None:
        self.configure_peer()
        with patch.object(
            EngineeringPlatformExecutionHostFactory,
            "preflight_configuration",
            return_value={"authoritative": True},
        ) as preflight:
            result = self.service.installed_health(("dispatch",))
        self.assertEqual(result["state"], "HEALTHY")
        configuration = preflight.call_args.args[0]
        self.assertEqual(configuration.expected_ep_instance_id, "ep-instance-1")
        self.assertEqual(preflight.call_args.kwargs, {"timeout_seconds": 1.0})

    def test_newer_runtime_schema_fails_closed_before_health_projection(self) -> None:
        future = RUNTIME_SCHEMA_VERSION + 1
        with self.database._connection:
            self.database._connection.execute(
                "UPDATE runtime_metadata SET value=? WHERE key IN ('schema_version','migration_version')",
                (str(future),),
            )
            self.database._connection.execute(f"PRAGMA user_version={future}")
        response = self.api.handle(
            "GET", "/v1/health/readiness?capability=local_work", "Bearer " + CREDENTIAL,
        )
        self.assertEqual((response.status, response.body["error"]["code"]), (
            503, "PROJECTION_UNAVAILABLE",
        ))

    def test_authoritative_installation_identity_accepts_persisted_uuid(self) -> None:
        installation_id = "123e4567-e89b-12d3-a456-426614174000"
        self._metadata(installation_id=installation_id)
        result = self.service.installed_health(("local_work",))
        self.assertEqual(result["installation_id"], installation_id)

    def test_health_snapshot_has_one_bounded_integrity_read(self) -> None:
        statements = []
        sqlite_connect = __import__("sqlite3").connect

        class RecordingConnection:
            def __init__(self, *args, **kwargs):
                self.connection = sqlite_connect(*args, **kwargs)

            @property
            def row_factory(self):
                return self.connection.row_factory

            @row_factory.setter
            def row_factory(self, value):
                self.connection.row_factory = value

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, statement, *args):
                statements.append(statement)
                return self.connection.execute(statement, *args)

        with patch("forge.operations_read_api.sqlite3.connect", side_effect=RecordingConnection):
            result = self.service.installed_health(("local_work",))
        self.assertEqual(result["state"], "HEALTHY")
        checks = [statement for statement in statements if "_check" in statement]
        self.assertEqual(checks, ["PRAGMA quick_check(1)"])

        calls = 0

        def expired_clock() -> float:
            nonlocal calls
            calls += 1
            return 0.0 if calls == 1 else 2.0

        bounded = InstalledOperationsReadService(
            self.root, clock=lambda: NOW, query_timeout_seconds=1.0, query_clock=expired_clock,
        )
        response = OperationsReadAPI(bounded, CREDENTIAL).handle(
            "GET", "/v1/health/readiness?capability=local_work", "Bearer " + CREDENTIAL,
        )
        self.assertEqual((response.status, response.body["error"]["code"]), (
            503, "PROJECTION_UNAVAILABLE",
        ))

    def test_health_projection_reuses_canonical_component_registry(self) -> None:
        components = component_registry()
        component_ids = {component.component_id for component in components}
        self.assertEqual(COMPONENT_REGISTRY_VERSION, "1.0")
        self.assertEqual(component_ids, {
            "forge_server", "operations_console", "dashboard_relay", "platform_database",
            "mission_dispatcher", "planning_provider", "codex_runtime", "python_runtime",
            "ep_peer", "http_ingress", "cli_ingress", "operational_logging", "tailscale_access",
        })
        checks = installed_health_registry()
        self.assertTrue({check.component_id for check in checks} <= component_ids)
        self.assertEqual(
            {(check.component_id, check.check_id) for check in checks},
            {("forge_server", "process"), ("platform_database", "storage"),
             ("ep_peer", "execution_peer")},
        )


class HealthHTTPTests(_InstalledHealthFixture):
    def test_liveness_readiness_auth_redaction(self) -> None:
        before = self.snapshot()
        server = make_server("127.0.0.1", 0, self.api)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/v1/health/live", timeout=2) as response:
                live = json.load(response)
            self.assertEqual(live, {
                "api_version": "1", "product": "forge",
                "liveness": {"alive": True, "state": "ALIVE"}, "read_only": True,
            })

            with self.assertRaises(HTTPError) as denied:
                urlopen(base + "/v1/health/readiness", timeout=2)
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()

            local = Request(
                base + "/v1/health/readiness?capability=local_work",
                headers={"Authorization": "Bearer " + CREDENTIAL},
            )
            with urlopen(local, timeout=2) as response:
                readiness = json.load(response)
            self.assertEqual((readiness["state"], readiness["runtime_id"]), (
                "HEALTHY", self.database.runtime_identity.runtime_id,
            ))

            aggregate = Request(
                base + "/v1/health/readiness",
                headers={"Authorization": "Bearer " + CREDENTIAL},
            )
            with self.assertRaises(HTTPError) as unavailable:
                urlopen(aggregate, timeout=2)
            aggregate_body = json.load(unavailable.exception)
            self.assertEqual((unavailable.exception.code, aggregate_body["state"]), (503, "DEGRADED"))
            unavailable.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

        rendered = json.dumps((live, readiness, aggregate_body), sort_keys=True)
        self.assertNotIn(CREDENTIAL, rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertEqual(self.snapshot(), before)


class HealthContractTests(_InstalledHealthFixture):
    def test_installed_http_cli_openapi_postman_parity(self) -> None:
        contract_root = Path(__file__).parents[1] / "forge" / "api"
        openapi = json.loads((contract_root / "operations-read-openapi-v1.json").read_text(encoding="utf-8"))
        postman = json.loads((contract_root / "operations-read-postman-v1.json").read_text(encoding="utf-8"))
        health_paths = {"/v1/health/live", "/v1/health/readiness"}
        self.assertTrue(health_paths.issubset(openapi["paths"]))
        postman_urls = {item["request"]["url"].split("?", 1)[0] for item in postman["item"]}
        self.assertEqual(
            health_paths,
            {path for path in health_paths if "{{baseUrl}}" + path in postman_urls},
        )
        self.assertEqual(openapi["paths"]["/v1/health/live"]["get"]["security"], [])
        self.assertEqual(
            openapi["paths"]["/v1/health/readiness"]["get"]["security"],
            [{"bearerAuth": []}],
        )

        output = StringIO()
        with redirect_stdout(output):
            live_exit = main(["--data-root", str(self.root), "health", "live"])
        cli_live = json.loads(output.getvalue())
        self.assertEqual((live_exit, cli_live), (0, self.service.liveness()))

        self._metadata(last_access_at=datetime.now(UTC).isoformat())
        output = StringIO()
        with redirect_stdout(output):
            ready_exit = main([
                "--data-root", str(self.root), "health", "readiness",
                "--capability", "local_work",
            ])
        cli_ready = json.loads(output.getvalue())
        self.assertEqual((ready_exit, cli_ready["state"]), (0, "HEALTHY"))
        self.assertEqual(
            {item["check_id"] for item in cli_ready["checks"]},
            {"process", "storage", "execution_peer"},
        )


class InstalledDistributionHealthTests(unittest.TestCase):
    def test_candidate_wheel_runs_installed_http_and_cli_outside_checkout(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            wheel, version = _write_candidate_wheel(repository, temporary)
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            environment.update({"PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1"})
            virtual_environment = temporary / "installed"
            venv.EnvBuilder(with_pip=True).create(virtual_environment)
            python = virtual_environment / "bin" / "python"
            forge = virtual_environment / "bin" / "forge"

            installed = subprocess.run(
                [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
                cwd=temporary, env=environment, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            location = subprocess.run(
                [
                    str(python), "-I", "-c",
                    "import forge,json,pathlib; print(json.dumps({'file':str(pathlib.Path(forge.__file__).resolve())}))",
                ],
                cwd=temporary, env=environment, text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(location.returncode, 0, location.stderr)
            installed_file = Path(json.loads(location.stdout)["file"])
            self.assertTrue(installed_file.is_relative_to(virtual_environment.resolve()))
            self.assertFalse(installed_file.is_relative_to(repository.resolve()))

            root = temporary / "runtime"
            initialized = subprocess.run(
                [str(forge), "--data-root", str(root), "server", "init"],
                cwd=temporary, env=environment, text=True, capture_output=True, timeout=20,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            runtime_id = json.loads(initialized.stdout)["instance_id"]
            observed_version = subprocess.run(
                [str(forge), "--version"], cwd=temporary, env=environment,
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual((observed_version.returncode, observed_version.stdout.strip()), (0, version))

            credential_file = temporary / "operations-api.credential"
            credential_file.write_text(CREDENTIAL + "\n", encoding="utf-8")
            credential_file.chmod(0o600)
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            server = subprocess.Popen(
                [
                    str(forge), "--data-root", str(root), "operations-api",
                    "--credential-file", str(credential_file), "--port", str(port),
                ],
                cwd=temporary, env=environment, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True,
            )
            base = f"http://127.0.0.1:{port}"
            try:
                deadline = time.monotonic() + 5
                while True:
                    if server.poll() is not None:
                        self.fail("installed operations API exited before accepting requests")
                    try:
                        with urlopen(base + "/v1/health/live", timeout=0.25) as response:
                            live = json.load(response)
                        break
                    except URLError:
                        if time.monotonic() >= deadline:
                            self.fail("installed operations API did not become ready within five seconds")
                        time.sleep(0.05)
                before = _logical_runtime_snapshot(root)
                self.assertEqual(live["liveness"], {"alive": True, "state": "ALIVE"})

                local_request = Request(
                    base + "/v1/health/readiness?capability=local_work",
                    headers={"Authorization": "Bearer " + CREDENTIAL},
                )
                with urlopen(local_request, timeout=2) as response:
                    local = json.load(response)
                self.assertEqual((local["state"], local["runtime_id"], local["installation_id"]), (
                    "HEALTHY", runtime_id, runtime_id,
                ))

                aggregate_request = Request(
                    base + "/v1/health/readiness",
                    headers={"Authorization": "Bearer " + CREDENTIAL},
                )
                with self.assertRaises(HTTPError) as degraded_response:
                    urlopen(aggregate_request, timeout=2)
                degraded = json.load(degraded_response.exception)
                self.assertEqual((degraded_response.exception.code, degraded["state"]), (503, "DEGRADED"))
                degraded_response.exception.close()

                cli_live = subprocess.run(
                    [str(forge), "--data-root", str(root), "health", "live"],
                    cwd=temporary, env=environment, text=True, capture_output=True, timeout=10,
                )
                cli_ready = subprocess.run(
                    [
                        str(forge), "--data-root", str(root), "health", "readiness",
                        "--capability", "local_work",
                    ],
                    cwd=temporary, env=environment, text=True, capture_output=True, timeout=10,
                )
                self.assertEqual(cli_live.returncode, 0, cli_live.stderr)
                self.assertEqual(cli_ready.returncode, 0, cli_ready.stderr)
                self.assertEqual(json.loads(cli_live.stdout)["liveness"]["state"], "ALIVE")
                self.assertEqual(json.loads(cli_ready.stdout)["runtime_id"], runtime_id)
                self.assertEqual(_logical_runtime_snapshot(root), before)

                connection = sqlite3.connect(root / "forge.db")
                try:
                    with connection:
                        connection.execute(
                            "UPDATE runtime_metadata SET value='maintenance' WHERE key='status'",
                        )
                finally:
                    connection.close()
                maintenance = _logical_runtime_snapshot(root)
                with self.assertRaises(HTTPError) as unavailable_response:
                    urlopen(local_request, timeout=2)
                unavailable = json.load(unavailable_response.exception)
                self.assertEqual(
                    (unavailable_response.exception.code, unavailable["state"]),
                    (503, "UNAVAILABLE"),
                )
                unavailable_response.exception.close()
                self.assertEqual(_logical_runtime_snapshot(root), maintenance)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
                if server.stderr is not None:
                    server.stderr.close()


if __name__ == "__main__":
    unittest.main()
