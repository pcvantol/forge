"""Boundary tests for the ordinary PR changed-product-file coverage gate."""
from __future__ import annotations

import unittest

from scripts.check_changed_product_coverage import check_coverage


class ChangedProductCoverageTests(unittest.TestCase):
    def test_strict_boundary_and_missing_source_fail_closed(self) -> None:
        report = {"files": {
            "forge/at_boundary.py": {"summary": {"covered_lines": 401, "num_statements": 500}},
            "forge/above.py": {"summary": {"covered_lines": 402, "num_statements": 500}},
        }}
        self.assertEqual(check_coverage(report, ["forge/above.py"]), [])
        failures = check_coverage(report, ["forge/at_boundary.py", "forge/missing.py"])
        self.assertEqual(len(failures), 2)
        self.assertIn("must be >80.2%", failures[0])
        self.assertIn("missing coverage", failures[1])

    def test_malformed_coverage_fails_closed(self) -> None:
        self.assertEqual(check_coverage({"files": {"forge/a.py": {"summary": {
            "covered_lines": True, "num_statements": 1,
        }}}}, ["forge/a.py"]), ["forge/a.py: invalid executable-line coverage"])
        with self.assertRaisesRegex(ValueError, "no file data"):
            check_coverage({}, ["forge/a.py"])


if __name__ == "__main__":
    unittest.main()
