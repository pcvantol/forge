"""Real command outcomes survive private evidence failures; no premature PASS."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('inspection_qualifier',Path('scripts/qualification/qualify_installed_inspection_adoption.py'))
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)

class QualificationRetentionTests(unittest.TestCase):
    def test_real_nonzero_keeps_primary_when_both_log_sinks_fail(self):
        with tempfile.TemporaryDirectory() as name:
            records=[];root=Path(name)
            with patch.object(q.BINDING.CAPTURE,'retain',side_effect=OSError('full')):
                with self.assertRaisesRegex(RuntimeError,'COMMAND_NONZERO'):
                    q.command_capture([sys.executable,'-c','import sys;print("original");sys.stderr.write("diagnostic");sys.exit(7)'],module='synthetic',output=root,cwd=root,env=None,commands=records)
            self.assertEqual(records[0]['primary_failure'],{'category':'COMMAND_NONZERO','observed_exit':7})
            self.assertEqual(records[0]['log_bytes'],[9,10])
            self.assertEqual(len(records[0]['secondary_failures']),2)
            self.assertTrue(records[0]['owned_process_waited'])
            self.assertTrue(records[0]['reader_threads_joined'])

    def test_real_timeout_retains_received_bytes_and_primary_with_sink_failure(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);records=[]
            with patch.object(q.BINDING.CAPTURE,'COMMAND_TIMEOUT',0.3),patch.object(q.BINDING.CAPTURE,'retain',side_effect=OSError('full')):
                with self.assertRaisesRegex(RuntimeError,'COMMAND_TIMEOUT'):
                    q.command_capture([sys.executable,'-u','-c','import time;print("before timeout");time.sleep(5)'],module='synthetic',output=root,cwd=root,env=None,commands=records)
            self.assertEqual(records[0]['primary_failure']['category'],'COMMAND_TIMEOUT')
            self.assertGreater(records[0]['log_bytes'][0],0)
            self.assertTrue(records[0]['owned_process_waited'])
            self.assertTrue(records[0]['reader_threads_joined'])

    def test_final_private_failure_emits_red_receipt_then_raises(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);receipt={'result':'EP_INSPECTION_ADOPTION_HTTP_PASS'}
            with patch.object(q,'private',side_effect=OSError('full')):
                with self.assertRaises(OSError):q.finish_receipt(root,receipt,[],None)
            self.assertEqual(json.loads((root/'installed-inspection-adoption.public.json').read_text())['result'],'FAIL')

    def test_final_private_failure_preserves_existing_primary(self):
        with tempfile.TemporaryDirectory() as name:
            primary=TimeoutError('original');receipt={'result':'FAIL'}
            with patch.object(q,'private',side_effect=OSError('full')):
                q.finish_receipt(Path(name),receipt,[],primary)
            self.assertIn('retention',primary.__notes__[0])

class RemainingDeadlineTests(unittest.TestCase):
    def test_real_command_uses_remaining_probe_budget_without_global_timeout_change(self):
        import time
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);records=[];start=time.monotonic()
            self.assertEqual(q.BINDING.CAPTURE.COMMAND_TIMEOUT,30)
            with self.assertRaisesRegex(RuntimeError,'COMMAND_TIMEOUT'):
                q.command_capture([sys.executable,'-u','-c','import time;print("deadline-bound");time.sleep(2)'],
                    module='synthetic',output=root,cwd=root,env=None,commands=records,timeout=0.2)
            self.assertLess(time.monotonic()-start,1)
            self.assertEqual(q.BINDING.CAPTURE.COMMAND_TIMEOUT,30)
            self.assertEqual(records[0]['primary_failure']['category'],'COMMAND_TIMEOUT')
