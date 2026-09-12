"""Contract tests for the read-only installed runtime status projection."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.__main__ import _status
from forge.runtime import RuntimeBootstrap


class RuntimeStatusProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "forge-server"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _initialize(self):
        return RuntimeBootstrap(data_root=self.root, forge_version="test").open()

    def _snapshot(self) -> dict[Path, bytes]:
        if not self.root.exists():
            return {}
        return {
            path.relative_to(self.root): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def test_initialized_idle_dispatcher_is_redacted_and_read_only(self) -> None:
        self._initialize().close()

        projection = _status(str(self.root))

        self.assertTrue(projection["initialized"])
        self.assertEqual(projection["dispatcher"], {"status": "IDLE"})
        self.assertNotIn("active_mission_id", json.dumps(projection, sort_keys=True))

    def test_initialized_active_dispatcher_is_redacted_and_read_only(self) -> None:
        database = self._initialize()
        database.save_dispatcher_state(
            status="ACTIVE", mission_sequence=("MISSION-SECRET",), active_mission_id="MISSION-SECRET",
        )
        database.close()

        projection = _status(str(self.root))

        self.assertTrue(projection["initialized"])
        self.assertEqual(projection["dispatcher"], {"status": "ACTIVE"})
        self.assertNotIn("MISSION-SECRET", json.dumps(projection, sort_keys=True))

    def test_uninitialized_root_is_reported_without_creation(self) -> None:
        projection = _status(str(self.root))

        self.assertFalse(projection["initialized"])
        self.assertEqual(projection["runtime_status"], "uninitialized")
        self.assertFalse(self.root.exists())

    def test_storage_error_is_reported_without_mutating_storage(self) -> None:
        self._initialize().close()
        database = self.root / "forge.db"
        database.write_bytes(b"not a sqlite database")
        before = self._snapshot()

        projection = _status(str(self.root))

        self.assertTrue(projection["initialized"])
        self.assertEqual(projection["runtime_status"], "unavailable")
        self.assertEqual(projection["execution_host_peer"]["status"], "ERROR")
        self.assertEqual(self._snapshot(), before)
