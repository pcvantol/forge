"""Prove actual installed worker isolation guards without invoking a whole matrix."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

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
