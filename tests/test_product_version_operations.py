"""Regression coverage for the repository-owned product version operation."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "advance_product_version.py"
SPEC = importlib.util.spec_from_file_location("advance_product_version", SCRIPT)
assert SPEC and SPEC.loader
versioning = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(versioning)


def repository(tmp_path: Path, version: str = "2.3.0") -> tuple[Path, str]:
    (tmp_path / "product-version.json").write_text(
        json.dumps({"schema_version": 1, "product": "forge", "version": version}) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "product-version.json"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "base"],
        check=True,
    )
    return tmp_path, subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()


def apply(root: Path, head: str, operation: str = "version-op-0001", lineage: str = "refs/heads/feature/a") -> str:
    return versioning.advance(
        root, "patch", expected_version="2.3.0", operation_id=operation,
        expected_head=head, event_lineage=lineage,
    )


class ProductVersionOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root, self.head = repository(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_operation_receipt_makes_retry_idempotent(self) -> None:
        self.assertEqual(apply(self.root, self.head), "2.3.1")
        self.assertEqual(apply(self.root, self.head), "2.3.1")
        self.assertEqual(json.loads((self.root / "product-version.json").read_text())["version"], "2.3.1")
        self.assertTrue((self.root / ".github/product-version-operations/version-op-0001.json").exists())

    def test_changed_meaning_for_operation_id_conflicts(self) -> None:
        apply(self.root, self.head)
        with self.assertRaisesRegex(RuntimeError, "conflicting reuse"):
            apply(self.root, self.head, lineage="refs/heads/feature/other")

    def test_docs_only_operation_does_not_allocate_or_allow_reclassification(self) -> None:
        self.assertEqual(
            versioning.advance(self.root, "none", expected_version="2.3.0", operation_id="version-docs-0001",
                               expected_head=self.head, event_lineage="increment:docs-1"),
            "2.3.0",
        )
        self.assertEqual(json.loads((self.root / "product-version.json").read_text())["version"], "2.3.0")
        with self.assertRaisesRegex(RuntimeError, "conflicting reuse"):
            versioning.advance(self.root, "patch", expected_version="2.3.0", operation_id="version-docs-0001",
                               expected_head=self.head, event_lineage="increment:docs-1")

    def test_stale_expected_head_writes_neither_receipt_nor_version(self) -> None:
        (self.root / "unrelated").write_text("changed", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "unrelated"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "changed"], check=True)
        with self.assertRaisesRegex(RuntimeError, "expected Git head"):
            apply(self.root, self.head)
        self.assertEqual(json.loads((self.root / "product-version.json").read_text())["version"], "2.3.0")
        self.assertFalse((self.root / ".github/product-version-operations").exists())

    def test_staged_receipt_recovers_without_second_bump(self) -> None:
        target = "2.3.1"
        receipt = self.root / ".github/product-version-operations/version-op-0001.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps(versioning._operation_input("version-op-0001", self.head, "2.3.0", "patch", None, "refs/heads/feature/a", versioning.POLICY_REVISION, target)), encoding="utf-8")
        self.assertEqual(apply(self.root, self.head), target)
        self.assertEqual(json.loads((self.root / "product-version.json").read_text())["version"], target)

    def test_apply_requires_explicit_operation_provenance(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "apply requires"):
            versioning.advance(self.root, "patch")

    def test_release_candidate_binds_exact_branch_head_and_version(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "branch", "-m", "release-2.3.0"], check=True)
        self.assertEqual(
            versioning.verify_release_candidate(self.root, "release-2.3.0", self.head, "2.3.0"), "2.3.0"
        )
        with self.assertRaisesRegex(RuntimeError, "branch version"):
            versioning.verify_release_candidate(self.root, "release-2.3.1", self.head, "2.3.0")
        with self.assertRaisesRegex(RuntimeError, "approved exact"):
            versioning.verify_release_candidate(self.root, "release-2.3.0", "0" * 40, "2.3.0")

    def test_release_candidate_rejects_branch_only_authority(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "branch", "-m", "release-2.3.1"], check=True)
        with self.assertRaisesRegex(RuntimeError, "canonical product version"):
            versioning.verify_release_candidate(self.root, "release-2.3.1", self.head, "2.3.1")
