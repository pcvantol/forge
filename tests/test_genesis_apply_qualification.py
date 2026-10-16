"""First-chain evidence guard regressions; no actual EP grant/server/effects."""
from copy import deepcopy
from hashlib import sha256
from importlib.util import spec_from_file_location,module_from_spec
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import zipfile
from tests.test_genesis_apply_contract import dispatch_fixture
from forge.genesis_apply_contract import ep_request

ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('r57_first_chain',ROOT/'scripts/qualification/qualify_installed_genesis_apply.py')
Q=module_from_spec(spec);spec.loader.exec_module(Q)


class FirstChainEvidenceGuards(TestCase):
    def test_missing_qualified_pin_initializes_no_peer_or_scratch_and_retains_failure(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);args=SimpleNamespace(output_dir=root/'evidence',scratch_root=root/'untouched',python=Path('/unused'),wheel=root/'unused.whl')
            with patch.object(Q,'probe',return_value=None),patch.object(Q,'EPServer') as peer:
                with self.assertRaisesRegex(ValueError,'qualified producer'):Q.run(args)
                peer.assert_not_called()
            report=json.loads((args.output_dir/'first-real-installed-chain.public.json').read_bytes())
            self.assertEqual(report['result'],'FAIL');self.assertTrue(report['cleanup']);self.assertFalse(args.scratch_root.exists())

    def test_primary_pin_refusal_survives_secondary_receipt_write_error(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);args=SimpleNamespace(output_dir=root/'evidence',scratch_root=root/'untouched',python=Path('/unused'),wheel=root/'unused.whl')
            with patch.object(Q,'probe',return_value=None),patch.object(Q,'private',side_effect=OSError('sink unavailable')):
                with self.assertRaisesRegex(ValueError,'qualified producer') as observed:Q.run(args)
            self.assertTrue(any('receipt retention failed' in note for note in observed.exception.__notes__))

    def test_ep_owner_nonzero_preserved_when_report_retention_also_fails(self):
        server=Q.EPServer.__new__(Q.EPServer);server.args=SimpleNamespace(ep_python=Path('/unused'))
        server.root=Path('/unused');server.output=Path('/unused');server.data=Path('/unused/s');server.env={};server.command_counter=0
        report={'primary_failure':{'category':'COMMAND_NONZERO','observed_exit':7},'capture_complete':False,'actual_exit':7}
        with patch.object(Q.C.BINDING.CAPTURE,'capture',return_value=(report,b'',b'diagnostic')),patch.object(Q.C.BINDING.CAPTURE,'retain',side_effect=OSError('sink unavailable')):
            with self.assertRaises(RuntimeError) as observed:server.command('genesis_cli','issue')
        self.assertEqual(observed.exception.capture_report['primary_failure']['observed_exit'],7)
        self.assertTrue(any('report retention failed' in note for note in observed.exception.__notes__))

    def test_b8r_must_match_actual_original_commit_declaration_and_physical_target(self):
        original,plan,decision=dispatch_fixture();request,_=ep_request(original,plan,decision,'original')
        declaration=json.loads(request['bundle']['files']['.engineering-platform/repository.json']['utf8'])
        ids=plan['documents']['identity'];operation={'commit':'a'*40,'tree':'b'*40};target=Path('/private/tmp/synthetic-target')
        surface={**declaration,'validation':{**declaration['validation'],'description':None},'requirements':{'host':{},'tools':{}},'integrations':{}}
        rows={'ep_genesis_operations':[dict(operation_id='original',grant_id='grant',request_digest=sha256(Q.canonical(request)).hexdigest(),original_request=json.dumps(request),state='COMPLETE',project_id=ids['project_id'],repository_id=ids['repository_id'],evidence=json.dumps({'known':dict(commit_ref=operation['commit'],tree=operation['tree'],committed_declaration_verified=True)}))],
              'ep_project_registrations':[dict(project_id=ids['project_id'],status='ACTIVE',attachment_contract=json.dumps(dict(schema_version='1.0',authority_repository_id=ids['authority_repository_id'])))],
              'ep_repository_registrations':[dict(**ids,role='authority',attachment_contract=json.dumps(surface))],
              'ep_local_repository_bindings':[dict(project_id=ids['project_id'],repository_id=ids['repository_id'],local_root=str(target),state='BOUND')]}
        self.assertTrue(Q.verify_b8r(rows,request,operation,plan['documents'],target,'grant')['committed_registration_and_target_binding_verified'])
        for choice in ('target','declaration','authority','commit','grant'):
            changed=deepcopy(rows)
            if choice=='target':changed['ep_local_repository_bindings'][0]['local_root']='/private/tmp/foreign'
            elif choice=='declaration':changed['ep_repository_registrations'][0]['attachment_contract']='{}'
            elif choice=='authority':changed['ep_repository_registrations'][0]['authority_repository_id']='foreign'
            elif choice=='commit':changed['ep_genesis_operations'][0]['evidence']=json.dumps({'known':dict(commit_ref='f'*40,tree=operation['tree'],committed_declaration_verified=True)})
            else:changed['ep_genesis_operations'][0]['grant_id']='foreign'
            with self.subTest(choice=choice),self.assertRaises(ValueError):Q.verify_b8r(changed,request,operation,plan['documents'],target,'grant')

    def test_supplied_wheel_hash_cannot_substitute_changed_source_or_extra_installed_file(self):
        # Tiny synthetic Git/package fixture, not an EP release or qualification.
        with TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();package=source/'src/engineering_platform';(package/'schemas').mkdir(parents=True)
            (package/'__init__.py').write_text('VALUE=1\n');(package/'schemas/genesis-local-bootstrap-v1.schema.json').write_text('{}\n')
            (source/'pyproject.toml').write_text('[project]\nname="engineering-platform"\nversion="2.3.123"\n[project.scripts]\nep="engineering_platform:main"\n[tool.setuptools.package-data]\nengineering_platform=["schemas/*.json"]\n')
            def git(*args):return subprocess.check_output(['git','-C',str(source),*args],stderr=subprocess.DEVNULL)
            git('init');git('add','.');git('-c','user.name=Synthetic','-c','user.email=synthetic@example.invalid','commit','-m','synthetic fixture')
            revision=git('rev-parse','HEAD').decode().strip();tree=git('rev-parse','HEAD^{tree}').decode().strip()
            installed=root/'installed/engineering_platform';(installed/'schemas').mkdir(parents=True)
            payload={'engineering_platform/__init__.py':b'VALUE=1\n','engineering_platform/schemas/genesis-local-bootstrap-v1.schema.json':b'{}\n'}
            for name,raw in payload.items():(installed.parent/name).write_bytes(raw)
            wheel=root/'synthetic.whl'
            def build(changed=False):
                with zipfile.ZipFile(wheel,'w') as archive:
                    for name,raw in payload.items():archive.writestr(name,b'VALUE=2\n' if changed and name.endswith('__init__.py') else raw)
                    archive.writestr('engineering_platform-2.3.123.dist-info/METADATA','Name: engineering-platform\nVersion: 2.3.123\n')
                    archive.writestr('engineering_platform-2.3.123.dist-info/entry_points.txt','[console_scripts]\nep = engineering_platform:main\n')
            args=SimpleNamespace(ep_source_root=source,ep_source_revision=revision,ep_source_tree=tree,ep_wheel=wheel,ep_python=Path('/unused'),producer_pin=dict(producer_tree=tree,producer_version='2.3.123',producer_schema_sha256=sha256(b'{}\n').hexdigest()))
            def info():return dict(package=str(installed),version='2.3.123',direct={'archive_info':{'hashes':{'sha256':args.ep_wheel_sha256}}},entries={'ep':'engineering_platform:main'})
            build();args.ep_wheel_sha256=sha256(wheel.read_bytes()).hexdigest()
            with patch.object(Q,'probe',side_effect=lambda *a:info()):self.assertTrue(Q.ep_payload(args)['source_payload_entrypoints_exact'])
            (installed/'extra.py').write_text('extra=1\n')
            with patch.object(Q,'probe',side_effect=lambda *a:info()),self.assertRaisesRegex(ValueError,'inventory'):Q.ep_payload(args)
            (installed/'extra.py').unlink();build(changed=True);args.ep_wheel_sha256=sha256(wheel.read_bytes()).hexdigest()
            (installed/'__init__.py').write_text('VALUE=2\n')
            with patch.object(Q,'probe',side_effect=lambda *a:info()),self.assertRaisesRegex(ValueError,'payload differs'):Q.ep_payload(args)

    def test_owned_session_children_stop_even_after_unreaped_leader_exit(self):
        import os,sys,time,signal
        if not hasattr(os,'waitid') or not hasattr(os,'WNOWAIT'):self.skipTest('nonreaping POSIX wait unavailable')
        helper='''from dataclasses import dataclass
from pathlib import Path
import os,subprocess,hashlib
@dataclass(frozen=True)
class ProcessIdentity:
 pid:int
 process_group:int
 start_fingerprint:str
 executable_identity:str
def _canonical_executable_identity(value):return str(Path(value).resolve())
def capture_process_identity(pid,group=None):
 try:
  actual=os.getpgid(pid)
  if group is not None and actual!=group:return None
  text=subprocess.check_output(['ps','-o','lstart=','-o','comm=','-p',str(pid)],text=True,stderr=subprocess.DEVNULL).strip().split(maxsplit=5)
  if len(text)!=6:return None
  birth=' '.join(text[:5])
  return ProcessIdentity(pid,actual,hashlib.sha256(f'{pid}|{actual}|{birth}'.encode()).hexdigest(),_canonical_executable_identity(text[5][:512]))
 except (OSError,subprocess.SubprocessError):return None
def verify_process_identity(expected):
 actual=capture_process_identity(expected.pid,expected.process_group)
 return 'NOT_ACTIVE' if actual is None else 'MATCH' if actual==expected else 'MISMATCH'
'''
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/'provider_process_identity.py').write_text(helper);marker=root/'child.pid'
            code="import subprocess,sys;from pathlib import Path;p=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(30)']);Path(sys.argv[1]).write_text(str(p.pid))"
            parent=subprocess.Popen([sys.executable,'-I','-c',code,str(marker)],start_new_session=True)
            server=Q.EPServer.__new__(Q.EPServer);server.args=SimpleNamespace(ep_package=root);server.process=parent;server.log=None
            server.facts=lambda:({},[],{})
            try:
                deadline=time.monotonic()+5
                while not marker.exists() or os.waitid(os.P_PID,parent.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is None:
                    if time.monotonic()>deadline:raise TimeoutError('own fixture leader exit')
                    time.sleep(.01)
                child=int(marker.read_text());os.kill(child,0)
                server.stop()
                self.assertIsNotNone(parent.returncode)
                with self.assertRaises(ProcessLookupError):os.killpg(parent.pid,0)
            finally:
                if parent.returncode is None:
                    try:os.killpg(parent.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    parent.wait(timeout=5)
