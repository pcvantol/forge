"""Installed-service qualification for bounded aggregate health composition."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from forge.__main__ import main
from forge.operations_read_api import InstalledOperationsReadService, OperationsReadAPI, make_server
from forge.runtime import RuntimeBootstrap


NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
CREDENTIAL = "synthetic-health-credential"


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
        self.assertEqual(healthy["installation_id"], "forge-installation")
        self.assertEqual(self.snapshot(), before)

        self._metadata(status="maintenance")
        unavailable = self.service.installed_health(("local_work",))
        self.assertEqual(unavailable["state"], "UNAVAILABLE")

        self._metadata(status="active", last_access_at=(NOW - timedelta(minutes=5)).isoformat())
        stale = self.service.installed_health(("local_work",))
        self.assertEqual(stale["state"], "UNKNOWN")
        storage = next(item for item in stale["checks"] if item["check_id"] == "storage")
        self.assertEqual((storage["freshness"], storage["reason_code"]), ("STALE", "OBSERVATION_STALE"))

        self._metadata(last_access_at=None)
        missing = self.service.installed_health(("local_work",))
        storage = next(item for item in missing["checks"] if item["check_id"] == "storage")
        self.assertEqual((missing["state"], storage["freshness"]), ("UNKNOWN", "MISSING"))


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


if __name__ == "__main__":
    unittest.main()
