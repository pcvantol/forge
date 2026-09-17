"""Behavioral coverage for terminal reconciliation of an existing Forge release."""

import importlib.util
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).parents[1] / "scripts" / "reconcile_existing_release.py"
SPEC = importlib.util.spec_from_file_location("forge_existing_release_reconciliation", SCRIPT)
assert SPEC and SPEC.loader
reconcile = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reconcile
SPEC.loader.exec_module(reconcile)


class ExistingReleaseReconciliationTests(unittest.TestCase):
    version = "2.7.22"
    source = "a" * 40
    original_run_id = "35254063298"
    controller = "b" * 40
    reconciliation_run = "40000000000"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.wheel = self.root / f"forge_autonomy-{self.version}-py3-none-any.whl"
        self.sdist = self.root / f"forge_autonomy-{self.version}.tar.gz"
        metadata = f"Metadata-Version: 2.4\nName: forge-autonomy\nVersion: {self.version}\n\n"
        with zipfile.ZipFile(self.wheel, "w") as archive:
            archive.writestr(f"forge_autonomy-{self.version}.dist-info/METADATA", metadata)
        with tarfile.open(self.sdist, "w:gz") as archive:
            data = metadata.encode()
            member = tarfile.TarInfo(f"forge_autonomy-{self.version}/PKG-INFO")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        self.wheel_digest = sha256(self.wheel.read_bytes()).hexdigest()
        self.sdist_digest = sha256(self.sdist.read_bytes()).hexdigest()
        self.hashes = self.root / "SHA256SUMS"
        self.hashes.write_text(
            f"{self.wheel_digest}  dist/{self.wheel.name}\n"
            f"{self.sdist_digest}  dist/{self.sdist.name}\n",
            encoding="utf-8",
        )
        self.operation = reconcile.ReleaseOperation.create(
            operation_id=f"forge-release-{self.version}-{self.source}",
            version=self.version,
            policy_revision="forge-bootstrap-release-cadence-v2",
            source_revision=self.source,
            artifacts={
                "wheel": "sha256:" + self.wheel_digest,
                "sdist": "sha256:" + self.sdist_digest,
            },
        ).transition("QUALIFIED", evidence={
            "exact_main_sha": self.source,
            "qualification": "forge-production-distribution",
            "artifact_digests": {
                f"dist/{self.wheel.name}": "sha256:" + self.wheel_digest,
                f"dist/{self.sdist.name}": "sha256:" + self.sdist_digest,
            },
        })
        self.qualified_bytes = self.operation_bytes(self.operation)
        self.qualified_name = f"forge-release-qualified-{self.version}-{self.source}.json"
        self.assets = self.root / "assets"
        self.assets.mkdir()
        (self.assets / self.qualified_name).write_bytes(self.qualified_bytes)
        self.release = self.release_document([self.qualified_name])
        self.run = {
            "databaseId": int(self.original_run_id),
            "status": "completed",
            "conclusion": "failure",
            "headSha": self.source,
            "event": "workflow_dispatch",
            "workflowName": "Forge production release",
            "jobs": [
                {"name": "build-and-qualify", "conclusion": "success"},
                {"name": "publish-pypi", "conclusion": "success"},
                {"name": "registry-readback-and-published-evidence", "conclusion": "failure"},
                {"name": "record-release-complete", "conclusion": "skipped"},
            ],
        }

    @staticmethod
    def operation_bytes(operation: object) -> bytes:
        return (json.dumps(reconcile.asdict(operation), sort_keys=True, separators=(",", ":")) + "\n").encode()

    def release_document(self, names: list[str], *, draft: bool = True, database_id: int = 123) -> dict[str, object]:
        assets = []
        for name in names:
            content = (self.assets / name).read_bytes()
            assets.append({
                "name": name,
                "state": "uploaded",
                "size": len(content),
                "digest": "sha256:" + sha256(content).hexdigest(),
            })
        return {
            "tagName": f"forge-v{self.version}",
            "targetCommitish": self.source,
            "databaseId": database_id,
            "id": "RE_kwDOReleaseNode",
            "apiUrl": "https://api.github.com/repos/example/forge/releases/123",
            "isDraft": draft,
            "isPrerelease": False,
            "isImmutable": False,
            "assets": assets,
        }

    @property
    def release_identity(self) -> dict[str, object]:
        return reconcile.validate_release_inventory(
            self.release, version=self.version, source_revision=self.source,
        )["release"]

    def validate(self, **changes: object) -> dict[str, object]:
        values = {
            "run_document": self.run,
            "qualified_action": self.qualified_bytes,
            "qualified_release": self.qualified_bytes,
            "hashes": self.hashes,
            "wheel": self.wheel,
            "sdist": self.sdist,
            "version": self.version,
            "source_revision": self.source,
            "original_run_id": self.original_run_id,
            "controller_source": self.controller,
            "reconciliation_run_id": self.reconciliation_run,
            "release_document": self.release,
        }
        values.update(changes)
        return reconcile.validate_reconciliation(**values)

    def published_operation(self) -> object:
        return self.operation.transition("PUBLISHED", evidence=self.validate())

    def test_exact_historical_release_and_fresh_registry_bytes_are_accepted(self) -> None:
        evidence = self.validate()
        self.assertEqual(evidence["readback"], "PASS")
        self.assertEqual(evidence["product_source_revision"], self.source)
        self.assertEqual(evidence["release_controller_source"], self.controller)
        self.assertEqual(evidence["github_release"], self.release_identity)

    def test_wrong_artifact_or_unexpected_original_failure_is_rejected(self) -> None:
        self.wheel.write_bytes(b"different registry bytes")
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "registry artifacts"):
            self.validate()
        changed_run = {**self.run, "conclusion": "success"}
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "conclusion"):
            self.validate(run_document=changed_run)

    def test_changed_release_receipt_and_release_object_are_rejected(self) -> None:
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "differs"):
            self.validate(qualified_release=self.qualified_bytes + b" ")
        changed = self.release_document([self.qualified_name], database_id=124)
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "identity changed"):
            reconcile.validate_same_release(
                self.release, changed, version=self.version, source_revision=self.source,
            )

    def test_inventory_rejects_unknown_duplicate_and_incomplete_lineage(self) -> None:
        unknown = {**self.release, "assets": [*self.release["assets"], {
            "name": "forge_autonomy-2.7.22-py3-none-any.whl", "state": "uploaded",
            "size": 1, "digest": "sha256:" + "0" * 64,
        }]}
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "unexpected asset"):
            reconcile.validate_release_inventory(unknown, version=self.version, source_revision=self.source)
        duplicate = {**self.release, "assets": [*self.release["assets"], self.release["assets"][0]]}
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "duplicate"):
            reconcile.validate_release_inventory(duplicate, version=self.version, source_revision=self.source)
        complete = f"forge-release-complete-{self.version}-{self.source}.json"
        (self.assets / complete).write_text("{}", encoding="utf-8")
        incomplete = self.release_document([self.qualified_name, complete])
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "published predecessor"):
            reconcile.validate_release_inventory(incomplete, version=self.version, source_revision=self.source)
        prerelease = {**self.release, "isPrerelease": True}
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "must not be a prerelease"):
            reconcile.validate_release_inventory(prerelease, version=self.version, source_revision=self.source)

    def test_release_asset_bytes_and_symlinks_are_fail_closed(self) -> None:
        self.assertEqual(
            reconcile.validate_release_assets(
                self.release, self.assets, version=self.version, source_revision=self.source,
            )["assets"],
            [self.qualified_name],
        )
        (self.assets / self.qualified_name).write_bytes(b"changed")
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "differs"):
            reconcile.validate_release_assets(
                self.release, self.assets, version=self.version, source_revision=self.source,
            )
        (self.assets / self.qualified_name).unlink()
        (self.assets / self.qualified_name).symlink_to(self.hashes)
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "unsafe"):
            reconcile.validate_release_assets(
                self.release, self.assets, version=self.version, source_revision=self.source,
            )

    def test_followup_lineage_is_stable_across_resume_controller_runs(self) -> None:
        published = self.published_operation()
        published_path = self.root / "published.json"
        published_path.write_bytes(self.operation_bytes(published))
        complete_evidence = reconcile.completion_evidence(
            version=self.version, original_run_id=self.original_run_id,
            controller_source="c" * 40, reconciliation_run_id="50000000000",
            source_revision=self.source, release_identity=self.release_identity,
        )
        complete = published.transition("RELEASE_COMPLETE", evidence=complete_evidence)
        complete_path = self.root / "complete.json"
        complete_path.write_bytes(self.operation_bytes(complete))
        result = reconcile.validate_followup_receipts(
            published_path=published_path, pending_path=None, complete_path=complete_path,
            original_run_id=self.original_run_id, release_identity=self.release_identity,
        )
        self.assertEqual(result["state"], "RELEASE_COMPLETE")
        self.assertEqual(result["controller_runs"], [
            {"phase": "publication", "run_id": self.reconciliation_run,
             "controller_source": self.controller},
            {"phase": "completion", "run_id": "50000000000",
             "controller_source": "c" * 40},
        ])
        self.assertEqual(
            reconcile.validate_followup_receipts(
                published_path=published_path, pending_path=None, complete_path=complete_path,
                original_run_id=self.original_run_id, release_identity=self.release_identity,
            ), result,
        )

    def test_cleanup_pending_is_durable_and_may_advance_to_complete(self) -> None:
        published = self.published_operation()
        published_path = self.root / "published.json"
        published_path.write_bytes(self.operation_bytes(published))
        pending_evidence = reconcile.cleanup_pending_evidence(
            original_run_id=self.original_run_id, controller_source="c" * 40,
            reconciliation_run_id="50000000000", source_revision=self.source,
            release_identity=self.release_identity, failed_targets=["published-assets"],
        )
        pending = published.transition("CLEANUP_PENDING", evidence=pending_evidence)
        pending_path = self.root / "pending.json"
        pending_path.write_bytes(self.operation_bytes(pending))
        result = reconcile.validate_followup_receipts(
            published_path=published_path, pending_path=pending_path, complete_path=None,
            original_run_id=self.original_run_id, release_identity=self.release_identity,
        )
        self.assertEqual(result["state"], "CLEANUP_PENDING")
        complete = pending.transition("RELEASE_COMPLETE", evidence=reconcile.completion_evidence(
            version=self.version, original_run_id=self.original_run_id,
            controller_source="d" * 40, reconciliation_run_id="60000000000",
            source_revision=self.source, release_identity=self.release_identity,
        ))
        complete_path = self.root / "complete.json"
        complete_path.write_bytes(self.operation_bytes(complete))
        result = reconcile.validate_followup_receipts(
            published_path=published_path, pending_path=pending_path, complete_path=complete_path,
            original_run_id=self.original_run_id, release_identity=self.release_identity,
        )
        self.assertEqual(result["state"], "RELEASE_COMPLETE")

    def test_new_publication_and_controller_run_bind_exact_current_provenance(self) -> None:
        qualified = self.root / "qualified.json"
        qualified.write_bytes(self.qualified_bytes)
        publication = self.root / "publication.json"
        publication.write_text(json.dumps(self.validate()), encoding="utf-8")
        result = reconcile.validate_new_publication_evidence(
            qualified_path=qualified, publication_path=publication,
            original_run_id=self.original_run_id, release_identity=self.release_identity,
            controller_source=self.controller, reconciliation_run_id=self.reconciliation_run,
        )
        self.assertEqual(result["controller_runs"][0]["run_id"], self.reconciliation_run)
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "this controller run"):
            reconcile.validate_new_publication_evidence(
                qualified_path=qualified, publication_path=publication,
                original_run_id=self.original_run_id, release_identity=self.release_identity,
                controller_source="f" * 40, reconciliation_run_id=self.reconciliation_run,
            )
        run = {
            "databaseId": int(self.reconciliation_run), "headSha": self.controller,
            "event": "workflow_dispatch", "workflowName": "Forge existing release reconciliation",
            "status": "completed", "conclusion": "success",
        }
        self.assertEqual(
            reconcile.validate_controller_run(
                run, run_id=self.reconciliation_run, controller_source=self.controller,
            )["controller_source"], self.controller,
        )
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "headSha"):
            reconcile.validate_controller_run(
                run, run_id=self.reconciliation_run, controller_source="f" * 40,
            )

    def test_followup_receipt_hydration_is_monotonic_and_idempotent(self) -> None:
        evidence_root = self.root / "evidence"
        store = reconcile.ReleaseOperationStore(evidence_root)
        store.acquire(self.operation.operation_id)
        try:
            store.save(self.operation)
        finally:
            store.release(self.operation.operation_id)
        published = self.published_operation()
        receipt = self.root / "published.json"
        receipt.write_bytes(self.operation_bytes(published))
        self.assertEqual(
            reconcile.hydrate_followup_receipt(evidence_root, self.operation.operation_id, receipt), published,
        )
        self.assertEqual(
            reconcile.hydrate_followup_receipt(evidence_root, self.operation.operation_id, receipt), published,
        )
        receipt.write_bytes(self.qualified_bytes)
        with self.assertRaisesRegex(reconcile.ExistingReleaseReconciliationError, "invalid operation or state"):
            reconcile.hydrate_followup_receipt(evidence_root, self.operation.operation_id, receipt)

    def test_workflow_separates_artifact_execution_from_release_mutation(self) -> None:
        workflow = Path(".github/workflows/forge-existing-release-reconcile.yml").read_text(encoding="utf-8")
        validation = workflow.split("  validate-existing-release:", 1)[1].split(
            "  smoke-existing-release:", 1,
        )[0]
        smoke = workflow.split("  smoke-existing-release:", 1)[1].split(
            "  reconcile-existing-release:", 1,
        )[0]
        mutation = workflow.split("  reconcile-existing-release:", 1)[1]
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("contents: read", validation)
        self.assertNotIn("pip install", validation)
        self.assertNotIn("installed_smoke", validation)
        self.assertNotIn("gh release edit", validation)
        self.assertIn("forge-registry-wheel", smoke)
        self.assertIn("env -i HOME=", smoke)
        self.assertIn("--no-index --no-deps", smoke)
        self.assertNotIn("upload-artifact", smoke)
        self.assertNotIn("publication.json", smoke)
        self.assertIn("contents: write", mutation)
        self.assertNotIn("pip install", mutation)
        self.assertNotIn("registry-readback", mutation)
        self.assertNotIn("forge-release-smoke-", mutation)
        self.assertIn("validate-publication", mutation)
        self.assertIn("validate-controller-run", mutation)
        self.assertIn("verify_controller_runs", mutation)
        self.assertIn("same-release", mutation)
        self.assertIn("validate-assets", mutation)
        self.assertIn("$tag^{commit}", mutation)
        self.assertIn("--mark-cleanup-pending", mutation)
        self.assertIn("--wheel-digest", mutation)
        self.assertIn("--complete", mutation)
        self.assertNotIn("gh-action-pypi-publish", workflow)
        self.assertNotIn("twine upload", workflow)
        self.assertNotIn("python3 -m build", workflow)
        self.assertNotIn("git tag", workflow)


if __name__ == "__main__":
    unittest.main()
