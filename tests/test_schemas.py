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
)


class SchemaContractTests(unittest.TestCase):
    def test_every_foundation_schema_is_versioned_json(self) -> None:
        for name in SCHEMAS:
            document = json.loads((ROOT / "schemas" / name).read_text())
            self.assertIn("$id", document)
            self.assertIn("0.2", document["$id"])

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


if __name__ == "__main__":
    unittest.main()
