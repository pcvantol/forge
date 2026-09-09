"""Installed-runtime storage boundary regressions."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from forge.runtime import DataRootResolver, RuntimeBootstrap, RuntimeResolutionError, RuntimeResolver


class CanonicalDataRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def test_macos_default_and_precedence_are_deterministic(self) -> None:
        home = self.root / "home"
        env_root = self.root / "environment"
        cli_root = self.root / "cli"
        resolver = DataRootResolver(environment={"HOME": str(home), "FORGE_DATA_ROOT": str(env_root)}, platform="darwin")
        self.assertEqual(resolver.resolve(), env_root.resolve())
        self.assertEqual(DataRootResolver(cli_data_root=cli_root, environment={"HOME": str(home), "FORGE_DATA_ROOT": str(env_root)}, platform="darwin").resolve(), cli_root.resolve())
        self.assertEqual(DataRootResolver(environment={"HOME": str(home)}, platform="darwin").resolve(), (home / "Library" / "Application Support" / "Forge Server").resolve())

    def test_resolution_help_version_and_status_do_not_create_a_root(self) -> None:
        root = self.root / "safe"
        self.assertEqual(RuntimeResolver(data_root=root).resolve().path, (root / "forge.db").resolve())
        self.assertFalse(root.exists())
        for arguments in (("--help",), ("--version",), ("--data-root", str(root), "server", "status")):
            completed = subprocess.run((sys.executable, "-m", "forge", *arguments), capture_output=True, text=True, check=True)
            self.assertTrue(completed.stdout)
            self.assertFalse(root.exists())

    def test_init_creates_one_root_and_stable_identity(self) -> None:
        root = self.root / "canonical"
        first = RuntimeBootstrap(data_root=root, forge_version="test").open()
        identity = first.runtime_identity.runtime_id
        first.close()
        self.assertEqual(RuntimeResolver(data_root=root).resolve().path, (root / "forge.db").resolve())
        self.assertTrue((root / "instance" / "runtime-instance.json").is_file())
        self.assertTrue(all((root / name).is_dir() for name in ("artifacts", "journals", "logs", "backups", "cache", "locks")))
        second = RuntimeBootstrap(data_root=root, forge_version="test").open()
        try:
            self.assertEqual(second.runtime_identity.runtime_id, identity)
        finally:
            second.close()

    def test_roots_are_independent_and_legacy_git_storage_is_ignored(self) -> None:
        checkout = self.root / "checkout"
        legacy = checkout / ".git" / "forge-runtime"
        legacy.mkdir(parents=True)
        (legacy / "runtime.db").write_text("not a Forge database", encoding="utf-8")
        first = RuntimeBootstrap(checkout, data_root=self.root / "one", forge_version="test").open()
        second = RuntimeBootstrap(checkout, data_root=self.root / "two", forge_version="test").open()
        try:
            self.assertNotEqual(first.runtime_identity.runtime_id, second.runtime_identity.runtime_id)
            self.assertEqual((legacy / "runtime.db").read_text(encoding="utf-8"), "not a Forge database")
        finally:
            first.close(); second.close()

    def test_initialized_root_missing_database_fails_closed(self) -> None:
        root = self.root / "missing"
        database = RuntimeBootstrap(data_root=root, forge_version="test").open()
        database.close()
        (root / "forge.db").unlink()
        with self.assertRaisesRegex(RuntimeResolutionError, "missing forge.db"):
            RuntimeResolver(data_root=root).resolve()


if __name__ == "__main__":
    unittest.main()
