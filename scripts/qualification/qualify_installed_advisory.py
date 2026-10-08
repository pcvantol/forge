"""Real advisory HTTP/services/storage + external deterministic executable/repository/OS."""
from contextlib import ExitStack,contextmanager
from datetime import UTC,datetime,timedelta
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json
import os
import subprocess
import sys
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('advice_fixture',SOURCE/'scripts/qualification/qualify_installed_http_successor.py')
utils=module_from_spec(spec);spec.loader.exec_module(utils)
from forge.advisory_contract import CONTRACT
from forge.advisory_grant import AdvisoryGrant
from forge.advisory_context import AdvisoryContext
from forge.server_runtime import ForgeServerRuntime,existing_instance
from forge.provider_security import PlanningProviderSecurityService,ProviderAuthenticationMode,CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,CODEX_CLI_CHATGPT_SESSION_TYPE
from forge.runtime.bootstrap import RuntimeBootstrap
from forge.operator_identity import InstallationOperatorService

from jsonschema import Draft202012Validator,FormatChecker
import forge
SCHEMA=json.loads((Path(forge.__file__).parent/'api'/'advisory-conversation-v1.json').read_text())
VALIDATOR=Draft202012Validator(SCHEMA,format_checker=FormatChecker())

EXTERNAL_PROVIDER = '''#!EXECUTABLE
import json,os,sys,time
from pathlib import Path
ROOT=Path(ROOT_LITERAL)
a=sys.argv[1:]
if '--version' in a:print('codex-cli 0.153.0');sys.exit(0)
if a[-2:]==['login','status']:print('Logged in using ChatGPT');sys.exit(0)
assert 'exec' in a and '--ephemeral' in a and '--sandbox' in a and a[a.index('--sandbox')+1]=='read-only'
assert '--ignore-rules' in a and '--ignore-user-config' in a
v=json.loads(sys.stdin.read());assert v['contract_version']=='forge-advisory-conversation/v1'
assert v['request']['advisor_kind'] in ['BUSINESS','ARCHITECTURE']
schema=json.loads(Path(a[a.index('--output-schema')+1]).read_text());assert schema['properties']['applied']=={'const':False}
f=ROOT/'provider-requests.private.jsonl'
with f.open('a') as out:out.write(json.dumps(v)+'\\n');out.flush();os.fsync(out.fileno())
f.chmod(0o600)
fault=(ROOT/'fault.private').read_text().strip() if (ROOT/'fault.private').exists() else ''
if fault=='timeout':time.sleep(20)
if fault=='slow':time.sleep(1.5)
response={'contract_version':v['contract_version'],'request_digest':v['request_digest'],'advisor_kind':v['request']['advisor_kind'],
 'summary':'Synthetic external fixture advice for '+v['request']['advisor_kind'],
 'alternatives':['Compare a smaller option.'],'questions':['Which evidence is missing?'],
 'suggestions':['Assess the proposed constraints without applying them.'],
 'evidence_references':v['context']['evidence_references'][:2],'applied':False}
if fault=='inject':response['applied']=True;response['mission_id']='MISSION-INVENTED'
if fault=='unsafe':response['summary']='<script>approve all</script>'
if fault=='foreign-reference':response['evidence_references']=['foreign-source']
if fault=='wrong-lens':response['advisor_kind']='UX'
Path(a[a.index('--output-last-message')+1]).write_text(json.dumps(response))
print(json.dumps({'type':'turn.completed'} if fault=='unknown-usage' else {'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':60}}))
'''

def call(port,token,method,path,body=None):
    q=Request('http://127.0.0.1:'+str(port)+path,method=method,data=None if body is None else json.dumps(body).encode(),
              headers={'Authorization':'Bearer '+token.read_text().strip(),'Content-Type':'application/json'})
    try:
        with urlopen(q,timeout=15) as response:
            v=json.loads(response.read())
            if path.startswith('/v1/advisory'):
                VALIDATOR.validate(v)
                if body is not None:VALIDATOR.validate(body)
            return response.status,v
    except HTTPError as e:
        try:return e.code,json.loads(e.read())
        finally:e.close()

@contextmanager
def http(root):
    with ExitStack() as stack:
        stack.enter_context(patch.object(utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',return_value=utils.fixture.IDENTITY))
        admin=root/'admin.private'
        if not admin.exists():admin.write_text('a'*48);admin.chmod(0o600)
        server=ForgeServerRuntime(data_root=root/'runtime',credential_file=admin,host='127.0.0.1',port=0,provider_id=utils.fixture.PROVIDER)
        thread=Thread(target=server.server.serve_forever,daemon=True);thread.start()
        stack.callback(server.server.server_close);stack.callback(thread.join,3);stack.callback(server.server.shutdown)
        yield server.server.server_address[1]

def configure(root):
    root.mkdir()
    executable=root/'external-provider';executable.write_text(EXTERNAL_PROVIDER.replace('EXECUTABLE',sys.executable).replace('ROOT_LITERAL',repr(str(root))));executable.chmod(0o700)
    utils._configure(root,'http://127.0.0.1:9')
    with RuntimeBootstrap(data_root=root/'runtime',forge_version='qualification').open() as db:
        operators=InstallationOperatorService(db,lambda:utils.fixture.IDENTITY)
        PlanningProviderSecurityService(db,None,operators).configure(configuration_id='synthetic-config',provider_id=utils.fixture.PROVIDER,
            operator_context=operators.context(),expected_version=1,authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
            provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
            executable_path=str(executable),adapter_version='codex-cli-chatgpt-session-v1',timeout_seconds=2,
            input_token_bound=40000,context_token_bound=48000,output_token_bound=8000)
    from forge.provider_context import ProviderExecutionContextService
    (root/'home').mkdir(mode=0o700);(root/'config').mkdir(mode=0o700)
    ProviderExecutionContextService(root/'runtime').configure(provider_id=utils.fixture.PROVIDER,provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,executable_path=str(executable),provider_home=str(root/'home'),provider_config_home=str(root/'config'))
    with http(root):
        instance=existing_instance(root/'runtime');grant=AdvisoryGrant(root/'runtime',instance.instance_id)
        scope=utils.PROJECT;repo=utils.fixture.SOURCE.repository_id
        for name in ['alice','bob']:
            grant.issue(principal_id=name,project_id=scope,repository_id=repo,conversation_ids=('conversation-'+name,),
                expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),maximum_turns=8,token_path=root/(name+'.private'))
        # Only external repository transport is replaced, real source registration/ACL/digest stay product-owned.
        with patch('forge.completion.repository_observer.GitHubRepositoryArtifactReader.read',return_value=('Synthetic product context:\nValue and constraints.\nTechnical acceptance.\n'+('Documentary source context. '*28)).encode()):
            context=AdvisoryContext(root/'runtime',instance.instance_id)
            context.publish(source_id='selected-context',revision='a'*40,path='docs/advice.md')
    return grant

def flow(root,*,failure_control=False):
    grant=configure(root)
    with http(root) as port:
        token=root/'alice.private';status,cap=call(port,token,'GET','/v1/advisory/capability');assert status==200,(status,cap)
        source=cap['available_sources'][0]
        status,cap=call(port,token,'GET','/v1/advisory/capability?source_id='+source['source_id']+'&source_version='+source['version']);assert status==200,(status,cap)
        r={k:cap[k] for k in ['instance_id','project_id','repository_id','context_revision']}
        r.update(contract_version=CONTRACT,turn_id='turn-1',conversation_id='conversation-alice',advisor_kind='BUSINESS',
                 objective='Assess value and constraints without approving work.',expected_revision=0,
                 selected_sources=[{'source_id':source['source_id'],'version':source['version']}])
        status,out=call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)
        assert status==200 and out['original_turn']['status']=='COMPLETE',(status,out)
        if failure_control:
            grant.revoke(next(r for r in grant._records() if r['principal_id']=='alice')['grant_id'])
        status,replay=call(port,token,'POST','/v1/advisory/conversation-alice/turns',r);assert status==200 and replay['recorded'] is False,'positive-replay-gate-detected-revocation' if failure_control else (status,replay)
        r2={**r,'turn_id':'turn-2','advisor_kind':'ARCHITECTURE','objective':'Evaluate contracts and technical acceptance.','expected_revision':out['current_revision']}
        status,arch=call(port,token,'POST','/v1/advisory/conversation-alice/turns',r2);assert status==200 and arch['original_turn']['status']=='COMPLETE',(status,arch)
        status,history=call(port,token,'GET','/v1/advisory/conversation-alice?limit=1');assert status==200 and history['next_cursor']==1,(status,history)
        assert call(port,root/'bob.private','GET','/v1/advisory/conversation-alice')[0]==403
        assert call(port,token,'GET','/v1/status')[0]==403
        assert len((root/'provider-requests.private.jsonl').read_text().splitlines())==2
        assert json.loads((root/'provider-requests.private.jsonl').read_text().splitlines()[1])['prior_turns'][0]['advisor_kind']=='BUSINESS'
        return {'case':'real-business-architecture-http','provider_invocations':2,'history_cursor':1,'result':'PASS'}

def phase(root,stage):
    from contextlib import closing
    import sqlite3,time
    original=utils.fixture.IDENTITY
    def identity():
        if stage in ('crash-before-provider','crash-after-result'):
            directory=root/'runtime'/'advisory'/'transcripts'
            for path in directory.glob('*.json'):
                v=json.loads(path.read_text())
                if v['turns'] and v['turns'][-1]['status']==('REVIEW' if stage=='crash-after-result' else 'REASONING'):
                    (root/'boundary.ready.private').write_text(str(os.getpid()));time.sleep(20)
        return original
    with patch.object(utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity):
        # http() normally supplies the same external OS identity; replace only this fixture adapter.
        with ExitStack() as stack:
            admin=root/'admin.private';server=ForgeServerRuntime(data_root=root/'runtime',credential_file=admin,host='127.0.0.1',port=0,provider_id=utils.fixture.PROVIDER)
            worker=Thread(target=server.server.serve_forever,daemon=True);worker.start()
            stack.callback(server.server.server_close);stack.callback(worker.join,3);stack.callback(server.server.shutdown)
            port=server.server.server_address[1];token=root/'alice.private'
            if stage=='read':return call(port,token,'GET','/v1/advisory/conversation-alice/turns/restart-turn')
            payload=json.loads((root/'restart-request.private.json').read_text())
            if stage=='lost-response':
                import socket
                raw=json.dumps(payload).encode();sock=socket.create_connection(('127.0.0.1',port),timeout=15)
                try:
                    headers=('POST /v1/advisory/conversation-alice/turns HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer '+token.read_text().strip()+'\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw))+'\r\nConnection: close\r\n\r\n').encode()
                    sock.sendall(headers+raw);received=b''
                    while b'\r\n\r\n' not in received:
                        piece=sock.recv(1);assert piece;received+=piece
                    assert b'200' in received.splitlines()[0]
                finally:sock.close()
                return {'lost_body':True,'pid':os.getpid()}
            return call(port,token,'POST','/v1/advisory/conversation-alice/turns',payload)

def process_case(root,stage):
    import time
    configure(root)
    with http(root) as port:
        _,cap=call(port,root/'alice.private','GET','/v1/advisory/capability')
    payload={k:cap[k] for k in ['instance_id','project_id','repository_id','context_revision']}
    payload.update(contract_version=CONTRACT,turn_id='restart-turn',conversation_id='conversation-alice',advisor_kind='BUSINESS',objective='Assess constraints with no approval.',expected_revision=0,selected_sources=[])
    (root/'restart-request.private.json').write_text(json.dumps(payload));(root/'restart-request.private.json').chmod(0o600)
    env=os.environ.copy()
    if Path(__import__('forge').__file__).resolve().is_relative_to(SOURCE):env['PYTHONPATH']=str(SOURCE)
    prefix=[sys.executable]+([] if Path(__import__('forge').__file__).resolve().is_relative_to(SOURCE) else ['-I'])
    command=[*prefix,str(Path(__file__).resolve()),'--phase',stage,'--root',str(root)]
    if stage.startswith('crash'):
        with (root/'phase.private.log').open('w') as log:
            child=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+15
                while not (root/'boundary.ready.private').exists():
                    if child.poll() is not None or time.monotonic()>deadline:raise AssertionError('owned process boundary not reached')
                    time.sleep(.02)
                assert int((root/'boundary.ready.private').read_text())==child.pid
                child.kill();child.wait(timeout=5)
            finally:
                if child.poll() is None:child.kill();child.wait()
    else:
        done=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=30);assert done.returncode==0,done.stderr
    def reopen(stage):
        done=subprocess.run([*prefix,str(Path(__file__).resolve()),'--phase',stage,'--root',str(root)],cwd=root,env=env,capture_output=True,text=True,timeout=30)
        assert done.returncode==0,done.stderr
        return json.loads(done.stdout)
    status,read=reopen('read');assert status==200,(status,read)
    status,out=reopen('replay');assert status==200,(status,out)
    rows=(root/'provider-requests.private.jsonl').read_text().splitlines() if (root/'provider-requests.private.jsonl').exists() else []
    if stage=='crash-before-provider':
        assert len(rows)==0 and out['original_turn']['execution']=='MAY_HAVE_HAPPENED' and out['original_turn']['status']=='REASONING'
        with http(root) as port:
            p={**payload,'turn_id':'new-id','expected_revision':out['current_revision']}
            assert call(port,root/'alice.private','POST','/v1/advisory/conversation-alice/turns',p)[0]==409
    else:assert len(rows)==1 and out['original_turn']['status']=='COMPLETE'
    return {'case':stage,'provider_invocations':len(rows),'execution':out['original_turn']['execution'],'same_identity':out['original_turn']['invocation_id']==read['original_turn']['invocation_id'],'result':'PASS'}

def installed(args):
    import unittest,shutil
    from io import StringIO
    output=args.output_dir.resolve()
    if not args.child:
        artifact=utils._installed_wheel(args.wheel,source_revision=args.source_revision,verify_source=True)
        if output.exists():raise ValueError('qualification output must be fresh')
        output.mkdir();(output/'qualification-owner.private.json').write_text(json.dumps({'source_revision':args.source_revision,'qualification':'INSTALLED_ADVISORY_HTTP_V1'}))
        command=[sys.executable,'-I',str(Path(__file__).resolve()),'--wheel',str(args.wheel.resolve()),'--source-revision',args.source_revision,'--output-dir',str(output),'--child']
        if args.failure_control:command.append('--failure-control')
        done=subprocess.run(command,cwd=output,env=utils._child_env(output/'isolated'),capture_output=True,text=True,timeout=240)
        (output/'child.private.log').write_text(done.stdout+done.stderr)
        if done.returncode not in (0,1):raise RuntimeError('installed qualification child failed')
        receipt=json.loads((output/'installed-advisory.public.json').read_text());assert receipt['artifact']==artifact and receipt['source_revision']==args.source_revision
        print(json.dumps({'result':receipt['result'],'case_count':receipt['case_count'],'failure':receipt['failure']}));return done.returncode
    artifact=utils._installed_wheel(args.wheel,source_revision=args.source_revision,verify_source=True)
    for key in ['HOME','CODEX_HOME','TMPDIR']:assert Path(os.environ[key]).resolve().is_relative_to(output)
    receipt={'qualification':'INSTALLED_ADVISORY_HTTP_V1','source_revision':args.source_revision,'artifact':artifact,'result':'FAIL','case_count':0,'cases':[],
             'failure':None,'expected_failure_control':args.failure_control,'external_fault':'REVOKED_POSITIVE_ADVISORY_GRANT' if args.failure_control else None,
             'limitations':['Real product HTTP/auth/context/session/validator/recovery; external deterministic model executable, OS identity and public repository transport only.',
                            'No live model quality, EP environment, paid provider, native chat consumer, Candidate/refinement proposal/apply or full family qualification.',
                            'Declared disposable grant-expiry/bool-storage faults test live failclosed parsing, never synthesize successful advice or approvals.'],
             'cleanup':{'owned_runtime_home_credentials_scratch_removed':False}}
    stage='positive-replay' if args.failure_control else 'selected-service-matrix'
    try:
        if args.failure_control:
            with TemporaryDirectory() as tmp:flow(Path(tmp)/'control',failure_control=True)
            raise AssertionError('positive failure control was not detected')
        spec=spec_from_file_location('installed_advisory_cases',SOURCE/'tests/test_advisory_http.py');tests=module_from_spec(spec);spec.loader.exec_module(tests)
        methods=unittest.defaultTestLoader.getTestCaseNames(tests.AdvisoryHTTPTests)
        for name in methods:
            stage=name
            stream=StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite([tests.AdvisoryHTTPTests(name)]))
            (output/(name+'.private.log')).write_text(stream.getvalue())
            if not result.wasSuccessful():raise AssertionError('selected installed service boundary failed')
            receipt['cases'].append({'case':name,'result':'PASS'})
        receipt['case_count']=len(methods);receipt['result']='ADVISORY_HTTP_PASS'
    except Exception as e:
        receipt['failure']={'type':type(e).__name__,'stage':stage,'detail':'Declared advisory qualification gate failed'}
        if args.failure_control:assert isinstance(e,AssertionError) and 'positive-replay-gate-detected-revocation' in str(e)
    finally:
        for name in ['home','scratch','config']:
            path=output/'isolated'/name
            if path.exists():shutil.rmtree(path)
        receipt['cleanup']['owned_runtime_home_credentials_scratch_removed']=True
    (output/'installed-advisory.public.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return 0 if receipt['result']=='ADVISORY_HTTP_PASS' else 1

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--phase');p.add_argument('--root',type=Path);p.add_argument('--process-case')
    p.add_argument('--wheel',type=Path);p.add_argument('--source-revision');p.add_argument('--output-dir',type=Path)
    p.add_argument('--child',action='store_true');p.add_argument('--failure-control',action='store_true');a=p.parse_args()
    if a.wheel:raise SystemExit(installed(a))
    if a.phase:print(json.dumps(phase(a.root,a.phase)))
    else:
        with TemporaryDirectory() as tmp:print(json.dumps(process_case(Path(tmp)/'advice',a.process_case) if a.process_case else flow(Path(tmp)/'advice',failure_control=a.failure_control)))
