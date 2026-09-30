"""CLI routing preserves explicit commands without authorizing Mission effects."""
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from forge.__main__ import main


class CliTransportTests(unittest.TestCase):
    def _call(self, args):
        output = StringIO()
        with redirect_stdout(output):
            code = main(["--data-root", "/tmp/forge-cli-transport-isolated", "mission", *args])
        return code, json.loads(output.getvalue())

    def test_mission_governance_commands_keep_their_selected_operation(self):
        with patch("forge.mission_cli.inspect", return_value={"status": "VALID"}) as inspect:
            self.assertEqual(self._call(["inspect", "--input", "/tmp/request.json"])[0], 0)
            inspect.assert_called_once_with("/tmp/request.json")
        with patch("forge.mission_cli.approve", return_value={"status": "APPROVED"}) as approve:
            self.assertEqual(self._call(["approve-business", "--input", "/tmp/request.json"])[0], 0)
            self.assertEqual(self._call(["approve-architecture", "--input", "/tmp/request.json"])[0], 0)
            self.assertEqual([call.args[2] for call in approve.call_args_list], ["business", "architecture"])
        with patch("forge.mission_cli.admit", return_value={"status": "ADMITTED"}) as admit:
            self.assertEqual(self._call(["admit", "--input", "/tmp/request.json"])[0], 0)
            admit.assert_called_once()

    def test_mission_execution_commands_preserve_status_and_truth_route(self):
        with patch("forge.mission_cli.run", return_value={"status": "COMPLETED"}) as run:
            self.assertEqual(self._call([
                "run", "--mission-id", "mission-1", "--repository-truth", "/tmp/truth.json",
            ])[0], 0)
            self.assertEqual(self._call(["reopen", "--mission-id", "mission-1"])[0], 0)
            self.assertEqual(run.call_args_list[0].kwargs["truth_path"], "/tmp/truth.json")
            self.assertIsNone(run.call_args_list[1].kwargs["truth_path"])
        with patch("forge.mission_cli.status", return_value={"status": "BLOCKED"}) as status:
            self.assertEqual(self._call(["status", "--mission-id", "mission-1"])[0], 0)
            status.assert_called_once()
        with patch("forge.mission_cli.stop", return_value={"stop_requested": False}) as stop:
            self.assertEqual(self._call(["stop", "--mission-id", "mission-1"])[0], 2)
            stop.assert_called_once()

    def test_cli_error_is_machine_readable_without_mission_mutation(self):
        with patch("forge.mission_cli.inspect", side_effect=ValueError("invalid Mission")):
            code, body = self._call(["inspect", "--input", "/tmp/request.json"])
        self.assertEqual(code, 1)
        self.assertEqual(body["status"], "ERROR")

    def test_preserve_failure_returns_product_error_instead_of_traceback(self):
        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-root", "/tmp/forge-cli-transport-absent", "server", "preserve",
                "--operation-id", "absent-preserve", "--instances-root", "/tmp",
                "--instance-id", "instance-a", "--runtime-id", "instance-a",
                "--installation-id", "installation-a", "--installed-version", "2.7.39",
                "--installed-source", "a" * 40, "--installed-artifact-digest", "sha256:" + "b" * 64,
            ])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "ERROR")


if __name__ == "__main__":
    unittest.main()
