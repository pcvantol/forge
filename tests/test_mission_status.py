"""Read-only Mission status distinguishes attempted planning from materialized plans."""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from forge.mission_cli import status


class MissionStatusTests(unittest.TestCase):
    def test_attempt_without_materialized_plan_remains_visible(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "forge.db"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE mission_state (mission_id TEXT, document TEXT)")
                connection.execute("CREATE TABLE action_derivations (mission_id TEXT)")
                connection.execute("INSERT INTO mission_state VALUES (?, ?)", ("MISSION-0042", "{}"))
                connection.execute("INSERT INTO action_derivations VALUES (?)", ("MISSION-0042",))
            state = SimpleNamespace(
                mission_id="MISSION-0042", status=SimpleNamespace(value="BLOCKED"), revision=4,
                actions=(), current_engineering_action=None, planning_history=(),
                repository_truth=None, execution_history=(), state_history=(),
                waiting_reason="provider result unavailable", completion=None)
            with patch("forge.mission_cli.DataRootResolver.resolve", return_value=Path(directory)), \
                    patch("forge.mission_cli.MissionStateStore._decode", return_value=state):
                observed = status(directory, "MISSION-0042")
            self.assertEqual(observed["planning_attempts_recorded"], 1)
            self.assertEqual(observed["materialized_plans"], 0)
            self.assertTrue(observed["read_only"])


if __name__ == "__main__":
    unittest.main()
