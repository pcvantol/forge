"""Regression coverage for the bounded Portfolio Intelligence Repository Truth input."""

from __future__ import annotations

from hashlib import sha256
import unittest

from forge.models.architecture_review import ReviewInputKind
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot


def digest(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def evidence(identifier: str) -> RepositoryTruthEvidence:
    return RepositoryTruthEvidence(identifier, "repository_document", "abc123", f"repository://forge/{identifier}", digest(identifier))


class RepositoryTruthSnapshotTests(unittest.TestCase):
    def test_snapshot_is_deterministic_and_exposes_architecture_review_evidence(self) -> None:
        first = RepositoryTruthSnapshot("truth-1", "forge", "abc123", "2026-08-05T19:00:00Z", (evidence("b"), evidence("a")))
        second = RepositoryTruthSnapshot("truth-1", "forge", "abc123", "2026-08-05T19:00:00Z", (evidence("a"), evidence("b")))

        self.assertEqual(first.content_digest, second.content_digest)
        review_evidence = first.as_review_evidence(locator="runtime://repository-truth/truth-1")
        self.assertEqual(review_evidence.kind, ReviewInputKind.REPOSITORY_TRUTH)
        self.assertEqual(review_evidence.content_digest, first.content_digest)
        self.assertEqual(review_evidence.revision, "abc123")

    def test_snapshot_rejects_duplicate_or_unpinned_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            RepositoryTruthSnapshot("truth-1", "forge", "abc123", "2026-08-05T19:00:00Z", (evidence("a"), evidence("a")))
        with self.assertRaisesRegex(ValueError, "sha256"):
            RepositoryTruthEvidence("a", "repository_document", "abc123", "repository://forge/a", "not-a-digest")

    def test_snapshot_does_not_offer_repository_or_recommendation_operations(self) -> None:
        snapshot = RepositoryTruthSnapshot("truth-1", "forge", "abc123", "2026-08-05T19:00:00Z", (evidence("a"),))
        self.assertFalse(hasattr(snapshot, "read_repository"))
        self.assertFalse(hasattr(snapshot, "recommend"))


if __name__ == "__main__":
    unittest.main()
