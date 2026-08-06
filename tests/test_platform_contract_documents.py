"""Regression coverage for Forge's execution-facing document contract."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class PlatformContractDocumentTests(unittest.TestCase):
    def test_root_contract_documents_exist_and_are_cross_linked(self) -> None:
        documents = {
            name: (ROOT / name).read_text(encoding="utf-8")
            for name in (
                "BOOTSTRAP.md",
                "ENGINEERING_METHOD.md",
                "PROMPT_INITIALIZATION.md",
                "AGENTS.md",
            )
        }
        for name in documents:
            self.assertTrue((ROOT / name).is_file())
        self.assertIn("ENGINEERING_METHOD.md", documents["BOOTSTRAP.md"])
        self.assertIn("PROMPT_INITIALIZATION.md", documents["BOOTSTRAP.md"])
        self.assertIn("AGENTS.md", documents["BOOTSTRAP.md"])

    def test_companion_documents_preserve_canonical_ownership_boundary(self) -> None:
        method = (ROOT / "ENGINEERING_METHOD.md").read_text(encoding="utf-8")
        initialization = (ROOT / "PROMPT_INITIALIZATION.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Mission Intake", method)
        self.assertIn("Execution Host", method)
        self.assertIn("Development Host", initialization)
        self.assertIn("capability qualification", initialization)
        self.assertIn("Forge-to-Engineering-Platform boundary", agents)


if __name__ == "__main__":
    unittest.main()
