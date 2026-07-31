import json
import tempfile
import unittest
from pathlib import Path

from forge.planning import PlanningDocumentLoader, PlanningRegistry


ROOT = Path(__file__).resolve().parents[1]


class EngineeringPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.example = json.loads((ROOT / "examples" / "planning.example.json").read_text())
        self.loader = PlanningDocumentLoader({"engineering-kb"})

    def test_valid_goal_and_increment_proposal_are_loaded(self) -> None:
        report = self.loader.load(self.example)
        self.assertTrue(report.valid)
        assert report.document is not None
        self.assertEqual(report.document.goals[0].id, "planning-foundation")
        self.assertEqual(report.document.increment_proposals[0].risk_level.value, "low")
        self.assertEqual(report.document.plans[0].status.value, "proposed")

    def test_dependency_validation_rejects_unknown_and_cyclic_dependencies(self) -> None:
        unknown = json.loads(json.dumps(self.example))
        unknown["increment_proposals"][0]["dependencies"] = ["missing-proposal"]
        unknown_report = self.loader.load(unknown)
        self.assertFalse(unknown_report.valid)
        self.assertIn("increment_reference", [issue.code for issue in unknown_report.issues])

        cyclic = json.loads(json.dumps(self.example))
        cyclic["increment_proposals"].append({
            **cyclic["increment_proposals"][0],
            "id": "planning-validation",
            "dependencies": ["planning-contracts"],
        })
        cyclic["increment_proposals"][0]["dependencies"] = ["planning-validation"]
        cyclic_report = self.loader.load(cyclic)
        self.assertFalse(cyclic_report.valid)
        self.assertIn("proposal_dependency_cycle", [issue.code for issue in cyclic_report.issues])

        out_of_order = json.loads(json.dumps(self.example))
        out_of_order["increment_proposals"].append({
            **out_of_order["increment_proposals"][0],
            "id": "planning-validation",
            "dependencies": [],
        })
        out_of_order["plans"][0]["ordered_increment_ids"] = ["planning-contracts", "planning-validation"]
        out_of_order["plans"][0]["dependencies"] = [{"increment_id": "planning-contracts", "depends_on": ["planning-validation"]}]
        out_of_order_report = self.loader.load(out_of_order)
        self.assertFalse(out_of_order_report.valid)
        self.assertIn("dependency_order", [issue.code for issue in out_of_order_report.issues])

    def test_evidence_references_are_preserved_and_known_sources_are_checked(self) -> None:
        report = self.loader.load(self.example)
        assert report.document is not None
        evidence = report.document.goals[0].evidence_references[0]
        self.assertEqual(evidence.source_id, "engineering-kb")
        self.assertEqual(evidence.source_version, "2026.07")

        invalid = json.loads(json.dumps(self.example))
        invalid["goals"][0]["evidence_references"][0]["source_id"] = "unknown-source"
        invalid_report = self.loader.load(invalid)
        self.assertFalse(invalid_report.valid)
        self.assertIn("evidence_source_reference", [issue.code for issue in invalid_report.issues])

    def test_invalid_planning_documents_are_rejected_and_registry_is_local(self) -> None:
        invalid = json.loads(json.dumps(self.example))
        del invalid["goals"][0]["desired_outcome"]
        report = self.loader.load(invalid)
        self.assertFalse(report.valid)
        self.assertIn("required", [issue.code for issue in report.issues])

        valid = self.loader.load(self.example)
        assert valid.document is not None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planning.json"
            registry = PlanningRegistry(path, self.loader)
            registry.save(valid.document)
            self.assertEqual(registry.load(), valid.document)
            persisted = json.loads(path.read_text())
            self.assertEqual(persisted["registry_version"], "0.5")


if __name__ == "__main__":
    unittest.main()
