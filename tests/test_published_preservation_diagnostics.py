"""Bounded fault controls for the qualification evidence boundary, no product mocks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
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

    def test_actual_owned_child_stopped_when_acquisition_write_fails(self):
        case=self.root/'running-child';case.mkdir()
        children=[]
        original=m.subprocess.Popen
        def launch(*a,**kw):
            child=original(*a,**kw);children.append(child);return child
        try:
            with patch.object(m.subprocess,'Popen',side_effect=launch), patch.object(self.d,'write',side_effect=OSError('SECRET')), patch.object(m.time,'monotonic',side_effect=[0,31]):
                with self.assertRaises(AssertionError):m.crash(['/bin/sleep','30'],case,'BACKED_UP',{'PATH':'/usr/bin:/bin'})
            self.assertEqual(len(children),1)
            self.assertIsNotNone(children[0].poll())
            self.assertEqual(children[0].returncode,-9)
            with self.assertRaises(ProcessLookupError):os.killpg(children[0].pid,0)
            self.assertFalse(self.d.document['complete'])
            self.assertEqual(self.d.document['primary_failure']['substage'],'crash-acquisition')
            self.assertTrue(list(self.d.private.glob('*interrupted-child*')))
        finally:
            for child in children:
                if child.poll() is None:os.killpg(child.pid,9);child.wait(timeout=5)

    def test_final_cleanup_capacity_exhaustion_returns_red(self):
        m.ACTIVE_DIAGNOSTIC=None
        output=self.root/'capacity-qualifier'
        args=SimpleNamespace(source_revision='a'*40,output_dir=output,inputs=self.root,fetch_inputs=False)
        for version in ('2.7.39','2.8.1'):
            (self.root/('forge_autonomy-'+version+'-py3-none-any.whl')).write_bytes(b'pin')
        binding=dict(m.controller().PRESERVATION_ARTIFACT_BINDING)
        binding['installed_artifact_digest']=binding['wheel_sha256']='sha256:'+m.digest(self.root/'forge_autonomy-2.8.1-py3-none-any.whl')
        def fake_source(cmd,**kw):
            if cmd[1]=='show':return (m.CONTROLLER if cmd[-1].endswith('update_installed_forge.py') else Path(m.__file__)).read_bytes()
            return 'b'*40+'\n'
        def fixture_case(*args):
            # Only qualifier capacity fault injection; no actual matrix product effects.
            m.ACTIVE_DIAGNOSTIC.document['events']=[{}]*(m.MAX_DIAGNOSTIC_EVENTS-2)
            return {'result':'PASS'}
        with patch.object(m.subprocess,'check_output',side_effect=fake_source), patch.object(m,'controller',return_value=SimpleNamespace(PRESERVATION_ARTIFACT_BINDING=binding)), patch.object(m,'case',side_effect=fixture_case), patch.object(m,'denials',side_effect=fixture_case):
            self.assertEqual(m.qualify(args),1)
        receipt=json.loads((output/'published-preservation.public.json').read_text())
        diagnostic=json.loads((output/'published-preservation-diagnostics.public.json').read_text())
        self.assertEqual(receipt['result'],'FAIL')
        self.assertEqual(receipt['diagnostic_retention'],'INCOMPLETE')
        self.assertFalse(diagnostic['complete'])
        self.assertTrue(receipt['cleanup']['owned_runtime_home_credentials_scratch_removed'])

    def _retention_fault(self, label, data):
        if label.startswith('command-'):
            raise OSError('SECRET /Users/private retention fault')
        return self.original_retain(label, data)

    def test_real_timeout_retention_failure_preserves_primary_and_gate_red(self):
        # Real run timeout remains60 seconds. Only evidence-retention is injected.
        m.ACTIVE_DIAGNOSTIC=None
        output=self.root/'real-timeout-gate'
        args=SimpleNamespace(source_revision='a'*40,output_dir=output,inputs=self.root,fetch_inputs=False)
        original_retain=m.Diagnostics.retain
        def retain(d,label,data):
            if label.startswith('command-'):raise OSError('SECRET retention')
            return original_retain(d,label,data)
        def source(cmd,**kw):
            if cmd[1]=='show':return (m.CONTROLLER if cmd[-1].endswith('update_installed_forge.py') else Path(m.__file__)).read_bytes()
            return 'b'*40+'\n'
        def timeout_case(*unused):
            m.checkpoint('resume-command')
            return m.run([sys.executable,'-I','-c','import time; print("SECRET",flush=True); time.sleep(61)'],output,env={'PATH':'/usr/bin:/bin'})
        with patch.object(m.subprocess,'check_output',side_effect=source),patch.object(m,'case',side_effect=timeout_case),patch.object(m.Diagnostics,'retain',retain):
            self.assertEqual(m.qualify(args),1)
        receipt=json.loads((output/'published-preservation.public.json').read_text())
        diagnostic=json.loads((output/'published-preservation-diagnostics.public.json').read_text())
        self.assertEqual(receipt['failure']['category'],'COMMAND_TIMEOUT')
        self.assertEqual(diagnostic['primary_failure']['category'],'COMMAND_TIMEOUT')
        self.assertEqual(diagnostic['secondary_failure']['category'],'OS_ERROR')
        event=next(e for e in diagnostic['events'] if e.get('outcome')=='COMMAND_TIMEOUT')
        self.assertIsNone(event['exit_code'])
        self.assertFalse(diagnostic['complete'])
        self.assertTrue(receipt['cleanup']['owned_runtime_home_credentials_scratch_removed'])
        self.assertNotIn('SECRET',json.dumps(diagnostic)+json.dumps(receipt))

    def test_real_nonzero_retention_failure_preserves_primary_and_gate_red(self):
        m.ACTIVE_DIAGNOSTIC=None
        output=self.root/'real-nonzero-gate'
        args=SimpleNamespace(source_revision='a'*40,output_dir=output,inputs=self.root,fetch_inputs=False)
        original_retain=m.Diagnostics.retain
        def retain(d,label,data):
            if label.startswith('command-'):raise OSError('SECRET retention')
            return original_retain(d,label,data)
        def source(cmd,**kw):
            if cmd[1]=='show':return (m.CONTROLLER if cmd[-1].endswith('update_installed_forge.py') else Path(m.__file__)).read_bytes()
            return 'b'*40+'\n'
        def failed_case(*unused):
            m.checkpoint('resume-command')
            return m.run([sys.executable,'-I','-c','print(\'{"status":"ERROR","token":"SECRET"}\'); raise SystemExit(7)'],output,env={'PATH':'/usr/bin:/bin'})
        with patch.object(m.subprocess,'check_output',side_effect=source),patch.object(m,'case',side_effect=failed_case),patch.object(m.Diagnostics,'retain',retain):
            self.assertEqual(m.qualify(args),1)
        receipt=json.loads((output/'published-preservation.public.json').read_text())
        diagnostic=json.loads((output/'published-preservation-diagnostics.public.json').read_text())
        self.assertEqual(receipt['failure']['category'],'ASSERTION_FAILED')
        self.assertEqual(diagnostic['primary_failure']['category'],'ASSERTION_FAILED')
        self.assertEqual(diagnostic['secondary_failure']['category'],'OS_ERROR')
        event=next(e for e in diagnostic['events'] if e.get('outcome')=='COMMAND_NONZERO')
        self.assertEqual(event['exit_code'],7);self.assertEqual(event['status'],'ERROR')
        self.assertFalse(diagnostic['complete'])
        self.assertTrue(receipt['cleanup']['owned_runtime_home_credentials_scratch_removed'])
        self.assertNotIn('SECRET',json.dumps(diagnostic)+json.dumps(receipt))

    def test_success_and_expected_negative_keep_check_semantics_with_retention_fault(self):
        self.original_retain=self.d.retain
        for check,code in ((True,0),(False,7)):
            m.checkpoint('resume-command')
            with patch.object(self.d,'retain',side_effect=self._retention_fault):
                done=m.run([sys.executable,'-I','-c','print(\'{"status":"ERROR","token":"SECRET"}\'); raise SystemExit('+str(code)+')'],self.root,env={'PATH':'/usr/bin:/bin'},check=check)
            self.assertEqual(done.returncode,code)
            self.assertIsNone(self.d.document['primary_failure'])
            self.assertEqual(self.d.document['secondary_failure']['category'],'OS_ERROR')
            self.assertFalse(self.d.document['complete'])

    def test_workflow_upload_only_explicit_public_files(self):
        workflow=(SOURCE/'.github/workflows/ci.yml').read_text()
        section=workflow.split('name: forge-published-preservation-${{ github.sha }}')[1]
        self.assertIn('published-preservation-diagnostics.public.json',section)
        self.assertNotIn('private',section)
        self.assertIn('timeout-minutes: 3',workflow.split('Exact published 2.7.39 to 2.8.1 preservation maintenance')[1])

if __name__=='__main__':unittest.main()
