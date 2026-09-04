"""Structural validation for the derived V1 implementation DAG."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]

class DagTests(unittest.TestCase):
    def test_dag_is_complete_and_acyclic(self):
        graph = json.loads((ROOT / "docs/architecture/forge-v1-implementation-dag.json").read_text())
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(len(nodes), len(graph["nodes"]))
        external = set(graph["external_gates"])
        for node in nodes.values():
            self.assertTrue(node["owner"] == "Forge")
            self.assertTrue(node["dor"] and node["dod"] and node["human_gates"])
            self.assertTrue(set(node["external_gates"]).issubset(external))
            self.assertTrue(set(node["predecessors"]).issubset(nodes))
            self.assertNotEqual(node["v1_classification"], "POST_V1" if node["id"] != "F8" else "V1_REQUIRED")
        seen, active = set(), set()
        def visit(key):
            self.assertNotIn(key, active)
            if key not in seen:
                active.add(key)
                for predecessor in nodes[key]["predecessors"]: visit(predecessor)
                active.remove(key); seen.add(key)
        for key in nodes: visit(key)

if __name__ == "__main__": unittest.main()
