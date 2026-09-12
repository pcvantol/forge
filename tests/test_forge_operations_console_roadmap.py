"""Offline guards for the documentary, non-executable Operations Console DAG."""
from graphlib import TopologicalSorter
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "docs/roadmap/forge-operations-console-v1.json"


class ForgeOperationsConsoleRoadmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))

    def test_graph_remains_documentary_and_outside_first_e2e_path(self):
        self.assertEqual(self.graph["capability"], "FORGE::OPERATIONS_CONSOLE_V1")
        self.assertEqual(self.graph["authority"], "DOCUMENTARY")
        self.assertEqual(self.graph["priority_lane"], "POST_AUTONOMY")
        for flag in ("executable", "authorizes_execution", "first_e2e_prerequisite"):
            self.assertIs(self.graph[flag], False)
        self.assertEqual(self.graph["status"], "PLANNED")

    def test_unique_forge_nodes_have_valid_acyclic_dependencies(self):
        nodes = self.graph["nodes"]
        expected = {f"FOC-{number}" for number in range(7)} | {"FOC-Q"}
        self.assertEqual(len(nodes), len(expected))
        by_id = {node["id"]: node for node in nodes}
        self.assertEqual(set(by_id), expected)
        for node in nodes:
            self.assertEqual(node["owner"], "forge")
            self.assertEqual(node["status"], "PLANNED")
            self.assertTrue(node["completion_evidence"])
            self.assertEqual(len(node["depends_on"]), len(set(node["depends_on"])))
            self.assertNotIn(node["id"], node["depends_on"])
            self.assertTrue(set(node["depends_on"]) <= expected)
        ordered = tuple(TopologicalSorter({n["id"]: n["depends_on"] for n in nodes}).static_order())
        self.assertEqual(set(ordered), expected)
        for node_id in ("FOC-3", "FOC-4", "FOC-5"):
            self.assertEqual(set(by_id[node_id]["depends_on"]), {"FOC-1", "FOC-2"})
        self.assertEqual(set(by_id["FOC-Q"]["depends_on"]), {"FOC-3", "FOC-4", "FOC-5", "FOC-6"})

    def test_all_five_requested_sections_are_documented(self):
        self.assertEqual(self.graph["sections"], [
            "local_host_components", "logs", "configuration", "active_missions", "historical_missions",
        ])
        architecture = (ROOT / self.graph["architecture"]).read_text(encoding="utf-8")
        for number, title in enumerate(("Local host components", "Logs", "Configuration", "Active Missions", "Historical Missions"), 1):
            self.assertIn(f"### {number}. {title}", architecture)

    def test_scoped_roadmap_table_matches_json_dependencies(self):
        text = (ROOT / self.graph["scoped_roadmap"]).read_text(encoding="utf-8")
        rows = {}
        for line in text.splitlines():
            if line.startswith("| FOC-"):
                columns = [value.strip() for value in line.strip("|").split("|")]
                rows[columns[0]] = set(re.findall(r"FOC-(?:\d+|Q)", columns[2]))
        self.assertEqual(rows, {n["id"]: set(n["depends_on"]) for n in self.graph["nodes"]})
        for milestone in self.graph["milestones"]:
            self.assertTrue(set(milestone["requires"]) <= set(rows))

    def test_console_docs_are_reachable_and_local_links_exist(self):
        paths = [self.graph[key] for key in ("architecture", "scoped_roadmap", "canonical_roadmap")]
        paths += ["docs/architecture/FORGE_V1_IMPLEMENTATION_DAG.md", "docs/architecture/FORGE_SERVER_DEPLOYMENT_TARGET.md"]
        for path in paths:
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("FORGE_OPERATIONS_CONSOLE_V1.md", text)
        # Validate links in the new documents only; existing unrelated docs retain their own checks.
        for key in ("architecture", "scoped_roadmap"):
            path = ROOT / self.graph[key]
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" not in target:
                    self.assertTrue((path.parent / target.split("#", 1)[0]).resolve().is_file(), target)


    def test_shared_status_shell_footer_requirements_have_existing_node_owners(self):
        requirements = self.graph["shared_requirements"]
        expected = {"FOC-STATUS", "FOC-SHELL", "FOC-FOOTER"}
        self.assertEqual(len(requirements), len(expected))
        self.assertEqual({r["id"] for r in requirements}, expected)
        nodes = {n["id"]: n for n in self.graph["nodes"]}
        read_only = self.graph["milestones"][0]
        self.assertEqual(set(read_only["shared_requirements"]), expected)
        architecture = (ROOT / self.graph["architecture"]).read_text(encoding="utf-8")
        roadmap = (ROOT / self.graph["scoped_roadmap"]).read_text(encoding="utf-8")
        for requirement in requirements:
            self.assertEqual(requirement["status"], "PLANNED")
            owners = set(requirement["delivered_by"])
            self.assertTrue(owners)
            self.assertTrue(owners <= set(read_only["requires"]))
            self.assertIn(requirement["id"], architecture)
            self.assertIn(requirement["id"], roadmap)
            for owner in owners | {"FOC-Q"}:
                self.assertIn(requirement["id"], nodes[owner]["shared_requirements"])
        for node in nodes.values():
            self.assertTrue(set(node["shared_requirements"]) <= expected)

    def test_platform_status_contract_does_not_invent_global_blockers(self):
        status = next(r for r in self.graph["shared_requirements"] if r["id"] == "FOC-STATUS")
        self.assertEqual(status["subject"], "FORGE_SERVER_INSTANCE")
        self.assertEqual(status["groups"], ["platform", "access", "ingress", "execution"])
        self.assertEqual(set(status["aggregate_states"]), {"HEALTHY", "DEGRADED", "BLOCKED", "UNKNOWN"})
        self.assertEqual(status["aggregation"], "BACKEND_OWNED_SCOPED_REQUIRED_DEPENDENCIES")
        for flag in ("optional_unused_relay_blocks_local_operation", "empty_queue_is_failure",
                     "platform_health_is_execution_authority"):
            self.assertIs(status[flag], False)

    def test_basic_controls_and_live_footer_remain_presentation_only(self):
        requirements = {r["id"]: r for r in self.graph["shared_requirements"]}
        shell, footer = requirements["FOC-SHELL"], requirements["FOC-FOOTER"]
        self.assertEqual(shell["controls"], [
            "platform_status_indicator", "manual_refresh", "project_selector", "language_selector",
            "theme_toggle", "expand_collapse", "automatic_refresh_toggle",
        ])
        self.assertIs(shell["presentation_only"], True)
        self.assertIs(shell["refresh_pause_is_mission_pause"], False)
        self.assertIs(shell["project_selection_changes_runtime_binding"], False)
        self.assertEqual(footer["fields"], [
            "product_name", "installed_product_version", "last_live_status_signal",
            "connection_mode_state", "freshness",
        ])
        self.assertIs(footer["serverpush_required"], False)
        self.assertIs(footer["render_time_is_live_signal"], False)


if __name__ == "__main__":
    unittest.main()
