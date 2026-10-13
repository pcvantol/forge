"""Prove actual installed worker isolation guards without invoking a whole matrix."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile
import os
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('adoption_qualifier',Path('scripts/qualification/qualify_installed_project_adoption.py'))
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)


class WorkerGuards(unittest.TestCase):
    def test_actual_socket_direct_and_directory_descriptor_source_probes_are_denied(self):
        prefix=MODULE.WORKER.split('entry=[',1)[0]
        command=prefix+"\nassert not attempts\nprint('GUARD_PROBES_PASS')\n"
        result=subprocess.run([sys.executable,'-I','-c',command,str(Path.cwd())],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'GUARD_PROBES_PASS')

    def test_real_process_invocation_is_denied_after_guard_probes(self):
        prefix=MODULE.WORKER.split('entry=[',1)[0]
        command=prefix+"\nimport subprocess\ntry:\n subprocess.run([sys.executable,'-c',\"print('SHOULD_NOT_EXECUTE')\"])\nexcept PermissionError:\n print('COMMAND_REFUSED')\nelse:\n raise AssertionError('unexpected command execution')\n"
        result=subprocess.run([sys.executable,'-I','-c',command,str(Path.cwd())],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'COMMAND_REFUSED')


class ReceiptRetention(unittest.TestCase):
    def test_primary_timeout_and_nonzero_survive_secondary_receipt_io_failure(self):
        for primary in [subprocess.TimeoutExpired("synthetic", 30), subprocess.CalledProcessError(7, "synthetic")]:
            receipt = {"result": "FAIL", "diagnostic_complete": True}
            with self.subTest(primary=type(primary).__name__):
                with patch.object(Path, "write_text", side_effect=OSError("private path must not escape")), patch.object(MODULE._tool._process, "retain"):
                    try:
                        try:
                            raise primary
                        finally:
                            MODULE.retain_receipt(Path("unused"), receipt, primary)
                    except BaseException as observed:
                        self.assertIs(observed, primary)
                self.assertFalse(receipt["diagnostic_complete"])
                self.assertEqual(receipt["receipt_write_failure"], {"category": "OSError"})
                self.assertEqual(primary.__notes__, ["Qualification receipt write failed: OSError"])

    def test_success_is_not_reported_when_receipt_write_fails(self):
        receipt = {"result": "PROJECT_ADOPTION_OFFLINE_PASS", "diagnostic_complete": True}
        with patch.object(Path, "write_text", side_effect=OSError("synthetic")), patch.object(MODULE._tool._process, "retain"):
            with self.assertRaises(OSError):
                MODULE.retain_receipt(Path("unused"), receipt, None)
        self.assertFalse(receipt["diagnostic_complete"])

    def test_actual_command_outcomes_retained_despite_public_sink_failure(self):
        for category, command in [("COMMAND_NONZERO", "raise SystemExit(7)"), ("COMMAND_TIMEOUT", "import time; time.sleep(10)")]:
            with self.subTest(category=category), tempfile.TemporaryDirectory() as directory:
                output=Path(directory)
                with patch.object(MODULE._tool._process, "COMMAND_TIMEOUT", 0.1):
                    report, _, _ = MODULE._tool._process.capture([sys.executable, "-c", command], case=category, output=output, cwd=output, env={"PATH":os.environ.get("PATH", "")})
                self.assertEqual(report["primary_failure"]["category"], category)
                self.assertTrue(report["owned_process_waited"])
                self.assertTrue(report["reader_threads_joined"])
                receipt={"result":"FAIL", "diagnostic_complete":True, "cases":[report], "cleanup":True}
                primary=RuntimeError("actual bounded command failure")
                with patch.object(Path, "write_text", side_effect=OSError("synthetic public sink failure")):
                    MODULE.retain_receipt(output, receipt, primary)
                retained=__import__("json").loads((output/"installed-project-adoption.retention-failure.private.json").read_bytes())
                self.assertEqual(retained["cases"][0]["primary_failure"], report["primary_failure"])
                self.assertFalse(retained["diagnostic_complete"])
                self.assertTrue(retained["cleanup"])
                self.assertEqual(retained["receipt_write_failure"], {"category":"OSError"})

    def test_all_sinks_unavailable_preserves_primary_and_reports_incomplete(self):
        receipt={"result":"FAIL", "diagnostic_complete":True};primary=RuntimeError("original")
        with patch.object(Path,"write_text",side_effect=OSError("private detail")), patch.object(MODULE._tool._process,"retain",side_effect=OSError("private fallback")), patch("sys.stderr",new_callable=__import__("io").StringIO) as stream:
            MODULE.retain_receipt(Path("unused"),receipt,primary)
        self.assertFalse(receipt["diagnostic_complete"])
        self.assertEqual(receipt["fallback_write_failure"], {"category":"OSError"})
        self.assertNotIn("private",stream.getvalue())
        self.assertIn('"result": "FAIL"',stream.getvalue())
