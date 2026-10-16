"""Actual outside-checkout installed HTTP Genesis plans; all decisions synthetic."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import UTC,datetime,timedelta
from importlib.util import spec_from_file_location,module_from_spec
import argparse,json,subprocess,sys,hashlib,sqlite3,socket,time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

SOURCE=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('content_qualification',Path(__file__).with_name('qualify_installed_proposal_content_http.py'))
C=module_from_spec(spec);spec.loader.exec_module(C)
CONTRACT='forge-genesis-bootstrap-effect-plan/v1'


def capture_command(python,arguments,root,output,case):
    report,stdout,stderr=C.BINDING.CAPTURE.capture(C.invocation(python,arguments),case=case,output=output,cwd=root,env={'PATH':'/usr/bin:/bin','HOME':str(root)},expected=0)
    primary=None
    if report['primary_failure'] or not report['capture_complete']:
        primary=RuntimeError('installed owning command/capture failed')
        primary.capture_report=report
    try:
        C.BINDING.CAPTURE.retain(output/(case+'.capture.private.json'),(json.dumps(report,sort_keys=True,indent=2)+'\n').encode())
    except OSError as retention_error:
        report['secondary_failures'].append({'stage':'report-retention','category':type(retention_error).__name__})
        report['capture_complete']=False
        if primary is None:
            primary=retention_error
            primary.capture_report=report
        else:
            primary.add_note('command report retention failed: '+type(retention_error).__name__)
    if primary is not None:
        raise primary
    return json.loads(stdout)


def exact_fault_red(error,observation,path):
    # Only the deliberately introduced authority flag defect is an expected red.
    return (tuple(error.absolute_path)==('execution_authorized',) and error.validator=='const'
            and error.validator_value is False and error.instance is True
            and observation=={'path':path,'status':200,'execution_authorized':True})


def run(args):
    args.output_dir.mkdir(mode=0o700)
    receipt={'operator_identity_evidence':'NOT_YET_QUALIFIED','qualification':'GENESIS_BOOTSTRAP_EFFECT_PLAN_HTTP_V1','result':'FAIL','cases':[],'cleanup':False,'decisions':'SYNTHETIC_TECHNICAL_NOT_OWNER_APPROVAL',
             'transport':'ACTUAL_NONEDITABLE_HTTP_SEPARATE_SERVER_OS',
             **C.BINDING.installed_binding(args.python,args.wheel,args.source_revision)}
    schema_path=Path(subprocess.check_output([str(args.python),'-I','-c',"from importlib.resources import files;print(files('forge').joinpath('api/genesis-bootstrap-v1.json'))"],cwd=args.wheel.parent).decode().strip())
    schema=json.loads(schema_path.read_bytes())
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
    observation={}
    previous_validator=C.validate_wire
    def wire(path,value,body,status):
        previous_validator(path,value,body,status)
        if path.startswith('/v1/genesis-bootstrap/'):
            observation.clear();observation.update(path=path,status=status,execution_authorized=value.get('execution_authorized'))
            branch='Capability' if status==200 and path.endswith('/capability') else 'Response' if status==200 else 'ErrorResponse'
            response_schema={'$schema':schema['$schema'],'$defs':schema['$defs'],'$ref':'#/$defs/'+branch}
            Draft202012Validator(response_schema).validate(value)
            if status==200 and body is not None:
                Draft202012Validator(schema).validate(body)
    C.validate_wire=wire
    count=0
    def command(arguments,root):
        nonlocal count
        count+=1
        return capture_command(args.python,arguments,root,args.output_dir,'genesis-setup-'+str(count))
    primary=None
    try:
        with TemporaryDirectory(prefix='r56-genesis-installed-') as tmp:
            parent=Path(tmp).resolve(); root=parent/'synthetic'
            setup=command([str(Path(__file__).with_name('proposal_content_fixture.py')),str(root)],parent)
            receipt['operator_identity_evidence']='MODELED_TRUSTED_OS_FIXTURE' if C.MODELED_OS else 'ACTUAL_MACOS_GENERATED_UID'
            data=['--data-root',str(root/'runtime')]
            command(['-m','forge.proposal_content_cli',*data,'init'],root)
            expiry=(datetime.now(UTC)+timedelta(hours=1)).isoformat()
            command(['-m','forge.proposal_content_cli',*data,'issue','--principal-id',setup['human_principal_id'],'--proposal-principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--permission','READ','--permission','DECIDE','--role','BUSINESS','--role','ARCHITECTURE','--expires-at',expiry,'--token-file',str(root/'decide.private')],root)
            with C.server(args.python,root,args.output_dir) as (port,pid,_):
                original=json.loads(subprocess.check_output(['git','-C',str(SOURCE),'show',args.source_revision+':examples/project-bootstrap/authority-input.json']))
                request={'contract_version':'forge-project-proposal-http/v1','instance_id':setup['instance_id'],'dossier_id':'synthetic-dossier','operation_id':'source-original','proposal_kind':'pb-render/1.0','input':original}
                status,source=C.call(port,root/'prepare.private','POST','/v1/onboarding/plans',request)
                assert status==200,(status,source)
                status,content=C.call(port,root/'decide.private','GET','/v1/project-proposal-decisions/proposals/'+source['plan_id']+'?dossier_id=synthetic-dossier')
                assert status==200,(status,content)
                for role in ('BUSINESS','ARCHITECTURE'):
                    status,content=C.call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',C.request_for(content,role,'content-'+role.lower()))
                    assert status==200,(status,content)
                assert content['state']=='CONTENT_APPROVED' and not content['effects_authorized']
                receipt['cases'].append('actual-original-r52-http-and-distinct-r54-role-decisions')
                command(['-m','forge.genesis_bootstrap_cli',*data,'init'],root)
                scope=['--proposal-principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--source-plan-id',source['plan_id'],'--expires-at',expiry]
                command(['-m','forge.genesis_bootstrap_cli',*data,'issue','--principal-id','synthetic-service',*scope,'--permission','READ','--permission','PREPARE','--token-file',str(root/'bootstrap.private')],root)
                EFFECTS=('CREATE_NEW_TARGET','INITIALIZE_LOCAL_GIT','WRITE_EXACT_MANIFEST_FILES','RUN_EXTERNALLY_PINNED_VALIDATION','CREATE_LOCAL_COMMIT','REGISTER_COMMITTED_AUTHORITY_ATTACHMENT')
                EFFECT_PURPOSE='GENESIS_BOOTSTRAP_EFFECT_ONLY/1.0'
                r={'contract_version':CONTRACT,'instance_id':setup['instance_id'],'dossier_id':'synthetic-dossier','operation_id':'exact-plan','source_plan_id':source['plan_id'],'source_subject':content['subject'],'expected_content_revision':2,'target':{'ep_instance_id':'synthetic-ep','placement_ref':'synthetic-placement','target_ref':'synthetic-target'},'effects':list(EFFECTS),'expires_at':expiry,'expected_plan_revision':0,'previous_plan_id':None,'blocking_open_points':[]}
                source_bytes=(root/'runtime/onboarding/proposals/store.json').read_bytes()
                status,view=C.call(port,root/'bootstrap.private','POST','/v1/genesis-bootstrap/plans',r)
                assert status==200,(status,view)
                plan=view['plan']; assert view['effect_decision_eligible'] and not view['effect_decision_currently_applicable']
                assert plan['state']=='EP_ADMISSION_REQUIRED' and plan['identity_state']=='PROPOSED_NOT_RESERVED'
                status,source_read=C.call(port,root/'prepare.private','GET','/v1/onboarding/plans/'+source['plan_id']+'?dossier_id=synthetic-dossier')
                assert status==200,(status,source_read)
                files=[{k:f[k] for k in ('path','mode','sha256','content')} for f in plan['documents']['files']]
                assert files==source_read['result']['artifacts'] and len(files)==37 and all(f['mode']==420 for f in files)
                assert (root/'runtime/onboarding/proposals/store.json').read_bytes()==source_bytes
                receipt['cases'].append('exact-37-original-bytes-no-rerender-no-reservation-no-target-effect')
                exact=root/'plans.private';exact.write_text(json.dumps([{'plan_id':plan['plan_id'],'plan_digest':plan['plan_digest']}])) ;exact.chmod(0o600)
                effect_grant=command(['-m','forge.genesis_bootstrap_cli',*data,'issue','--principal-id',setup['human_principal_id'],*scope,'--permission','READ','--permission','DECIDE_EFFECT','--exact-plans-file',str(exact),'--token-file',str(root/'effect.private')],root)
                d={'contract_version':CONTRACT,'instance_id':setup['instance_id'],'dossier_id':'synthetic-dossier','operation_id':'exact-effect','plan_id':plan['plan_id'],'plan_digest':plan['plan_digest'],'purpose':EFFECT_PURPOSE,'decision':'APPROVE_EFFECT','reason':'Synthetic technical confirmation of this exact document-only plan; no execution permission.','expected_decision_revision':0,'previous_decision_id':None}
                status,decided=C.call(port,root/'effect.private','POST','/v1/genesis-bootstrap/decisions',d)
                assert status==200,(status,decided)
                assert decided['effect_decision_currently_applicable'] and not decided['execution_authorized']
                original_decision=decided['original_decision']
                status,duplicate=C.call(port,root/'effect.private','POST','/v1/genesis-bootstrap/decisions',d)
                assert status==200 and duplicate==decided,(status,duplicate)
                assert C.call(port,root/'effect.private','POST','/v1/genesis-bootstrap/decisions',{**d,'reason':'Changed bytes under same operation.'})[0]==409
                assert C.call(port,root/'prepare.private','GET','/v1/genesis-bootstrap/capability')[0]==403
                receipt['cases'].append('separate-canonical-human-finite-exact-effect-purpose-idempotent-readback')
            with C.server(args.python,root,args.output_dir) as (port,second,_):
                assert second!=pid
                status,recovered=C.call(port,root/'effect.private','GET','/v1/genesis-bootstrap/decision-intents/exact-effect?dossier_id=synthetic-dossier')
                assert status==200 and recovered['original_decision']==original_decision and recovered['plan']==plan and recovered['effect_decision_revision']==1,(status,recovered)
                assert not recovered['execution_authorized'] and recovered['target_write']=='NOT_PERFORMED' and recovered['ep_credential']=='NOT_ISSUED'
                receipt['cases'].append('separate-server-os-restart-original-decision-and-plan-no-execution')
                cli_file=root/'original-readback.private'
                cli_receipt=command([str(Path(__file__).with_name('genesis_cli_readback.py')),str(cli_file),*data,'decision-intent','--token-file',str(root/'effect.private'),'--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--reference','exact-effect'],root)
                assert cli_receipt['exit_code']==0 and cli_receipt['sha256']==hashlib.sha256(cli_file.read_bytes()).hexdigest()
                cli=json.loads(cli_file.read_bytes());assert cli==recovered
                receipt['cases'].append('ordinary-installed-cli-http-original-readback-parity')
            # Reuse the original persisted plan/decisions; no new proposal or renderer.
            with C.server(args.python,root,args.output_dir) as (port,third,_):
                path='/v1/genesis-bootstrap/plans/'+plan['plan_id']+'?dossier_id=synthetic-dossier'
                with ThreadPoolExecutor(max_workers=2) as pool:
                    answers=list(pool.map(lambda _:C.call(port,root/'bootstrap.private','POST','/v1/genesis-bootstrap/plans',r),range(2)))
                assert all(status==200 and value['plan']==plan for status,value in answers)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    answers=list(pool.map(lambda _:C.call(port,root/'effect.private','POST','/v1/genesis-bootstrap/decisions',d),range(2)))
                assert all(status==200 and value['original_decision']==original_decision for status,value in answers)
                for token in ('admin.private','prepare.private','decide.private'):
                    assert C.call(port,root/token,'GET','/v1/genesis-bootstrap/capability')[0]==403
                assert C.call(port,root/'bootstrap.private','POST','/v1/genesis-bootstrap/decisions',d)[0]==403
                assert C.call(port,root/'bootstrap.private','GET',path.replace('synthetic-dossier','foreign-dossier'))[0]==403
                assert C.call(port,root/'bootstrap.private','POST','/v1/genesis-bootstrap/plans',{**r,'instance_id':'foreign-instance'})[0]==403
                assert C.call(port,root/'bootstrap.private','POST','/v1/genesis-bootstrap/plans',{**r,'effects':['WRITE_ARBITRARY']})[0]==400
                receipt['cases'].append('actual-concurrent-exact-replays-cross-purpose-instance-dossier-effect-denials')
                lost={**d,'operation_id':'lost-original-effect','decision':'REQUEST_CHANGES','reason':'Synthetic change request to exercise lost commit response.','expected_decision_revision':1,'previous_decision_id':original_decision['decision_id']}
                raw=json.dumps(lost).encode()
                headers=('POST /v1/genesis-bootstrap/decisions HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+(root/'effect.private').read_text().strip()+'\r\nX-Forge-Bootstrap-Audience: synthetic-workspace\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw))+'\r\nConnection: close\r\n\r\n').encode()
                with socket.create_connection(('127.0.0.1',port),timeout=3) as client:
                    client.sendall(headers+raw);client.shutdown(socket.SHUT_WR)
                deadline=time.monotonic()+10
                while True:
                    status,lost_read=C.call(port,root/'effect.private','GET','/v1/genesis-bootstrap/decision-intents/lost-original-effect?dossier_id=synthetic-dossier')
                    if status==200:break
                    if status!=404 or time.monotonic()>deadline:raise RuntimeError('original lost decision unavailable')
                    time.sleep(.05)
                lost_record=lost_read['original_decision'];assert lost_read['effect_decision_revision']==2
            with C.server(args.python,root,args.output_dir) as (port,fourth,_):
                assert fourth!=third
                status,restored=C.call(port,root/'effect.private','GET','/v1/genesis-bootstrap/decision-intents/lost-original-effect?dossier_id=synthetic-dossier')
                assert status==200 and restored['original_decision']==lost_record and restored['effect_decision_revision']==2
                receipt['cases'].append('actual-lost-success-response-and-additional-server-os-restart-no-second-decision')
                again={**d,'operation_id':'explicit-successor','expected_decision_revision':2,'previous_decision_id':lost_record['decision_id']}
                status,current=C.call(port,root/'effect.private','POST','/v1/genesis-bootstrap/decisions',again)
                assert status==200 and current['effect_decision_currently_applicable']
                change=C.request_for(content,'BUSINESS','original-content-change');change['decision']='REQUEST_CHANGES'
                status,changed_content=C.call(port,root/'decide.private','POST','/v1/project-proposal-decisions/decisions',change);assert status==200
                status,changed=C.call(port,root/'bootstrap.private','GET',path)
                assert status==200 and not changed['effect_decision_currently_applicable'] and 'SOURCE_CONTENT_CHANGED' in changed['inapplicability_reasons']
                assert changed['effect_history'][0]==original_decision
                assert C.call(port,root/'effect.private','POST','/v1/genesis-bootstrap/decisions',{**again,'operation_id':'blocked-changed-source','expected_decision_revision':3,'previous_decision_id':current['original_decision']['decision_id']})[0]==409
                receipt['cases'].append('current-content-change-invalidates-positive-effect-with-original-history-preserved')
                command(['-m','forge.genesis_bootstrap_cli',*data,'revoke','--grant-id',effect_grant['grant_id']],root)
                assert C.call(port,root/'effect.private','GET','/v1/genesis-bootstrap/capability')[0] in (401,403)
                assert C.call(port,root/'bootstrap.private','GET',path)[1]['effect_history'][0]==original_decision
                short=(datetime.now(UTC)+timedelta(seconds=2)).isoformat()
                short_scope=scope.copy();short_scope[short_scope.index('--expires-at')+1]=short
                command(['-m','forge.genesis_bootstrap_cli',*data,'issue','--principal-id','synthetic-observer',*short_scope,'--permission','READ','--token-file',str(root/'short.private')],root)
                while datetime.now(UTC)<datetime.fromisoformat(short):time.sleep(.03)
                assert C.call(port,root/'short.private','GET','/v1/genesis-bootstrap/capability')[0] in (401,403)
                receipt['cases'].append('actual-owner-revoke-real-clock-expiry-no-cached-protected-success')
                own_store=root/'runtime/onboarding/genesis-bootstrap/store.json';saved=own_store.read_bytes()
                own_store.unlink()
                try:assert C.call(port,root/'bootstrap.private','GET',path)[0]==503
                finally:own_store.write_bytes(saved);own_store.chmod(0o600)
                assert C.call(port,root/'bootstrap.private','GET',path)[1]['effect_history'][0]==original_decision
                receipt['cases'].append('initialized-store-loss-fails-closed-and-exact-original-restoration')
            # Introduce one real bounded isolated installed-source defect, then restore it.
            location=Path(subprocess.check_output([str(args.python),'-I','-c','import forge.genesis_bootstrap_service as m;print(m.__file__)'],cwd=root).decode().strip())
            original_source=location.read_bytes();marker=b"'state':'EP_ADMISSION_REQUIRED','execution_authorized':False"
            assert original_source.count(marker)==1
            red=False
            try:
                location.write_bytes(original_source.replace(marker,marker.replace(b'False',b'True')))
                with C.server(args.python,root,args.output_dir) as (port,_,_):
                    try:
                        C.call(port,root/'bootstrap.private','GET',path)
                    except ValidationError as detector_error:
                        if not exact_fault_red(detector_error,observation,path):
                            raise
                        red=True
                        (args.output_dir/'restored-fault-detector-original-failure.public.json').write_text(json.dumps({'result':'EXPECTED_FAIL','defect':'FALSE_EXECUTION_AUTHORIZATION','actual_status':observation['status'],'observed_execution_authorized':observation['execution_authorized'],'detector_failure':type(detector_error).__name__}))
                assert red
            finally:
                location.write_bytes(original_source)
            assert location.read_bytes()==original_source
            with C.server(args.python,root,args.output_dir) as (port,_,_):
                status,value=C.call(port,root/'bootstrap.private','GET',path)
                assert status==200 and value['execution_authorized'] is False and value['effect_history'][0]==original_decision
            with closing(sqlite3.connect(root/'runtime/forge.db')) as db:
                for table in ['mission_id_allocations','mission_state','governance_decisions','planning_provider_generation_permits']:
                    assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
            assert (root/'runtime/onboarding/proposals/store.json').read_bytes()==source_bytes
            assert len(json.loads((root/'runtime/onboarding/genesis-bootstrap/store.json').read_bytes())['records'])==4
            receipt['no_project_repo_ep_model_mission_effects']=True
            receipt['retained_original_proposals']=1
            receipt['retained_effect_decisions']=3
            receipt['restored_fault_detector']={'red':red,'restored_green':True,'installed_source_sha256':hashlib.sha256(original_source).hexdigest()}
            receipt['cases'].append('same-actual-http-detector-red-for-restored-real-installed-defect-then-green')
            receipt['plan_digest']=plan['plan_digest']; receipt['file_count']=37
        receipt['cleanup']=not parent.exists(); receipt['result']='PASS'
        return receipt
    except BaseException as error:
        primary=error
        receipt['failure']={'category':type(error).__name__,'capture_report':getattr(error,'capture_report',None)}
        raise
    finally:
        C.validate_wire=previous_validator
        if 'parent' in locals():
            receipt['cleanup']=not parent.exists()
        C.BINDING.retain_receipt(args.output_dir,receipt,primary)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--python',type=Path,required=True);parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--source-revision',required=True);parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--modeled-os-identity',action='store_true')
    args=parser.parse_args();C.MODELED_OS=args.modeled_os_identity
    print(json.dumps(run(args),indent=2))

if __name__=='__main__':
    main()
