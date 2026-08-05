"""Read-only Generation 1 completion qualification regressions."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.qualification import qualify_generation_one_bootstrap
from forge.runtime import RuntimeDatabase


class GenerationOneBootstrapQualificationTests(unittest.TestCase):
    def test_qualifies_an_existing_empty_runtime_instance_without_dispatching(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = RuntimeDatabase(root)
            self.addCleanup(database.close)
            report = qualify_generation_one_bootstrap(database)
            self.assertEqual(report.answer, "YES")
            self.assertEqual(report.recommended_next_increment, "Portfolio Intelligence Foundation")
            self.assertEqual(report.projection["source"], "runtime_instance")
            self.assertEqual(report.projection["dispatcher_status"], "IDLE")
            self.assertFalse(report.missing_runtime_evidence)
            self.assertEqual(report.projection["runtime_instance_status"], "intentionally_empty")

    def test_records_bootstrap_missions_as_historical_not_runtime_state(self) -> None:
        with TemporaryDirectory() as directory:
            database = RuntimeDatabase(Path(directory))
            self.addCleanup(database.close)
            report = qualify_generation_one_bootstrap(database)
            self.assertEqual(report.answer, "YES")
            self.assertEqual(report.projection["historical_bootstrap_mission_ids"], (
                "MISSION-0001", "MISSION-0002", "MISSION-0003", "MISSION-0004", "MISSION-0005",
            ))

    def test_runtime_state_after_bootstrap_fails_completion_qualification(self) -> None:
        with TemporaryDirectory() as directory:
            database = RuntimeDatabase(Path(directory))
            self.addCleanup(database.close)
            database._connection.execute(
                "INSERT INTO mission_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("MISSION-1001", "CREATED", "CREATED", None, None, "{}", "{}", None, "{}"),
            )
            database._connection.commit()
            report = qualify_generation_one_bootstrap(database)
            self.assertEqual(report.answer, "NO")
            self.assertIn("runtime_instance:intentionally_empty", report.missing_runtime_evidence)

    def test_fails_closed_when_dispatcher_is_not_idle(self) -> None:
        with TemporaryDirectory() as directory:
            database = RuntimeDatabase(Path(directory))
            self.addCleanup(database.close)
            database.save_dispatcher_state(status="ACTIVE", mission_sequence=("MISSION-1001",), active_mission_id="MISSION-1001")
            report = qualify_generation_one_bootstrap(database)
            self.assertEqual(report.answer, "NO")
            self.assertIsNone(report.recommended_next_increment)
            self.assertIn("dispatcher:idle", report.missing_runtime_evidence)


if __name__ == "__main__":
    unittest.main()
