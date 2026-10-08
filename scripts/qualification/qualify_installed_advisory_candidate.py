"""Installed Candidate producer; only external model/OS/repository doubles."""
from contextlib import ExitStack,closing
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from threading import Thread
import os,sys,json,time,sqlite3,subprocess
import forge

SOURCE=Path(__file__).resolve().parents[2]

def test_driver():
    for name,path in [('test_advisory_http','tests/test_advisory_http.py'),('candidate_qualification_cases','tests/test_advisory_candidate_http.py')]:
        spec=spec_from_file_location(name,SOURCE/path);module=module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

def phase(root,stage):
    cases=test_driver();q=cases.qual;original=q.utils.fixture.IDENTITY
    def identity():
        if stage in ('crash-before-effect','crash-after-effect'):
            path=root/'runtime'/'governance'/'candidates.sqlite'
            if path.exists():
                try:
                    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                        pending=db.execute('SELECT count(*) FROM advisory_candidate_intents').fetchone()[0]
                        done=db.execute('SELECT count(*) FROM advisory_candidate_registrations').fetchone()[0]
                    if pending and done==(0 if stage=='crash-before-effect' else 1):
                        (root/'candidate-boundary.ready.private').write_text(str(os.getpid()));time.sleep(20)
                except sqlite3.Error:pass
        return original
    with patch.object(q.utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity):
        with ExitStack() as stack:
            server=q.ForgeServerRuntime(data_root=root/'runtime',credential_file=root/'admin.private',host='127.0.0.1',port=0,provider_id=q.utils.fixture.PROVIDER)
            worker=Thread(target=server.server.serve_forever,daemon=True);worker.start()
            stack.callback(server.server.server_close);stack.callback(worker.join,3);stack.callback(server.server.shutdown)
            port=server.server.server_address[1];token=root/'candidate.private';payload=json.loads((root/'registration-request.private.json').read_text())
            target='/v1/advisory-candidates/conversation-alice/proposals/candidate-proposal/registrations'
            if stage=='read':return cases.call(port,token,'GET',target+'/registration-1')
            if stage=='new-key':return cases.call(port,token,'POST',target,{**payload,'operation_id':'new-recovery-key'})
            if stage=='lost-response':
                import socket
                raw=json.dumps(payload).encode();sock=socket.create_connection(('127.0.0.1',port),timeout=15)
                try:
                    headers=('POST '+target+' HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer '+token.read_text().strip()+'\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw))+'\r\nConnection: close\r\n\r\n').encode();sock.sendall(headers+raw);received=b''
                    while b'\r\n\r\n' not in received:
                        piece=sock.recv(1);assert piece;received+=piece
                    assert b'200' in received.splitlines()[0]
                finally:sock.close()
                return {'lost_body':True,'pid':os.getpid()}
            return cases.call(port,token,'POST',target,payload)

def process_case(root,stage):
    cases=test_driver();q=cases.qual;cases.setup(root)
    with q.http(root) as port:
        token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice'
        _,cap=cases.call(port,token,'GET','/v1/advisory-candidates/capability');_,s=cases.call(port,token,'GET',base+'/source/first')
        status,saved=cases.call(port,token,'POST',base+'/proposals',cases.definition(s['source'],cap));assert status==200
        payload=cases.command(saved['proposal']);(root/'registration-request.private.json').write_text(json.dumps(payload));(root/'registration-request.private.json').chmod(0o600)
    env=os.environ.copy();source=Path(forge.__file__).resolve().is_relative_to(SOURCE)
    if source:env['PYTHONPATH']=str(SOURCE)
    prefix=[sys.executable]+([] if source else ['-I'])
    command=[*prefix,str(Path(__file__).resolve()),'--phase',stage,'--root',str(root)]
    if stage.startswith('crash'):
        with (root/'candidate-phase.private.log').open('w') as log:
            child=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+15
                while not (root/'candidate-boundary.ready.private').exists():
                    if child.poll() is not None or time.monotonic()>deadline:raise AssertionError('owned Candidate process boundary not reached')
                    time.sleep(.02)
                assert int((root/'candidate-boundary.ready.private').read_text())==child.pid;child.kill();child.wait(timeout=5)
            finally:
                if child.poll() is None:child.kill();child.wait()
    else:
        done=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=30);assert done.returncode==0,done.stderr
    def reopen(stage):
        done=subprocess.run([*prefix,str(Path(__file__).resolve()),'--phase',stage,'--root',str(root)],cwd=root,env=env,capture_output=True,text=True,timeout=30)
        assert done.returncode==0,done.stderr;return json.loads(done.stdout)
    status,read=reopen('read');assert status==200,(status,read)
    if stage=='crash-before-effect':
        assert read['state']=='PENDING';assert reopen('new-key')[0]==409
        with closing(sqlite3.connect(root/'runtime'/'governance'/'candidates.sqlite')) as db:assert db.execute('SELECT count(*) FROM candidates').fetchone()[0]==0
    status,out=reopen('replay');assert status==200,(status,out)
    status,later=reopen('read');assert status==200 and out['original_receipt']==later['original_receipt']
    with closing(sqlite3.connect(root/'runtime'/'governance'/'candidates.sqlite')) as db:
        assert db.execute('SELECT count(*) FROM candidates').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM advisory_candidate_registrations').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM advisory_candidate_intents').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM allocations').fetchone()[0]==0
    assert len((root/'provider-requests.private.jsonl').read_text().splitlines())==1
    return {'case':stage,'result':'PASS','candidate_count':1,'provider_invocations':1,'same_original_receipt':True,'fresh_processes':True}

def positive_control(root):
    cases=test_driver();grant=cases.setup(root)
    with cases.qual.http(root) as port:
        token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice';_,cap=cases.call(port,token,'GET','/v1/advisory-candidates/capability');_,s=cases.call(port,token,'GET',base+'/source/first');_,saved=cases.call(port,token,'POST',base+'/proposals',cases.definition(s['source'],cap))
        payload=cases.command(saved['proposal']);target=base+'/proposals/candidate-proposal/registrations';assert cases.call(port,token,'POST',target,payload)[0]==200
        grant.revoke(grant._records()[0]['grant_id'])
        assert cases.call(port,token,'POST',target,payload)[0]==200,'revoked-positive-candidate-replay-detected'

def installed(args):
    import shutil,unittest
    from io import StringIO
    cases=test_driver();utils=cases.qual.utils;output=args.output_dir.resolve()
    artifact=utils._installed_wheel(args.wheel,source_revision=args.source_revision,verify_source=True)
    if not args.child:
        if output.exists():raise ValueError('fresh qualification output required')
        output.mkdir();(output/'qualification-owner.private.json').write_text(json.dumps({'source_revision':args.source_revision,'qualification':'INSTALLED_ADVISORY_CANDIDATE_V1'}))
        command=[sys.executable,'-I',str(Path(__file__).resolve()),'--wheel',str(args.wheel.resolve()),'--source-revision',args.source_revision,'--output-dir',str(output),'--child']
        if args.failure_control:command.append('--failure-control')
        done=subprocess.run(command,cwd=output,env=utils._child_env(output/'isolated'),capture_output=True,text=True,timeout=240)
        (output/'child.private.log').write_text(done.stdout+done.stderr)
        if done.returncode not in (0,1):raise RuntimeError('installed Candidate child failed')
        receipt=json.loads((output/'installed-advisory-candidate.public.json').read_text());assert receipt['artifact']==artifact and receipt['source_revision']==args.source_revision
        print(json.dumps({'result':receipt['result'],'case_count':receipt['case_count'],'failure':receipt['failure']}));return done.returncode
    for name in ['HOME','CODEX_HOME','TMPDIR']:assert Path(os.environ[name]).resolve().is_relative_to(output)
    receipt={'qualification':'INSTALLED_ADVISORY_CANDIDATE_V1','source_revision':args.source_revision,'artifact':artifact,'result':'FAIL','case_count':0,'cases':[],'failure':None,'expected_failure_control':args.failure_control,'external_fault':'REVOKED_POSITIVE_CANDIDATE_GRANT' if args.failure_control else None,'limitations':['Real HTTP/auth/advice/proposals/canonical lifecycle/intent/receipt/readback; external model executable, OS identity and public repository transport only.','No live model quality, approval/Mission/Action/EP/target effect, native consumer, operational users instance, release or full family claim.'],'cleanup':{'owned_runtime_home_credentials_scratch_removed':False}}
    stage='positive-candidate-replay' if args.failure_control else 'selected-service-matrix'
    try:
        if args.failure_control:
            with TemporaryDirectory() as tmp:positive_control(Path(tmp)/'control')
            raise AssertionError('expected positive gate did not fail')
        methods=unittest.defaultTestLoader.getTestCaseNames(cases.AdvisoryCandidateHTTPTests)
        for name in methods:
            stage=name;stream=StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite([cases.AdvisoryCandidateHTTPTests(name)]));(output/(name+'.private.log')).write_text(stream.getvalue())
            if not result.wasSuccessful():raise AssertionError('installed Candidate acceptance failed')
            receipt['cases'].append({'case':name,'result':'PASS'})
        receipt['case_count']=len(methods);receipt['result']='ADVISORY_CANDIDATE_PASS'
    except Exception as e:
        receipt['failure']={'type':type(e).__name__,'stage':stage,'detail':'Declared Candidate gate failed'}
        if args.failure_control:assert isinstance(e,AssertionError) and 'revoked-positive-candidate-replay-detected' in str(e)
    finally:
        for name in ['home','scratch','config']:
            path=output/'isolated'/name
            if path.exists():shutil.rmtree(path)
        receipt['cleanup']['owned_runtime_home_credentials_scratch_removed']=True
    (output/'installed-advisory-candidate.public.json').write_text(json.dumps(receipt,indent=2)+'\n');return 0 if receipt['result']=='ADVISORY_CANDIDATE_PASS' else 1

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--phase');p.add_argument('--root',type=Path);p.add_argument('--wheel',type=Path);p.add_argument('--source-revision');p.add_argument('--output-dir',type=Path);p.add_argument('--child',action='store_true');p.add_argument('--failure-control',action='store_true');a=p.parse_args()
    if a.phase:print(json.dumps(phase(a.root.resolve(),a.phase)));raise SystemExit(0)
    raise SystemExit(installed(a))
