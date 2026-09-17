"""Offline documentary guards; not runtime, HTTP or browser qualification."""
from graphlib import TopologicalSorter
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "docs/roadmap/live-project-roadmap-management-v1.json"


class LiveProjectRoadmapContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        cls.roadmap = (ROOT / cls.graph["roadmap"]).read_text(encoding="utf-8")
        cls.design = (ROOT / cls.graph["architecture"]).read_text(encoding="utf-8")

    def test_documentary_scope_and_no_execution_authority(self):
        g = self.graph
        self.assertEqual(g["increment"], "LIVE_PROJECT_ROADMAP_MANAGEMENT_V1")
        self.assertEqual((g["authority"], g["status"], g["version_change"]), ("DOCUMENTARY", "PLANNED", "NO_BUMP"))
        for flag in ("executable", "authorizes_execution", "first_live_canary_prerequisite"):
            self.assertIs(g[flag], False)
        self.assertEqual(g["groups"], ["ACTIVE", "APPROVED_PENDING", "CANDIDATES", "EXPECTED", "HISTORY"])
        self.assertEqual(g["release_modes"], ["MANUAL_RELEASE", "AUTO_WHEN_ELIGIBLE"])

    def test_owned_nodes_and_table_edges_are_valid_and_acyclic(self):
        nodes = self.graph["nodes"]
        by_id = {n["id"]: n for n in nodes}
        self.assertEqual(len(nodes), 9)
        self.assertEqual(len(by_id), len(nodes))
        for n in nodes:
            self.assertEqual(n["owner"], "forge")
            self.assertEqual(n["status"], "PLANNED")
            self.assertEqual(n["qualification_evidence"], [])
            self.assertTrue(set(n["depends_on"]) <= set(by_id))
            self.assertNotIn(n["id"], n["depends_on"])
        self.assertEqual(set(TopologicalSorter({n["id"]: n["depends_on"] for n in nodes}).static_order()), set(by_id))
        rows = {}
        for line in self.roadmap.splitlines():
            if line.startswith("| PRM-F-") and len(line.strip("|").split("|")) == 3:
                cells = [x.strip() for x in line.strip("|").split("|")]
                rows[cells[0]] = set(re.findall(r"PRM-F-[A-Z]+", cells[2]))
        self.assertEqual(rows, {n["id"]: set(n["depends_on"]) for n in nodes})

    def test_scenarios_remain_mandatory_future_work(self):
        scenarios = self.graph["scenario_registry"]
        expected = [f"PMT-{i:02}" for i in range(1, 37)]
        self.assertEqual([s["id"] for s in scenarios], expected)
        rows = {}
        for line in self.roadmap.splitlines():
            if re.match(r"^\| PMT-\d{2} \|", line):
                cells = [x.strip() for x in line.strip("|").split("|")]
                self.assertEqual(len(cells), 3)
                self.assertNotIn(cells[0], rows)
                rows[cells[0]] = (cells[1], cells[2])
        self.assertEqual(rows, {s["id"]: (s["requirement"], s["test_layer"]) for s in scenarios})
        for scenario in scenarios:
            self.assertIs(scenario["required"], True)
            self.assertEqual(scenario["status"], "PLANNED")
        self.assertEqual(scenarios[2]["test_layer"], "OUTER_LOOP")
        self.assertIn("FIE-01..28", self.graph["ci_joins"]["inner"])
        self.assertIn("FOE-01..10", self.graph["ci_joins"]["outer"])

    def test_authority_effects_and_projection_boundaries(self):
        inv = self.graph["invariants"]
        for flag in ("approval_implies_execution_authority", "frozen_freezes_action_script",
                     "read_projection_can_start_mission", "workspace_owns_scheduler", "priority_overrides_hard_dependency",
                     "duplicate_activation_allowed", "resume_resets_budget", "read_refresh_invokes_ai",
                     "retired_expectation_deletes_approved_mission", "workspace_close_stops_authorized_work",
                     "mock_ci_pass_is_live_ep_proof", "console_replaces_workspace"):
            self.assertIs(inv[flag], False)
        self.assertIs(inv["automatic_start_requires_explicit_current_authority"], True)
        self.assertIs(inv["snapshot_and_source_freshness_required"], True)
        self.assertEqual(inv["peer_transport"], "AUTHENTICATED_VERSIONED_HTTP_ONLY")

    def test_project_modes_are_planned_and_do_not_approve_work(self):
        g = self.graph
        self.assertEqual(g["project_modes"], ["MISSION_RELEASE", "APPROVED_WORKLIST", "DELEGATED_DEVELOPMENT"])
        self.assertEqual(g["project_mode_default"], {"recommended": "MISSION_RELEASE", "active": None})
        self.assertEqual(set(g["qualification_slices"]), {"manual_release", "approved_worklist", "delegated_development"})
        self.assertFalse(g["refinement"]["mission_3_scope_changed"])
        self.assertFalse(g["refinement"]["activated_policy"])
        for mode in g["project_modes"]:
            self.assertIn(mode, self.design)
            self.assertIn(mode, self.roadmap)
        for sha in g["refinement"]["source_pins"].values():
            self.assertRegex(sha, r"^[0-9a-f]{40}$")
            self.assertIn(sha, self.design)

    def test_project_loop_authority_and_roadmap_publication_invariants(self):
        inv = self.graph["invariants"]
        for flag in ("factual_progress_changes_approved_direction", "recommendation_changes_committed_priority",
                     "ep_finding_grants_mission_authority", "mode_selection_creates_grant",
                     "approved_worklist_auto_adopts_findings", "projection_commit_starts_product_mission",
                     "inner_loop_pass_qualifies_project_loop", "current_acceptance_defect_can_be_hidden_as_backlog"):
            self.assertIs(inv[flag], False)
        self.assertIs(inv["repository_projection_via_authorized_delivery"], True)
        self.assertIs(inv["delegated_decisions_require_explicit_supported_authority"], True)
        by_id = {n["id"]: n for n in self.graph["nodes"]}
        self.assertIn("PRM-F-PRIORITY", by_id["PRM-F-ELIGIBILITY"]["depends_on"])
        self.assertNotIn("PRM-F-DELEGATION", by_id["PRM-F-ACTIVATION"]["depends_on"])
        self.assertIn("PRM-REPOSITORY", self.graph["node_evidence_gates"]["PRM-F-REPOSITORY"])
        self.assertIn("PRM-DELEGATION", self.graph["node_evidence_gates"]["PRM-F-DELEGATION"])

    def test_evidence_requirements_and_navigation(self):
        gates = {g["id"] for g in self.graph["evidence_gates"]}
        for node, required in self.graph["node_evidence_gates"].items():
            self.assertIn(node, {n["id"] for n in self.graph["nodes"]})
            self.assertTrue(set(required) <= gates)
        for sha in self.graph["source_pins"].values():
            self.assertRegex(sha, r"^[0-9a-f]{40}$")
            self.assertIn(sha, self.design)
        for key in ("architecture", "roadmap"):
            self.assertTrue((ROOT / self.graph[key]).is_file())
        self.assertIn("MANUAL_RELEASE", self.design)
        self.assertIn("AUTO_WHEN_ELIGIBLE", self.design)

    def test_parent_navigation_preserves_product_boundary(self):
        parent = json.loads((ROOT / "docs/architecture/forge-v1-implementation-dag.json").read_text(encoding="utf-8"))
        nodes = {n["id"]: n for n in parent["nodes"]}
        self.assertEqual(len(nodes), 11)
        self.assertEqual(nodes["F5"]["predecessors"], ["F2"])
        self.assertEqual(nodes["F5"]["state"], "CONTRACT_ONLY")
        self.assertEqual(nodes["F5"]["documentary_refinement"], GRAPH_PATH.relative_to(ROOT).as_posix())
        self.assertEqual(nodes["F10"]["predecessors"], ["F3", "F4", "F6"])
        self.assertEqual(self.graph["external_node_dependencies"], {})


if __name__ == "__main__":
    unittest.main()
