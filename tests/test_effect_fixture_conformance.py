"""EP 2.3.110 installed HTTP captures stay byte and schema pinned in Forge."""
from __future__ import annotations

from unittest.mock import patch
import unittest

from forge.qualification import effect_fixture_conformance as producer


class EffectFixtureConformanceTests(unittest.TestCase):
    def test_all_five_installed_producer_captures_and_schemas(self):
        receipt = producer.source_receipt()
        self.assertEqual(receipt["producer_source_sha"], producer.PRODUCER_SOURCE)
        observed = [producer.validate_capture(name) for name in producer.CAPTURES]
        self.assertEqual(len(observed), 5)
        self.assertEqual({item["mode"] for item in observed}, {
            "READ_ONLY_ASSESSMENT", "DOCUMENTATION_ONLY", "ARCHITECTURE_DESIGN_ONLY",
            "BOUNDED_REPOSITORY_CHANGE",
        })
        self.assertTrue(all(item["qualified"] and item["review_count"] == 2 for item in observed))
        self.assertEqual({item["delivery"] for item in observed}, {"EVIDENCE_ONLY", "GIT"})

    def test_changed_manifest_or_capture_bytes_cannot_be_relabelled_as_producer_proof(self):
        actual = producer._bytes
        with patch.object(producer, "_bytes", side_effect=lambda name: b"{}" if name == "manifest.json" else actual(name)):
            with self.assertRaisesRegex(producer.EffectFixtureError, "manifest bytes"):
                producer.source_receipt()
        changed = producer.CAPTURES[0]
        with patch.object(producer, "_bytes", side_effect=lambda name: b"{}" if name == changed else actual(name)):
            with self.assertRaisesRegex(producer.EffectFixtureError, "bytes changed"):
                producer.validate_capture(changed)


if __name__ == "__main__":
    unittest.main()
