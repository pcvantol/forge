"""Guard the durable release-state ordering expected by production delivery."""

from pathlib import Path
import unittest


class ProductionReleaseWorkflowTests(unittest.TestCase):
    def test_prepublication_operation_binds_exact_artifacts_and_terminal_states(self) -> None:
        workflow = Path(".github/workflows/forge-production-release.yml").read_text(encoding="utf-8")

        qualified_job = workflow.index("  build-and-qualify:")
        published_job = workflow.index("  registry-readback-and-published-evidence:")
        complete_job = workflow.index("  record-release-complete:")
        self.assertLess(qualified_job, published_job)
        self.assertLess(published_job, complete_job)
        self.assertIn("concurrency:", workflow)
        self.assertIn("--prepare-qualified", workflow)
        self.assertIn("--validate-qualified", workflow)
        self.assertIn("--mark-published", workflow)
        self.assertIn("--mark-cleanup-pending", workflow)
        self.assertIn("--complete", workflow)
        self.assertIn("forge-release-$VERSION-$SOURCE_SHA", workflow)
        self.assertIn('gh release create "$TAG" "$QUALIFIED" --draft --target "$SOURCE_SHA"', workflow)
        self.assertIn("Existing PyPI publication has no durable original release receipt", workflow)
        self.assertIn("forge-release-published-$VERSION-$SOURCE_SHA.json", workflow)
        self.assertIn("needs: [release-context, build-and-qualify, publish-pypi, registry-readback-and-published-evidence]", workflow)
        self.assertIn("gh release download \"$TAG\" --pattern \"$PUBLISHED_RECEIPT\" --dir published-readback", workflow)
        self.assertIn("CLEANUP_PENDING", workflow)
        self.assertIn("forge-pending-readback", workflow)
        self.assertIn("durable cleanup-pending receipt does not match PUBLISHED release identity", workflow)
        self.assertIn("Unexpected PyPI identity lookup status", workflow)
        self.assertIn('for artifact in "$wheel" "$sdist"; do', workflow)
        self.assertIn("registry-readback-digests.json", workflow)
        self.assertLess(workflow.index('for target in published-readback published-input/dist; do'), workflow.index("--complete"))
        self.assertLess(workflow.index("durable cleanup-pending receipt"), workflow.index("--complete"))
        self.assertIn("--wheel-digest \"$WHEEL_DIGEST\"", workflow)


if __name__ == "__main__":
    unittest.main()
