"""Offline design/DAG guards, not launchd or Tailnet operational qualification."""
from graphlib import TopologicalSorter
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "docs/roadmap/forge-console-hosting-v1.json"


class ForgeConsoleHostingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = json.loads(GRAPH.read_text(encoding="utf-8"))
        cls.parent = json.loads((ROOT / cls.graph["parent_graph"]).read_text(encoding="utf-8"))
        cls.contract = (ROOT / cls.graph["architecture"]).read_text(encoding="utf-8")
        cls.roadmap = (ROOT / cls.graph["scoped_roadmap"]).read_text(encoding="utf-8")

    def test_extension_is_reachable_without_reclassifying_existing_work(self):
        g, p = self.graph, self.parent
        self.assertEqual(p["hosting_graph"], GRAPH.relative_to(ROOT).as_posix())
        self.assertEqual(p["hosting_contract"], g["architecture"])
        self.assertEqual(p["hosting_roadmap"], g["scoped_roadmap"])
        self.assertEqual(p["required_qualification_extensions"], {"FCP-Q": ["FSH-Q"]})
        self.assertEqual(len(p["work_packages"]), 9)
        for graph in (g, p):
            self.assertEqual(graph["capability"], "FORGE::OPERATIONS_CONSOLE_V1")
            self.assertEqual(graph["authority"], "DOCUMENTARY")
            self.assertEqual(graph["status"], "PLANNED")
            self.assertEqual(graph["priority_lane"], "POST_AUTONOMY")
            for key in ("executable", "authorizes_execution", "first_e2e_prerequisite"):
                self.assertIs(graph[key], False)

    def test_internal_and_inherited_edges_are_acyclic_and_explicit(self):
        nodes = self.graph["work_packages"]
        by_id = {n["id"]: n for n in nodes}
        self.assertEqual(len(nodes), 7)
        self.assertEqual(len(by_id), len(nodes))
        deps = {n["id"]: n["depends_on"] for n in nodes}
        for n in nodes:
            self.assertEqual(n["owner"], "forge")
            self.assertEqual(n["status"], "PLANNED")
            self.assertTrue(n["completion_evidence"])
            self.assertTrue(set(n["depends_on"]) <= set(by_id))
            self.assertNotIn(n["id"], n["depends_on"])
            self.assertEqual(len(n["depends_on"]), len(set(n["depends_on"])))
        self.assertEqual(set(TopologicalSorter(deps).static_order()), set(by_id))
        inherited = set(self.graph["inherited_contracts"])
        combined = {key: list(value) for key, value in deps.items()}
        for key, value in self.graph["external_prerequisites"].items():
            self.assertIn(key, by_id)
            self.assertTrue(set(value) <= inherited)
            self.assertNotIn("FCP-Q", value)
            combined[key].extend(value)
        combined["FCP-Q"] = ["FSH-Q"]
        combined["FOC-Q"] = ["FCP-Q"]
        tuple(TopologicalSorter(combined).static_order())
        rows = {}
        for line in self.roadmap.splitlines():
            if line.startswith("| FSH-"):
                cells = [s.strip() for s in line.strip("|").split("|")]
                rows[cells[0]] = set(re.findall(r"FSH-[A-Z-]+", cells[1]))
        self.assertEqual(rows, {key: set(value) for key, value in deps.items()})

    def test_services_have_one_supervisor_and_distinct_product_roles(self):
        self.assertEqual(self.graph["service_components"], ["forge_server", "operations_console", "dashboard_relay"])
        s = self.graph["supervision"]
        self.assertEqual(s["owner"], "launchd")
        self.assertEqual(s["console_relationship"], "PRODUCT_SUBORDINATE_SEPARATE_JOB")
        self.assertIs(s["double_supervision_allowed"], False)
        self.assertIn("EXPLICIT_NON_ROOT", s["system_mode"])
        self.assertIn("not a child also spawned/restarted by the Server", self.contract)
        self.assertIn("ACTUAL installed account/", self.contract)

    def test_relay_is_required_delivery_but_not_required_local_activation(self):
        r = self.graph["relay"]
        self.assertIs(r["required_v1_deliverable"], True)
        self.assertEqual(r["activation"], "EXPLICIT_OPT_IN")
        self.assertEqual(r["listener"], "QUALIFIED_TAILNET_ADDRESS_ONLY")
        self.assertEqual(r["port"], "FORGE_OWNED_CONSOLE_PORT")
        self.assertIs(r["remote_end_to_end_probe_required"], True)
        for key in ("wildcard_fallback_allowed", "ep_relay_reused", "public_funnel_allowed",
                    "tailnet_membership_is_admin_authority", "unused_relay_blocks_local_operation"):
            self.assertIs(r[key], False)
        for phrase in ("port conflicts", "second", "Origin/Host/CSRF", "Never display a fabricated HTTPS URL"):
            self.assertIn(phrase, self.contract)

    def test_all_component_roles_are_documented_without_inventing_processes(self):
        roles = self.graph["required_component_roles"]
        self.assertEqual(len(roles), len(set(roles)))
        self.assertTrue(set(self.graph["service_components"]) <= set(roles))
        for role in roles:
            self.assertIn(f"`{role}`", self.contract)
        for phrase in ("ONE versioned Forge component registry", "Every row opens", "explicitly N/A",
                       "disabled explanations", "NEVER restart EP"):
            self.assertIn(phrase, self.contract)

    def test_restart_is_not_reexecution_or_upgrade(self):
        r = self.graph["restart"]
        for key in ("backend_allowlist_required", "expected_identity_and_revision_required",
                    "durable_operation_id_required", "safe_boundary_required", "same_runtime_readback_required"):
            self.assertIs(r[key], True)
        for key in ("restarts_repeat_provider_generation", "restart_is_upgrade", "restart_resets_budget",
                    "controls_ep_or_tailscale_service"):
            self.assertIs(r[key], False)
        for phrase in ("MAY_HAVE_HAPPENED", "Persist ACCEPTED", "idempotent operation ID",
                       "Expired authority is not renewed", "intentional stop/disable"):
            self.assertIn(phrase, self.contract)

    def test_central_reuses_existing_storage_and_fences_relocation(self):
        c = self.graph["central"]
        self.assertEqual(c["existing_database"], "forge.db")
        self.assertEqual(c["existing_resolver"], "DataRootResolver")
        for key in ("independent_of_ep", "service_root_is_explicit", "relocation_repoints_all_owned_root_references"):
            self.assertIs(c[key], True)
        for key in ("rename_or_migration_required", "console_direct_sql_allowed",
                    "relay_owns_durable_state", "service_home_fallback_allowed"):
            self.assertIs(c[key], False)
        for phrase in ("one canonical Forge storage authority", "No second active installation",
                       "The old root is fenced", "$HOME/Library/Application Support/Forge Server"):
            self.assertIn(phrase, self.contract)

    def test_quality_admin_boundary_and_source_pins_are_retained(self):
        self.assertIs(self.graph["workspace_replaced"], False)
        for sha in self.graph["source_pins"].values():
            self.assertRegex(sha, r"^[0-9a-f]{40}$")
            self.assertIn(sha, self.contract)
        for phrase in ("80.20%", "all four Playwright shards", "en/nl/de/fr/es", "NOT Workspace",
                       "real macOS installed service/account", "not a completed"):
            self.assertIn(phrase, self.contract)

    def test_target_and_central_docs_link_the_new_scoped_plan(self):
        for path in ("docs/architecture/canonical-data-root.md",
                     "docs/architecture/FORGE_SERVER_DEPLOYMENT_TARGET.md"):
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("FORGE_CONSOLE_HOSTING_AND_CENTRAL_V1.md", text)
            self.assertIn("FORGE_CONSOLE_HOSTING_V1.md", text)
        self.assertIn("no-OS-restart", self.roadmap)
        self.assertIn("FOC-Q -> FCP-Q -> FSH-Q", self.roadmap)
        for key in ("parent_graph", "architecture", "scoped_roadmap"):
            self.assertTrue((ROOT / self.graph[key]).is_file())


if __name__ == "__main__":
    unittest.main()
