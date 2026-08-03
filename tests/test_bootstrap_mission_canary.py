"""Regression coverage for the canonical end-to-end Bootstrap Mission Canary."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.canary import (
    CANARY_ACTION_ID, CANARY_CORRELATION_ID, CANARY_HOST_RUN_ID, CANARY_INTENT_ID,
    CANARY_MISSION_ID, run_bootstrap_mission_canary,
)


class BootstrapMissionCanaryTests(unittest.TestCase):
    def test_canary_exercises_one_complete_host_transaction_with_stable_identity(self) -> None:
        with TemporaryDirectory() as directory:
            report = run_bootstrap_mission_canary(Path(directory) / "canary.sqlite3")
        self.assertEqual(report.answer, "YES")
        self.assertEqual((report.mission_id, report.intent_id, report.action_id),
                         (CANARY_MISSION_ID, CANARY_INTENT_ID, CANARY_ACTION_ID))
        self.assertEqual((report.execution_host_run_id, report.correlation_id),
                         (CANARY_HOST_RUN_ID, CANARY_CORRELATION_ID))
        self.assertEqual(report.admission_levels, ("execution_host_level_1", "workspace_level_2", "capability_level_3"))
        self.assertEqual(report.evidence_kinds,
                         ("execution_host", "engineering", "repository", "validation", "mission_completion"))


if __name__ == "__main__":
    unittest.main()
