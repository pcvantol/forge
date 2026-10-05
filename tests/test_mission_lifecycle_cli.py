"""The installed Mission lifecycle CLI uses the same guarded product operation as HTTP."""
from contextlib import nullcontext, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from forge.mission_lifecycle_cli import archive_no_dispatch, main


REQUEST = [
    "--data-root", "/tmp/forge-lifecycle-test", "archive-no-dispatch",
    "--mission-id", "MISSION-0001", "--expected-instance-id", "runtime-1",
    "--expected-revision", "2", "--reason-code", "historical_no_dispatch_reconciled",
    "--correlation-id", "lifecycle-1",
]


class MissionLifecycleCliTests(unittest.TestCase):
    def test_adapter_owns_controller_and_runtime_locks_and_closes_database(self) -> None:
        database = SimpleNamespace(path=Path("/tmp/forge.db"), close=Mock())
        repository = object()
        result = SimpleNamespace(to_dict=lambda: {"status": "ARCHIVED"})
        service = Mock()
        service.archive_quiescent_no_dispatch.return_value = result
        lock = Mock()
        lock.acquire.return_value = nullcontext()
        with patch("forge.mission_lifecycle_cli._governance", return_value=(database, repository)), \
             patch("forge.mission_lifecycle_cli.require_no_controller", return_value=nullcontext()), \
             patch("forge.mission_lifecycle_cli.RuntimeServiceLock", return_value=lock), \
             patch("forge.mission_lifecycle_cli.MissionLifecycleService", return_value=service), \
             patch("forge.mission_lifecycle_cli._now", return_value="2026-10-05T08:00:00Z"):
            observed = archive_no_dispatch(
                "/tmp/forge-lifecycle-test", "MISSION-0001",
                expected_instance_id="runtime-1", expected_revision=2,
                reason_code="historical_no_dispatch_reconciled", correlation_id="lifecycle-1",
            )
        self.assertEqual(observed, {"status": "ARCHIVED"})
        database.close.assert_called_once_with()
        service.archive_quiescent_no_dispatch.assert_called_once_with(
            "MISSION-0001", expected_instance_id="runtime-1", expected_revision=2,
            reason_code="historical_no_dispatch_reconciled", correlation_id="lifecycle-1",
            occurred_at="2026-10-05T08:00:00Z",
            authenticated_principal_reference=None,
        )

    def test_cli_emits_a_secret_free_result_or_bounded_error(self) -> None:
        output = StringIO()
        with patch("forge.mission_lifecycle_cli.archive_no_dispatch",
                   return_value={"status": "ARCHIVED", "host_dispatched": False}), \
             redirect_stdout(output):
            self.assertEqual(main(REQUEST), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "ARCHIVED")

        output = StringIO()
        with patch("forge.mission_lifecycle_cli.archive_no_dispatch",
                   side_effect=PermissionError("private detail")), redirect_stdout(output):
            self.assertEqual(main(REQUEST), 1)
        self.assertEqual(json.loads(output.getvalue()), {
            "status": "ERROR", "error_type": "PermissionError",
        })


if __name__ == "__main__":
    unittest.main()
