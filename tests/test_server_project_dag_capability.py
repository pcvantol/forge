from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from forge._version import canonical_version
from forge.runtime import RuntimeBootstrap
from forge.server_runtime import ForgeServerRuntime, existing_instance


class ProjectDagCapabilityTests(TestCase):
    def _runtime(self, root: Path) -> ForgeServerRuntime:
        database = RuntimeBootstrap(data_root=root, forge_version="fixture-version").open()
        database.close()
        credential = root / "server-credential"
        credential.write_text("private-test-bearer\n", encoding="utf-8")
        credential.chmod(0o600)
        return ForgeServerRuntime(
            data_root=root, credential_file=credential, host="127.0.0.1", port=0,
        )

    def test_real_server_binds_supported_subset_to_selected_instance_without_effects(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "selected"
            server = self._runtime(root)
            worker = Thread(target=server.server.serve_forever, daemon=True)
            worker.start()
            url = f"http://127.0.0.1:{server.server.server_port}/v1/project-dag/capability"
            try:
                marker = root / "instance" / "runtime-instance.json"
                database = root / "forge.db"
                before = (marker.read_bytes(), database.read_bytes())
                with patch.object(server.services, "provider_readiness", side_effect=AssertionError("provider")), \
                     patch.object(server.services, "mission_status", side_effect=AssertionError("mission")):
                    for _ in range(2):
                        with self.assertRaises(HTTPError) as denied:
                            urlopen(url, timeout=2)
                        self.assertEqual(denied.exception.code, 401)
                        denied.exception.close()
                        request = Request(url, headers={"Authorization": "Bearer private-test-bearer"})
                        with urlopen(request, timeout=2) as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(response.headers["Cache-Control"], "no-store")
                            body = json.load(response)
                        self.assertEqual(body["contract_version"], "forge-project-dag-http-capability/v1")
                        self.assertEqual(body["instance_id"], existing_instance(root).instance_id)
                        self.assertEqual(body["server_product_version"], canonical_version())
                        self.assertNotIn("runtime_product_version", body)
                        self.assertEqual(body["support"], "SUPPORTED_NOT_READINESS")
                        self.assertEqual(body["authentication"], "INSTANCE_BEARER")
                        self.assertEqual(body["project_scope"], "CONFIGURED_PROJECT_ID_ONLY")
                        self.assertEqual(body["adapter"], "HTTP")
                        self.assertEqual(body["operations"], [
                            {"method": "GET", "path": "/v1/projects"},
                            {"method": "GET", "path": "/v1/projects/{project_id}/roadmap"},
                        ])
                        for field in (
                            "project_mission_attribution", "project_capability_graph",
                            "candidate_and_expected_views",
                        ):
                            self.assertEqual(body[field], "UNAVAILABLE")
                        self.assertTrue(body["read_only"])
                        contract = json.loads((Path(__file__).parents[1] / "forge" / "api" /
                                               "server-openapi-v1.json").read_text(encoding="utf-8"))
                        fields = contract["components"]["schemas"]["ProjectDagCapability"]["properties"]
                        self.assertEqual(set(body), set(fields))
                        for name, definition in fields.items():
                            if "const" in definition:
                                self.assertEqual(body[name], definition["const"])
                        self.assertNotIn("private-test-bearer", json.dumps(body))
                        self.assertNotIn(str(root), json.dumps(body))
                self.assertEqual((marker.read_bytes(), database.read_bytes()), before)
                self.assertEqual(server.api.handle(
                    "POST", "/v1/project-dag/capability", "Bearer private-test-bearer",
                ).status, 404)
                self.assertEqual(server.api.handle(
                    "GET", "http://elsewhere/v1/project-dag/capability", "Bearer private-test-bearer",
                ).status, 400)
            finally:
                server.server.shutdown()
                server.server.server_close()
                worker.join(timeout=2)

    def test_replaced_root_cannot_rebind_capability_to_another_instance(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            selected = base / "selected"
            other = base / "other"
            server = self._runtime(selected)
            other_server = self._runtime(other)
            other_id = existing_instance(other).instance_id
            other_server.server.server_close()
            try:
                selected.rename(base / "parked")
                selected.symlink_to(other, target_is_directory=True)
                response = server.api.handle(
                    "GET", "/v1/project-dag/capability", "Bearer private-test-bearer",
                )
                self.assertEqual(response.status, 503)
                self.assertEqual(response.body["error"]["code"], "INSTANCE_UNAVAILABLE")
                self.assertNotIn(other_id, json.dumps(response.body))
            finally:
                server.server.server_close()
