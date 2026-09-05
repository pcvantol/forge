"""Regression coverage for the canonical default project coverage policy."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
POLICY = ROOT / "docs/architecture/self-contained-engineering-contract-bootstrap.md"
QUALITY_LOOP = ROOT / "docs/architecture/engineering-quality-learning-loop.md"


class DefaultProjectQualityPolicyTests(unittest.TestCase):
    def test_canonical_default_and_required_invariants_are_defined(self) -> None:
        policy = POLICY.read_text(encoding="utf-8")

        for invariant in (
            "DEFAULT_PROJECT_PRODUCTION_COVERAGE_POLICY = DEFINED",
            "DEFAULT_PROJECT_PRODUCTION_COVERAGE_THRESHOLD = 80.00%",
            "PRODUCTION_SCOPE_AGGREGATE = ALL_PRODUCTION_CODE",
            "PROJECT_CAN_DEFINE_STRICTER_THRESHOLD = TRUE",
            "SILENT_WEAKENING_ALLOWED = FALSE",
            "GOVERNED_EXCEPTION_REQUIRED_BELOW_DEFAULT = TRUE",
            "CRITICAL_LOW_COVERAGE_REMAINS_VISIBLE = TRUE",
            "DUPLICATE_QUALITY_POLICY_AUTHORITY = 0",
            "PROJECT_PRODUCTION_CODE_COVERAGE_GATE = REQUIRED",
            "PRODUCTION_CODE_EXCLUDED_FOR_CONVENIENCE = FALSE",
            "COVERAGE_THRESHOLD_SILENTLY_LOWERED = FALSE",
            "BLANKET_NO_COVER_FOR_REACHABLE_PRODUCTION_CODE = FALSE",
            "MEANINGLESS_TESTS_FOR_PERCENTAGE_ONLY = FALSE",
        ):
            self.assertIn(invariant, policy)

    def test_quality_learning_consumes_instead_of_redefining_coverage_policy(self) -> None:
        loop = QUALITY_LOOP.read_text(encoding="utf-8")

        self.assertIn("Self-Contained Engineering Contract Bootstrap", loop)
        self.assertIn("does not redefine the threshold, production scope, or", loop)
        self.assertIn("selected-module passes", loop)


if __name__ == "__main__":
    unittest.main()
