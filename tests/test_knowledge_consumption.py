import json
import tempfile
import unittest
from pathlib import Path

from forge.knowledge import KnowledgeSourceRegistry, ReadOnlyKnowledgeConsumer
from forge.models import KnowledgeLifecycle, KnowledgeSource, KnowledgeTrustClassification


def source() -> KnowledgeSource:
    return KnowledgeSource(
        "engineering-kb", "Engineering Knowledge Base", "knowledge_base", "file:///knowledge/engineering",
        metadata={"topic": "governance evidence"}, schema_version="0.4", version="2026.07", reference="baseline-1",
        trust_classification=KnowledgeTrustClassification.CERTIFIED,
    )


class KnowledgeConsumptionTests(unittest.TestCase):
    def test_registers_and_lists_a_versioned_read_only_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = KnowledgeSourceRegistry(Path(directory) / "knowledge-sources.json")
            registry.register(source())
            self.assertEqual([item.id for item in registry.list()], ["engineering-kb"])
            persisted = json.loads((Path(directory) / "knowledge-sources.json").read_text())
            self.assertEqual(persisted["sources"][0]["access_mode"], "read_only")

    def test_rejects_invalid_or_mutable_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = KnowledgeSourceRegistry(Path(directory) / "knowledge-sources.json")
            legacy = KnowledgeSource("legacy", "Legacy", "repository", "file:///legacy")
            with self.assertRaisesRegex(ValueError, "explicit version"):
                registry.register(legacy)
            with self.assertRaisesRegex(ValueError, "read-only"):
                KnowledgeSource("mutable", "Mutable", "repository", "file:///mutable", read_only=False)

    def test_consumption_exposes_evidence_but_never_mutates_the_source(self) -> None:
        item = source()
        result = ReadOnlyKnowledgeConsumer().find(item, "governance", "evidence")
        self.assertEqual(result[0].evidence_location, "file:///knowledge/engineering")
        self.assertEqual(result[0].lifecycle, KnowledgeLifecycle.AVAILABLE)
        self.assertEqual(item.to_dict()["access_mode"], "read_only")

    def test_retrieval_output_is_deterministic(self) -> None:
        consumer = ReadOnlyKnowledgeConsumer()
        first = consumer.find(source(), "evidence governance")
        second = consumer.find(source(), "governance evidence")
        self.assertEqual(first, second)
        self.assertEqual(consumer.find(source(), "unmatched"), ())


if __name__ == "__main__":
    unittest.main()
