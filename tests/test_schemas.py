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
    "evidence-reference-0.5.schema.json",
    "engineering-goal-0.5.schema.json",
    "engineering-increment-proposal-0.5.schema.json",
    "engineering-plan-0.5.schema.json",
    "planning-document-0.5.schema.json",
    "engineering-proposal-0.6.schema.json",
    "engineering-prompt-artifact-0.7.schema.json",
    "phase-completion-1.0.schema.json",
)


class SchemaContractTests(unittest.TestCase):
    def test_every_foundation_schema_is_versioned_json(self) -> None:
        for name in SCHEMAS:
            document = json.loads((ROOT / "schemas" / name).read_text())
            self.assertIn("$id", document)
            self.assertTrue(any(version in document["$id"] for version in ("0.2", "0.3", "0.5", "0.6", "0.7", "1.0")))

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

    def test_planning_schemas_remain_declarative_and_versioned(self) -> None:
        document = json.loads((ROOT / "schemas" / "planning-document-0.5.schema.json").read_text())
        proposal = json.loads((ROOT / "schemas" / "engineering-increment-proposal-0.5.schema.json").read_text())
        self.assertEqual(document["properties"]["document_type"]["const"], "forge.engineering_planning")
        self.assertEqual(document["properties"]["schema_version"]["const"], "0.5")
        self.assertEqual(proposal["properties"]["risk_level"]["enum"], ["low", "medium", "high"])

    def test_engineering_proposal_schema_is_governed_and_versioned(self) -> None:
        proposal = json.loads((ROOT / "schemas" / "engineering-proposal-0.6.schema.json").read_text())
        self.assertEqual(proposal["properties"]["schema_version"]["const"], "0.6")
        self.assertEqual(proposal["properties"]["status"]["enum"], ["DRAFT", "PROPOSED", "APPROVED", "EXECUTED"])

    def test_prompt_artifact_schema_is_provider_independent_and_versioned(self) -> None:
        artifact = json.loads((ROOT / "schemas" / "engineering-prompt-artifact-0.7.schema.json").read_text())
        self.assertEqual(artifact["properties"]["schema_version"]["const"], "0.7")
        self.assertEqual(artifact["properties"]["status"]["enum"], ["DRAFT", "READY"])
        self.assertNotIn("provider", artifact["properties"]["execution_instructions"])

    def test_phase_completion_schema_requires_reproducible_evidence(self) -> None:
        document = json.loads((ROOT / "schemas" / "phase-completion-1.0.schema.json").read_text())
        self.assertEqual(document["properties"]["schema_version"]["const"], "1.0")
        self.assertEqual(document["$defs"]["evidence"]["properties"]["outcome"]["enum"], ["PASS", "FAIL"])
        self.assertEqual(document["$defs"]["reference"]["required"], ["kind", "source_id", "source_version", "locator", "content_digest"])


if __name__ == "__main__":
    unittest.main()
