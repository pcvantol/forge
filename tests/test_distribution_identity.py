"""Regression coverage for the packaged Forge identity and resources."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from forge._version import canonical_version
from forge.foundation.loader import _SCHEMA_DIRECTORY as FOUNDATION_SCHEMAS
from forge.planning.loader import _SCHEMA_DIRECTORY as PLANNING_SCHEMAS


ROOT = Path(__file__).parents[1]


class DistributionIdentityTests(unittest.TestCase):
    def test_pyproject_declares_the_fixed_distribution_import_and_cli_identities(self) -> None:
        content = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "forge-autonomy"', content)
        self.assertIn('forge = "forge.__main__:main"', content)
        self.assertIn('version = {attr = "forge._version.__version__"}', content)

    def test_source_version_is_the_canonical_product_manifest(self) -> None:
        expected = json.loads((ROOT / "product-version.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual(canonical_version(), expected)

    def test_cli_version_is_read_only_and_canonical(self) -> None:
        expected = json.loads((ROOT / "product-version.json").read_text(encoding="utf-8"))["version"]
        result = subprocess.run([sys.executable, "-m", "forge", "--version"], cwd=ROOT, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), expected)
        help_result = subprocess.run([sys.executable, "-m", "forge", "--help"], cwd=ROOT, text=True, capture_output=True, check=True)
        self.assertIn("Forge mission planning", help_result.stdout)

    def test_runtime_schema_resources_are_available_from_both_loaders(self) -> None:
        self.assertTrue((FOUNDATION_SCHEMAS / "foundation-document.schema.json").is_file())
        self.assertTrue((PLANNING_SCHEMAS / "planning-document-0.5.schema.json").is_file())


if __name__ == "__main__":
    unittest.main()
