"""Structural validation for the derived V1 implementation DAG."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]


class DagTests(unittest.TestCase):
    def test_dag_is_complete_acyclic_and_traces_ep_gates(self):
        graph = json.loads((ROOT / "docs/architecture/forge-v1-implementation-dag.json").read_text())
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual("DERIVED", graph["authority"])
        self.assertEqual("ENGINEERING_PLATFORM", graph["ep_node_authority"])
        self.assertEqual(len(nodes), len(graph["nodes"]))
        external = set(graph["external_gates"])
        for node in nodes.values():
            self.assertTrue(node["dor"] and node["dod"] and node["human_gates"])
            self.assertTrue(set(node["external_gates"]).issubset(external))
            self.assertTrue(set(node["predecessors"]).issubset(nodes))
        details = {detail["id"]: detail for detail in graph["external_gate_details"]}
        self.assertEqual(external, set(details))
        for gate in ("EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1", "EP::ENGINEERING_CONTRACT_FOUNDATION_V1_QUALIFIED"):
            detail = details[gate]
            self.assertEqual("engineering-platform", detail["owner"])
            self.assertTrue(detail["producer_capability"])
            self.assertTrue(detail["qualification_gate"])
            self.assertTrue(detail["prerequisite_trace"])
            self.assertTrue(detail["source_provenance"]["ep_main_sha"])
            self.assertTrue(detail["source_provenance"]["observed_at"])
            self.assertEqual("HISTORICAL_SOURCE_PIN", detail["source_provenance"]["observation_classification"])
            self.assertEqual("RESOLVE_FRESH_EP_ORIGIN_MAIN", detail["source_provenance"]["current_status_resolution"])
        seen, active = set(), set()
        def visit(key):
            self.assertNotIn(key, active)
            if key not in seen:
                active.add(key)
                for predecessor in nodes[key]["predecessors"]:
                    visit(predecessor)
                active.remove(key)
                seen.add(key)
        for key in nodes:
            visit(key)


if __name__ == "__main__":
    unittest.main()
