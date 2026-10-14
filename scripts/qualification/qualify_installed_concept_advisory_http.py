"""External HTTP against a separately installed Server and explicit model fixture."""
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import contextmanager
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from importlib.util import spec_from_file_location,module_from_spec
import argparse
import json
import socket
import subprocess
import time
import sys
import os

SOURCE=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('existing_http_binding',Path(__file__).with_name('qualify_installed_project_proposal_http.py'))
BINDING=module_from_spec(spec);spec.loader.exec_module(BINDING)
CONTRACT='forge-preproject-concept-advisory/v1'
MODELED_OS=False
PRIVATE_TRACE=None

def invocation(python,args):
    if not MODELED_OS:return [str(python),'-I',*args]
    code="import os,runpy,sys;from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter,NamedOperatorIdentity;MacOSGeneratedUIDIdentityAdapter.resolve=lambda self:NamedOperatorIdentity('r53-isolated-trusted-os-fixture',os.getuid());a=sys.argv[1:];sys.argv=a[1:] if a[0]=='-m' else a;runpy.run_module(sys.argv[0],run_name='__main__') if a[0]=='-m' else runpy.run_path(a[0],run_name='__main__')"
    return [str(python),'-I','-c',code,*args]


def retain_trace(method,path,status,body):
    if PRIVATE_TRACE is None:return
    raw=(json.dumps({'method':method,'path':path,'status':status,'response':body})+'\n').encode()
    if PRIVATE_TRACE.exists() and PRIVATE_TRACE.stat().st_size+len(raw)>1048576:raise RuntimeError('finite private HTTP capture exceeded')
    fd=os.open(PRIVATE_TRACE,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
    with os.fdopen(fd,'ab') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())

def call(port,token,method,path,body=None):
    request=Request('http://127.0.0.1:'+str(port)+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token.read_text().strip(),'X-Forge-Concept-Audience':'synthetic-workspace','Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=15) as response:
            body=json.loads(response.read());retain_trace(method,path,response.status,body);return response.status,body
    except HTTPError as error:
        try:
            body=json.loads(error.read());retain_trace(method,path,error.code,body);return error.code,body
        finally:error.close()


@contextmanager
def server(python,root,output):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with (output/'server.private.log').open('ab') as log:
        process=subprocess.Popen(invocation(python,['-m','forge','--data-root',str(root/'runtime'),'server','run','--credential-file',str(root/'admin.private'),'--port',str(port),'--provider-id','concept-fixture','--tick-interval','1']),cwd=root,stdout=log,stderr=log,start_new_session=True)
        try:
            deadline=time.monotonic()+15
            while True:
                if process.poll() is not None:raise RuntimeError('installed Server exited')
                try:
                    status,cap=call(port,root/'alice.private','GET','/v1/concept-advisory/capability')
                    if status==200:break
                    raise RuntimeError('installed capability denied')
                except (URLError,ConnectionError):
                    if time.monotonic()>deadline:raise TimeoutError('installed readiness timeout')
                    time.sleep(0.05)
            yield port,process.pid,cap
        finally:
            primary=sys.exc_info()[1]
            try:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            except Exception as error:
                if primary is None:raise
                primary.add_note('owned Server cleanup incomplete: '+type(error).__name__)


def run(args):
    global PRIVATE_TRACE
    output=args.output_dir;output.mkdir(mode=0o700);PRIVATE_TRACE=output/"http.private.jsonl"
    receipt={'result':'FAIL','cases':[],'cleanup':False,'provider_evidence':'MODELED_EXTERNAL_PROVIDER_NOT_LIVE_ADVICE_QUALITY',
             'transport_evidence':'ACTUAL_INSTALLED_HTTP_SEPARATE_SERVER_OS','operator_identity_evidence':'MODELED_TRUSTED_OS_FIXTURE' if MODELED_OS else 'ACTUAL_MACOS_GENERATED_UID',
             **BINDING.installed_binding(args.python,args.wheel,args.source_revision)}
    primary=None
    try:
        with TemporaryDirectory(prefix='concept-r53-') as scratch:
            parent=Path(scratch).resolve();root=parent/'synthetic'
            report,stdout,stderr=BINDING.CAPTURE.capture(invocation(args.python,[str(Path(__file__).with_name('concept_advisory_fixture.py')),str(root)]),case='explicit-setup',output=output,cwd=parent,env={'PATH':'/usr/bin:/bin','HOME':str(parent)},expected=0)
            if report['primary_failure'] or not report['capture_complete']:raise RuntimeError('synthetic setup failed')
            stdout_setup=stdout
            template=json.loads(subprocess.check_output(['git','-C',str(SOURCE),'show','HEAD:examples/concept-advisory/business-turn.json']))
            with server(args.python,root,output) as (port,first,cap):
                token=root/'alice.private';assert not (root/'provider-requests.private.jsonl').exists()
                receipt['cases'].append('capability-no-generation-no-project')
                request={**template,'instance_id':cap['instance_id'],'dossier_id':'dossier-alice','conversation_id':'conversation-alice','transfer_policy_digest':cap['provider']['transfer_policy_digest']}
                status,business=call(port,token,'POST','/v1/concept-advisory/turns',request);assert status==200 and business['original_turn']['status']=='COMPLETE',(status,business)
                assert call(port,token,'POST','/v1/concept-advisory/turns',request)[1]['original_turn']==business['original_turn']
                receipt['cases'].append('business-advice-exact-source-proposal-replay')
                revised=json.loads(json.dumps(request));revised.update(operation_id='followup',turn_id='followup',expected_revision=1)
                revised['briefing']['revision']=2;revised['briefing']['fields']['users']='Explicitly accepted local volunteers'
                # Contract digest is stdlib canonical, identical to owning digest.
                from hashlib import sha256
                revised['briefing_digest']='sha256:'+sha256(json.dumps(revised['briefing'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
                status,followup=call(port,token,'POST','/v1/concept-advisory/turns',revised);assert status==200 and followup['original_turn']['status']=='COMPLETE'
                receipt['cases'].append('followup-explicit-refined-briefing-prior-context')
                architecture={**revised,'operation_id':'architecture','turn_id':'architecture','advisor_kind':'ARCHITECTURE','expected_revision':2}
                status,architect=call(port,token,'POST','/v1/concept-advisory/turns',architecture);assert status==200 and architect['original_turn']['status']=='COMPLETE'
                receipt['cases'].append('architecture-exact-before-changeproposal')
                assert call(port,root/'bob.private','GET','/v1/concept-advisory/history?dossier_id=dossier-alice&conversation_id=conversation-alice')[0]==403
                assert call(port,root/'admin.private','GET','/v1/concept-advisory/capability')[0]==403
                receipt['cases'].append('cross-scope-admin-no-fallback')
                # Concurrent identical submit reads one durable original; no extra provider call.
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=2) as pool:
                    duplicated=list(pool.map(lambda _:call(port,token,'POST','/v1/concept-advisory/turns',architecture),range(2)))
                assert all(status==200 and body['original_turn']==architect['original_turn'] for status,body in duplicated)
                assert call(port,token,'POST','/v1/concept-advisory/turns',{**architecture,'message':'Changed same operation'})[0]==409
                receipt['cases'].append('concurrent-identical-original-and-changed-key-conflict')
                # Truly lost success response: close without reading any response bytes.
                lost={**architecture,'operation_id':'lost','turn_id':'lost','expected_revision':3}
                raw=json.dumps(lost).encode();header=('POST /v1/concept-advisory/turns HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+token.read_text().strip()+'\r\nX-Forge-Concept-Audience: synthetic-workspace\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw))+'\r\nConnection: close\r\n\r\n').encode()
                with socket.create_connection(('127.0.0.1',port),timeout=3) as client:client.sendall(header+raw);client.shutdown(socket.SHUT_WR)
                deadline=time.monotonic()+10
                while True:
                    status,original=call(port,token,'GET','/v1/concept-advisory/intents/lost?dossier_id=dossier-alice&conversation_id=conversation-alice')
                    if status==200 and original['original_turn']['status']=='COMPLETE':break
                    if time.monotonic()>deadline:raise TimeoutError('lost success recovery unavailable')
                    time.sleep(0.05)
                lost_turn=original['original_turn'];receipt['cases'].append('real-lost-success-original-intent')
            with server(args.python,root,output) as (port,second,cap):
                assert first!=second
                status,recovered=call(port,token,'GET','/v1/concept-advisory/intents/operation-one?dossier_id=dossier-alice&conversation_id=conversation-alice')
                assert status==200 and recovered['original_turn']==business['original_turn']
                assert call(port,token,'POST','/v1/concept-advisory/turns',architecture)[1]['original_turn']==architect['original_turn']
                assert call(port,token,'GET','/v1/concept-advisory/intents/lost?dossier_id=dossier-alice&conversation_id=conversation-alice')[1]['original_turn']==lost_turn
                receipt['cases'].append('separate-server-os-restart-original-intent-no-second-call')
                (root/'fault.private').write_text('inject')
                invalid={**architecture,'operation_id':'invalid','turn_id':'invalid','expected_revision':4}
                status,failed=call(port,token,'POST','/v1/concept-advisory/turns',invalid)
                assert status==200 and failed['original_turn']['status']=='FAILED' and failed['original_turn']['outcome']['output'] is None
                receipt['cases'].append('invalid-model-tools-patch-output-rejected-consumption-retained')
                (root/'fault.private').write_text('timeout')
                uncertain={**architecture,'operation_id':'uncertain','turn_id':'uncertain','expected_revision':5}
                status,pending=call(port,token,'POST','/v1/concept-advisory/turns',uncertain)
                assert status==200 and pending['original_turn']['status']=='UNCERTAIN'
                assert call(port,token,'POST','/v1/concept-advisory/turns',uncertain)[1]['original_turn']==pending['original_turn']
                assert call(port,token,'POST','/v1/concept-advisory/turns',{**uncertain,'operation_id':'another','turn_id':'another','expected_revision':6})[0]==409
                receipt['cases'].append('uncertain-modelstart-blocks-second-generation')
                (root/'fault.private').unlink()
            with server(args.python,root,output) as (port,third,cap):
                assert third not in (first,second)
                assert call(port,token,'GET','/v1/concept-advisory/intents/uncertain?dossier_id=dossier-alice&conversation_id=conversation-alice')[1]['original_turn']==pending['original_turn']
                assert call(port,token,'POST','/v1/concept-advisory/turns',{**uncertain,'operation_id':'restart-another','turn_id':'restart-another','expected_revision':6})[0]==409
                receipt['cases'].append('uncertain-restart-preserves-budget-no-second-call')
                from datetime import UTC,datetime,timedelta
                expiring=root/'expiring.private'
                issue=['-m','forge.concept_advisory_cli','--data-root',str(root/'runtime'),'issue','--principal-id','expiry-principal','--audience','synthetic-workspace','--provider-id','concept-fixture','--transfer-policy-digest',cap['provider']['transfer_policy_digest'],'--expires-at',(datetime.now(UTC)+timedelta(seconds=3)).isoformat(),'--token-file',str(expiring),'--dossier-id','expiry-dossier','--conversation-id','expiry-conversation','--permission','READ','--maximum-turns','1','--maximum-tokens','48000','--maximum-seconds','2']
                report,stdout,stderr=BINDING.CAPTURE.capture(invocation(args.python,issue),case='owner-expiry-issue',output=output,cwd=root,env={'PATH':'/usr/bin:/bin','HOME':str(root)},expected=0)
                assert report['capture_complete'] and not report['primary_failure']
                assert call(port,expiring,'GET','/v1/concept-advisory/capability')[0]==200
                deadline=time.monotonic()+5
                while call(port,expiring,'GET','/v1/concept-advisory/capability')[0]==200:
                    if time.monotonic()>deadline:raise TimeoutError('real concept grant expiry not enforced')
                    time.sleep(0.1)
                assert call(port,expiring,'GET','/v1/concept-advisory/history?dossier_id=expiry-dossier&conversation_id=expiry-conversation')[0]==401
                receipt['cases'].append('actual-owner-issued-readonly-real-expiry-no-modelcall')
                report,stdout,stderr=BINDING.CAPTURE.capture(invocation(args.python,['-m','forge.concept_advisory_cli','--data-root',str(root/'runtime'),'revoke','--grant-id',json.loads(stdout_setup)['grant_ids']['alice']]),case='owner-revoke',output=output,cwd=root,env={'PATH':'/usr/bin:/bin','HOME':str(root)},expected=0)
                assert report['capture_complete'] and not report['primary_failure']
                assert call(port,token,'GET','/v1/concept-advisory/history?dossier_id=dossier-alice&conversation_id=conversation-alice')[0]==401
                receipt['cases'].append('actual-owner-revocation-denies-history-and-replay')
            calls=[json.loads(line) for line in (root/'provider-requests.private.jsonl').read_text().splitlines()]
            assert len(calls)==6 and calls[1]['prior_turns'][0]['request']==request and calls[2]['request']['briefing']==revised['briefing']
            import sqlite3
            with sqlite3.connect(root/'runtime'/'forge.db') as db:
                for table in ['mission_id_allocations','mission_state','governance_decisions']:assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
                active_permits=db.execute('SELECT COUNT(*) FROM planning_provider_generation_permits').fetchone()[0];assert active_permits==0
                permits=db.execute("SELECT COUNT(*) FROM forge_operational_logs WHERE event='planning_provider_generation_permit_acquired'").fetchone()[0]
                committed=db.execute("SELECT COUNT(*) FROM forge_operational_logs WHERE event='planning_provider_generation_transport_committed'").fetchone()[0]
                assert permits==committed==6
            (output/'provider-requests.private.jsonl').write_bytes((root/'provider-requests.private.jsonl').read_bytes());(output/'provider-requests.private.jsonl').chmod(0o600)
            receipt.update(result='PREPROJECT_CONCEPT_ADVISORY_HTTP_COMPACT_PASS',provider_calls=6,durable_permits=permits,no_project_ep_approval_mission_effects=True)
        receipt['cleanup']=not root.exists()
    except BaseException as error:
        primary=error;receipt['failure']={'category':type(error).__name__};raise
    finally:
        if 'root' in locals():receipt['cleanup']=not root.exists()
        BINDING.retain_receipt(output,receipt,primary)
        original=output/'installed-project-proposal-http.public.json'
        if original.exists():original.rename(output/'installed-concept-advisory-http.public.json')
    print(receipt['result'],len(receipt['cases']))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--python',required=True,type=Path);parser.add_argument('--wheel',required=True,type=Path);parser.add_argument('--source-revision',required=True);parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--modeled-os-identity',action='store_true')
    args=parser.parse_args();MODELED_OS=args.modeled_os_identity;run(args)
