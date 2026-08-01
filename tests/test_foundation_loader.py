import json
import unittest
from pathlib import Path
from unittest.mock import patch

from forge.foundation import FoundationDocumentLoader


ROOT = Path(__file__).resolve().parents[1]


class FoundationDocumentLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = FoundationDocumentLoader()
        self.example = json.loads((ROOT / "examples" / "foundation.example.json").read_text())

    def test_loads_the_packaged_foundation_example_into_immutable_models(self) -> None:
        report = self.loader.load_path(ROOT / "examples" / "foundation.example.json")
        self.assertTrue(report.valid)
        self.assertEqual(report.document_version, "0.3")
        self.assertEqual(report.document.workspace.id, "forge-workspace")
        self.assertEqual(report.document.repository_catalog.id, "forge-catalog")
        self.assertIsInstance(report.issues, tuple)

    def test_reports_invalid_json_without_including_document_content(self) -> None:
        report = self.loader.load('{"private": "do-not-repeat"')
        self.assertFalse(report.valid)
        self.assertEqual(report.issues[0].stage, "parse")
        self.assertNotIn("do-not-repeat", report.issues[0].message)

    def test_rejects_unsupported_document_versions_before_schema_validation(self) -> None:
        document = dict(self.example)
        document["schema_version"] = "9.9"
        report = self.loader.load(document)
        self.assertEqual(report.issues[0].stage, "version")
        self.assertEqual(report.issues[0].code, "unsupported_version")

    def test_schema_errors_are_stably_ordered(self) -> None:
        document = dict(self.example)
        document["workspace"] = {"schema_version": "0.2"}
        report = self.loader.load(document)
        self.assertFalse(report.valid)
        self.assertEqual(report.issues, tuple(sorted(report.issues)))
        self.assertTrue(all(issue.stage == "schema" for issue in report.issues))

    def test_cross_reference_and_duplicate_role_failures_are_reported(self) -> None:
        document = json.loads(json.dumps(self.example))
        document["workspace"]["repository_catalog_id"] = "missing-catalog"
        document["repository_catalog"]["entries"]["supporting"] = ["missing-repository", "forge-repository"]
        report = self.loader.load(document)
        self.assertFalse(report.valid)
        self.assertEqual([issue.code for issue in report.issues], ["catalog_reference", "duplicate_repository_role", "repository_reference"])

    def test_duplicate_component_ids_are_rejected_after_schema_validation(self) -> None:
        document = json.loads(json.dumps(self.example))
        document["repositories"].append(dict(document["repositories"][0]))
        report = self.loader.load(document)
        self.assertFalse(report.valid)
        self.assertEqual(report.issues[0].code, "duplicate_id")

    def test_uses_only_the_packaged_schema_allow_list(self) -> None:
        document = json.loads(json.dumps(self.example))
        document["$schema"] = "https://untrusted.example/schema.json"
        report = self.loader.load(document)
        self.assertFalse(report.valid)
        self.assertEqual(report.issues[0].code, "additional_property")

    def test_invalid_document_never_reaches_model_construction(self) -> None:
        document = dict(self.example)
        document["workspace"] = {"schema_version": "0.2"}
        with patch.object(self.loader, "_construct", wraps=self.loader._construct) as construct:
            report = self.loader.load(document)
        self.assertFalse(report.valid)
        construct.assert_not_called()

    def test_validation_report_is_human_readable_and_deterministic(self) -> None:
        example_path = ROOT / "examples" / "foundation.example.json"
        report = self.loader.load_path(example_path)
        self.assertEqual(
            report.to_text(),
            "\n".join(
                [
                    "Forge Foundation Validation",
                    "",
                    "Status: PASS",
                    "",
                    f"Document: {example_path}",
                    "Schema: v0.3",
                    "Models: Workspace, RepositoryCatalog, KnowledgeSource, Capability",
                    "Errors: 0",
                    "Warnings: 0",
                ]
            ),
        )
        invalid = self.loader.load_path(ROOT / "missing.foundation.json")
        self.assertIn(f"Document: {ROOT / 'missing.foundation.json'}", invalid.to_text())
        self.assertIn("Suggested correction: Provide a readable local Foundation Document path.", invalid.to_text())


if __name__ == "__main__":
    unittest.main()
