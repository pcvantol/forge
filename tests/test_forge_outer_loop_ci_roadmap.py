"""Documentary guards only; these tests do not implement or qualify either E2E."""
from graphlib import TopologicalSorter
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OuterLoopCIRoadmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = json.loads((ROOT / "docs/roadmap/forge-outer-loop-ci-v1.json").read_text())
        cls.contract = (ROOT / cls.graph["architecture"]).read_text()
        cls.roadmap = (ROOT / cls.graph["scoped_roadmap"]).read_text()

    def test_later_documentary_scope_does_not_authorize_execution(self):
        g = self.graph
        self.assertEqual(g["status"], "PLANNED")
        self.assertEqual(g["authority"], "DOCUMENTARY")
        self.assertEqual(g["priority_lane"], "LATER_RUNTIME_QUALIFICATION")
        for key in ("executable", "authorizes_live_execution", "changes_current_live_canary_authority",
                    "requires_console", "requires_installer", "requires_dedicated_server_for_application_suite"):
            self.assertIs(g[key], False)

    def test_five_nodes_and_inner_predecessor_match_the_scoped_dag(self):
        nodes = self.graph["nodes"]
        deps = {n["id"]: n["depends_on"] for n in nodes}
        self.assertEqual(len(nodes), 5)
        self.assertEqual(len(nodes), len(deps))
        for n in nodes:
            self.assertEqual(n["owner"], "forge")
            self.assertEqual(n["status"], "PLANNED")
            self.assertTrue(n["completion_evidence"])
            self.assertTrue(set(n["depends_on"]) <= deps.keys())
            self.assertNotIn(n["id"], n["depends_on"])
        self.assertEqual(set(TopologicalSorter(deps).static_order()), set(deps))
        self.assertEqual(self.graph["external_dependencies"], {"FCO-FLOW": ["FCI-CI"]})
        rows = {}
        for line in self.roadmap.splitlines():
            if line.startswith("| FCO-"):
                cells = [v.strip() for v in line.strip("|").split("|")]
                rows[cells[0]] = set(re.findall(r"FCO-[A-Z-]+", cells[2]))
        self.assertEqual(rows, {k: set(v) for k, v in deps.items()})

    def test_ten_required_families_preserve_governance_and_real_core(self):
        scenarios = self.graph["scenarios"]
        self.assertEqual([s["id"] for s in scenarios], [f"FOE-{i:02}" for i in range(1, 11)])
        for scenario in scenarios:
            self.assertTrue(scenario["required"])
            self.assertEqual(scenario["status"], "PLANNED")
            self.assertIn(f'| {scenario["id"]} |', self.contract)
        inv = self.graph["invariants"]
        self.assertIs(inv["next_mission_requires_current_approvals"], True)
        self.assertIs(inv["new_process_restart_required"], True)
        for key, value in inv.items():
            if key not in {"next_mission_requires_current_approvals", "new_process_restart_required"}:
                self.assertIs(value, False, key)
        self.assertIn("real authorization/approval", self.contract)
        self.assertIn("Do not", self.contract)

    def test_ci_is_installed_required_and_not_a_live_proof_claim(self):
        ci = self.graph["planned_ci"]
        self.assertEqual(ci["events"], ["pull_request", "push_main", "workflow_dispatch"])
        self.assertEqual(ci["permissions"], {"contents": "read"})
        self.assertEqual(ci["default_suite_retries"], 0)
        self.assertEqual(ci["target_job_timeout_minutes"], 10)
        for key in ("installed_wheel_required", "required_scenario_gate", "same_suite_in_release_qualification"):
            self.assertIs(ci[key], True)
        self.assertIn("Mock-CI PASS is NOT live", self.contract)

    def test_server_is_existing_hosting_follow_on_not_new_canary_gate(self):
        server = self.graph["server_follow_on"]
        self.assertEqual(server["after"], "CURRENT_LIVE_E2E_RESULT_REVIEWED")
        self.assertEqual(server["existing_node"], "FSH-SERVICES")
        for key in ("server_requires_console", "server_requires_outer_loop_suite",
                    "already_deployed_server_claimed", "new_executable_dag_authority"):
            self.assertIs(server[key], False)
        self.assertIn("one installed", self.contract)
        self.assertIn("before Console/relay", self.contract)

    def test_navigation_and_both_ci_lines_remain_distinct(self):
        for key in ("architecture", "scoped_roadmap", "canonical_roadmap", "runtime_roadmap"):
            self.assertTrue((ROOT / self.graph[key]).is_file())
        for path in (self.graph["canonical_roadmap"], self.graph["runtime_roadmap"],
                     "docs/roadmap/FORGE_INNER_LOOP_CI_V1.md"):
            self.assertIn("FORGE_OUTER_LOOP_CI_V1.md", (ROOT / path).read_text())
        self.assertEqual(self.graph["entry"], "INNER_LOOP_VERIFIED_MISSION_COMPLETION")
        self.assertEqual(self.graph["exit"], "GOVERNED_NEXT_MISSION_COMPLETION_OR_NO_WORK")
        self.assertIn("Mission Candidate", (ROOT / self.graph["canonical_roadmap"]).read_text())


if __name__ == "__main__":
    unittest.main()
