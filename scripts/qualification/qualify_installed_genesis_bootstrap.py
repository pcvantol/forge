"""Actual outside-checkout installed HTTP Genesis plans; all decisions synthetic."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import UTC,datetime,timedelta
from importlib.util import spec_from_file_location,module_from_spec
import argparse,json,subprocess,sys,hashlib,sqlite3
from contextlib import closing

SOURCE=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('content_qualification',Path(__file__).with_name('qualify_installed_proposal_content_http.py'))
C=module_from_spec(spec);spec.loader.exec_module(C)
CONTRACT='forge-genesis-bootstrap-effect-plan/v1'


def run(args):
    args.output_dir.mkdir(mode=0o700)
    receipt={'result':'FAIL','cases':[],'cleanup':False,'decisions':'SYNTHETIC_TECHNICAL_NOT_OWNER_APPROVAL',
             'transport':'ACTUAL_NONEDITABLE_HTTP_SEPARATE_SERVER_OS',
             **C.BINDING.installed_binding(args.python,args.wheel,args.source_revision)}
    count=0
    def command(arguments,root):
        nonlocal count
        count+=1
        report,stdout,stderr=C.BINDING.CAPTURE.capture(C.invocation(args.python,arguments),case='genesis-setup-'+str(count),output=args.output_dir,cwd=root,env={'PATH':'/usr/bin:/bin','HOME':str(root)},expected=0)
        if report['primary_failure'] or not report['capture_complete']:
            raise RuntimeError('installed owning setup/capture failed')
        return json.loads(stdout)
    primary=None
    try:
        with TemporaryDirectory(prefix='r56-genesis-installed-') as tmp:
            parent=Path(tmp).resolve(); root=parent/'synthetic'
            setup=command([str(Path(__file__).with_name('proposal_content_fixture.py')),str(root)],parent)
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
                command(['-m','forge.genesis_bootstrap_cli',*data,'issue','--principal-id',setup['human_principal_id'],*scope,'--permission','READ','--permission','DECIDE_EFFECT','--exact-plans-file',str(exact),'--token-file',str(root/'effect.private')],root)
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
            with closing(sqlite3.connect(root/'runtime/forge.db')) as db:
                for table in ['mission_id_allocations','mission_state','governance_decisions','planning_provider_generation_permits']:
                    assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
            receipt['no_project_repo_ep_model_mission_effects']=True
            receipt['operator_identity_evidence']='ACTUAL_MACOS_GENERATED_UID'
            receipt['plan_digest']=plan['plan_digest']; receipt['file_count']=37
        receipt['cleanup']=not parent.exists(); receipt['result']='PASS'
        return receipt
    except BaseException as error:
        primary=error
        raise
    finally:
        if 'parent' in locals():
            receipt['cleanup']=not parent.exists()
        C.BINDING.retain_receipt(args.output_dir,receipt,primary)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--python',type=Path,required=True);parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--source-revision',required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args),indent=2))

if __name__=='__main__':
    main()
