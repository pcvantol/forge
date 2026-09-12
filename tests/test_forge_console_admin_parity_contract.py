"""Offline documentation guards; these do not qualify an implemented console."""
from graphlib import TopologicalSorter
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DAG = ROOT / "docs/roadmap/forge-console-admin-parity-v1.json"


class ForgeConsoleAdminParityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = json.loads(DAG.read_text(encoding="utf-8"))
        cls.parent = json.loads((ROOT / cls.graph["parent_graph"]).read_text(encoding="utf-8"))
        cls.contract = (ROOT / cls.graph["architecture"]).read_text(encoding="utf-8")
        cls.roadmap = (ROOT / cls.graph["scoped_roadmap"]).read_text(encoding="utf-8")

    def test_discoverable_documentary_extension_preserves_parent(self):
        g, p = self.graph, self.parent
        self.assertEqual(p["admin_parity_graph"], DAG.relative_to(ROOT).as_posix())
        self.assertEqual(p["admin_parity_contract"], g["architecture"])
        self.assertEqual(p["required_qualification_extensions"], {"FOC-Q": ["FCP-Q"]})
        for graph in (g, p):
            self.assertEqual(graph["status"], "PLANNED")
            self.assertEqual(graph["priority_lane"], "POST_AUTONOMY")
            self.assertEqual(graph["authority"], "DOCUMENTARY")
            for key in ("executable", "authorizes_execution", "first_e2e_prerequisite"):
                self.assertIs(graph[key], False)
        self.assertEqual(len(p["nodes"]), 8)
        self.assertEqual(len(p["configuration_work_packages"]), 9)
        self.assertEqual({r["id"] for r in p["shared_requirements"]},
                         {"FOC-STATUS", "FOC-SHELL", "FOC-FOOTER"})

    def test_subdag_is_acyclic_and_matches_roadmap(self):
        nodes = self.graph["work_packages"]
        by_id = {node["id"]: node for node in nodes}
        self.assertEqual(len(nodes), len(by_id))
        self.assertEqual(len(nodes), 9)
        parent_ids = {node["id"] for node in self.parent["nodes"]}
        for node in nodes:
            self.assertEqual(node["status"], "PLANNED")
            self.assertEqual(node["owner"], "forge")
            self.assertTrue(set(node["depends_on"]) <= set(by_id))
            self.assertTrue(set(node["delivered_by"]) <= parent_ids)
            self.assertNotIn(node["id"], node["depends_on"])
            self.assertTrue(node["completion_evidence"])
        dependencies = {node["id"]: node["depends_on"] for node in nodes}
        self.assertEqual(set(TopologicalSorter(dependencies).static_order()), set(by_id))
        rows = {}
        for line in self.roadmap.splitlines():
            if line.startswith("| FCP-"):
                cells = [value.strip() for value in line.strip("|").split("|")]
                rows[cells[0]] = set(re.findall(r"FCP-[A-Z0-9-]+", cells[1]))
        self.assertEqual(rows, {key: set(value) for key, value in dependencies.items()})

    def test_github_inventory_does_not_invent_runtime_auth(self):
        g = self.graph["github_assessment"]
        self.assertEqual(g["scope"], "INSPECTED_INSTALLED_MISSION_COMPOSITION")
        self.assertIs(g["standalone_runtime_provider_observed"], False)
        self.assertIs(g["release_workflow_uses_gh"], True)
        self.assertIs(g["local_login_required_by_this_design"], False)
        self.assertIs(g["future_direct_consumer_requires_admin_contract"], True)
        self.assertIn("gh release view/download/create", self.contract)
        self.assertIn("not a Forge Server provider session", self.contract)

    def test_all_log_functions_and_immutable_boundary(self):
        logs = self.graph["log_contract"]
        self.assertEqual(logs["functions"], ["search", "filter", "sort", "select", "copy", "download", "delete"])
        self.assertEqual(logs["levels"], ["DEBUG", "INFO", "WARNING", "ERROR"])
        self.assertEqual(logs["retention_days_for_eligible_diagnostics"], [30, 60, 90, 120, 180, 360])
        self.assertIs(logs["filter_before_pagination"], True)
        self.assertIs(logs["deletion_requires_eligibility"], True)
        self.assertIs(logs["immutable_journal_delete_allowed"], False)
        self.assertIs(logs["diagnostic_level_suppresses_mandatory_audit"], False)
        for title in ("Search", "Filter", "Sort", "Select", "Copy", "Download", "Delete"):
            self.assertIn(f"| {title} |", self.contract)
        self.assertIn("hiding rows is not deletion", self.contract)

    def test_exact_five_locales_and_complementary_admin(self):
        self.assertEqual(self.graph["locales"], ["en", "nl", "de", "fr", "es"])
        self.assertIs(self.graph["workspace_replaced"], False)
        self.assertIn("not a new React/Vue SPA", self.contract)
        self.assertIn("Workspace retains project/portfolio", self.contract)
        self.assertIn("No browser-native alert/confirm/prompt", self.contract)

    def test_pairing_reuses_contract_without_trusting_discovery(self):
        p = self.graph["pairing"]
        self.assertEqual(p["descriptor"], "forge-platform.instance-descriptor/v1")
        for key in ("same_service_contract_as_installer", "automatic_after_authorized_intent", "separate_hosts_required"):
            self.assertIs(p[key], True)
        for key in ("discovery_is_authorization", "manual_token_copy_required", "silent_retarget_allowed", "peer_sql_allowed", "full_installer_required"):
            self.assertIs(p[key], False)
        self.assertIn("short-lived", self.contract)
        self.assertIn("single-use ceremony", self.contract)

    def test_coverage_and_playwright_requirements_are_truthful(self):
        q = self.graph["quality"]
        for key in ("forge_backend_aggregate_minimum", "forge_backend_per_module_minimum",
                    "forge_frontend_aggregate_minimum", "forge_frontend_per_module_minimum"):
            self.assertGreater(q[key], 80.0)
        self.assertEqual(q["ep_observed_python_aggregate_minimum"], 80.0)
        self.assertIs(q["ep_frontend_coverage_claimed"], False)
        self.assertEqual(q["frontend_metrics"], ["statements", "lines", "functions", "branches"])
        self.assertIs(q["unmeasured_production_is_failure"], True)
        self.assertEqual((q["playwright_shards"], q["ci_workers_per_shard"], q["ci_retries"], q["ci_max_failures"]), (4, 1, 1, 3))
        self.assertEqual(q["local_batch_deadline_seconds"], 300)
        self.assertIs(q["playwright_is_code_coverage"], False)

    def test_source_pins_and_required_navigation(self):
        for sha in self.graph["source_pins"].values():
            self.assertRegex(sha, r"^[0-9a-f]{40}$")
            self.assertIn(sha, self.contract)
        for key in ("architecture", "parent_graph", "scoped_roadmap"):
            self.assertTrue((ROOT / self.graph[key]).is_file())
        self.assertIn("FORGE_CONSOLE_EP_PARITY_AND_PAIRING_V1.md", self.roadmap)
        self.assertIn("forge-console-admin-parity-v1.json", self.roadmap)


if __name__ == "__main__":
    unittest.main()
