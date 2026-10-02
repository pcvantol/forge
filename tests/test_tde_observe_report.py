"""The observe job must expose actual TDE decisions without inventing PASS."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.report_tde_observe import report


class TDEObserveReportTests(unittest.TestCase):
    def _evidence(self, root: Path, *, decision: str = "PASS", status: str = "QUALIFIED",
                  rules: int = 0, exits: str = "assessment_exit=0\nqualification_exit=0\n") -> None:
        (root / "assessment.json").write_text(json.dumps({
            "evidence": {"assessment": {"assessmentDecision": decision}},
            "qualification": {"policyDecision": decision, "triggeredRules": [{}] * rules},
        }), encoding="utf-8")
        (root / "qualification.json").write_text(json.dumps({
            "repositoryQualification": {"assessmentDecision": decision, "qualificationStatus": status},
        }), encoding="utf-8")
        (root / "summary.txt").write_text(exits, encoding="utf-8")

    def test_complete_pass_is_visible_without_warning(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._evidence(root)
            summary, warning = report(root)
        self.assertFalse(warning)
        self.assertIn("| Assessment decision | `PASS` |", summary)
        self.assertIn("| Repository qualification | `QUALIFIED` |", summary)
        self.assertIn("successful completion is not a TDE assessment PASS", summary)

    def test_actual_failure_shape_is_visible_despite_nonblocking_job(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._evidence(root, decision="FAIL", status="FAILED", rules=29,
                           exits="assessment_exit=2\nqualification_exit=2\n")
            summary, warning = report(root)
        self.assertTrue(warning)
        self.assertIn("| Repository assessment decision | `FAIL` |", summary)
        self.assertIn("| Triggered policy rules | `29` |", summary)
        self.assertIn("| Qualification command exit | `2` |", summary)

    def test_missing_or_inconsistent_evidence_never_looks_green(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._evidence(root, exits="assessment_exit=2\nassessment_exit=0\nassessment_exit=0\nqualification_exit=0\n")
            summary, warning = report(root)
            self.assertTrue(warning)
            self.assertIn("| Assessment decision | `PASS` |", summary)
            self.assertIn("| Assessment command exit | `UNAVAILABLE` |", summary)
            assessment = json.loads((root / "assessment.json").read_text())
            assessment["qualification"]["policyDecision"] = "FAIL"
            (root / "assessment.json").write_text(json.dumps(assessment), encoding="utf-8")
            summary, warning = report(root)
            self.assertTrue(warning)
            self.assertIn("| Assessment decision | `UNAVAILABLE` |", summary)
            self.assertIn("| Assessment command exit | `UNAVAILABLE` |", summary)
            (root / "qualification.json").write_text("{broken", encoding="utf-8")
            summary, warning = report(root)
            self.assertTrue(warning)
            self.assertIn("| Repository qualification | `UNAVAILABLE` |", summary)


if __name__ == "__main__":
    unittest.main()
