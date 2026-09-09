"""Behavioral coverage for Forge's pre-publication release journal."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


MODULE = Path(__file__).parents[1] / "scripts" / "release_operation.py"
SPEC = importlib.util.spec_from_file_location("forge_release_operation", MODULE)
assert SPEC and SPEC.loader
release_operation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_operation
SPEC.loader.exec_module(release_operation)


class ForgeReleaseOperationTests(unittest.TestCase):
    source = "a" * 40
    policy = "forge-bootstrap-release-cadence-v2"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.wheel = self.root / "forge_autonomy-2.3.0-py3-none-any.whl"
        self.sdist = self.root / "forge_autonomy-2.3.0.tar.gz"
        self.wheel.write_bytes(b"qualified Forge wheel")
        self.sdist.write_bytes(b"qualified Forge source distribution")
        self.evidence = self.root / "release-evidence"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def expected(self, operation_id: str = "forge-release-0001"):
        return release_operation.ReleaseOperation.create(
            operation_id=operation_id,
            version="2.3.0",
            policy_revision=self.policy,
            source_revision=self.source,
            artifacts={
                "wheel": release_operation.ReleaseOperationStore.artifact_digest(self.wheel),
                "sdist": release_operation.ReleaseOperationStore.artifact_digest(self.sdist),
            },
        )

    def prepare(self, expected=None, qualification=None):
        expected = expected or self.expected()
        return release_operation.prepare_qualified(
            release_operation.ReleaseOperationStore(self.evidence),
            expected,
            qualification or {"exact_main_sha": self.source, "qualification": "PASS"},
        )

    def publish(self, expected=None):
        expected = expected or self.expected()
        self.prepare(expected)
        return release_operation.mark_published(
            release_operation.ReleaseOperationStore(self.evidence),
            expected,
            {"registry": "pypi", "readback": "PASS", "wheel": expected.artifacts["wheel"], "sdist": expected.artifacts["sdist"]},
        )

    def test_retry_is_idempotent_but_changed_artifact_or_qualification_fails_closed(self) -> None:
        first = self.prepare()
        self.assertEqual("QUALIFIED", first.state)
        self.assertEqual(first, self.prepare())
        self.wheel.write_bytes(b"different wheel bytes")
        with self.assertRaisesRegex(release_operation.ReleaseOperationError, "different bytes or provenance"):
            self.prepare()
        self.wheel.write_bytes(b"qualified Forge wheel")
        with self.assertRaisesRegex(release_operation.ReleaseOperationError, "qualified release evidence changed"):
            self.prepare(qualification={"exact_main_sha": self.source, "qualification": "DIFFERENT"})

    def test_release_lock_rejects_concurrent_operations(self) -> None:
        first = release_operation.ReleaseOperationStore(self.evidence)
        first.acquire("forge-release-0001")
        try:
            with self.assertRaisesRegex(release_operation.ReleaseOperationError, "another release operation"):
                release_operation.ReleaseOperationStore(self.evidence).acquire("forge-release-0002")
        finally:
            first.release("forge-release-0001")

    def test_same_version_with_different_bytes_cannot_rewrite_publication_identity(self) -> None:
        self.publish()
        self.sdist.write_bytes(b"same version but altered source distribution")
        competing = self.expected("forge-release-0002")
        self.prepare(competing)
        with self.assertRaisesRegex(release_operation.ReleaseOperationError, "different bytes or provenance"):
            release_operation.mark_published(
                release_operation.ReleaseOperationStore(self.evidence),
                competing,
                {"registry": "pypi", "readback": "PASS", "wheel": competing.artifacts["wheel"], "sdist": competing.artifacts["sdist"]},
            )

    def test_published_and_release_complete_are_distinct_and_resume_safely(self) -> None:
        published = self.publish()
        self.assertEqual("PUBLISHED", published.state)
        cleanup = {"result": "COMPLETE", "temporary_paths": ["registry-readback", "pypi-dist"]}
        completed = release_operation.complete(release_operation.ReleaseOperationStore(self.evidence), self.expected(), cleanup)
        self.assertEqual("RELEASE_COMPLETE", completed.state)
        self.assertEqual(completed, release_operation.complete(
            release_operation.ReleaseOperationStore(self.evidence), self.expected(), cleanup
        ))

    def test_cleanup_pending_is_durable_and_resumes(self) -> None:
        self.publish()
        pending = release_operation.mark_cleanup_pending(
            release_operation.ReleaseOperationStore(self.evidence), self.expected(),
            {"result": "CLEANUP_PENDING", "targets": ["registry-readback"], "error": "permission denied"},
        )
        self.assertEqual("CLEANUP_PENDING", pending.state)
        completed = release_operation.complete(
            release_operation.ReleaseOperationStore(self.evidence), self.expected(),
            {"result": "COMPLETE", "temporary_paths": ["registry-readback"]},
        )
        self.assertEqual("RELEASE_COMPLETE", completed.state)

    def test_changed_publication_receipt_and_nonfinite_evidence_are_rejected(self) -> None:
        self.publish()
        with self.assertRaisesRegex(release_operation.ReleaseOperationError, "receipt changed"):
            release_operation.mark_published(
                release_operation.ReleaseOperationStore(self.evidence), self.expected(),
                {"registry": "pypi", "readback": "DIFFERENT"},
            )
        with self.assertRaisesRegex(release_operation.ReleaseOperationError, "durable JSON evidence"):
            self.expected("forge-release-0003").transition("QUALIFIED", evidence={"value": float("nan")})

    def test_path_with_spaces_and_symlink_has_one_digest_identity(self) -> None:
        spaced = self.root / "release inputs"
        spaced.mkdir()
        artifact = spaced / "forge wheel.whl"
        artifact.write_bytes(b"immutable release artifact")
        linked = self.root / "forge wheel link.whl"
        os.symlink(artifact, linked)
        self.assertEqual(
            release_operation.ReleaseOperationStore.artifact_digest(artifact),
            release_operation.ReleaseOperationStore.artifact_digest(linked),
        )

    def test_unknown_persisted_field_fails_closed(self) -> None:
        self.prepare()
        record = next((self.evidence / "operations").glob("*.json"))
        payload = json.loads(record.read_text(encoding="utf-8"))
        payload["unexpected"] = True
        record.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(release_operation.ReleaseOperationError, "unknown or missing"):
            release_operation.ReleaseOperationStore(self.evidence).load("forge-release-0001")

    def test_digest_only_recovery_keeps_cleanup_transitions_bound_after_artifacts_are_removed(self) -> None:
        expected = self.expected()
        self.publish(expected)
        wheel_digest, sdist_digest = expected.artifacts["wheel"], expected.artifacts["sdist"]
        self.wheel.unlink()
        self.sdist.unlink()
        recovered = release_operation._expected(
            release_operation.argparse.Namespace(
                operation_id=expected.operation_id,
                version=expected.version,
                policy_revision=expected.policy_revision,
                source_revision=expected.source_revision,
                wheel=None,
                sdist=None,
                wheel_digest=wheel_digest,
                sdist_digest=sdist_digest,
            )
        )
        self.assertEqual(expected, recovered)
        self.assertEqual(
            "RELEASE_COMPLETE",
            release_operation.complete(
                release_operation.ReleaseOperationStore(self.evidence), recovered,
                {"result": "COMPLETE", "temporary_paths": ["operation-input"]},
            ).state,
        )

    def test_path_and_digest_or_missing_identity_are_rejected(self) -> None:
        with self.assertRaisesRegex(release_operation.ReleaseOperationError, "either a path or a digest"):
            release_operation._expected(
                release_operation.argparse.Namespace(
                    operation_id="forge-release-0001", version="2.3.0", policy_revision=self.policy,
                    source_revision=self.source, wheel=self.wheel, sdist=self.sdist,
                    wheel_digest="sha256:" + "0" * 64, sdist_digest=None,
                )
            )
        with self.assertRaisesRegex(release_operation.ReleaseOperationError, "requires an exact artifact path or SHA-256"):
            release_operation._expected(
                release_operation.argparse.Namespace(
                    operation_id="forge-release-0001", version="2.3.0", policy_revision=self.policy,
                    source_revision=self.source, wheel=None, sdist=self.sdist,
                    wheel_digest=None, sdist_digest=None,
                )
            )


if __name__ == "__main__":
    unittest.main()
