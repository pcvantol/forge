"""Exercise the published Server V1 catalogue through its real HTTP listener."""
from __future__ import annotations

from contextlib import ExitStack
from http.client import HTTPConnection
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from forge._version import canonical_version
from forge.runtime import RuntimeBootstrap
from forge.server_runtime import ForgeServerRuntime, SERVER_ROUTE_INVENTORY


API = Path(__file__).parents[1] / "forge" / "api"
TOKEN = "route-qualification-bearer"

# Versioned V1 acceptance inventory, independent of the production tuple and
# contract files. A removed or silently omitted case must fail this gate.
EXPECTED_ROUTES = frozenset({
    ("GET", "/v1/project-dag/capability"),
    ("GET", "/v1/status"),
    ("GET", "/v1/health"),
    ("GET", "/v1/readiness"),
    ("GET", "/v1/readiness/standalone"),
    ("GET", "/v1/instance"),
    ("GET", "/v1/version"),
    ("GET", "/v1/provider-context"),
    ("GET", "/v1/projects"),
    ("GET", "/v1/projects/{project_id}/roadmap"),
    ("POST", "/v1/provider-context"),
    ("GET", "/v1/execution-host/preflight"),
    ("POST", "/v1/execution-host/configure"),
    ("POST", "/v1/execution-host/detach"),
    ("GET", "/v1/execution-host/detach/{operation_id}"),
    ("POST", "/v1/missions/inspect"),
    ("POST", "/v1/missions/approve-business"),
    ("POST", "/v1/missions/approve-architecture"),
    ("POST", "/v1/missions/admit"),
    ("GET", "/v1/missions/{mission_id}"),
    ("POST", "/v1/missions/{mission_id}/controller/start"),
    ("POST", "/v1/missions/{mission_id}/controller/reopen"),
    ("POST", "/v1/missions/{mission_id}/lifecycle/archive-no-dispatch"),
})

SERVICE_ROUTES = {
    ("GET", "/v1/readiness"): "readiness",
    ("GET", "/v1/readiness/standalone"): "standalone_readiness",
    ("GET", "/v1/instance"): "instance",
    ("GET", "/v1/provider-context"): "provider_context",
    ("POST", "/v1/provider-context"): "configure_provider_context",
    ("GET", "/v1/execution-host/preflight"): "execution_host_preflight",
    ("POST", "/v1/execution-host/configure"): "configure_execution_host",
    ("POST", "/v1/execution-host/detach"): "detach_execution_host",
    ("GET", "/v1/execution-host/detach/{operation_id}"): "detach_execution_host_status",
    ("POST", "/v1/missions/inspect"): "mission_document",
    ("POST", "/v1/missions/approve-business"): "mission_document",
    ("POST", "/v1/missions/approve-architecture"): "mission_document",
    ("POST", "/v1/missions/admit"): "mission_document",
    ("POST", "/v1/missions/{mission_id}/controller/start"): "mission_start",
    ("POST", "/v1/missions/{mission_id}/controller/reopen"): "mission_reopen",
    ("POST", "/v1/missions/{mission_id}/lifecycle/archive-no-dispatch"): "mission_archive_no_dispatch",
}
READ_ROUTES = {
    ("GET", "/v1/status"): "installed_status",
    ("GET", "/v1/health"): "installed_health_snapshot",
    ("GET", "/v1/projects"): "project_index",
    ("GET", "/v1/projects/{project_id}/roadmap"): "project_roadmap",
    ("GET", "/v1/missions/{mission_id}"): "mission_detail",
}


def _concrete(path: str) -> str:
    return (path.replace("{project_id}", "qualified-project")
            .replace("{operation_id}", "qualified-operation")
            .replace("{mission_id}", "MISSION-QUAL"))


def _request(port: int, method: str, path: str, *, authorization: str | None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if authorization is not None:
        headers["Authorization"] = authorization
    body = b'{"repository_truth":{}}' if method == "POST" else None
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(method, _concrete(path), body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class ServerRouteQualificationTests(unittest.TestCase):
    def test_frozen_v1_catalogue_agrees_with_inventory_openapi_and_postman(self) -> None:
        openapi = json.loads((API / "server-openapi-v1.json").read_text(encoding="utf-8"))
        postman = json.loads((API / "server-postman-v1.json").read_text(encoding="utf-8"))
        openapi_routes = {
            (method.upper(), path)
            for path, operations in openapi["paths"].items()
            for method in operations if method.lower() in {"get", "post", "put", "patch", "delete"}
        }
        postman_routes = {
            (item["request"]["method"].upper(),
             item["request"]["url"]["raw"].removeprefix("{{baseUrl}}")
             .replace("{{projectId}}", "{project_id}")
             .replace("{{missionId}}", "{mission_id}"))
            for item in postman["item"]
        }
        self.assertEqual(len(EXPECTED_ROUTES), 23)
        self.assertEqual(set(SERVER_ROUTE_INVENTORY), EXPECTED_ROUTES)
        self.assertEqual(openapi_routes, EXPECTED_ROUTES)
        self.assertEqual(postman_routes, EXPECTED_ROUTES)

    def test_real_listener_denies_every_route_before_dispatch(self) -> None:
        with TemporaryDirectory() as directory:
            server = self._server(Path(directory) / "instance")
            worker = Thread(target=server.server.serve_forever, daemon=True)
            worker.start()
            try:
                with patch.object(server.api, "handle", side_effect=AssertionError("application dispatched")) as dispatch:
                    for method, path in sorted(EXPECTED_ROUTES):
                        for authorization in (None, "Bearer incorrect"):
                            with self.subTest(method=method, path=path, authorization=authorization):
                                status, body = _request(
                                    server.server.server_port, method, path,
                                    authorization=authorization,
                                )
                                self.assertEqual(status, 401)
                                self.assertEqual(body["error"]["code"], "AUTHENTICATION_REQUIRED")
                    dispatch.assert_not_called()
            finally:
                server.server.shutdown()
                server.server.server_close()
                worker.join(timeout=3)

    def test_real_listener_recognizes_every_authenticated_route(self) -> None:
        with TemporaryDirectory() as directory:
            server = self._server(Path(directory) / "instance")
            worker = Thread(target=server.server.serve_forever, daemon=True)
            worker.start()
            try:
                with ExitStack() as stack:
                    mocked_services = {}
                    for name in (
                        "instance", "provider_context", "execution_host_preflight",
                        "configure_provider_context", "configure_execution_host",
                        "detach_execution_host", "detach_execution_host_status",
                        "mission_document", "mission_start", "mission_reopen",
                        "mission_archive_no_dispatch",
                    ):
                        mocked_services[name] = stack.enter_context(patch.object(
                            server.services, name, return_value={"service": name},
                        ))
                    for name in ("readiness", "standalone_readiness"):
                        mocked_services[name] = stack.enter_context(patch.object(
                            server.services, name, return_value={"ready": True, "service": name},
                        ))
                    read_service = server.api._read_api.service
                    mocked_reads = {}
                    for name in READ_ROUTES.values():
                        mocked_reads[name] = stack.enter_context(patch.object(
                            read_service, name,
                            return_value={"service": name, "outcome": "HEALTHY", "availability": "AVAILABLE"},
                        ))
                    observed: set[tuple[str, str]] = set()
                    for method, path in sorted(EXPECTED_ROUTES):
                        with self.subTest(method=method, path=path):
                            status, body = _request(
                                server.server.server_port, method, path,
                                authorization="Bearer " + TOKEN,
                            )
                            self._assert_recognized(status, body)
                            expected_service = SERVICE_ROUTES.get((method, path))
                            if expected_service is not None:
                                self.assertEqual(status, 200)
                                self.assertEqual(body.get("service"), expected_service)
                                mocked_services[expected_service].assert_called()
                                if expected_service == "mission_document":
                                    self.assertEqual(
                                        mocked_services[expected_service].call_args.args[0],
                                        path.rsplit("/", 1)[1],
                                    )
                                elif expected_service == "detach_execution_host_status":
                                    mocked_services[expected_service].assert_called_with("qualified-operation")
                                elif expected_service == "mission_start":
                                    mocked_services[expected_service].assert_called_with("MISSION-QUAL", {})
                                elif expected_service == "mission_reopen":
                                    mocked_services[expected_service].assert_called_with("MISSION-QUAL")
                                elif expected_service == "mission_archive_no_dispatch":
                                    call = mocked_services[expected_service].call_args
                                    self.assertEqual(
                                        call.args, ("MISSION-QUAL", {"repository_truth": {}}),
                                    )
                                    self.assertRegex(
                                        call.kwargs["authenticated_principal_reference"],
                                        r"\Aforge-server-admin-session:v1:[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z",
                                    )
                            expected_read = READ_ROUTES.get((method, path))
                            if expected_read is not None:
                                self.assertEqual(status, 200)
                                self.assertEqual(body.get("service"), expected_read)
                                mocked_reads[expected_read].assert_called()
                                if expected_read == "project_roadmap":
                                    mocked_reads[expected_read].assert_called_with("qualified-project")
                                elif expected_read == "mission_detail":
                                    mocked_reads[expected_read].assert_called_with("MISSION-QUAL")
                            if path == "/v1/project-dag/capability":
                                self.assertEqual(status, 200)
                                self.assertEqual(body.get("contract_version"), "forge-project-dag-http-capability/v1")
                                self.assertEqual(body.get("capability_id"), "PROJECT_DAG_READ_V1")
                                self.assertEqual(body.get("support"), "SUPPORTED_NOT_READINESS")
                            elif path == "/v1/version":
                                self.assertEqual(status, 200)
                                self.assertEqual(body.get("product"), "forge-autonomy")
                                self.assertEqual(body.get("product_version"), canonical_version())
                                self.assertIsInstance(body.get("storage_schema"), int)
                                self.assertTrue(body.get("instance_id"))
                            elif expected_service is None and expected_read is None:
                                self.assertEqual(status, 200)
                            observed.add((method, path))
                    self.assertEqual(observed, EXPECTED_ROUTES)
            finally:
                server.server.shutdown()
                server.server.server_close()
                worker.join(timeout=3)

    def test_missing_route_response_is_a_failed_qualification(self) -> None:
        with self.assertRaisesRegex(AssertionError, "ROUTE_NOT_FOUND"):
            self._assert_recognized(404, {"error": {"code": "ROUTE_NOT_FOUND"}})

    def _assert_recognized(self, status: int, body: dict) -> None:
        self.assertIn(status, {200, 400, 404, 409, 503}, body)
        self.assertNotEqual(body.get("error", {}).get("code"), "ROUTE_NOT_FOUND", body)

    @staticmethod
    def _server(root: Path) -> ForgeServerRuntime:
        database = RuntimeBootstrap(data_root=root, forge_version="route-qualification").open()
        database.close()
        credential = root / "bearer"
        credential.write_text(TOKEN + "\n", encoding="utf-8")
        credential.chmod(0o600)
        return ForgeServerRuntime(
            data_root=root, credential_file=credential, host="127.0.0.1", port=0,
        )
