from __future__ import annotations

import json
from pathlib import Path
import unittest

from forge.server_runtime import SERVER_ROUTE_INVENTORY


API = Path(__file__).parents[1] / "forge" / "api"


class ForgeServerApiContractTests(unittest.TestCase):
    def test_openapi_and_postman_exactly_match_server_route_inventory(self) -> None:
        openapi = json.loads((API / "server-openapi-v1.json").read_text(encoding="utf-8"))
        postman = json.loads((API / "server-postman-v1.json").read_text(encoding="utf-8"))

        openapi_routes = {
            (method.upper(), path)
            for path, operations in openapi["paths"].items()
            for method in operations
            if method.lower() in {"get", "post", "put", "patch", "delete"}
        }
        postman_routes = set()
        for item in postman["item"]:
            request = item["request"]
            raw = request["url"]["raw"].removeprefix("{{baseUrl}}")
            raw = raw.replace("{{missionId}}", "{mission_id}")
            postman_routes.add((request["method"].upper(), raw))

        expected = set(SERVER_ROUTE_INVENTORY)
        self.assertEqual(openapi_routes, expected)
        self.assertEqual(postman_routes, expected)
        self.assertEqual(openapi["openapi"], "3.1.0")
        self.assertEqual(openapi["components"]["securitySchemes"]["bearerAuth"]["scheme"], "bearer")

    def test_server_contract_has_no_ep_proxy_or_implicit_initialization_route(self) -> None:
        paths = {path for _method, path in SERVER_ROUTE_INVENTORY}
        self.assertNotIn("/v1/ep/{path}", paths)
        self.assertNotIn("/v1/instance/init", paths)
        self.assertTrue(all(not path.startswith("/v1/proxy") for path in paths))


if __name__ == "__main__":
    unittest.main()
