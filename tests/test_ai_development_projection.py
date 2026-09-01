"""Regression coverage for Forge's offline generic-contract projection."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECTION = ROOT / "docs" / "ai-development"
VALIDATOR = PROJECTION / "validate_projection.py"
SOURCE_SHA = "ec070e399ff4dbd92e760370002995fe4f4d52d6"


def validate(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(directory / "validate_projection.py"),
            "--profile",
            "forge",
            "--source-commit",
            SOURCE_SHA,
            "--extension-identity",
            "FORGE_DEVELOPMENT_EXTENSION",
        ],
        text=True,
        capture_output=True,
        check=False,
    )


class AiDevelopmentProjectionTests(unittest.TestCase):
    def test_canonical_projection_validates_offline(self) -> None:
        result = validate(PROJECTION)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_generated_projection_drift_fails_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / "ai-development"
            shutil.copytree(PROJECTION, copy)
            generated = copy / "GENERATED_PROJECTION.md"
            generated.write_text(generated.read_text() + "\nmanual drift\n")
            result = validate(copy)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("projection drift", result.stderr)

    def test_extension_changes_do_not_invalidate_generated_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / "ai-development"
            shutil.copytree(PROJECTION, copy)
            extension = copy / "FORGE_DEVELOPMENT_EXTENSION.md"
            extension.write_text(extension.read_text() + "\nForge-local note.\n")
            result = validate(copy)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_offline_bootstrap_can_discover_forge_entrypoints(self) -> None:
        required = {
            "BOOTSTRAP.md",
            "FORGE_GENESIS_PROVENANCE.md",
            "docs/ai-development/GENERATED_PROJECTION.md",
            "docs/ai-development/FORGE_DEVELOPMENT_EXTENSION.md",
            "docs/architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md",
            "knowledge/bootstrap/10_ROADMAP.md",
            "scripts/validate.sh",
            ".tde.yml",
            "docs/handoff/forge-managed-repository-phase-1b.md",
        }
        self.assertTrue(all((ROOT / path).is_file() for path in required))
        extension = (PROJECTION / "FORGE_DEVELOPMENT_EXTENSION.md").read_text()
        self.assertIn("first-class peer", extension)
        self.assertIn("installed Engineering\nPlatform", extension)


if __name__ == "__main__":
    unittest.main()
