"""Regression coverage for the complete canonical bootstrap qualification."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.dispatcher import BOOTSTRAP_MISSION_SEQUENCE
from forge.qualification import run_bootstrap_sequence_qualification


class BootstrapSequenceQualificationTests(unittest.TestCase):
    def test_executes_the_complete_fifo_portfolio_and_persists_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            report = run_bootstrap_sequence_qualification(Path(directory))
            evidence = json.loads(Path(report.evidence_path).read_text(encoding="utf-8"))
            self.assertEqual(report.answer, "YES")
            self.assertEqual(report.dispatcher_status, "IDLE")
            self.assertEqual(report.mission_ids, BOOTSTRAP_MISSION_SEQUENCE)
            self.assertEqual([item["mission_id"] for item in evidence["missions"]], list(BOOTSTRAP_MISSION_SEQUENCE))
            self.assertTrue(all(item["completion_outcome"] == "COMPLETED" for item in evidence["missions"]))
            self.assertTrue(all(item["execution_evidence"] and item["architecture_review"] for item in evidence["missions"]))

    def test_resume_is_idempotent_after_complete_persisted_qualification(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory); first = run_bootstrap_sequence_qualification(root)
            host_before = (root / "engineering-platform-evidence.json").read_text(encoding="utf-8")
            second = run_bootstrap_sequence_qualification(root)
            self.assertEqual(first, second)
            self.assertEqual((root / "engineering-platform-evidence.json").read_text(encoding="utf-8"), host_before)


if __name__ == "__main__":
    unittest.main()
