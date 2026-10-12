"""Causal assurance controls for original command outcome and exact source binding."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('bootstrap_process_under_test',Path('scripts/qualification/project_bootstrap_process.py'))
PROCESS=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(PROCESS)


class QualificationProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='forge-pb-process-',dir=str(Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def run_command(self,code,case):
        return PROCESS.capture([sys.executable,'-I','-c',code],case=case,output=self.root,cwd=self.root,env={'PATH':os.environ.get('PATH','')})

    def test_actual_nonzero_retention_error_keeps_primary(self):
        with patch.object(PROCESS,'retain',side_effect=OSError('synthetic unavailable sink')):
            report,stdout,stderr=self.run_command("print('original');raise SystemExit(7)",'nonzero')
        self.assertEqual(report['primary_failure'],{'category':'COMMAND_NONZERO','observed_exit':7})
        self.assertEqual(report['actual_exit'],7);self.assertIn(b'original',stdout)
        self.assertFalse(report['capture_complete']);self.assertEqual(len(report['secondary_failures']),2)
        self.assertTrue(report['owned_process_waited'])

    def test_actual_unmodified_timeout_retention_error_keeps_primary(self):
        self.assertEqual(PROCESS.COMMAND_TIMEOUT,30)
        with patch.object(PROCESS,'retain',side_effect=OSError('synthetic unavailable sink')):
            report,stdout,stderr=self.run_command("import time;print('before timeout',flush=True);time.sleep(60)",'timeout')
        self.assertEqual(report['primary_failure'],{'category':'COMMAND_TIMEOUT','observed_exit':None})
        self.assertEqual(report['actual_exit'],-9);self.assertIn(b'before timeout',stdout)
        self.assertFalse(report['capture_complete']);self.assertEqual(len(report['secondary_failures']),2)
        self.assertTrue(report['owned_process_waited'])

    def test_success_missing_evidence_is_incomplete_and_capture_is_bounded(self):
        report,stdout,stderr=self.run_command("print('x'*200000)",'capacity')
        self.assertEqual(report['actual_exit'],0);self.assertIsNone(report['primary_failure'])
        self.assertTrue(report['truncated']);self.assertFalse(report['capture_complete'])
        self.assertEqual(len(stdout),PROCESS.MAXIMUM_LOG)
        self.assertLessEqual((self.root/'private-capacity-0.log').stat().st_size,PROCESS.MAXIMUM_LOG)
        with patch.object(PROCESS,'retain',side_effect=OSError('sink')):
            report,_,_=self.run_command("print('ok')",'successful-command')
        self.assertIsNone(report['primary_failure']);self.assertFalse(report['capture_complete'])
        self.assertTrue(report['owned_process_waited'])


    def test_actual_wheel_omission_extra_and_source_mismatch_controls(self):
        import zipfile
        spec=importlib.util.spec_from_file_location('bootstrap_qualifier_under_test',Path('scripts/qualification/qualify_installed_project_bootstrap.py'))
        qualifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(qualifier)
        installed=self.root/'installed';(installed/'forge').mkdir(parents=True)
        (installed/'forge/core.py').write_bytes(b'committed product')
        expected={'forge/core.py':b'committed product'}
        for label,members,should_pass in [('positive',expected,True),('missing',{},False),('extra',{**expected,'forge/other.py':b'extra'},False),('mismatch',{'forge/core.py':b'other compatible product'},False)]:
            wheel=self.root/(label+'.whl')
            with zipfile.ZipFile(wheel,'w') as archive:
                for name,raw in members.items():archive.writestr(name,raw)
            with zipfile.ZipFile(wheel) as archive:
                if should_pass:self.assertEqual(set(qualifier.verify_payload(archive,expected,installed)),set(expected))
                else:
                    with self.assertRaises(ValueError):qualifier.verify_payload(archive,expected,installed)
        (installed/'forge/core.py').write_bytes(b'changed install')
        with zipfile.ZipFile(self.root/'positive.whl') as archive:
            with self.assertRaises(ValueError):qualifier.verify_payload(archive,expected,installed)


    def test_exited_leader_inherited_pipe_descendant_is_stopped(self):
        import json
        import signal
        import time
        marker=self.root/'owned-descendant.json'
        code=("import json,os,subprocess,sys;from pathlib import Path; "
              "p=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(60)']); "
              f"Path({str(marker)!r}).write_text(json.dumps({{'pid':p.pid,'pgid':os.getpgrp()}})); "
              "print('leader exits',flush=True)")
        started=time.monotonic()
        try:
            report,stdout,stderr=self.run_command(code,'owned-descendant')
            self.assertLess(time.monotonic()-started,5)
            self.assertTrue(report['capture_complete'])
            self.assertTrue(report['owned_process_waited'])
            self.assertTrue(report['reader_threads_joined'])
            self.assertTrue(report['owned_process_group_stop_requested'])
            self.assertIsNone(report['primary_failure']);self.assertEqual(report['actual_exit'],0)
            self.assertIn(b'leader exits',stdout)
        finally:
            # Causal RED against the historical helper must also stop only its own fixture group.
            if marker.exists():
                identity=json.loads(marker.read_text())
                try:os.killpg(identity['pgid'],signal.SIGKILL)
                except ProcessLookupError:pass
