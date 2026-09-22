from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from tempfile import TemporaryDirectory
import unittest

from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
    CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderSecurityService,
    ProviderAuthenticationMode,
)
from forge.runtime import RuntimeBootstrap
from forge.server_runtime import (
    ForgeServerRuntime,
    ForgeServerRuntimeError,
    ServerInstanceLease,
    existing_instance,
)
from forge.secure_store import SecretState


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
                self.assertEqual(accepted.body["storage_schema"], 39)
                self.assertEqual(accepted.body["instance_id"], existing_instance(root).instance_id)
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
                self.assertEqual(response["storage_schema"], 39)
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
