"""Actual advice/registration and two canonical decisions over the HTTP product."""
from contextlib import closing
from datetime import UTC,datetime,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json,sqlite3,unittest,jsonschema
import forge
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from test_advisory_candidate_http import setup as candidate_setup,call as candidate_call,definition,command,qual
from forge.candidate_decision_contract import CONTRACT
from forge.candidate_decision_grant import CandidateDecisionGrant
from forge.governed_candidate_intake import GovernedCandidateIntake,GovernedCandidateIntakeError
from forge.governance import resolve_governance_profile
from forge.governance_authority import ArchitecturePlanningEvidence
from forge.lifecycle import RecommendationLifecycleStore
from forge.models.architecture_mission import ArchitectureMission,ArchitectureMissionStatus
from forge.models.mission_recommendation import RequiredDiscipline
from forge.models.criterion_observation import canonical_digest
from forge.server_runtime import existing_instance
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.models.mission_effect import MissionEffectPolicy

SCHEMA=json.loads((Path(forge.__file__).parent/'api/candidate-decisions-v1.json').read_text())
VALIDATOR=jsonschema.Draft202012Validator(SCHEMA)

def call(port,token,method,path,body=None):
    request=Request('http://127.0.0.1:'+str(port)+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token.read_text().strip(),'Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=15) as response:
            value=json.loads(response.read());VALIDATOR.validate(value)
            if body is not None:VALIDATOR.validate(body)
            return response.status,value
    except HTTPError as error:
        try:return error.code,json.loads(error.read())
        finally:error.close()

def fixture(root):
    candidate_setup(root)
    with qual.http(root) as port:
        old=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice'
        _,cap=candidate_call(port,old,'GET','/v1/advisory-candidates/capability');_,source=candidate_call(port,old,'GET',base+'/source/first')
        r=definition(source['source'],cap);r['fields']['dependencies']=[];r['fields']['title']='Beoordeel naïeve ontwerpkeuzes en vóórwaarden'
        _,saved=candidate_call(port,old,'POST',base+'/proposals',r);status,out=candidate_call(port,old,'POST',base+'/proposals/candidate-proposal/registrations',command(saved['proposal']));assert status==200,out
        receipt=out['original_receipt'];i=existing_instance(root/'runtime');grant=CandidateDecisionGrant(root/'runtime',i.instance_id)
        principal=sha256(qual.utils.fixture.IDENTITY.generated_uid.encode()).hexdigest()[:16]
        scope={k:cap[k] for k in ('instance_id','project_id','repository_id')}
        for name,permissions in [('business',('READ','BUSINESS')),('architecture',('READ','ARCHITECTURE')),('both',('READ','BUSINESS','ARCHITECTURE')),('reader',('READ',))]:
            grant.issue(principal_id=principal if name!='reader' else 'independent-reader',project_id=scope['project_id'],repository_id=scope['repository_id'],profile_id='solo',permissions=permissions,candidates=[{'candidate_id':receipt['candidate']['id'],'subject_revision':canonical_digest(receipt['candidate'])}],maximum_decisions=8,expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=root/(name+'.private'))
        return grant,scope,receipt

def business(scope,receipt,operation='business-1'):
    return {'contract_version':CONTRACT,**scope,'operation_id':operation,'candidate_id':receipt['candidate']['id'],'subject_revision':canonical_digest(receipt['candidate']),'kind':'BUSINESS','rationale':'Explicit test-user Business approval on exact recorded scope.','confirm':True,'human_gates':['Owner explicitly reviews the exact documentary scope.']}

def architecture(scope,receipt,detail,operation='architecture-1'):
    c=receipt['candidate'];source=detail['current']['decisions']['BUSINESS'];aid=detail['current']['decisions']['ARCHITECTURE']['decision_id']
    # These are explicit synthetic USER inputs sent to the real route. No
    # approved Mission, successful advice or canonical decision is seeded.
    preview=ArchitectureMission('MISSION-PREVIEW',c['id'],c['title'],c['objective'],'Assess the contract and record its explicit constraints.','User supplied reduction in ambiguity.',aid,c['recommendation_id'],tuple(c['scope']),tuple(c['architecture_constraints']),tuple(c['acceptance_criteria']),('Explicit test-user technical assumption.',),tuple(c['dependencies']),('Explicit documentary inspection capability.',),(RequiredDiscipline.PLATFORM_ARCHITECTURE,),('Explicit test-user scope drift risk.',),ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,effect_policy=MissionEffectPolicy.from_dict(c['effect_policy']))
    planning=ArchitecturePlanningEvidence(tuple(c['scope']),(),('No code implementation or execution.',),('Explicit test-user scope drift risk.',),tuple(business(scope,receipt)['human_gates']),tuple(c['dependencies']),1000,500,canonical_digest(receipt['candidate']),mission_spec_digest=canonical_digest(preview.to_dict()),effect_policy=preview.effect_policy)
    return {'contract_version':CONTRACT,**scope,'operation_id':operation,'candidate_id':c['id'],'subject_revision':canonical_digest(receipt['candidate']),'kind':'ARCHITECTURE','rationale':'Explicit test-user Architecture approval of supplied exact planning.','confirm':True,'business_decision_id':source['decision_id'],'business_decision_digest':source['decision_digest'],'mission_preview':preview.to_dict(),'planning':planning.to_dict()}

def counts(root):
    with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
        out={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('mission_id_allocations','mission_state','governance_decisions','approved_worksets')}
    with closing(sqlite3.connect(root/'runtime'/'governance'/'candidates.sqlite')) as db:
        out['allocations']=db.execute('SELECT count(*) FROM allocations').fetchone()[0]
    out['provider_calls']=len((root/'provider-requests.private.jsonl').read_text().splitlines())
    return out

def installed_driver():
    from importlib.util import spec_from_file_location,module_from_spec
    import forge
    source=Path(__file__).resolve().parents[1]
    spec=spec_from_file_location('decision_installed_process_driver',source/'scripts/qualification/qualify_installed_candidate_decisions.py');module=module_from_spec(spec);spec.loader.exec_module(module)
    return module

class CandidateDecisionsHTTPTests(unittest.TestCase):
    def test_real_process_crashes_before_between_after_both_decisions_and_lost_http_body(self):
        driver=installed_driver()
        for kind in ('BUSINESS','ARCHITECTURE'):
            for stage in ('crash-before-effect','crash-between-stores','crash-after-effect','lost-response'):
                with self.subTest(kind=kind,stage=stage),TemporaryDirectory() as tmp:
                    result=driver.process_case(Path(tmp)/'decision-process',stage,kind)
                    self.assertEqual(result['result'],'PASS');self.assertTrue(result['fresh_os_processes'])

    def test_real_concurrent_http_decision_rejects_second_operation_promptly(self):
        from threading import Thread,Event
        from unittest.mock import patch
        import time
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'concurrency';grant,scope,registered=fixture(root);path='/v1/candidate-decisions/'+registered['candidate']['id']+'/business';payload=business(scope,registered);ready=Event();release=Event();first=[]
            with qual.http(root) as port:
                def identity():
                    with closing(sqlite3.connect((root/'runtime'/'governance'/'candidates.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
                        used=db.execute('SELECT count(*) FROM candidate_decision_intents').fetchone()[0]
                    if used and not ready.is_set():
                        ready.set();self.assertTrue(release.wait(10))
                    return qual.utils.fixture.IDENTITY
                with patch.object(qual.utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity):
                    worker=Thread(target=lambda:first.append(call(port,root/'both.private','POST',path,payload)));worker.start()
                    try:
                        self.assertTrue(ready.wait(10));start=time.monotonic();status,out=call(port,root/'both.private','POST',path,{**payload,'operation_id':'second-concurrent'});self.assertEqual(status,409,out);self.assertLess(time.monotonic()-start,1)
                    finally:
                        release.set();worker.join(15)
                self.assertEqual(first[0][0],200,first)
                self.assertEqual(counts(root)['governance_decisions'],1);self.assertEqual(counts(root)['provider_calls'],1)
                self.assertEqual(call(port,root/'both.private','POST',path,payload)[0],200)

    def test_two_actual_operator_principals_in_isolated_instances_and_foreign_read_denial(self):
        from unittest.mock import patch
        from forge.operator_identity import NamedOperatorIdentity
        with TemporaryDirectory() as tmp:
            operator_ids=[];first=None
            for n,identity in enumerate((qual.utils.fixture.IDENTITY,NamedOperatorIdentity('separate-real-test-operator',502))):
                # Only the OS identity adapter boundary/fixture identity changes.
                # Operator bootstrap/grants/roles/canonical signatures remain real.
                with patch.object(qual.utils.fixture,'IDENTITY',identity):
                    root=Path(tmp)/('instance-'+str(n));grant,scope,registered=fixture(root);operator_ids.append(grant._records()[0]['operator_id']);path='/v1/candidate-decisions/'+registered['candidate']['id']
                    with qual.http(root) as port:
                        if first is not None:
                            self.assertEqual(call(port,first,'GET','/v1/candidate-decisions/capability')[0],401)
                        first=root/'both.private'
                        self.assertEqual(call(port,root/'reader.private','GET',path)[0],200)
                        self.assertEqual(call(port,root/'reader.private','POST',path+'/business',business(scope,registered))[0],403)
                        self.assertEqual(call(port,root/'both.private','POST',path+'/business',business(scope,registered,'same-operation'))[0],200)
                        _,detail=call(port,root/'both.private','GET',path);req=architecture(scope,registered,detail)
                        self.assertEqual(call(port,root/'both.private','POST',path+'/architecture',req)[0],200)
                        self.assertEqual(counts(root)['governance_decisions'],2);self.assertEqual(counts(root)['mission_id_allocations'],0)
            self.assertNotEqual(*operator_ids)

    def test_retained_allowance_alias_capacity_immutable_intents_and_current_subject_drift(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'budget';grant,scope,registered=fixture(root);candidate=registered['candidate']['id'];path='/v1/candidate-decisions/'+candidate
            with qual.http(root) as port:
                principal=grant._records()[0]['principal_id'];limited=root/'limited.private'
                grant.issue(principal_id=principal,project_id=scope['project_id'],repository_id=scope['repository_id'],profile_id='solo',permissions=['READ','BUSINESS','ARCHITECTURE'],candidates=[{'candidate_id':candidate,'subject_revision':canonical_digest(registered['candidate'])}],maximum_decisions=1,expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=limited)
                req=business(scope,registered);status,out=call(port,limited,'POST',path+'/business',req);self.assertEqual(status,200,out);original=out['original_receipt']
                _,detail=call(port,limited,'GET',path);arch=architecture(scope,registered,detail);self.assertEqual(call(port,limited,'POST',path+'/architecture',arch)[0],409)
                for n in range(1,64):
                    status,replayed=call(port,limited,'POST',path+'/business',{**req,'operation_id':'alias-'+str(n)});self.assertEqual(status,200,replayed);self.assertEqual(replayed['original_receipt'],original)
                self.assertEqual(call(port,limited,'POST',path+'/business',{**req,'operation_id':'capacity-overflow'})[0],409)
                with closing(sqlite3.connect(root/'runtime'/'governance'/'candidates.sqlite')) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM candidate_decision_intents').fetchone()[0],64)
                    self.assertEqual(db.execute('SELECT count(DISTINCT decision_id) FROM candidate_decision_intents').fetchone()[0],1)
                    with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE candidate_decision_intents SET document='{}'")
                    with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM candidate_decision_receipts')
                self.assertEqual(call(port,limited,'GET',path+'/operations/business-1')[0],200)
                with RecommendationLifecycleStore(root/'runtime'/'governance'/'candidates.sqlite') as store:
                    store.update_candidate(candidate,objective='Actual supported later amendment to the subject.')
                status,current=call(port,limited,'GET',path+'/operations/business-1');self.assertEqual(status,200,current);self.assertEqual(current['original_receipt'],original);self.assertFalse(current['current']['subject_within_grant']);self.assertFalse(current['current']['decisions']['BUSINESS']['applicable'])
                self.assertEqual(call(port,limited,'POST',path+'/business',req)[0],409)
                self.assertEqual(counts(root)['governance_decisions'],1)

    def test_genuine_positive_revoke_failure_detector_preserves_original_canonical_evidence(self):
        driver=installed_driver()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'positive-control'
            with self.assertRaisesRegex(AssertionError,'revoked-positive-decision-replay-detected'):
                driver.positive_control(root)
            self.assertEqual(counts(root)['governance_decisions'],1)
            self.assertEqual(counts(root)['mission_id_allocations'],0);self.assertEqual(counts(root)['provider_calls'],1)
    def test_namespaces_wrong_scope_actor_and_no_implicit_decisions(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'denials';grant,scope,registered=fixture(root);candidate=registered['candidate']['id'];path='/v1/candidate-decisions/'+candidate;req=business(scope,registered)
            with qual.http(root) as port:
                for old in ('admin.private','alice.private','candidate.private'):
                    self.assertEqual(call(port,root/old,'GET','/v1/candidate-decisions/capability')[0],403)
                    self.assertEqual(call(port,root/old,'POST',path+'/business',req)[0],403)
                for old in ('/v1/status','/v1/missions/approve-business','/v1/advisory/capability','/v1/advisory-candidates/capability','/v1/worksets'):
                    self.assertEqual(call(port,root/'both.private','GET',old)[0],403)
                for changed in ({'actor':'primary_operator'},{'role':'business_owner'},{'confirm':1},{'human_gates':[]},{'rationale':'<script>approve</script>'},{'subject_revision':True},{'rationale':('ordinary context. '*40)+'secret=private-value'}):
                    self.assertEqual(call(port,root/'business.private','POST',path+'/business',{**req,**changed})[0],409)
                for key in ('instance_id','project_id','repository_id'):
                    self.assertEqual(call(port,root/'business.private','POST',path+'/business',{**req,key:'foreign'})[0],403)
                self.assertEqual(call(port,root/'both.private','GET','/v1/candidate-decisions/foreign-candidate')[0],403)
                self.assertEqual(call(port,root/'business.private','POST',path+'/business',{**req,'subject_revision':'sha256:'+'b'*64})[0],403)
                principal=grant._records()[0]['principal_id'];kwargs=dict(principal_id=principal,project_id=scope['project_id'],repository_id=scope['repository_id'],profile_id='solo',permissions=['READ','BUSINESS'],candidates=[{'candidate_id':candidate,'subject_revision':canonical_digest(registered['candidate'])}],maximum_decisions=1,expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=root/'denied.private')
                for changed in ({'principal_id':'different-remote-person'},{'profile_id':'duo'},{'project_id':'foreign'},{'maximum_decisions':True},{'permissions':['BUSINESS']},{'candidates':[]},{'expires_at':'2000-01-01T00:00:00+00:00'}):
                    with self.subTest(changed=changed),self.assertRaises((ValueError,PermissionError,KeyError)):
                        grant.issue(**{**kwargs,**changed})
                self.assertEqual(counts(root)['governance_decisions'],0);self.assertEqual(counts(root)['provider_calls'],1)

    def test_expired_revoked_grant_and_actual_operator_revocation_no_effect(self):
        from forge.operator_identity import InstallationOperatorService
        from forge.runtime.bootstrap import RuntimeBootstrap
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'revocation';grant,scope,registered=fixture(root);path='/v1/candidate-decisions/'+registered['candidate']['id'];req=business(scope,registered);token=root/'business.private'
            with qual.http(root) as port:
                original=grant.path.read_bytes();records=grant._records();records[0]['expires_at']='2000-01-01T00:00:00+00:00';grant._save(records)
                self.assertEqual(call(port,token,'POST',path+'/business',req)[0],401);grant.path.write_bytes(original)
                corrupt=grant._records();corrupt[1]['token_digest']=corrupt[0]['token_digest'];grant._save(corrupt)
                self.assertEqual(call(port,token,'GET','/v1/candidate-decisions/capability')[0],401);grant.path.write_bytes(original)
                corrupt=grant._records();corrupt[0]['operator_binding_version']=True;grant._save(corrupt)
                self.assertEqual(call(port,token,'GET','/v1/candidate-decisions/capability')[0],401);grant.path.write_bytes(original)
                grant.revoke(grant._records()[0]['grant_id']);self.assertEqual(call(port,token,'POST',path+'/business',req)[0],401)
                with RuntimeBootstrap(data_root=root/'runtime',forge_version='test').open() as db:
                    operator=InstallationOperatorService(db,lambda:qual.utils.fixture.IDENTITY);operator.revoke(operator.context())
                self.assertEqual(call(port,root/'both.private','POST',path+'/business',req)[0],403)
                self.assertEqual(call(port,root/'reader.private','GET',path)[0],403)
                self.assertEqual(counts(root)['governance_decisions'],0)

    def test_architecture_requires_real_business_exact_gates_complete_matching_planning(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'planning';grant,scope,registered=fixture(root);path='/v1/candidate-decisions/'+registered['candidate']['id']
            with qual.http(root) as port:
                _,detail=call(port,root/'both.private','GET',path);req=architecture(scope,registered,detail)
                self.assertEqual(call(port,root/'architecture.private','POST',path+'/architecture',req)[0],409)
                _,out=call(port,root/'business.private','POST',path+'/business',business(scope,registered))
                with InstalledDynamicMissionRuntime.open_for_governance_read(str(root/'runtime')) as runtime,RecommendationLifecycleStore.read_only(root/'runtime'/'governance'/'candidates.sqlite') as store:
                    bridge=GovernedCandidateIntake(store,runtime,resolve_governance_profile('solo'))
                    with self.assertRaises(GovernedCandidateIntakeError):
                        bridge.approved_envelope(registered['candidate']['id'],ArchitectureMission.from_dict(req['mission_preview']),ArchitecturePlanningEvidence.from_dict(req['planning']))
                _,detail=call(port,root/'both.private','GET',path);req=architecture(scope,registered,detail)
                changes=[{'planning':{**req['planning'],'risk_inputs':[True]}},{'planning':{**req['planning'],'non_goals':[7]}},{'mission_preview':{**req['mission_preview'],'technical_assumptions':[7]}},{'mission_preview':{**req['mission_preview'],'required_capabilities':[True]}},{'business_decision_id':'foreign-decision'},{'business_decision_digest':'sha256:'+'b'*64},{'planning':None},{'mission_preview':None},{'planning':{**req['planning'],'context_input_bound':True}},{'planning':{**req['planning'],'human_gates':['Different human gate.']}},{'planning':{**req['planning'],'mission_spec_digest':'sha256:'+'b'*64}},{'mission_preview':{**req['mission_preview'],'technical_assumptions':[]}},{'mission_preview':{**req['mission_preview'],'actor':'invented'}},{'mission_preview':{**req['mission_preview'],'scope':['Changed scope.']}}]
                for n,change in enumerate(changes):
                    changed={**req,'operation_id':'invalid-plan-'+str(n),**change}
                    self.assertEqual(call(port,root/'architecture.private','POST',path+'/architecture',changed)[0],409)
                    self.assertEqual(counts(root)['governance_decisions'],1)
                self.assertEqual(call(port,root/'architecture.private','POST',path+'/architecture',req)[0],200)
                self.assertEqual(counts(root)['governance_decisions'],2)

    def test_source_acl_and_candidate_subject_drift_deny_fresh_effects(self):
        from forge.advisory_context import AdvisoryContext
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'drift';grant,scope,registered=fixture(root);path='/v1/candidate-decisions/'+registered['candidate']['id'];req=business(scope,registered)
            with qual.http(root) as port:
                with RecommendationLifecycleStore(root/'runtime'/'governance'/'candidates.sqlite') as store:
                    store.update_candidate(registered['candidate']['id'],objective='Actual supported Candidate amendment outside this read-only decision slice.')
                self.assertEqual(call(port,root/'business.private','POST',path+'/business',req)[0],409)
                status,detail=call(port,root/'both.private','GET',path);self.assertEqual(status,200,detail);self.assertFalse(detail['current']['subject_within_grant']);self.assertIsNone(detail['current']['candidate'])
                AdvisoryContext(root/'runtime',scope['instance_id']).revoke('selected-context')
                self.assertEqual(call(port,root/'both.private','GET',path)[0],403)
                self.assertEqual(counts(root)['governance_decisions'],0)

    def test_cli_parity_owner_provision_no_credential_export_and_pure_reads(self):
        from io import StringIO
        from unittest.mock import patch
        from forge.candidate_decision_cli import main
        from forge.candidate_decision_grant import main as owner_main
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'cli';grant,scope,registered=fixture(root);root.chmod(0o700);candidate=registered['candidate']['id'];path='/v1/candidate-decisions/'+candidate
            with qual.http(root) as port:
                args=['--data-root',str(root/'runtime'),'--token-file',str(root/'both.private')]
                db=root/'runtime'/'forge.db';store=root/'runtime'/'governance'/'candidates.sqlite';before=(db.read_bytes(),store.read_bytes())
                for command in (['capability'],['prepare','--candidate-id',candidate]):
                    with patch('sys.stdout',new_callable=StringIO) as out:
                        self.assertEqual(main(args+command),0);self.assertTrue(json.loads(out.getvalue())['read_only'])
                self.assertEqual(before,(db.read_bytes(),store.read_bytes()))
                req=root/'business-request.private.json';req.write_text(json.dumps(business(scope,registered)));req.chmod(0o600)
                with patch('sys.stdout',new_callable=StringIO) as out:
                    self.assertEqual(main(args+['business','--request-file',str(req)]),0);original=json.loads(out.getvalue())['original_receipt']
                _,detail=call(port,root/'both.private','GET',path);req.write_text(json.dumps(architecture(scope,registered,detail)))
                with patch('sys.stdout',new_callable=StringIO):self.assertEqual(main(args+['architecture','--request-file',str(req)]),0)
                with patch('sys.stdout',new_callable=StringIO) as out:
                    self.assertEqual(main(args+['operation','--candidate-id',candidate,'--operation-id','business-1']),0);self.assertEqual(json.loads(out.getvalue())['original_receipt'],original)
                token=root/'owner-issued.private';r=grant._records()[0]
                for owner_action in (['identity'],['inspect','--candidate-id',candidate]):
                    with patch('sys.stdout',new_callable=StringIO) as out:
                        self.assertEqual(owner_main(['--data-root',str(root/'runtime')]+owner_action),0);self.assertTrue(json.loads(out.getvalue())['read_only'])
                owner_args=['--data-root',str(root/'runtime'),'issue','--principal-id',r['principal_id'],'--project-id',scope['project_id'],'--repository-id',scope['repository_id'],'--profile-id','solo','--permission','READ','--permission','BUSINESS','--candidate',candidate+'='+canonical_digest(registered['candidate']),'--maximum-decisions','8','--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(token)]
                with patch('sys.stdout',new_callable=StringIO) as out:
                    self.assertEqual(owner_main(owner_args),0);issued=json.loads(out.getvalue());self.assertNotIn(token.read_text().strip(),out.getvalue())
                with patch('sys.stdout',new_callable=StringIO):self.assertEqual(owner_main(['--data-root',str(root/'runtime'),'revoke','--grant-id',issued['grant_id']]),0)
                req.chmod(0o644)
                with patch('sys.stdout',new_callable=StringIO):self.assertEqual(main(args+['business','--request-file',str(req)]),1)
                with patch('sys.stdout',new_callable=StringIO):self.assertEqual(owner_main(owner_args),1)
                self.assertEqual(counts(root)['governance_decisions'],2);self.assertEqual(counts(root)['provider_calls'],1)
    def test_actual_separate_business_architecture_receipts_and_intake_validation_without_admit(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'decisions';grant,scope,registered=fixture(root);candidate=registered['candidate']['id'];path='/v1/candidate-decisions/'+candidate
            with qual.http(root) as port:
                self.assertEqual(call(port,root/'reader.private','GET','/v1/candidate-decisions/capability')[0],200)
                status,detail=call(port,root/'both.private','GET',path);self.assertEqual(status,200,detail)
                arch=architecture(scope,registered,detail)
                self.assertEqual(call(port,root/'architecture.private','POST',path+'/architecture',arch)[0],409)
                req=business(scope,registered)
                self.assertEqual(call(port,root/'reader.private','POST',path+'/business',req)[0],403)
                self.assertEqual(call(port,root/'architecture.private','POST',path+'/business',req)[0],403)
                status,out=call(port,root/'business.private','POST',path+'/business',req);self.assertEqual(status,200,out);self.assertTrue(out['recorded']);self.assertFalse(out['read_only']);self.assertEqual(out['state'],'COMPLETE');self.assertNotEqual(registered['candidate_digest'],canonical_digest(registered['candidate']))
                original=out['original_receipt'];self.assertEqual(out['current']['recommendation_status'],'BUSINESS_APPROVED')
                for body in (req,{**req,'operation_id':'business-alias'}):
                    status,replay=call(port,root/'business.private','POST',path+'/business',body);self.assertEqual(status,200,replay);self.assertFalse(replay['recorded']);self.assertEqual(replay['original_receipt'],original)
                self.assertEqual(call(port,root/'business.private','POST',path+'/business',{**req,'rationale':'Different same-key content.'})[0],409)
                _,detail=call(port,root/'architecture.private','GET',path);arch=architecture(scope,registered,detail)
                self.assertEqual(call(port,root/'business.private','POST',path+'/architecture',arch)[0],403)
                status,out=call(port,root/'architecture.private','POST',path+'/architecture',arch);self.assertEqual(status,200,out);self.assertEqual(out['current']['recommendation_status'],'ARCHITECTURE_APPROVED')
                self.assertNotEqual(original['decision_id'],out['original_receipt']['decision_id'])
                with InstalledDynamicMissionRuntime.open_for_governance_read(str(root/'runtime')) as runtime,RecommendationLifecycleStore.read_only(root/'runtime'/'governance'/'candidates.sqlite') as store:
                    bridge=GovernedCandidateIntake(store,runtime,resolve_governance_profile('solo'))
                    envelope=bridge.approved_envelope(candidate,ArchitectureMission.from_dict(arch['mission_preview']),ArchitecturePlanningEvidence.from_dict(arch['planning']))
                    self.assertEqual(envelope.subject_revision,canonical_digest(registered['candidate']));self.assertEqual(envelope.planning.dependencies,())
                status,current=call(port,root/'business.private','GET',path+'/operations/business-1');self.assertEqual(status,200,current);self.assertEqual(current['original_receipt'],original);self.assertEqual(current['current']['recommendation_status'],'ARCHITECTURE_APPROVED')
                self.assertTrue(current['current']['decisions']['BUSINESS']['applicable']);self.assertTrue(current['current']['decisions']['ARCHITECTURE']['applicable'])
                self.assertEqual(counts(root),{'mission_id_allocations':0,'mission_state':0,'governance_decisions':2,'approved_worksets':0,'allocations':0,'provider_calls':1})
