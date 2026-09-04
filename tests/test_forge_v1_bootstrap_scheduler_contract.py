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
        required = {"write_scopes", "read_scopes", "exclusive_scopes", "integration_scopes", "dor", "pre_merge", "merge_gate", "post_merge"}
        for node in contract["node_contracts"].values():
            self.assertEqual(required, set(node))
            self.assertTrue(node["write_scopes"] and node["exclusive_scopes"])
            self.assertTrue(node["dor"] and node["pre_merge"] and node["post_merge"])
        self.assertIn("APPROVED_MISSION_BOUND", contract["dispatch_requires"])
        self.assertIn("OPERATOR_BOOTSTRAP_AUTHORIZATION", contract["dispatch_requires"])


if __name__ == "__main__":
    unittest.main()
