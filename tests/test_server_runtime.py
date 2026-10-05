from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
    CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderSecurityService,
    ProviderAuthenticationMode,
)
from forge.runtime import RuntimeBootstrap
from forge.runtime.database import RUNTIME_SCHEMA_VERSION
from forge.execution_host_configuration import EngineeringPlatformPeerConfigurationService
from forge.server_runtime import (
    ForgeServerRuntime,
    ForgeServerRuntimeError,
    ServerInstanceLease,
    existing_instance,
)
from forge.secure_store import SecretState
from forge.secure_store import SecretReference
from forge.workspace_read_grant import WorkspaceReadGrant, main as read_grant_main


class _Store:
    def status(self, _reference):
        return SecretState.RESOLVABLE


class ForgeServerRuntimeTests(unittest.TestCase):
    def _root(self, temporary: str, name: str) -> Path:
        root = Path(temporary) / name
        database = RuntimeBootstrap(data_root=root, forge_version="test").open()
        database.close()
        return root

    def _credential(self, root: Path) -> Path:
        path = root / "server-credential"
        path.write_text("server-test-credential\n", encoding="utf-8")
        path.chmod(0o600)
        return path

    def test_server_requires_an_existing_explicit_current_instance(self) -> None:
        with TemporaryDirectory() as temporary:
            absent = Path(temporary) / "absent"
            with self.assertRaisesRegex(ForgeServerRuntimeError, "existing initialized"):
                existing_instance(absent)
            self.assertFalse(absent.exists())

    def test_server_rejects_nonpositive_tick_before_opening_an_instance(self) -> None:
        with TemporaryDirectory() as temporary:
            absent = Path(temporary) / "absent"
            with self.assertRaisesRegex(ValueError, "tick interval must be positive"):
                ForgeServerRuntime(
                    data_root=absent, credential_file=absent / "credential",
                    host="127.0.0.1", port=0, tick_interval=0,
                )
            self.assertFalse(absent.exists())

    def test_two_instances_bind_distinct_runtime_state_and_listeners(self) -> None:
        with TemporaryDirectory() as temporary:
            root_a = self._root(temporary, "alpha")
            root_b = self._root(temporary, "beta")
            server_a = ForgeServerRuntime(
                data_root=root_a, credential_file=self._credential(root_a),
                host="127.0.0.1", port=0,
            )
            server_b = ForgeServerRuntime(
                data_root=root_b, credential_file=self._credential(root_b),
                host="127.0.0.1", port=0,
            )
            try:
                instance_a = server_a.api.handle("GET", "/v1/instance", "Bearer server-test-credential")
                instance_b = server_b.api.handle("GET", "/v1/instance", "Bearer server-test-credential")
                self.assertEqual((instance_a.status, instance_b.status), (200, 200))
                self.assertNotEqual(
                    instance_a.body["instance"]["instance_id"],
                    instance_b.body["instance"]["instance_id"],
                )
                self.assertNotEqual(
                    instance_a.body["listener"]["port"],
                    instance_b.body["listener"]["port"],
                )
                self.assertNotEqual(
                    Path(instance_a.body["instance"]["data_root"]),
                    Path(instance_b.body["instance"]["data_root"]),
                )
            finally:
                server_a.server.server_close()
                server_b.server.server_close()

    def test_server_lease_is_per_instance_not_machine_global(self) -> None:
        with TemporaryDirectory() as temporary:
            root_a = self._root(temporary, "alpha")
            root_b = self._root(temporary, "beta")
            lease_a = ServerInstanceLease(root_a)
            with lease_a.acquire():
                with ServerInstanceLease(root_b).acquire():
                    pass
                with self.assertRaisesRegex(ForgeServerRuntimeError, "owns this instance"):
                    with ServerInstanceLease(root_a).acquire():
                        pass

    def test_server_api_requires_authentication_and_does_not_initialize(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "alpha")
            server = ForgeServerRuntime(
                data_root=root, credential_file=self._credential(root),
                host="127.0.0.1", port=0,
            )
            try:
                denied = server.api.handle("GET", "/v1/version", None)
                accepted = server.api.handle("GET", "/v1/version", "Bearer server-test-credential")
                self.assertEqual((denied.status, accepted.status), (401, 200))
                self.assertEqual(accepted.body["storage_schema"], RUNTIME_SCHEMA_VERSION)
                self.assertEqual(accepted.body["instance_id"], existing_instance(root).instance_id)
            finally:
                server.server.server_close()

    def test_installed_workspace_grant_limits_http_reads_and_revokes_immediately(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "workspace")
            EngineeringPlatformPeerConfigurationService(root).configure(
                binding_id="ep", endpoint="https://ep.test", expected_ep_instance_id="ep-instance",
                ep_consumer_id="consumer", execution_host_id="ep-host", ep_project_id="project",
                ep_repository_id="repository", repository_identity="forge-repository",
                credential_reference=SecretReference.parse("keychain://forge.ep/consumer"),
                operator_id="operator",
            )
            grant_path = root / "credentials" / "workspace-read-grant.json"
            token_path = root / "workspace-token"
            instance_id = existing_instance(root).instance_id
            grant = WorkspaceReadGrant(root, instance_id, grant_path)
            with self.assertRaisesRegex(ValueError, "repository binding"):
                grant.issue("foreign-repository", token_path)
            with patch("builtins.print") as output:
                self.assertEqual(read_grant_main([
                    "--data-root", str(root), "issue", "--repository-id", "repository",
                    "--token-file", str(token_path),
                ]), 0)
            self.assertEqual(json.loads(output.call_args.args[0])["revision"], 1)
            token = token_path.read_text(encoding="utf-8").strip()
            server = ForgeServerRuntime(
                data_root=root, credential_file=self._credential(root),
                host="127.0.0.1", port=0,
            )
            thread = Thread(target=server.server.serve_forever, daemon=True)
            thread.start()
            try:
                database_digest = hashlib.sha256((root / "forge.db").read_bytes()).hexdigest()
                contract = json.loads((Path(__file__).parents[1] / "forge" / "api" /
                                       "workspace-status-read-v1.json").read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(contract)
                def request(path: str, bearer: str, method: str = "GET") -> tuple[int, dict]:
                    item = Request(f"http://127.0.0.1:{server.server.server_port}{path}",
                                   headers={"Authorization": f"Bearer {bearer}"}, method=method)
                    try:
                        with urlopen(item, timeout=2) as response:
                            return response.status, json.load(response)
                    except HTTPError as error:
                        with error:
                            return error.code, json.load(error)

                for path in ("/v1/instance", "/v1/status"):
                    status, body = request(path, token)
                    self.assertEqual(status, 200)
                    kind = "instance" if path == "/v1/instance" else "status"
                    validator = Draft202012Validator(contract | {"$ref": f"#/$defs/{kind}"},
                                                       format_checker=FormatChecker())
                    validator.validate(body)
                    self.assertEqual(body["workspace_read_scope"], {
                        "contract_version": "forge-workspace-status-read/v1",
                        "instance_id": instance_id,
                        "repository_id": "repository",
                    })
                    body["workspace_read_scope"]["repository_id"] = ""
                    with self.assertRaises(ValidationError):
                        validator.validate(body)
                self.assertEqual(request("/v1/version", token)[0], 403)
                self.assertEqual(request("/v1/provider-context", token, "POST")[0], 403)
                self.assertEqual(request("/v1/instance", "wrong-token")[0], 401)
                self.assertEqual(request("/v1/instance", "server-test-credential")[0], 200)
                original = grant_path.read_bytes()
                foreign = json.loads(original)
                foreign["repository_id"] = "foreign-repository"
                grant_path.write_text(json.dumps(foreign), encoding="utf-8")
                self.assertEqual(request("/v1/instance", token)[0], 401)
                grant_path.write_bytes(original)
                other_root = self._root(temporary, "foreign-instance")
                EngineeringPlatformPeerConfigurationService(other_root).configure(
                    binding_id="ep", endpoint="https://ep.test", expected_ep_instance_id="ep-instance",
                    ep_consumer_id="consumer", execution_host_id="ep-host", ep_project_id="project",
                    ep_repository_id="repository", repository_identity="forge-repository",
                    credential_reference=SecretReference.parse("keychain://forge.ep/consumer"),
                    operator_id="operator",
                )
                other = ForgeServerRuntime(
                    data_root=other_root, credential_file=self._credential(other_root),
                    read_grant_file=grant_path, host="127.0.0.1", port=0,
                )
                try:
                    self.assertEqual(other.api.handle("GET", "/v1/instance", f"Bearer {token}").status, 401)
                finally:
                    other.server.server_close()
                new_token_path = root / "rotated-token"
                with patch("builtins.print") as output:
                    self.assertEqual(read_grant_main([
                        "--data-root", str(root), "rotate", "--repository-id", "repository",
                        "--token-file", str(new_token_path),
                    ]), 0)
                self.assertEqual(json.loads(output.call_args.args[0])["revision"], 2)
                rotated = new_token_path.read_text(encoding="utf-8").strip()
                self.assertEqual(request("/v1/instance", token)[0], 401)
                self.assertEqual(request("/v1/instance", rotated)[0], 200)
                with patch("builtins.print") as output:
                    self.assertEqual(read_grant_main(["--data-root", str(root), "revoke"]), 0)
                self.assertEqual(json.loads(output.call_args.args[0])["revision"], 3)
                self.assertEqual(request("/v1/instance", rotated)[0], 401)
                self.assertEqual(hashlib.sha256((root / "forge.db").read_bytes()).hexdigest(), database_digest)
            finally:
                server.server.shutdown()
                server.server.server_close()
                thread.join(timeout=2)

    def test_running_server_rejects_replaced_instance_root_before_work(self) -> None:
        for replacement in ("symlink", "directory"):
            with self.subTest(replacement=replacement), TemporaryDirectory() as temporary:
                base = Path(temporary)
                root_a = self._root(temporary, "alpha")
                root_b = self._root(temporary, "beta")
                other_id = existing_instance(root_b).instance_id
                server = ForgeServerRuntime(
                    data_root=root_a, credential_file=self._credential(root_a),
                    host="127.0.0.1", port=0,
                )
                thread = Thread(target=server.server.serve_forever, daemon=True)
                thread.start()
                try:
                    endpoint = f"http://127.0.0.1:{server.server.server_port}/v1/version"
                    authorized = Request(endpoint, headers={
                        "Authorization": "Bearer server-test-credential",
                    })
                    with urlopen(authorized, timeout=2) as response:
                        self.assertEqual(json.load(response)["instance_id"], server.instance.instance_id)
                    root_a.rename(base / "alpha-parked")
                    if replacement == "symlink":
                        root_a.symlink_to(root_b, target_is_directory=True)
                    else:
                        root_b.rename(root_a)
                    with patch.object(server.services, "configure_provider_context",
                                      side_effect=AssertionError("B mutation")) as mutation:
                        for request in (
                            authorized,
                            Request(endpoint.replace("/v1/version", "/v1/provider-context"),
                                    data=b"{}", method="POST", headers={
                                        "Authorization": "Bearer server-test-credential",
                                    }),
                        ):
                            with self.assertRaises(HTTPError) as unavailable:
                                urlopen(request, timeout=2)
                            self.assertEqual(unavailable.exception.code, 503)
                            body = unavailable.exception.read()
                            self.assertEqual(json.loads(body)["error"]["code"], "INSTANCE_UNAVAILABLE")
                            self.assertNotIn(other_id.encode(), body)
                            unavailable.exception.close()
                        mutation.assert_not_called()
                    self.assertEqual(server.api.handle(
                        "GET", "/v1/version", "Bearer server-test-credential",
                    ).status, 503)
                    with socket.create_connection(("127.0.0.1", server.server.server_port),
                                                  timeout=2) as client:
                        client.settimeout(0.75)
                        client.sendall(
                            b"POST /v1/provider-context HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                            b"Authorization: Bearer server-test-credential\r\n"
                            b"Content-Length: 50\r\n\r\n{"
                        )
                        with client.makefile("rb") as reply:
                            self.assertEqual(int(reply.readline().split()[1]), 503)
                    with self.assertRaisesRegex(ForgeServerRuntimeError, "root changed"):
                        server._tick()  # noqa: SLF001 - scheduler drift boundary
                    with self.assertRaisesRegex(ForgeServerRuntimeError, "root changed"):
                        server.serve_forever()
                    server._log.write("drifted")  # noqa: SLF001 - must not write into B
                    self.assertFalse((root_a / "logs" / "server-runtime.jsonl").exists())
                finally:
                    server.server.shutdown()
                    server.server.server_close()
                    thread.join(timeout=2)

    def test_explicit_standalone_readiness_does_not_authorize_ep_execution(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "standalone")
            server = ForgeServerRuntime(
                data_root=root, credential_file=self._credential(root),
                host="127.0.0.1", port=0,
            )
            try:
                server.state.scheduler("READY")
                with patch.object(server.services, "provider_readiness", return_value={
                    "state": "READY", "ready": True,
                }):
                    strict = server.api.handle("GET", "/v1/readiness", "Bearer server-test-credential")
                    standalone = server.api.handle(
                        "GET", "/v1/readiness/standalone", "Bearer server-test-credential",
                    )
                self.assertEqual(strict.status, 503)
                self.assertEqual(standalone.status, 200)
                self.assertTrue(standalone.body["service_ready"])
                self.assertFalse(standalone.body["execution_ready"])
                self.assertEqual(standalone.body["mode"], "STANDALONE")
                self.assertEqual(standalone.body["execution_host_peer"]["state"], "NOT_CONFIGURED")
            finally:
                server.server.server_close()

    def test_detached_peer_does_not_become_standalone_implicitly(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "detached")
            service = EngineeringPlatformPeerConfigurationService(root)
            old = service.configure(
                binding_id="ep", endpoint="https://ep.test", expected_ep_instance_id="ep-instance",
                ep_consumer_id="consumer-old", execution_host_id="ep-host", ep_project_id="project",
                ep_repository_id="repository", repository_identity="forge-repository",
                credential_reference=SecretReference.parse("keychain://forge.ep/consumer"),
                operator_id="operator",
            )
            instance = existing_instance(root).instance_id
            service.detach(
                operation_id="detach-test", instance_id=instance, expected_binding_id=old.binding_id,
                expected_revision=old.configuration_revision, expected_digest=old.configuration_digest,
                operator_id="operator",
            )
            server = ForgeServerRuntime(
                data_root=root, credential_file=self._credential(root), host="127.0.0.1", port=0,
            )
            try:
                server.state.scheduler("READY")
                with patch.object(server.services, "provider_readiness", return_value={"ready": True}):
                    response = server.api.handle(
                        "GET", "/v1/readiness/standalone", "Bearer server-test-credential",
                    )
                self.assertEqual(response.status, 503)
                self.assertFalse(response.body["service_ready"])
                self.assertEqual(response.body["execution_host_peer"]["state"], "DETACHED")
                self.assertEqual(response.body["mode"], "PEER_REQUIRED")
            finally:
                server.server.server_close()

    def test_http_peer_configuration_detach_and_status_are_exactly_bound(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "peer-http")
            server = ForgeServerRuntime(
                data_root=root, credential_file=self._credential(root), host="127.0.0.1", port=0,
            )
            authorization = "Bearer server-test-credential"
            configure = {
                "binding_id": "ep", "endpoint": "https://ep.test", "expected_instance_id": "ep-instance",
                "consumer_id": "consumer-old", "host_id": "ep-host", "project_id": "project",
                "repository_id": "repository", "repository_identity": "forge-repository",
                "credential_reference": "keychain://forge.ep/consumer", "operator_id": "operator",
                "timeout_seconds": 10.0, "allow_loopback_http": False,
                "replace": False, "expected_revision": None, "expected_digest": None,
            }
            try:
                created = server.api.handle("POST", "/v1/execution-host/configure", authorization, configure)
                self.assertEqual(created.status, 200)
                self.assertEqual(created.body["ep_consumer_id"], "consumer-old")
                self.assertEqual(server.api.handle(
                    "GET", "/v1/readiness/standalone", authorization,
                ).status, 503)
                self.assertEqual(server.api.handle(
                    "GET", "/v1/execution-host/preflight", authorization,
                ).status, 409)
                detached_request = {
                    "operation_id": "peer-http-detach", "instance_id": existing_instance(root).instance_id,
                    "expected_binding_id": "ep", "expected_revision": 1,
                    "expected_digest": created.body["configuration_digest"], "operator_id": "operator",
                }
                self.assertEqual(server.api.handle(
                    "POST", "/v1/execution-host/detach", None, detached_request,
                ).status, 401)
                detached = server.api.handle(
                    "POST", "/v1/execution-host/detach", authorization, detached_request,
                )
                self.assertEqual(detached.status, 200)
                self.assertEqual(detached.body["remote_consumer_revoke"], "NOT_ASSERTED")
                self.assertEqual(server.api.handle(
                    "GET", "/v1/execution-host/detach/peer-http-detach", authorization,
                ).body["phase"], "COMPLETE")
                self.assertEqual(server.api.handle(
                    "POST", "/v1/execution-host/detach", authorization,
                    {**detached_request, "expected_binding_id": "other"},
                ).status, 409)
                repaired = server.api.handle(
                    "POST", "/v1/execution-host/configure", authorization,
                    {**configure, "consumer_id": "consumer-new", "replace": True,
                     "expected_revision": 1, "expected_digest": detached.body["receipt_digest"]},
                )
                self.assertEqual(repaired.status, 200)
                self.assertEqual(repaired.body["configuration_revision"], 2)
                self.assertEqual(server.api.handle(
                    "POST", "/v1/execution-host/detach", authorization, detached_request,
                ).body, detached.body)
            finally:
                server.server.server_close()

    def test_http_transport_rejects_malformed_json_and_preserves_admin_routes(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "transport")
            server = ForgeServerRuntime(
                data_root=root, credential_file=self._credential(root), host="127.0.0.1", port=0,
            )
            authorization = "Bearer server-test-credential"
            thread = Thread(target=server.server.serve_forever, daemon=True)
            thread.start()
            try:
                for payload in (b"{broken", b"[1,2]"):
                    request = Request(
                        f"http://127.0.0.1:{server.server.server_port}/v1/execution-host/detach",
                        data=payload, method="POST", headers={"Authorization": authorization},
                    )
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(request, timeout=2)
                    self.assertEqual(caught.exception.code, 400)
                    self.assertEqual(json.loads(caught.exception.read())["error"]["code"], "REQUEST_INVALID")
                    caught.exception.close()
                with patch.object(server.services, "mission_document", return_value={"status": "VALID"}) as mission:
                    for operation in ("inspect", "approve-business", "approve-architecture", "admit"):
                        result = server.api.handle(
                            "POST", "/v1/missions/" + operation, authorization, {"id": "test"},
                        )
                        self.assertEqual(result.status, 200)
                    self.assertEqual(mission.call_count, 4)
                with patch.object(server.services, "mission_start", return_value={"status": "COMPLETED"}) as start:
                    path = "/v1/missions/mission-1/controller/start"
                    self.assertEqual(server.api.handle("POST", path, authorization, {}).status, 409)
                    self.assertEqual(server.api.handle(
                        "POST", path, authorization, {"repository_truth": {"id": "truth"}},
                    ).status, 200)
                    start.assert_called_once()
                with patch.object(server.services, "mission_reopen", return_value={"status": "COMPLETED"}):
                    self.assertEqual(server.api.handle(
                        "POST", "/v1/missions/mission-1/controller/reopen", authorization,
                    ).status, 200)
                archive_request = {
                    "expected_instance_id": "runtime-1", "expected_revision": 2,
                    "reason_code": "historical_no_dispatch_reconciled",
                    "correlation_id": "lifecycle-1",
                }
                with patch.object(server.services, "mission_archive_no_dispatch",
                                  return_value={"status": "ARCHIVED"}) as archive:
                    response = server.api.handle(
                        "POST", "/v1/missions/mission-1/lifecycle/archive-no-dispatch",
                        authorization, archive_request,
                    )
                    self.assertEqual(response.status, 200)
                    archive.assert_called_once()
                    args, kwargs = archive.call_args
                    self.assertEqual(args, ("mission-1", archive_request))
                    principal = kwargs["authenticated_principal_reference"]
                    self.assertRegex(principal, r"\Aforge-server-admin:v1:sha256:[0-9a-f]{64}\Z")
                    self.assertNotIn("server-secret", principal)
                with patch.object(server.services, "configure_provider_context", return_value={"state": "BOUND"}):
                    self.assertEqual(server.api.handle(
                        "POST", "/v1/provider-context", authorization, {},
                    ).status, 200)
                self.assertEqual(server.api.handle("GET", "/v1/absent", authorization).status, 404)
            finally:
                server.server.shutdown()
                server.server.server_close()
                thread.join(timeout=2)

    def test_http_rejects_invalid_bearer_without_waiting_for_body(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "auth-before-body")
            server = ForgeServerRuntime(
                data_root=root, credential_file=self._credential(root), host="127.0.0.1", port=0,
            )
            thread = Thread(target=server.server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server.server_port
                with patch.object(server.api, "handle", side_effect=AssertionError("app dispatched")):
                    for authorization, expected in (
                        (b"", 401),
                        (b"Authorization: Bearer wrong\r\n", 401),
                        (b"Authorization: Bearer wrong\r\nAuthorization: Bearer wrong\r\n", 400),
                    ):
                        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                            client.settimeout(0.75)
                            client.sendall(
                                b"POST /v1/provider-context HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                + authorization + b"Content-Length: 50\r\n\r\n{"
                            )
                            with client.makefile("rb") as reply:
                                self.assertEqual(int(reply.readline().split()[1]), expected)
                with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                    client.settimeout(0.2)
                    client.sendall(
                        b"POST /v1/absent HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                        b"Authorization: Bearer server-test-credential\r\n"
                        b"Content-Length: 7\r\n\r\n{"
                    )
                    with self.assertRaises(socket.timeout):
                        client.recv(1)
                    client.settimeout(2)
                    client.sendall(b'"x":1}')
                    with client.makefile("rb") as reply:
                        self.assertEqual(int(reply.readline().split()[1]), 404)
            finally:
                server.server.shutdown()
                server.server.server_close()
                thread.join(timeout=2)

    def test_mission_document_transport_uses_private_one_request_file(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "mission-document")
            server = ForgeServerRuntime(
                data_root=root, credential_file=self._credential(root), host="127.0.0.1", port=0,
            )
            seen = []

            def inspect(path):
                request = Path(path)
                seen.append((json.loads(request.read_text()), request.stat().st_mode & 0o777, request))
                return {"status": "VALID"}

            def approve(_root, path, role):
                inspect(path)
                return {"status": role}

            def admit(_root, path):
                inspect(path)
                return {"status": "ADMITTED"}

            try:
                with (patch("forge.server_runtime.mission_inspect", side_effect=inspect),
                      patch("forge.server_runtime.mission_approve", side_effect=approve),
                      patch("forge.server_runtime.mission_admit", side_effect=admit)):
                    for operation in ("inspect", "approve-business", "approve-architecture", "admit"):
                        self.assertIn("status", server.services.mission_document(operation, {"case": operation}))
                    with self.assertRaisesRegex(ValueError, "unsupported Mission"):
                        server.services.mission_document("unknown", {})
                self.assertEqual(len(seen), 4)
                self.assertTrue(all(mode == 0o600 and body["case"] for body, mode, _ in seen))
                self.assertTrue(all(not path.exists() for _, _, path in seen))
            finally:
                server.server.server_close()

    def test_foreground_server_starts_without_login_home_and_stops_cleanly_on_sigterm(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "headless")
            credential = self._credential(root)
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            environment = os.environ.copy()
            for name in ("HOME", "USER", "LOGNAME", "CODEX_HOME"):
                environment.pop(name, None)
            process = subprocess.Popen(
                [
                    sys.executable, "-m", "forge", "--data-root", str(root),
                    "server", "run", "--credential-file", str(credential),
                    "--host", "127.0.0.1", "--port", str(port),
                    "--tick-interval", "0.05",
                ],
                cwd=Path(__file__).parents[1],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                response = None
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        request = Request(
                            f"http://127.0.0.1:{port}/v1/version",
                            headers={"Authorization": "Bearer server-test-credential"},
                        )
                        with urlopen(request, timeout=0.5) as handle:
                            response = json.loads(handle.read())
                        break
                    except OSError:
                        time.sleep(0.05)
                self.assertIsNotNone(response, process.stderr.read() if process.poll() is not None else "")
                self.assertEqual(response["storage_schema"], RUNTIME_SCHEMA_VERSION)
                process.terminate()
                process.communicate(timeout=8)
                self.assertEqual(process.returncode, 0)
                log = (root / "logs" / "server-runtime.jsonl").read_text(encoding="utf-8")
                self.assertIn('"event":"server_running"', log)
                self.assertIn('"event":"server_stopped"', log)
                self.assertNotIn("server-test-credential", log)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_instance_owned_codex_context_is_used_for_headless_readiness(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "alpha")
            executable = Path(temporary) / "codex"
            provider_home = Path(temporary) / "provider-home"
            config_home = Path(temporary) / "codex-home"
            provider_home.mkdir()
            config_home.mkdir()
            executable.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--version\" ]; then echo 'codex-cli 0.153.4'; exit 0; fi\n"
                "if [ \"$1\" = \"login\" ] && [ \"$2\" = \"status\" ]; then\n"
                f"  [ \"$HOME\" = \"{provider_home}\" ] || exit 9\n"
                f"  [ \"$CODEX_HOME\" = \"{config_home}\" ] || exit 8\n"
                "  echo 'Logged in using ChatGPT'; exit 0\n"
                "fi\nexit 7\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)

            database = RuntimeBootstrap(data_root=root, forge_version="test").open()
            operators = InstallationOperatorService(
                database, lambda: NamedOperatorIdentity("server-provider-test", 501),
            )
            context = operators.first_bind()
            PlanningProviderSecurityService(database, _Store(), operators).configure(
                configuration_id="server-codex-config", provider_id="codex-chatgpt-session",
                operator_context=context,
                authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
                provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
                external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
                executable_path=str(executable), adapter_version="1.0",
                timeout_seconds=30, input_token_bound=64000,
                context_token_bound=128000, output_token_bound=16000,
            )
            database.close()

            server = ForgeServerRuntime(
                data_root=root, credential_file=self._credential(root),
                host="127.0.0.1", port=0,
            )
            try:
                response = server.api.handle(
                    "POST", "/v1/provider-context", "Bearer server-test-credential",
                    {
                        "provider_id": "codex-chatgpt-session",
                        "provider_type": CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
                        "executable_path": str(executable),
                        "provider_home": str(provider_home),
                        "provider_config_home": str(config_home),
                        "profile": None,
                        "expected_digest": None,
                    },
                )
                self.assertEqual(response.status, 200)
                readiness = server.services.provider_readiness()
                self.assertTrue(readiness["ready"])
                self.assertEqual(readiness["state"], "READY")
                self.assertEqual(readiness["instance_id"], existing_instance(root).instance_id)
                self.assertTrue(str(readiness["provider_context_digest"]).startswith("sha256:"))
            finally:
                server.server.server_close()


if __name__ == "__main__":
    unittest.main()
