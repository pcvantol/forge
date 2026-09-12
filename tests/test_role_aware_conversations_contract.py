"""Offline documentary guards; not runtime or live-advisor qualification."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "docs/roadmap/role-aware-conversations-v1.json"


class ConversationDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = json.loads(GRAPH.read_text(encoding="utf-8"))
        cls.design = (ROOT / cls.graph["architecture"]).read_text(encoding="utf-8")
        cls.roadmap = (ROOT / cls.graph["roadmap"]).read_text(encoding="utf-8")

    def test_design_only_boundary(self):
        self.assertEqual("DOCUMENTARY_ONLY", self.graph["authority"])
        self.assertFalse(self.graph["executable"])
        self.assertFalse(self.graph["first_canary_prerequisite"])
        self.assertEqual("Forge", self.graph["owner"])

    def test_three_advice_modes_do_not_grant_authority(self):
        self.assertEqual(["BUSINESS", "ARCHITECTURE", "UX"], self.graph["advisor_kinds"])
        expected = {
            "CHAT_TRANSCRIPT_IS_AUTHORITY", "ADVISOR_KIND_IS_AUTHORIZATION_ROLE",
            "UX_REVIEW_REQUIRED_FOR_EVERY_MISSION", "CHAT_DIRECT_REPOSITORY_MUTATION",
            "CHAT_CREATES_EXECUTION_AUTHORITY", "ROLE_CHAT_REQUIRED_FOR_FIRST_CANARY",
        }
        self.assertEqual(expected, set(self.graph["invariants"]))
        for key, value in self.graph["invariants"].items():
            self.assertIs(value, False)
            self.assertIn(key + " = FALSE", self.design)

    def test_dependencies_are_explicit_and_acyclic(self):
        nodes = {node["id"]: node for node in self.graph["nodes"]}
        self.assertEqual(len(nodes), len(self.graph["nodes"]))
        self.assertEqual(5, len(nodes))
        external = self.graph["external_predecessors"]
        seen, active = set(), set()
        def visit(key):
            self.assertNotIn(key, active)
            if key in seen:
                return
            active.add(key)
            node = nodes[key]
            self.assertEqual("PLANNED", node["status"])
            self.assertTrue(node["qualification"])
            self.assertTrue(set(node["predecessors"]).issubset(nodes))
            self.assertTrue(set(node["external_predecessors"]).issubset(external))
            for parent in node["predecessors"]:
                visit(parent)
            active.remove(key)
            seen.add(key)
        for key in nodes:
            visit(key)
        for gate in external.values():
            self.assertTrue(gate["owner"] and gate["reference"] and gate["required_contract"])

    def test_scenario_catalogue_and_later_outer_loop(self):
        self.assertEqual([f"RC-T{i:02}" for i in range(1, 21)], self.graph["scenario_ids"])
        self.assertEqual(["RC-T18"], self.graph["deferred_scenario_ids"])
        for scenario in self.graph["scenario_ids"]:
            self.assertIn(scenario, self.design)
        self.assertIn("RC-T18", self.roadmap)

    def test_roadmap_links_every_local_node_and_preserves_parent_boundary(self):
        self.assertEqual("PRODUCTIZATION_REFINEMENT_NOT_EXECUTION_EDGE", self.graph["parent_relationship"])
        for node in self.graph["nodes"]:
            self.assertIn(node["id"], self.roadmap)
            self.assertNotIn(self.graph["parent_reference"], node["predecessors"])
        self.assertIn("ROLE_AWARE_CONVERSATIONS_V1.md", self.roadmap)
        self.assertIn("MAY_HAVE_HAPPENED", self.design)

    def test_existing_f6_and_canary_edges_are_not_expanded(self):
        parent = json.loads((ROOT / "docs/architecture/forge-v1-implementation-dag.json").read_text())
        nodes = {node["id"]: node for node in parent["nodes"]}
        self.assertEqual("docs/roadmap/role-aware-conversations-v1.json", nodes["F6"]["documentary_refinement"])
        self.assertEqual(["F2"], nodes["F6"]["predecessors"])
        self.assertEqual(["F3", "F4", "F6"], nodes["F10"]["predecessors"])
        self.assertEqual(["BUSINESS_DECISION", "ARCHITECTURE_DECISION"], nodes["F6"]["human_gates"])


if __name__ == "__main__":
    unittest.main()
