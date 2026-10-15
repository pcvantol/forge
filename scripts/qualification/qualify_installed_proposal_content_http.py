"""Real installed R52 HTTP proposal to scoped content decision and durable readback."""
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import contextmanager,closing
from importlib.util import spec_from_file_location,module_from_spec
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from datetime import UTC,datetime,timedelta
from hashlib import sha256
import argparse,json,os,socket,subprocess,time,sqlite3,sys

SOURCE=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('r52_installed',Path(__file__).with_name('qualify_installed_project_proposal_http.py'));BINDING=module_from_spec(spec);spec.loader.exec_module(BINDING)
MODELED_OS=False
CONTRACT='forge-project-proposal-content-decision/v1'
PROFILE='CONTENT_BASELINE_ONLY/1.0'

def invocation(python,args):
    if not MODELED_OS:return [str(python),'-I',*args]
    code="import os,runpy,sys;from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter,NamedOperatorIdentity;MacOSGeneratedUIDIdentityAdapter.resolve=lambda self:NamedOperatorIdentity('r54-declared-trusted-os-fixture',os.getuid());a=sys.argv[1:];sys.argv=a[1:] if a[0]=='-m' else a;runpy.run_module(sys.argv[0],run_name='__main__') if a[0]=='-m' else runpy.run_path(a[0],run_name='__main__')"
    return [str(python),'-I','-c',code,*args]

def call(port,token,method,path,body=None):
    req=Request('http://127.0.0.1:'+str(port)+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token.read_text().strip(),'X-Forge-Content-Audience':'synthetic-workspace','Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=15) as response:status,value=response.status,json.loads(response.read())
        validate_wire(path,value,body,status);return status,value
    except HTTPError as error:
        try:
            value=json.loads(error.read());validate_wire(path,value,None,error.code);return error.code,value
        finally:error.close()

def validate_wire(path,value,body,status):
    if path.startswith('/v1/project-proposal-decisions/'):
        from jsonschema import Draft202012Validator
        schema=json.loads((SOURCE/'forge/api/project-proposal-decisions-v1.json').read_text())
        Draft202012Validator(schema).validate(value)
        if status==200 and body is not None:Draft202012Validator(schema).validate(body)

@contextmanager
def server(python,root,output):
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    with (output/'server.private.log').open('ab') as log:
        process=subprocess.Popen(invocation(python,['-m','forge','--data-root',str(root/'runtime'),'server','run','--credential-file',str(root/'admin.private'),'--port',str(port),'--tick-interval','1']),cwd=root,stdout=log,stderr=log,start_new_session=True)
        try:
            deadline=time.monotonic()+15
            while True:
                if process.poll() is not None:raise RuntimeError('installed Server exited')
                try:
                    status,cap=call(port,root/'decide.private','GET','/v1/project-proposal-decisions/capability')
                    if status==200:break
                    raise RuntimeError('installed content capability denied')
                except (URLError,ConnectionError):
                    if time.monotonic()>deadline:raise TimeoutError('installed Server readiness')
                    time.sleep(.05)
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

def request_for(snapshot,role,operation):
    return {'contract_version':CONTRACT,'instance_id':snapshot['instance_id'],'dossier_id':snapshot['dossier_id'],'operation_id':operation,'plan_id':snapshot['plan_id'],'subject':snapshot['subject'],'profile_id':PROFILE,'role':role,'decision':'APPROVE_CONTENT','expected_decision_revision':snapshot['decision_revision'],'previous_decision_id':snapshot['history'][-1]['decision_id'] if snapshot['history'] else None,'reason':'Synthetic technical decision: accept document content while retaining future engineering questions.','acknowledged_open_points':snapshot['open_points']}

def run(args):
    output=args.output_dir;output.mkdir(mode=0o700)
    receipt={'result':'FAIL','cases':[],'cleanup':False,'human_decisions':'SYNTHETIC_TECHNICAL_NOT_REAL_OWNER_BUSINESS_APPROVAL','operator_identity_evidence':'MODELED_TRUSTED_OS_FIXTURE' if MODELED_OS else 'ACTUAL_MACOS_GENERATED_UID','transport':'ACTUAL_NONEDITABLE_HTTP_SEPARATE_SERVER_OS',**BINDING.installed_binding(args.python,args.wheel,args.source_revision)}
    case_number=0;primary=None
    def command(arguments,root):
        nonlocal case_number
        case_number+=1
        report,stdout,stderr=BINDING.CAPTURE.capture(invocation(args.python,arguments),case='setup-'+str(case_number),output=output,cwd=root,env={'PATH':'/usr/bin:/bin','HOME':str(root)},expected=0)
        if report['primary_failure'] or not report['capture_complete']:raise RuntimeError('installed owning command/capture failed')
        return json.loads(stdout)
    try:
        with TemporaryDirectory(prefix='r54-proposal-content-') as tmp:
            parent=Path(tmp).resolve();root=parent/'synthetic'
            setup=command([str(Path(__file__).with_name('proposal_content_fixture.py')),str(root)],parent)
            command(['-m','forge.proposal_content_cli','--data-root',str(root/'runtime'),'init'],root)
            issued=command(['-m','forge.proposal_content_cli','--data-root',str(root/'runtime'),'issue','--principal-id',setup['human_principal_id'],'--proposal-principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--permission','READ','--permission','DECIDE','--role','BUSINESS','--role','ARCHITECTURE','--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(root/'decide.private')],root)
            try:
                with server(args.python,root,output) as (port,first,cap):
                    assert cap['profile']['required_roles']==['BUSINESS','ARCHITECTURE'] and not cap['apply']
                    original=json.loads(subprocess.check_output(['git','-C',str(SOURCE),'show','HEAD:examples/project-bootstrap/authority-input.json']))
                    body={'contract_version':'forge-project-proposal-http/v1','instance_id':setup['instance_id'],'dossier_id':'synthetic-dossier','operation_id':'prepare-original','proposal_kind':'pb-render/1.0','input':original}
                    status,plan=call(port,root/'prepare.private','POST','/v1/onboarding/plans',body);assert status==200,(status,plan)
                    receipt['cases'].append('actual-r52-http-prepare-read-frozen-document-proposal')
                    target='/v1/project-proposal-decisions/proposals/'+plan['plan_id']+'?dossier_id=synthetic-dossier'
                    status,snapshot=call(port,root/'decide.private','GET',target);assert status==200,(status,snapshot)
                    assert snapshot['state']=='DECISION_NEEDED' and snapshot['subject']['concept_revision'] is None
                    original_store=(root/'runtime/onboarding/proposals/store.json').read_bytes()
                    business=request_for(snapshot,'BUSINESS','business-original')
                    status,partial=call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',business);assert status==200,(status,partial)
                    assert partial['state']=='DECISION_NEEDED' and partial['decision_revision']==1
                    architecture=request_for(partial,'ARCHITECTURE','architecture-original')
                    status,complete=call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',architecture);assert status==200,(status,complete)
                    assert complete['state']=='CONTENT_APPROVED' and complete['effects_authorized'] is False
                    assert call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',business)[1]['original_decision']==partial['original_decision']
                    assert (root/'runtime/onboarding/proposals/store.json').read_bytes()==original_store
                    receipt['cases'].append('owner-issued-distinct-human-roles-partial-then-content-only-approval')
                    recovered=command(['-m','forge.proposal_content_cli','--data-root',str(root/'runtime'),'intent','--token-file',str(root/'decide.private'),'--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--operation-id','business-original'],root)
                    assert recovered['original_decision']==partial['original_decision']
                    receipt['cases'].append('actual-installed-cli-original-intent-readback-no-second-decision')
                    from concurrent.futures import ThreadPoolExecutor
                    change=request_for(complete,'BUSINESS','concurrent-change');change['decision']='REQUEST_CHANGES';change['reason']='Synthetic request to clarify the first audience.'
                    with ThreadPoolExecutor(max_workers=2) as pool:answers=list(pool.map(lambda _:call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',change),range(2)))
                    assert all(status==200 for status,_ in answers) and answers[0][1]['original_decision']==answers[1][1]['original_decision']
                    changed=answers[0][1];assert changed['state']=='CHANGES_REQUESTED' and changed['decision_revision']==3
                    assert call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',{**change,'reason':'Different bytes under the same operation.'})[0]==409
                    assert call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',{**business,'operation_id':'stale'})[0]==409
                    wrong=json.loads(json.dumps(request_for(changed,'ARCHITECTURE','foreign-subject')));wrong['subject']['result_digest']='f'*64
                    assert call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',wrong)[0]==409
                    receipt['cases'].append('actual-concurrent-single-decision-conflict-stale-and-exact-subject')
                    lost=request_for(changed,'ARCHITECTURE','lost-response');raw=json.dumps(lost).encode()
                    header=('POST /v1/project-proposal-decisions/decisions HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+(root/'decide.private').read_text().strip()+'\r\nX-Forge-Content-Audience: synthetic-workspace\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw))+'\r\nConnection: close\r\n\r\n').encode()
                    with socket.create_connection(('127.0.0.1',port),timeout=3) as client:client.sendall(header+raw);client.shutdown(socket.SHUT_WR)
                    deadline=time.monotonic()+10
                    while True:
                        status,found=call(port,root/'decide.private','GET','/v1/project-proposal-decisions/intents/lost-response?dossier_id=synthetic-dossier')
                        if status==200:break
                        if time.monotonic()>deadline:raise TimeoutError('original lost-response decision unavailable')
                        time.sleep(.05)
                    lost_record=found['original_decision'];assert found['decision_revision']==4
                    receipt['cases'].append('actual-lost-response-original-intent-without-new-operation')
                    again=request_for(found,'BUSINESS','business-successor');request_path=root/'successor.private';request_path.write_text(json.dumps(again));request_path.chmod(0o600)
                    successor=command(['-m','forge.proposal_content_cli','--data-root',str(root/'runtime'),'decide','--token-file',str(root/'decide.private'),'--audience','synthetic-workspace','--request-file',str(request_path)],root)
                    assert successor['decision_revision']==5 and successor['state']=='CONTENT_APPROVED' and successor['original_decision']['request']['previous_decision_id']==lost_record['decision_id']
                    receipt['cases'].append('explicit-changes-request-and-cas-successor-content-only-reapproval-cli-parity')
                    revised=json.loads(json.dumps(original));revised['product']['purpose']='A separately supplied revised project purpose.'
                    status,newplan=call(port,root/'prepare.private','POST','/v1/onboarding/plans',{**body,'operation_id':'new-source-version','input':revised});assert status==200
                    status,newview=call(port,root/'decide.private','GET','/v1/project-proposal-decisions/proposals/'+newplan['plan_id']+'?dossier_id=synthetic-dossier')
                    assert status==200 and newview['decision_revision']==0 and newview['history']==[] and newview['state']=='DECISION_NEEDED'
                    receipt['cases'].append('new-proposal-id-content-source-never-inherits-approval')
                    assert call(port,root/'admin.private','GET',target)[0]==403
                    role_args=['-m','forge.proposal_content_cli','--data-root',str(root/'runtime'),'issue','--principal-id',setup['human_principal_id'],'--proposal-principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--permission','READ','--permission','DECIDE','--role','BUSINESS','--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(root/'business-only.private')]
                    command(role_args,root)
                    assert call(port,root/'business-only.private','POST','/v1/project-proposal-decisions/decisions',request_for(successor,'ARCHITECTURE','wrong-role'))[0]==403
                    assert call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',{**request_for(successor,'BUSINESS','foreign-instance'),'instance_id':'foreign-instance'})[0]==403
                    assert call(port,root/'decide.private','GET','/v1/project-proposal-decisions/intents/business-original?dossier_id=foreign-dossier')[0]==403
                    receipt['cases'].append('actual-purpose-role-dossier-instance-admin-denials-no-fallback')

                with server(args.python,root,output) as (port,second,cap):
                    assert first!=second
                    status,recovered=call(port,root/'decide.private','GET','/v1/project-proposal-decisions/intents/architecture-original?dossier_id=synthetic-dossier')
                    assert status==200 and recovered['original_decision']==complete['original_decision'] and recovered['decision_revision']==5
                    status,old=call(port,root/'prepare.private','GET','/v1/onboarding/plans/'+plan['plan_id']+'?dossier_id=synthetic-dossier');assert status==200 and old==plan and old['result']['state']=='PROPOSED_NOT_APPROVED'
                    assert call(port,root/'prepare.private','GET',target)[0]==403
                    receipt['cases'].append('separate-server-os-original-recovery-r52-immutable-old-token-denied')
                    for path in [root/'runtime/onboarding/content-decisions/store.json',root/'runtime/onboarding/content-decisions/initialized.json',root/'runtime/onboarding/proposals/store.json']:
                        original_bytes=path.read_bytes()
                        path.unlink()
                        assert call(port,root/'decide.private','GET','/v1/project-proposal-decisions/intents/business-original?dossier_id=synthetic-dossier')[0]==503
                        path.write_bytes(original_bytes);path.chmod(0o600)
                        path.write_bytes(b'{}');path.chmod(0o600)
                        assert call(port,root/'decide.private','GET','/v1/project-proposal-decisions/intents/business-original?dossier_id=synthetic-dossier')[0] not in (200,404)
                        path.write_bytes(original_bytes);path.chmod(0o600)
                        status,restored=call(port,root/'decide.private','GET','/v1/project-proposal-decisions/intents/business-original?dossier_id=synthetic-dossier');assert status==200 and restored['original_decision']==partial['original_decision']
                    receipt['cases'].append('initialized-own-source-witness-missing-corrupt-fail-closed-exact-restore')
                    reader=root/'read-only.private'
                    command(['-m','forge.proposal_content_cli','--data-root',str(root/'runtime'),'issue','--principal-id','synthetic-observer','--proposal-principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--permission','READ','--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(reader)],root)
                    assert call(port,reader,'POST','/v1/project-proposal-decisions/decisions',request_for(successor,'BUSINESS','read-cannot-decide'))[0]==403
                    expiring=root/'expiring.private'
                    command(['-m','forge.proposal_content_cli','--data-root',str(root/'runtime'),'issue','--principal-id','synthetic-expiry-observer','--proposal-principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--permission','READ','--expires-at',(datetime.now(UTC)+timedelta(seconds=3)).isoformat(),'--token-file',str(expiring)],root)
                    assert call(port,expiring,'GET','/v1/project-proposal-decisions/capability')[0]==200
                    deadline=time.monotonic()+5
                    while call(port,expiring,'GET','/v1/project-proposal-decisions/capability')[0]==200:
                        if time.monotonic()>deadline:raise TimeoutError('actual content grant expiry not enforced')
                        time.sleep(.1)
                    assert call(port,expiring,'GET',target)[0]==401
                    receipt['cases'].append('actual-owner-issued-read-only-and-real-time-expiry')
                    before=(root/'runtime/onboarding/content-decisions/store.json').read_bytes()
                    command(['-m','forge.proposal_content_cli','--data-root',str(root/'runtime'),'revoke','--grant-id',issued['grant_id']],root)
                    assert call(port,root/'decide.private','GET',target)[0]==401
                    status,historical=call(port,reader,'GET',target);assert status==200 and historical['history'][0]==partial['original_decision'] and historical['decision_revision']==5
                    assert (root/'runtime/onboarding/content-decisions/store.json').read_bytes()==before
                    receipt['cases'].append('actual-revoke-current-access-denied-original-history-retained-for-authorized-reader')

                with closing(sqlite3.connect(root/'runtime/forge.db')) as db:
                    for table in ['mission_id_allocations','mission_state','governance_decisions','planning_provider_generation_permits']:assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
                receipt.update(result='PROJECT_PROPOSAL_CONTENT_HTTP_PASS',decision_records=5,no_project_repo_ep_model_mission_effects=True,separate_server_processes=True)
            finally:
                current=sys.exc_info()[1]
                try:
                    for source,name in [(root/'runtime/onboarding/proposals/store.json','original-r52-store.private.json'),(root/'runtime/onboarding/content-decisions/store.json','original-content-store.private.json')]:
                        if source.exists():
                            with source.open('rb') as stream:raw=stream.read(1048577)
                            if len(raw)>1048576:raise RuntimeError('finite original evidence capture exceeded')
                            BINDING.CAPTURE.retain(output/name,raw)
                except Exception as error:
                    if current is None:raise
                    current.add_note('original private diagnostics incomplete: '+type(error).__name__)
        receipt['cleanup']=not parent.exists()
    except BaseException as error:
        primary=error;receipt['result']='FAIL';receipt['failure']={'category':type(error).__name__};raise
    finally:
        if 'root' in locals():receipt['cleanup']=not root.exists()
        BINDING.retain_receipt(output,receipt,primary)
        original=output/'installed-project-proposal-http.public.json'
        if original.exists():original.rename(output/'installed-proposal-content-http.public.json')
    print('PROJECT_PROPOSAL_CONTENT_HTTP_PASS',len(receipt['cases']))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--python',type=Path,required=True);parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--source-revision',required=True);parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--modeled-os-identity',action='store_true');args=parser.parse_args();MODELED_OS=args.modeled_os_identity;run(args)
