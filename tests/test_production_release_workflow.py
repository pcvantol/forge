"""Guard the durable release-state ordering expected by production delivery."""

from pathlib import Path
import unittest


class ProductionReleaseWorkflowTests(unittest.TestCase):
    def test_published_evidence_precedes_terminal_completion(self) -> None:
        workflow = Path(".github/workflows/forge-production-release.yml").read_text(encoding="utf-8")

        published_job = workflow.index("  registry-readback-and-published-evidence:")
        complete_job = workflow.index("  record-release-complete:")
        self.assertLess(published_job, complete_job)
        self.assertIn("forge-release-published-$VERSION-$SOURCE_SHA.json", workflow)
        self.assertIn("'state': 'PUBLISHED'", workflow)
        self.assertIn("needs: [release-context, build-and-qualify, publish-pypi, registry-readback-and-published-evidence]", workflow)
        self.assertIn("gh release download \"$TAG\" --pattern \"$PUBLISHED_RECEIPT\" --dir release-evidence", workflow)
        self.assertIn("'state': 'RELEASE_COMPLETE'", workflow)


if __name__ == "__main__":
    unittest.main()
