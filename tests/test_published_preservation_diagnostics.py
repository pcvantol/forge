"""Bounded fault controls for the qualification evidence boundary, no product mocks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preservation_diagnostics', SOURCE/'scripts/qualification/qualify_published_preservation_2739_281.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PreservationDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.d = m.Diagnostics(self.root, 'a'*40)
        m.ACTIVE_DIAGNOSTIC = self.d
        self.addCleanup(setattr, m, 'ACTIVE_DIAGNOSTIC', None)
        self.d.case = 'crash-BACKED_UP'

    def public(self):
        return json.loads((self.root/'published-preservation-diagnostics.public.json').read_text())

    def test_primary_empty_assertion_has_exact_substage_and_no_secret(self):
        m.checkpoint('crash-boundary-check', expected=True, observed=False, requested_phase='BACKED_UP')
        try:
            raise AssertionError('token=SECRET /Users/private/path user database payload')
        except AssertionError as e:
            self.d.failure(e)
        self.assertEqual(self.public()['primary_failure']['substage'], 'crash-boundary-check')
        text=json.dumps(self.public())
        for forbidden in ('SECRET', '/Users/', 'database payload'):
            self.assertNotIn(forbidden,text)
        private=next(self.d.private.glob('*primary-failure*'))
        self.assertIn('SECRET',private.read_text())
        self.assertEqual(private.stat().st_mode & 0o777,0o600)

    def test_resume_exit_distinct_from_preservation_failure(self):
        for stage in ('resume-command', 'preservation-compare', 'backup-digest'):
            with self.subTest(stage=stage):
                self.d.document['primary_failure']=None
                m.checkpoint(stage, expected=True, observed=False)
                error=AssertionError()
                row=self.d.failure(error)
                self.assertEqual(row['substage'],stage)
                # Do not reuse a private evidence label across injected cases.
                for p in self.d.private.glob('*primary-failure*'):p.unlink()

    def test_command_payload_and_paths_only_private(self):
        m.checkpoint('resume-command')
        done=subprocess.CompletedProcess([],1,'{"status":"ERROR","token":"SECRET","path":"/Users/private"}', 'SECRET')
        with patch.object(m.subprocess,'run',return_value=done):
            with self.assertRaises(AssertionError):m.run([],self.root,env={})
        event=self.public()['events'][-1]
        self.assertEqual(event['exit_code'],1)
        self.assertEqual(event['status'],'ERROR')
        self.assertNotIn('SECRET',json.dumps(self.public()))
        self.assertIn('SECRET',next(self.d.private.glob('*command-*')).read_text())

    def test_private_truncation_and_public_closed_fields(self):
        v=self.d.retain('large',b'x'*(m.MAX_PRIVATE_LOG+100))
        self.assertTrue(v['truncated'])
        self.assertEqual(next(self.d.private.glob('*large*')).stat().st_size,m.MAX_PRIVATE_LOG)
        with self.assertRaises(ValueError):self.d.record('test',stdout='SECRET')
        with self.assertRaises(ValueError):self.d.record('test',observed='/Users/private')

    def test_capacity_explicit_incomplete(self):
        for _ in range(m.MAX_DIAGNOSTIC_EVENTS+1):self.d.record('capacity')
        self.assertFalse(self.public()['complete'])
        self.assertEqual(len(self.public()['events']),m.MAX_DIAGNOSTIC_EVENTS)

    def test_secondary_cleanup_does_not_replace_primary(self):
        self.d.record('resume-command')
        primary=self.d.failure(AssertionError())
        self.d.record('owned-cleanup')
        self.d.failure(OSError('SECRET'),secondary=True)
        self.assertEqual(self.public()['primary_failure'],primary)
        self.assertEqual(self.public()['secondary_failure']['substage'],'owned-cleanup')

    def test_retention_failure_keeps_primary_in_memory(self):
        self.d.record('preservation-compare')
        with patch.object(self.d,'retain',side_effect=OSError('secret')):
            row=self.d.failure(AssertionError())
        self.assertEqual(row,self.d.document['primary_failure'])
        self.assertFalse(self.d.document['complete'])
        self.assertEqual(self.d.document['retention_error'],'EVIDENCE_WRITE_FAILED')

    def test_crash_missed_boundary_retains_before_cleanup(self):
        case=self.root/'owned'
        case.mkdir()
        # A genuinely exited own child cannot hit a future boundary; actual crash
        # function/assertion executed, no changed production signal or deadline.
        with self.assertRaises(AssertionError):m.crash(['/usr/bin/true'],case,'BACKED_UP',{'PATH':'/usr/bin:/bin'})
        self.assertEqual(self.public()['primary_failure']['substage'],'crash-boundary-check')
        self.assertTrue(list(self.d.private.glob('*interrupted-child*')))
        self.assertFalse(self.public()['events'][-1]['observed'])

    def test_qualify_faults_stay_red_and_survive_case_cleanup(self):
        m.ACTIVE_DIAGNOSTIC = None
        original=m.shutil.rmtree
        for stage in ('crash-boundary-check', 'resume-command', 'preservation-compare'):
            with self.subTest(stage=stage):
                output=self.root/stage
                args=SimpleNamespace(source_revision='a'*40,output_dir=output,inputs=self.root,fetch_inputs=False)
                def fail(*unused):
                    m.checkpoint(stage, expected=True, observed=False)
                    raise AssertionError('SECRET /Users/private')
                def source(cmd,**kw):
                    if cmd[1]=='show':
                        return (m.CONTROLLER if cmd[-1].endswith('update_installed_forge.py') else Path(m.__file__)).read_bytes()
                    return 'b'*40+'\n'
                with patch.object(m.subprocess,'check_output',side_effect=source), patch.object(m,'case',side_effect=fail):
                    self.assertEqual(m.qualify(args),1)
                receipt=json.loads((output/'published-preservation.public.json').read_text())
                diagnostic=json.loads((output/'published-preservation-diagnostics.public.json').read_text())
                self.assertEqual(receipt['result'],'FAIL')
                self.assertEqual(receipt['failure']['substage'],stage)
                self.assertEqual(diagnostic['primary_failure']['substage'],stage)
                self.assertTrue(receipt['cleanup']['owned_runtime_home_credentials_scratch_removed'])
                self.assertFalse((output/'owned-cases').exists())
                self.assertTrue(list((output/'retained-private').glob('*primary-failure*')))
                self.assertNotIn('SECRET',json.dumps(receipt)+json.dumps(diagnostic))

    def test_workflow_upload_only_explicit_public_files(self):
        workflow=(SOURCE/'.github/workflows/ci.yml').read_text()
        section=workflow.split('name: forge-published-preservation-${{ github.sha }}')[1]
        self.assertIn('published-preservation-diagnostics.public.json',section)
        self.assertNotIn('private',section)
        self.assertIn('timeout-minutes: 3',workflow.split('Exact published 2.7.39 to 2.8.1 preservation maintenance')[1])

if __name__=='__main__':unittest.main()
