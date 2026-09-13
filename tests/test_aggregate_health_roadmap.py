"""Documentary integrity only; these tests do not qualify a health endpoint."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AggregateHealthRoadmapTests(unittest.TestCase):
    def setUp(self):
        self.graph = json.loads((ROOT / "docs/roadmap/forge-http-api-v1.json").read_text())
        self.refinement = next(item for item in self.graph["requirement_refinements"]
                               if item["id"] == "FORGE_AGGREGATE_HEALTH_V1")

    def test_original_lane_and_scenarios_are_retained(self):
        self.assertEqual({n["id"] for n in self.graph["nodes"]},
                         {"FH-CONTRACT", "FH-SERVICES", "FH-HTTP", "FH-CLI", "FH-Q"})
        self.assertEqual(self.graph["scenarios"], [f"HT-{i:02d}" for i in range(1, 8)])

    def test_refinement_uses_existing_nodes(self):
        nodes = {n["id"] for n in self.graph["nodes"]}
        self.assertEqual(set(self.refinement["owning_nodes"]), nodes)
        for node in self.graph["nodes"]:
            self.assertTrue(set(node["depends_on"]) <= nodes)

    def test_no_execution_or_qualification_is_claimed(self):
        self.assertFalse(self.graph["executable"])
        self.assertFalse(self.graph["execution_authority"])
        self.assertFalse(self.refinement["new_canary_predecessor"])
        self.assertEqual(self.refinement["qualification_evidence"], [])
        self.assertEqual(self.refinement["status"], "PLANNED")

    def test_probe_safety_and_existing_drift_gate_are_explicit(self):
        self.assertTrue(self.refinement["api_route_openapi_postman_drift_required"])
        for key in ("public_probe_discloses_secrets", "health_generates_or_mutates",
                    "disabled_optional_relay_blocks_local_readiness"):
            self.assertFalse(self.refinement[key])

    def test_all_cases_are_documented(self):
        text = (ROOT / self.refinement["document"]).read_text()
        cases = self.refinement["qualification_scenarios"]
        self.assertEqual(len(cases), len(set(cases)))
        self.assertEqual(cases, [f"FH-H{i:02d}" for i in range(1, 7)])
        for case in cases:
            self.assertIn(case, text)


if __name__ == "__main__":
    unittest.main()
