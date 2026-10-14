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

SOURCE=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('existing_http_binding',Path(__file__).with_name('qualify_installed_project_proposal_http.py'))
BINDING=module_from_spec(spec);spec.loader.exec_module(BINDING)
CONTRACT='forge-preproject-concept-advisory/v1'


def call(port,token,method,path,body=None):
    request=Request('http://127.0.0.1:'+str(port)+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token.read_text().strip(),'X-Forge-Concept-Audience':'synthetic-workspace','Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=15) as response:return response.status,json.loads(response.read())
    except HTTPError as error:
        try:return error.code,json.loads(error.read())
        finally:error.close()


@contextmanager
def server(python,root,output):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with (output/'server.private.log').open('ab') as log:
        process=subprocess.Popen([str(python),'-I','-m','forge','--data-root',str(root/'runtime'),'server','run','--credential-file',str(root/'admin.private'),'--port',str(port),'--provider-id','concept-fixture','--tick-interval','1'],cwd=root,stdout=log,stderr=log,start_new_session=True)
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
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def run(args):
    output=args.output_dir;output.mkdir(mode=0o700)
    receipt={'result':'FAIL','cases':[],'cleanup':False,'provider_evidence':'MODELED_EXTERNAL_PROVIDER_NOT_LIVE_ADVICE_QUALITY',
             'transport_evidence':'ACTUAL_INSTALLED_HTTP_SEPARATE_SERVER_OS','operator_identity_evidence':'ACTUAL_MACOS_GENERATED_UID',
             **BINDING.installed_binding(args.python,args.wheel,args.source_revision)}
    primary=None
    try:
        with TemporaryDirectory(prefix='concept-r53-') as scratch:
            parent=Path(scratch).resolve();root=parent/'synthetic'
            report,stdout,stderr=BINDING.CAPTURE.capture([str(args.python),'-I',str(Path(__file__).with_name('concept_advisory_fixture.py')),str(root)],case='explicit-setup',output=output,cwd=parent,env={'PATH':'/usr/bin:/bin','HOME':str(parent)},expected=0)
            if report['primary_failure'] or not report['capture_complete']:raise RuntimeError('synthetic setup failed')
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
            with server(args.python,root,output) as (port,second,cap):
                assert first!=second
                status,recovered=call(port,token,'GET','/v1/concept-advisory/intents/operation-one?dossier_id=dossier-alice&conversation_id=conversation-alice')
                assert status==200 and recovered['original_turn']==business['original_turn']
                assert call(port,token,'POST','/v1/concept-advisory/turns',architecture)[1]['original_turn']==architect['original_turn']
                receipt['cases'].append('separate-server-os-restart-original-intent-no-second-call')
            calls=[json.loads(line) for line in (root/'provider-requests.private.jsonl').read_text().splitlines()]
            assert len(calls)==3 and calls[1]['prior_turns'][0]['request']==request and calls[2]['request']['briefing']==revised['briefing']
            import sqlite3
            with sqlite3.connect(root/'runtime'/'forge.db') as db:
                for table in ['mission_id_allocations','mission_state','governance_decisions']:assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
                permits=db.execute('SELECT COUNT(*) FROM planning_provider_generation_permits').fetchone()[0];assert permits==3
            receipt.update(result='PREPROJECT_CONCEPT_ADVISORY_HTTP_COMPACT_PASS',provider_calls=3,durable_permits=permits,no_project_ep_approval_mission_effects=True)
        receipt['cleanup']=not root.exists()
    except BaseException as error:
        primary=error;receipt['failure']={'category':type(error).__name__};raise
    finally:
        BINDING.retain_receipt(output,receipt,primary)
        original=output/'installed-project-proposal-http.public.json'
        if original.exists():original.rename(output/'installed-concept-advisory-http.public.json')
    print(receipt['result'],len(receipt['cases']))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--python',required=True,type=Path);parser.add_argument('--wheel',required=True,type=Path);parser.add_argument('--source-revision',required=True);parser.add_argument('--output-dir',required=True,type=Path)
    run(parser.parse_args())
