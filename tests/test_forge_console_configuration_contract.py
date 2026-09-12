"""Documentary guards, not qualification of implemented configuration operations."""
from graphlib import TopologicalSorter
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ConsoleConfigurationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = json.loads((ROOT / "docs/roadmap/forge-operations-console-v1.json").read_text(encoding="utf-8"))
        cls.contract = (ROOT / cls.graph["configuration_contract"]).read_text(encoding="utf-8")
        cls.roadmap = (ROOT / cls.graph["scoped_roadmap"]).read_text(encoding="utf-8")
        cls.packages = {package["id"]: package for package in cls.graph["configuration_work_packages"]}

    def test_documentary_scope_does_not_authorize_runtime_operations(self):
        self.assertEqual(self.graph["authority"], "DOCUMENTARY")
        self.assertEqual(self.graph["priority_lane"], "POST_AUTONOMY")
        self.assertEqual(self.graph["status"], "PLANNED")
        for name in ("executable", "authorizes_execution", "first_e2e_prerequisite"):
            self.assertIs(self.graph[name], False)
        self.assertEqual({node["id"] for node in self.graph["nodes"]}, {f"FOC-{n}" for n in range(7)} | {"FOC-Q"})

    def test_packages_have_valid_independent_acyclic_edges_and_owners(self):
        expected = {"FC-CODEX", "FC-PYTHON", "FC-STATE", "FC-EXPORT", "FC-IMPORT", "FC-RELOCATE", "FC-VACUUM", "FC-REFRESH", "FC-TIMEOUT"}
        self.assertEqual(set(self.packages), expected)
        self.assertEqual(len(self.graph["configuration_work_packages"]), len(expected))
        nodes = {node["id"] for node in self.graph["nodes"]}
        for package in self.packages.values():
            self.assertEqual(package["owner"], "forge")
            self.assertEqual(package["status"], "PLANNED")
            self.assertEqual(package["qualified_by"], "FOC-Q")
            self.assertTrue(package["completion_evidence"])
            self.assertTrue(set(package["delivered_by"]) <= nodes)
            self.assertTrue(set(package["depends_on"]) <= expected)
            self.assertNotIn(package["id"], package["depends_on"])
        ordered = tuple(TopologicalSorter({key: value["depends_on"] for key, value in self.packages.items()}).static_order())
        self.assertEqual(set(ordered), expected)
        self.assertEqual(self.packages["FC-IMPORT"]["depends_on"], ["FC-EXPORT"])
        for name in ("FC-RELOCATE", "FC-VACUUM"):
            self.assertEqual(self.packages[name]["depends_on"], ["FC-STATE"])

    def test_markdown_dependency_table_matches_json(self):
        rows = {}
        for line in self.roadmap.splitlines():
            if line.startswith("| FC-"):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                rows[cells[0]] = re.findall(r"FC-[A-Z]+", cells[1])
        self.assertEqual(rows, {key: value["depends_on"] for key, value in self.packages.items()})
        self.assertIn("FORGE_SERVER_CONFIGURATION_AND_DATA_OPERATIONS_V1.md", self.roadmap)
        for package in self.packages:
            self.assertIn(package, self.contract)

    def test_independence_and_safety_flags_are_explicit(self):
        flags = self.graph["configuration_invariants"]
        for name in ("forge_tooling_independent_of_ep", "forge_local_venv_required"):
            self.assertIs(flags[name], True)
        for name in ("exports_include_credentials", "relocation_creates_new_runtime", "restore_resets_budget_or_expiry", "vacuum_interrupts_active_writers", "refresh_invokes_ai", "ep_execution_timeouts_editable_in_forge"):
            self.assertIs(flags[name], False)

    def test_timeout_review_is_pinned_and_separate_from_ep_execution(self):
        self.assertIn("4b5afb909b1f7a1a90abcbdb25a8621f4d542218", self.contract)
        for source in ("provider_security.py", "codex_cli_session.py", "openai_responses.py", "provider_adapter.py", "execution_host_configuration.py"):
            self.assertIn(source, self.contract)
        self.assertIn("Two separate non-generating calls, each `timeout=5`", self.contract)
        self.assertIn("same provider policy applies to both", self.contract)
        self.assertIn("Exclude from Forge-editable provider policy", self.contract)
        self.assertIn("not the whole call wall time", self.contract)

    def test_data_controls_are_guarded_not_ui_only_or_an_installer(self):
        for phrase in ("No backup restore to erase attempts", "recovery-blocked/read-only", "retained non-writer", "not pruning, retention", "does not give the browser SQL/filesystem", "FOC-5 requires the guarded configuration and data operations"):
            self.assertIn(phrase, self.contract)
        self.assertIn("FC-STATE/EXPORT/IMPORT/RELOCATE/VACUUM", " ".join(next(n for n in self.graph["nodes"] if n["id"] == "FOC-5")["completion_evidence"]))

    def test_refresh_examples_are_not_runtime_defaults_or_ai_timers(self):
        self.assertIn("5 seconds / 1 second are presentation examples", self.contract)
        self.assertIn("shipped defaults and effective values", self.contract)
        self.assertIn("do not alter an\nAI timeout", self.contract)
        self.assertIn("one-hour setting is a reference example", self.contract)

    def test_existing_shared_status_requirements_are_preserved(self):
        self.assertEqual({item["id"] for item in self.graph["shared_requirements"]}, {"FOC-STATUS", "FOC-SHELL", "FOC-FOOTER"})
        self.assertEqual(len(self.graph["sections"]), 5)
        self.assertIn("PENDING_PR", self.contract)
        self.assertIn("not assumed merged/installed support", self.contract)


if __name__ == "__main__":
    unittest.main()
