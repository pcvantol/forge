"""Documentary guards only; do not claim execution of the planned E2E suite."""
from graphlib import TopologicalSorter
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DAG = ROOT / "docs/roadmap/forge-inner-loop-ci-v1.json"


class InnerLoopCIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = json.loads(DAG.read_text(encoding="utf-8"))
        cls.contract = (ROOT / cls.graph["architecture"]).read_text(encoding="utf-8")
        cls.roadmap = (ROOT / cls.graph["scoped_roadmap"]).read_text(encoding="utf-8")

    def test_scope_is_installed_inner_loop_not_console_or_live_authority(self):
        g = self.graph
        self.assertEqual(g["capability"], "FORGE::INNER_LOOP_CI_INTEGRATION_V1")
        self.assertEqual(g["entry"], "MISSION_CANDIDATE")
        self.assertEqual(g["exit"], "EVIDENCE_DERIVED_MISSION_COMPLETION")
        self.assertEqual(g["priority_lane"], "RUNTIME_QUALIFICATION")
        self.assertEqual((g["authority"], g["status"]), ("DOCUMENTARY", "PLANNED"))
        for flag in ("executable", "authorizes_live_execution", "requires_console",
                     "requires_live_canary_completion", "changes_current_live_canary_authority"):
            self.assertIs(g[flag], False)

    def test_seven_unique_nodes_have_valid_acyclic_edges(self):
        nodes = self.graph["nodes"]
        expected = {"FCI-CONTRACT", "FCI-HARNESS", "FCI-EP", "FCI-FLOW",
                    "FCI-RESTART", "FCI-NEGATIVE", "FCI-CI"}
        by_id = {n["id"]: n for n in nodes}
        self.assertEqual(len(nodes), len(expected))
        self.assertEqual(set(by_id), expected)
        for n in nodes:
            self.assertEqual((n["owner"], n["status"]), ("forge", "PLANNED"))
            self.assertTrue(n["completion_evidence"])
            self.assertTrue(set(n["depends_on"]) <= expected)
            self.assertNotIn(n["id"], n["depends_on"])
            self.assertEqual(len(n["depends_on"]), len(set(n["depends_on"])))
        deps = {n["id"]: n["depends_on"] for n in nodes}
        self.assertEqual(set(TopologicalSorter(deps).static_order()), expected)
        self.assertEqual(set(by_id["FCI-FLOW"]["depends_on"]), {"FCI-HARNESS", "FCI-EP"})
        self.assertEqual(set(by_id["FCI-CI"]["depends_on"]), {"FCI-RESTART", "FCI-NEGATIVE"})

    def test_roadmap_dependencies_match_json_exactly(self):
        rows = {}
        for line in self.roadmap.splitlines():
            if line.startswith("| FCI-"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                rows[cells[0]] = set(re.findall(r"FCI-[A-Z-]+", cells[2]))
        self.assertEqual(rows, {n["id"]: set(n["depends_on"]) for n in self.graph["nodes"]})

    def test_scenario_inventory_is_complete_without_claiming_execution(self):
        scenarios = self.graph["scenarios"]
        expected = {f"FIE-{i:02d}" for i in range(1, 17)}
        self.assertEqual(len(scenarios), len(expected))
        self.assertEqual({s["id"] for s in scenarios}, expected)
        table_ids = set(re.findall(r"^\| (FIE-\d{2}) \|", self.contract, re.MULTILINE))
        self.assertEqual(table_ids, expected)
        for scenario in scenarios:
            self.assertIs(scenario["required"], True)
            self.assertEqual(scenario["status"], "PLANNED")
            self.assertTrue(scenario["name"])

    def test_only_external_boundaries_are_simulated(self):
        self.assertEqual(set(self.graph["mocked_boundaries"]), {
            "EP_HTTP_SERVER", "EXTERNAL_LLM_PROCESS_OR_TRANSPORT", "OS_IDENTITY_AND_SECURE_STORE"})
        real = set(self.graph["real_forge_boundaries"])
        self.assertTrue({"CANDIDATE_LIFECYCLE", "GOVERNANCE_AND_AUTHORITY", "MISSION_INTAKE_AND_ALLOCATOR",
                         "PUBLIC_RUNTIME_COMPOSITION", "EP_HTTP_ADAPTER_AND_EVIDENCE_VERIFIER",
                         "DURABLE_STORAGE_AND_RECONCILIATION", "RECOVERY_AND_COMPLETION"} <= real)
        self.assertIs(self.graph["wire_contracts"]["producer_fixture_provenance_required"], True)
        self.assertIn("validated\nindependently of Forge's serializer", self.contract)

    def test_runtime_invariants_do_not_mock_away_authority_or_recovery(self):
        inv = self.graph["invariants"]
        self.assertEqual(inv["actions_at_admission"], 0)
        for flag in ("new_os_process_required_for_restart", "unmet_criterion_required_for_successor"):
            self.assertIs(inv[flag], True)
        for flag in ("candidate_id_string_only_is_full_entry", "simulator_reads_forge_db", "ci_calls_live_provider",
                     "ci_submits_to_live_ep", "ci_mutates_github", "skip_is_pass", "mock_pass_is_live_e2e_pass",
                     "governance_bypass_allowed", "internal_forge_success_path_mocks_allowed"):
            self.assertIs(inv[flag], False)

    def test_ci_requires_installed_gate_evidence_and_release_reuse(self):
        ci = self.graph["planned_ci"]
        self.assertEqual(ci["events"], ["pull_request", "push_main", "workflow_dispatch"])
        self.assertEqual(ci["permissions"], {"contents": "read"})
        self.assertEqual(ci["default_suite_retries"], 0)
        self.assertGreater(ci["target_job_timeout_minutes"], 0)
        for flag in ("installed_wheel_required", "execute_outside_checkout", "merge_blocking_evidence_required",
                     "same_suite_in_release_qualification"):
            self.assertIs(ci[flag], True)
        self.assertIn(ci["check_name"], self.contract)
        self.assertIn("Required scenario absence, skip, timeout", self.contract)
        self.assertIn("This documentation update does not add a new", self.contract)

    def test_plan_is_linked_from_existing_runtime_roadmap(self):
        for key in ("architecture", "scoped_roadmap", "runtime_roadmap"):
            self.assertTrue((ROOT / self.graph[key]).is_file())
        source = self.graph["source_pin"]
        self.assertRegex(source, r"^[0-9a-f]{40}$")
        self.assertIn(source, self.contract)
        runtime_roadmap = (ROOT / self.graph["runtime_roadmap"]).read_text(encoding="utf-8")
        self.assertIn("FORGE_INNER_LOOP_CI_INTEGRATION_V1.md", runtime_roadmap)
        self.assertIn("FORGE_INNER_LOOP_CI_V1.md", runtime_roadmap)
        self.assertIn("forge-inner-loop-ci-v1.json", self.roadmap)


if __name__ == "__main__":
    unittest.main()
