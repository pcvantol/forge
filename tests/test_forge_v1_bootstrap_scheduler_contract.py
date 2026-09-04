"""Regression coverage for the non-executing V1 bootstrap scheduler contract."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]


class BootstrapSchedulerContractTests(unittest.TestCase):
    def test_contract_covers_each_dag_node_without_claiming_execution_authority(self):
        dag = json.loads((ROOT / "docs/architecture/forge-v1-implementation-dag.json").read_text())
        contract = json.loads((ROOT / "docs/architecture/forge-v1-bootstrap-scheduler-contract.json").read_text())
        self.assertEqual("DERIVED", contract["authority"])
        self.assertEqual("NOT_A_CANONICAL_EXECUTION_LEASE", contract["bootstrap_coordination"])
        self.assertEqual({node["id"] for node in dag["nodes"]}, set(contract["node_contracts"]))
        required = {"write_scopes", "read_scopes", "exclusive_scopes", "integration_scopes", "dor", "pre_merge", "merge_gate", "post_merge", "risk_class"}
        for node in contract["node_contracts"].values():
            self.assertEqual(required, set(node))
            self.assertTrue(node["write_scopes"] and node["exclusive_scopes"])
            self.assertTrue(node["dor"] and node["pre_merge"] and node["post_merge"])
        self.assertIn("APPROVED_MISSION_BOUND", contract["dispatch_requires"])
        self.assertIn("OPERATOR_BOOTSTRAP_AUTHORIZATION", contract["dispatch_requires"])

    def test_governance_contract_rejects_unsafe_bootstrap_progression(self):
        contract = json.loads((ROOT / "docs/architecture/forge-v1-bootstrap-scheduler-contract.json").read_text())
        governance = contract["governance"]
        self.assertEqual("HYBRID", governance["programme_authorization"]["model"])
        self.assertFalse(governance["scope_expansion_auto_accepted"])
        self.assertTrue(governance["programme_authorization"]["record_required"])
        self.assertTrue(governance["programme_authorization"]["stale_on"])
        self.assertEqual(
            {"PROGRAMME_AUTHORIZED", "NODE_IN_AUTHORIZED_SET", "DOR_PASS", "PREDECESSORS_DONE", "EXTERNAL_GATES_PASS", "DEPENDENCY_SAFE", "REPOSITORY_SAFE", "NO_UNRESOLVED_HUMAN_GATE", "AUTHORIZATION_NOT_STALE"},
            set(governance["dispatch_authority"]),
        )
        owner = governance["owner_authorization"]
        self.assertEqual({"NORMAL_LOW", "ELEVATED", "HIGH"}, set(owner["risk_mapping"]))
        self.assertTrue(owner["stale_on_new_commit"])
        self.assertEqual("NO_SEPARATE_OWNER_AUTHORIZATION", owner["applicability"]["NORMAL_LOW"])
        self.assertIn("EXACT_HEAD_OWNER_AUTHORIZATION_REQUIRED", owner["applicability"]["ELEVATED"])
        self.assertIn("SECURITY_REVIEW_REQUIRED", owner["applicability"]["HIGH"])
        self.assertFalse(governance["merge_policy"]["auto_merge"])
        self.assertTrue(governance["merge_policy"]["human_merge_required"])
        self.assertTrue(governance["merge_policy"]["parallel_merge_reevaluation"])
        self.assertFalse(governance["autonomous_repair_enabled"])
        for node in contract["node_contracts"].values():
            self.assertIn(node["risk_class"], owner["risk_mapping"])
            self.assertTrue(node["post_merge"])


if __name__ == "__main__":
    unittest.main()
