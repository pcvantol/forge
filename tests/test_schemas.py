import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = (
    "workspace.schema.json",
    "repository.schema.json",
    "repository-catalog.schema.json",
    "knowledge-source.schema.json",
    "capability.schema.json",
    "engineering-mode.schema.json",
    "governance-profile.schema.json",
    "foundation-document.schema.json",
)


class SchemaContractTests(unittest.TestCase):
    def test_every_foundation_schema_is_versioned_json(self) -> None:
        for name in SCHEMAS:
            document = json.loads((ROOT / "schemas" / name).read_text())
            self.assertIn("$id", document)
            self.assertTrue("0.2" in document["$id"] or "0.3" in document["$id"])

    def test_foundation_document_has_a_versioned_composite_envelope(self) -> None:
        document = json.loads((ROOT / "schemas" / "foundation-document.schema.json").read_text())
        self.assertEqual(document["properties"]["document_type"]["const"], "forge.foundation_document")
        self.assertEqual(document["properties"]["schema_version"]["const"], "0.3")

    def test_catalog_declares_roles_and_one_canonical_constraint(self) -> None:
        catalog = json.loads((ROOT / "schemas" / "repository-catalog.schema.json").read_text())
        entries = catalog["properties"]["entries"]
        self.assertEqual(entries["required"], ["canonical"])
        self.assertEqual(entries["properties"]["canonical"]["minItems"], 1)
        self.assertEqual(entries["properties"]["canonical"]["maxItems"], 1)

    def test_mode_and_governance_schemas_are_full_catalogs(self) -> None:
        modes = json.loads((ROOT / "schemas" / "engineering-mode.schema.json").read_text())
        profiles = json.loads((ROOT / "schemas" / "governance-profile.schema.json").read_text())
        self.assertEqual(modes["enum"], ["prototype", "managed", "production", "enterprise"])
        self.assertEqual(profiles["enum"], ["solo", "two_person", "team", "enterprise"])

    def test_knowledge_consumption_schema_requires_read_only_evidence_metadata(self) -> None:
        document = json.loads((ROOT / "schemas" / "knowledge-source-0.4.schema.json").read_text())
        self.assertEqual(document["properties"]["schema_version"]["const"], "0.4")
        self.assertEqual(document["properties"]["access_mode"]["const"], "read_only")
        self.assertEqual(document["properties"]["trust_classification"]["enum"], ["certified", "reference", "unverified"])


if __name__ == "__main__":
    unittest.main()
