"""Regression guard for the scheduler's provider-neutral dependency boundary."""

from __future__ import annotations

from pathlib import Path
import unittest


class SchedulerDependencyBoundaryTests(unittest.TestCase):
    def test_scheduler_core_has_no_bootstrap_host_or_local_transport_coupling(self) -> None:
        root = Path(__file__).resolve().parents[1] / "forge" / "scheduler"
        core = (root / "scheduler.py").read_text(encoding="utf-8") + (root / "__init__.py").read_text(encoding="utf-8")
        forbidden = (
            "engineeringplatform", "engineering platform", "djconnect", "icloud",
            ".djconnect", "inbox", "launchd", "dashboard", "/users/pcvantol",
        )
        self.assertEqual([term for term in forbidden if term in core.lower()], [])
        self.assertNotIn("adapter import", core)


if __name__ == "__main__":
    unittest.main()
