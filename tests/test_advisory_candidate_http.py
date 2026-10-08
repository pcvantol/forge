"""Real advice HTTP and canonical unapproved Candidate registration."""
from datetime import UTC,datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import closing
import unittest,json,sqlite3
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import jsonschema
import forge
SCHEMA=json.loads((Path(forge.__file__).parent/"api/advisory-candidate-v1.json").read_text())
VALIDATOR=jsonschema.Draft202012Validator(SCHEMA)
from test_advisory_http import qual,request
from forge.server_runtime import existing_instance
from forge.advisory_candidate_grant import AdvisoryCandidateGrant
from forge.advisory_candidate_contract import CONTRACT

def call(port,token,method,path,body=None):
    q=Request('http://127.0.0.1:'+str(port)+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token.read_text().strip(),'Content-Type':'application/json'})
    try:
        with urlopen(q,timeout=15) as response:
            value=json.loads(response.read());VALIDATOR.validate(value)
            if body is not None:VALIDATOR.validate(body)
            return response.status,value
    except HTTPError as e:
        try:return e.code,json.loads(e.read())
        finally:e.close()

def setup(root,principal='alice',proposals=('candidate-proposal',),fault=None):
    qual.configure(root)
    if fault:(root/'fault.private').write_text(fault)
    with qual.http(root) as port:
        _,cap=qual.call(port,root/(principal+'.private'),'GET','/v1/advisory/capability')
        src=cap['available_sources'][0]
        _,cap=qual.call(port,root/(principal+'.private'),'GET','/v1/advisory/capability?source_id='+src['source_id']+'&source_version='+src['version'])
        r={**request(cap),'conversation_id':'conversation-'+principal,'selected_sources':[{'source_id':src['source_id'],'version':src['version']}]}
        status,advice=qual.call(port,root/(principal+'.private'),'POST','/v1/advisory/conversation-'+principal+'/turns',r)
        assert status==200 and advice['original_turn']['status']==('COMPLETE' if fault is None else 'FAILED')
        i=existing_instance(root/'runtime');g=AdvisoryCandidateGrant(root/'runtime',i.instance_id)
        g.issue(principal_id=principal,project_id=cap['project_id'],repository_id=cap['repository_id'],conversation_id='conversation-'+principal,proposal_ids=proposals,expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),maximum_registrations=8,token_path=root/'candidate.private')
    return g

def definition(source,cap,proposal='candidate-proposal',expected=0):
    f={'title':'Assess documented design constraints','objective':'Assess the contract and record its explicit constraints.',
       'business_value':'User supplied reduction in ambiguity.','engineering_value':'User supplied contract clarity.',
       'architectural_value':'User supplied retained service boundary.','rationale':'Explicit user selected advice handoff.',
       'confidence':35,'scope':['Read and assess the selected documentary contract.'],'exclusions':['No code implementation or execution.'],
       'acceptance_criteria':['The documented constraints and unresolved questions are explicitly recorded.'],
       'architecture_constraints':['Preserve the existing service boundary.'],'dependencies':[],
       'effect_policy':{'contract_version':'1.0','mode':'READ_ONLY_ASSESSMENT','delivery':'EVIDENCE_ONLY','read_paths':['docs/advice.md'],'write_paths':[]}}
    return {'contract_version':CONTRACT,**{k:cap[k] for k in ['instance_id','project_id','repository_id','conversation_id']},'proposal_id':proposal,'turn_id':source['turn_id'],'expected_revision':expected,'expected_conversation_revision':source['conversation_revision'],'context_revision':source['context_revision'],'fields':f}

def command(d,operation='registration-1'):
    return {'contract_version':CONTRACT,**{k:d[k] for k in ['instance_id','project_id','repository_id','conversation_id','proposal_id','proposal_revision','proposal_digest']},'operation_id':operation,'expected_conversation_revision':d['source']['conversation_revision'],'context_revision':d['source']['context_revision'],'confirm':True}

class AdvisoryCandidateHTTPTests(unittest.TestCase):
    def test_real_advice_proposal_candidate_replay_and_no_approval_or_provider(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'candidate';setup(root)
            with qual.http(root) as port:
                token=root/'candidate.private';status,cap=call(port,token,'GET','/v1/advisory-candidates/capability');self.assertEqual(status,200)
                base='/v1/advisory-candidates/conversation-alice'
                status,s=call(port,token,'GET',base+'/source/first');self.assertEqual(status,200)
                r=definition(s['source'],cap)
                status,saved=call(port,token,'POST',base+'/proposals',r);self.assertEqual(status,200,saved);d=saved['proposal']
                self.assertFalse((root/'runtime'/'governance'/'candidates.sqlite').exists())
                self.assertEqual(call(port,token,'GET',base+'/proposals/candidate-proposal')[0],200)
                c=command(d);target=base+'/proposals/candidate-proposal/registrations'
                status,out=call(port,token,'POST',target,c);self.assertEqual(status,200,out);self.assertTrue(out['recorded']);self.assertEqual(out['current']['recommendation_status'],'RECOMMENDED')
                original=out['original_receipt'];self.assertEqual(original['candidate']['effect_policy']['mode'],'READ_ONLY_ASSESSMENT')
                for cmd in [c,command(d,'alias')]:
                    status,replay=call(port,token,'POST',target,cmd);self.assertEqual(status,200,replay);self.assertFalse(replay['recorded']);self.assertEqual(replay['original_receipt'],original)
                self.assertEqual(call(port,token,'GET',target+'/registration-1')[0],200)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
                with closing(sqlite3.connect(root/'runtime'/'governance'/'candidates.sqlite')) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM candidates').fetchone()[0],1)
                    self.assertEqual(db.execute('SELECT count(*) FROM allocations').fetchone()[0],0)
                    self.assertEqual(db.execute("SELECT count(*) FROM decision_evidence WHERE kind IN ('business_decision','architecture_decision')").fetchone()[0],0)
                with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                    for table in ['mission_id_allocations','mission_state','governance_decisions']:
                        self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_amendment_old_receipt_current_candidate_and_source_stale(self):
        from forge.lifecycle import RecommendationLifecycleStore
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'candidate';setup(root)
            with qual.http(root) as port:
                token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice';_,cap=call(port,token,'GET','/v1/advisory-candidates/capability');_,s=call(port,token,'GET',base+'/source/first');r=definition(s['source'],cap)
                _,out=call(port,token,'POST',base+'/proposals',r);d=out['proposal'];target=base+'/proposals/candidate-proposal/registrations';c=command(d)
                _,first=call(port,token,'POST',target,c);receipt=first['original_receipt']
                changed={**r,'expected_revision':1,'fields':{**r['fields'],'objective':'A user amended objective with its own explicit new revision.'}}
                status,out=call(port,token,'POST',base+'/proposals',changed);self.assertEqual(status,200,out);d2=out['proposal'];self.assertEqual(d2['proposal_revision'],2);self.assertNotEqual(d2['proposal_digest'],d['proposal_digest'])
                self.assertEqual(call(port,token,'POST',target,command(d,'stale-alias'))[0],409)
                status,second=call(port,token,'POST',target,command(d2,'registration-2'));self.assertEqual(status,200,second);self.assertNotEqual(second['original_receipt']['candidate']['id'],receipt['candidate']['id'])
                self.assertEqual(call(port,token,'POST',target,{**c,'proposal_revision':2,'proposal_digest':d2['proposal_digest']})[0],409)
                with RecommendationLifecycleStore(root/'runtime'/'governance'/'candidates.sqlite') as store:store.update_candidate(receipt['candidate']['id'],objective='Current canonical Candidate changed through the supported lifecycle API.')
                status,history=call(port,token,'GET',base+'/proposals/candidate-proposal?revision=1');self.assertEqual(status,200)
                self.assertEqual(history['registration']['original_receipt'],receipt);self.assertNotEqual(history['registration']['current']['candidate_digest'],receipt['candidate_digest'])
                # A genuine further advice turn changes the current conversation; no new registration may borrow stale context.
                _,acap=qual.call(port,root/'alice.private','GET','/v1/advisory/capability');src=acap['available_sources'][0]
                _,acap=qual.call(port,root/'alice.private','GET','/v1/advisory/capability?source_id='+src['source_id']+'&source_version='+src['version'])
                ar={**request(acap,turn='later',revision=s['source']['conversation_revision']),'selected_sources':[{'source_id':src['source_id'],'version':src['version']}]}
                self.assertEqual(qual.call(port,root/'alice.private','POST','/v1/advisory/conversation-alice/turns',ar)[0],200)
                self.assertEqual(call(port,token,'POST',target,command(d2,'source-stale-alias'))[0],409)
                replay=call(port,token,'POST',target,c)[1];self.assertEqual(replay['original_receipt'],receipt);self.assertFalse(replay['current']['source_fresh'])
                with closing(sqlite3.connect(root/'runtime'/'governance'/'candidates.sqlite')) as db:self.assertEqual(db.execute('SELECT count(*) FROM candidates').fetchone()[0],2)

    def test_authority_denials_unsafe_fields_expiry_revoke_source_acl_no_effect(self):
        from forge.advisory_context import AdvisoryContext
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'candidate';grant=setup(root)
            with qual.http(root) as port:
                token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice';_,cap=call(port,token,'GET','/v1/advisory-candidates/capability');_,s=call(port,token,'GET',base+'/source/first');r=definition(s['source'],cap)
                for old in ['alice.private','bob.private','admin.private']:
                    self.assertEqual(call(port,root/old,'GET','/v1/advisory-candidates/capability')[0],403)
                    self.assertEqual(call(port,root/old,'POST',base+'/proposals',r)[0],403)
                for path in ['/v1/status','/v1/projects','/v1/advisory/capability','/v1/worksets','/v1/missions/approve-business']:
                    self.assertEqual(call(port,token,'GET',path)[0],403)
                for changed in [{**r,'actor':'business-owner'},{**r,'expected_revision':True},{**r,'fields':{**r['fields'],'confidence':True}},{**r,'fields':{**r['fields'],'objective':'<script>unsafe</script>'}},{**r,'fields':{**r['fields'],'rationale':('ordinary context. '*40)+'secret=private-value'}},{**r,'fields':{**r['fields'],'effect_policy':{**r['fields']['effect_policy'],'write_paths':['src/application.py']}}}]:
                    self.assertEqual(call(port,token,'POST',base+'/proposals',changed)[0],400)
                for key in ['instance_id','project_id','repository_id']:
                    self.assertEqual(call(port,token,'POST',base+'/proposals',{**r,key:'foreign'})[0],403)
                self.assertEqual(call(port,token,'POST',base+'/proposals',{**r,'proposal_id':'foreign'})[0],403)
                self.assertEqual(call(port,token,'POST',base+'/proposals',{**r,'expected_conversation_revision':999})[0],409)
                self.assertFalse((root/'runtime'/'governance'/'candidates.sqlite').exists())
                _,out=call(port,token,'POST',base+'/proposals',r);d=out['proposal'];target=base+'/proposals/candidate-proposal/registrations';c=command(d)
                for changed in [{**c,'confirm':False},{**c,'proposal_revision':True},{**c,'context_revision':'invalid'},{**c,'role':'architecture-owner'}]:self.assertEqual(call(port,token,'POST',target,changed)[0],400)
                self.assertEqual(call(port,token,'POST',target,{**c,'expected_conversation_revision':999})[0],409)
                self.assertFalse((root/'runtime'/'governance'/'candidates.sqlite').exists())
                records=grant._records();original=grant.path.read_bytes();records[0]['expires_at']='2000-01-01T00:00:00+00:00';grant._save(records)
                self.assertEqual(call(port,token,'POST',target,c)[0],401);grant.path.write_bytes(original)
                broken=grant._records();broken[0]['maximum_registrations']=True;grant._save(broken);self.assertEqual(call(port,token,'GET','/v1/advisory-candidates/capability')[0],401);grant.path.write_bytes(original)
                AdvisoryContext(root/'runtime',existing_instance(root/'runtime').instance_id).revoke('selected-context')
                self.assertEqual(call(port,token,'GET',base+'/proposals/candidate-proposal')[0],403)
                self.assertEqual(call(port,token,'POST',target,c)[0],403);self.assertFalse((root/'runtime'/'governance'/'candidates.sqlite').exists())
                grant.revoke(grant._records()[0]['grant_id']);self.assertEqual(call(port,token,'GET',base+'/source/first')[0],401)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_real_process_crash_before_after_candidate_and_lost_body(self):
        from importlib.util import spec_from_file_location,module_from_spec
        path=Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_installed_advisory_candidate.py'
        spec=spec_from_file_location('candidate_process_driver',path);driver=module_from_spec(spec);spec.loader.exec_module(driver)
        for stage in ['crash-before-effect','crash-after-effect','lost-response']:
            with self.subTest(stage=stage),TemporaryDirectory() as tmp:
                proof=driver.process_case(Path(tmp)/'candidate',stage)
                self.assertEqual(proof['candidate_count'],1);self.assertTrue(proof['same_original_receipt']);self.assertEqual(proof['provider_invocations'],1)

    def test_canonical_conflict_rolls_back_ancestors_and_never_adopts_foreign_candidate(self):
        from dataclasses import replace
        from forge.lifecycle import RecommendationLifecycleStore,RecommendationStatus,LifecycleError
        from forge.advisory_candidate_service import AdvisoryCandidateService
        from forge.advisory_candidate_contract import candidate_objects,registration_receipt
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'candidate';grant=setup(root)
            with qual.http(root) as port:
                token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice';_,cap=call(port,token,'GET','/v1/advisory-candidates/capability');_,s=call(port,token,'GET',base+'/source/first');_,saved=call(port,token,'POST',base+'/proposals',definition(s['source'],cap));d=saved['proposal']
                principal=grant.authorize('Bearer '+token.read_text().strip());key=AdvisoryCandidateService._key(principal,d);now=datetime.now(UTC).isoformat();rec,can=candidate_objects(d,key,now);intent={'request':command(d),'proposal':d,'registered_at':now}
                with RecommendationLifecycleStore(root/'runtime'/'governance'/'candidates.sqlite') as store:
                    # Disposable existing-namespace conflict via supported unapproved lifecycle methods.
                    foreign=replace(rec,id='owned-negative-conflict');store.create_recommendation(foreign,actor=principal.reference,rationale='Declared negative namespace input.')
                    store.transition(foreign.id,RecommendationStatus.RECOMMENDED,actor=principal.reference,occurred_at=now,rationale='Unapproved negative input.')
                    occupied=replace(can,recommendation_id=foreign.id);store.create_candidate(occupied)
                    with self.assertRaises(LifecycleError):store.begin_candidate_registration('registration-1','forged-principal',key,intent,8)
                    store.begin_candidate_registration('registration-1',principal.reference,key,intent,8)
                    exact_receipt=registration_receipt(principal.reference,'registration-1',key,d,now)
                    with self.assertRaises(LifecycleError):store.finish_candidate_registration('registration-1',principal.reference,key,rec,can,{**exact_receipt,'registration_key':'sha256:'+'0'*64})
                    with self.assertRaises(LifecycleError):store.finish_candidate_registration('registration-1',principal.reference,key,rec,replace(can,objective='Different from the admitted user fields.'),exact_receipt)
                    with self.assertRaisesRegex(sqlite3.IntegrityError,'candidates.candidate_id'):store.finish_candidate_registration('registration-1',principal.reference,key,rec,can,exact_receipt)
                    with self.assertRaises(LifecycleError):store.get_recommendation(rec.id)
                    self.assertEqual(store.get_candidate(can.id),occupied)
                    self.assertIsNone(store.candidate_registration(key,principal.reference))
                    self.assertIsNotNone(store.candidate_registration_intent('registration-1',principal.reference))
                    self.assertEqual(store._connection.execute('SELECT count(*) FROM allocations').fetchone()[0],0)
                target=base+'/proposals/candidate-proposal/registrations'
                self.assertEqual(call(port,token,'POST',target,command(d))[0],503)
                self.assertEqual(call(port,token,'GET',target+'/registration-1')[1]['state'],'PENDING')
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_failed_or_unknown_advice_cannot_be_proposal_source(self):
        for fault in ['inject','unknown-usage']:
            with self.subTest(fault=fault),TemporaryDirectory() as tmp:
                root=Path(tmp)/'candidate';setup(root,fault=fault)
                with qual.http(root) as port:
                    token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice'
                    self.assertEqual(call(port,token,'GET',base+'/source/first')[0],409)
                    self.assertFalse((root/'runtime'/'governance'/'candidates.sqlite').exists())
                    self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_read_preview_cli_parity_and_real_intake_requires_separate_approvals(self):
        from contextlib import closing
        from io import StringIO
        from unittest.mock import patch
        from forge.advisory_candidate_cli import main
        from forge.advisory_candidate_grant import main as grant_main
        from forge.lifecycle import RecommendationLifecycleStore
        from forge.governed_candidate_intake import GovernedCandidateIntake,GovernedCandidateIntakeError
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'candidate';setup(root)
            with qual.http(root) as port:
                token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice';_,cap=call(port,token,'GET','/v1/advisory-candidates/capability');_,s=call(port,token,'GET',base+'/source/first');r=definition(s['source'],cap)
                inputs=root/'inputs';inputs.mkdir(mode=0o700);draft=inputs/'draft.json';draft.write_text(json.dumps(r));draft.chmod(0o600)
                args=['--data-root',str(root/'runtime'),'--token-file',str(token)]
                with patch('sys.stdout',new_callable=StringIO) as out:self.assertEqual(main(args+['save','--request-file',str(draft)]),0);d=json.loads(out.getvalue())['proposal']
                cmd=inputs/'command.json';cmd.write_text(json.dumps(command(d)));cmd.chmod(0o600)
                with patch('sys.stdout',new_callable=StringIO) as out:self.assertEqual(main(args+['register','--request-file',str(cmd)]),0);receipt=json.loads(out.getvalue())['original_receipt']
                before=(root/'runtime'/'governance'/'candidates.sqlite').read_bytes();runtime_before=(root/'runtime'/'forge.db').read_bytes()
                for action in [['capability'],['source','--conversation-id','conversation-alice','--turn-id','first'],['preview','--conversation-id','conversation-alice','--proposal-id','candidate-proposal','--revision','1'],['operation','--conversation-id','conversation-alice','--proposal-id','candidate-proposal','--operation-id','registration-1']]:
                    with patch('sys.stdout',new_callable=StringIO) as out:self.assertEqual(main(args+action),0);VALIDATOR.validate(json.loads(out.getvalue()))
                self.assertEqual((root/'runtime'/'governance'/'candidates.sqlite').read_bytes(),before);self.assertEqual((root/'runtime'/'forge.db').read_bytes(),runtime_before)
                with RecommendationLifecycleStore.read_only(root/'runtime'/'governance'/'candidates.sqlite') as store:
                    bridge=GovernedCandidateIntake(store,None,None)
                    with self.assertRaisesRegex(GovernedCandidateIntakeError,'both Candidate approvals'):bridge.approved_envelope(receipt['candidate']['id'],None,None)
                issued=root/'limited.private';gargs=['--data-root',str(root/'runtime'),'issue','--principal-id','alice','--project-id',cap['project_id'],'--repository-id',cap['repository_id'],'--conversation-id','conversation-alice','--proposal-id','candidate-proposal','--maximum-registrations','1','--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(issued)]
                with patch('sys.stdout',new_callable=StringIO) as out:self.assertEqual(grant_main(gargs),0);g=json.loads(out.getvalue());self.assertNotIn(issued.read_text().strip(),out.getvalue())
                with patch('sys.stdout',new_callable=StringIO):self.assertEqual(grant_main(['--data-root',str(root/'runtime'),'revoke','--grant-id',g['grant_id']]),0)
                self.assertEqual(call(port,issued,'GET','/v1/advisory-candidates/capability')[0],401)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_true_concurrent_registration_rejects_overlap_without_duplicate(self):
        from threading import Thread,Event
        from unittest.mock import patch
        import time
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'candidate';setup(root)
            with qual.http(root) as port:
                token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice';_,cap=call(port,token,'GET','/v1/advisory-candidates/capability');_,s=call(port,token,'GET',base+'/source/first');_,saved=call(port,token,'POST',base+'/proposals',definition(s['source'],cap));c=command(saved['proposal']);target=base+'/proposals/candidate-proposal/registrations';ready=Event();release=Event();first=[]
                def identity():
                    path=root/'runtime'/'governance'/'candidates.sqlite'
                    if path.exists():
                        try:
                            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:count=db.execute('SELECT count(*) FROM advisory_candidate_intents').fetchone()[0]
                            if count and not ready.is_set():ready.set();self.assertTrue(release.wait(10))
                        except sqlite3.Error:pass
                    return qual.utils.fixture.IDENTITY
                with patch.object(qual.utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity):
                    worker=Thread(target=lambda:first.append(call(port,token,'POST',target,c)));worker.start()
                    try:
                        self.assertTrue(ready.wait(10));start=time.monotonic();status,out=call(port,token,'POST',target,c);self.assertEqual(status,409,out);self.assertLess(time.monotonic()-start,1)
                    finally:release.set();worker.join(15)
                self.assertEqual(first[0][0],200,first);self.assertEqual(call(port,token,'POST',target,c)[0],200)
                with closing(sqlite3.connect(root/'runtime'/'governance'/'candidates.sqlite')) as db:self.assertEqual(db.execute('SELECT count(*) FROM candidates').fetchone()[0],1)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_isolated_instances_and_principals_cannot_read_or_register_foreign_proposals(self):
        with TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'alpha',Path(tmp)/'beta';setup(a);setup(b,principal='bob')
            with qual.http(a) as pa,qual.http(b) as pb:
                self.assertEqual(call(pb,a/'candidate.private','GET','/v1/advisory-candidates/capability')[0],401)
                self.assertEqual(call(pa,b/'candidate.private','GET','/v1/advisory-candidates/capability')[0],401)
                created=[]
                for root,port,actor in [(a,pa,'alice'),(b,pb,'bob')]:
                    token=root/'candidate.private';base='/v1/advisory-candidates/conversation-'+actor;_,cap=call(port,token,'GET','/v1/advisory-candidates/capability');_,s=call(port,token,'GET',base+'/source/first');_,saved=call(port,token,'POST',base+'/proposals',definition(s['source'],cap));status,out=call(port,token,'POST',base+'/proposals/candidate-proposal/registrations',command(saved['proposal']));self.assertEqual(status,200,out);created.append(out['original_receipt']['candidate']['id'])
                    other='bob' if actor=='alice' else 'alice';self.assertEqual(call(port,token,'GET','/v1/advisory-candidates/conversation-'+other+'/proposals/candidate-proposal')[0],403)
                self.assertNotEqual(created[0],created[1])
                # Same installation: independently issued principal scope and the same operation ID.
                with qual.http(a) as port:
                    _,cap=qual.call(port,a/'bob.private','GET','/v1/advisory/capability');r={**request(cap),'conversation_id':'conversation-bob'}
                    self.assertEqual(qual.call(port,a/'bob.private','POST','/v1/advisory/conversation-bob/turns',r)[0],200)
                    i=existing_instance(a/'runtime');g=AdvisoryCandidateGrant(a/'runtime',i.instance_id);token=a/'bob-candidate.private'
                    g.issue(principal_id='bob',project_id=cap['project_id'],repository_id=cap['repository_id'],conversation_id='conversation-bob',proposal_ids=['candidate-proposal'],expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),maximum_registrations=8,token_path=token)
                    base='/v1/advisory-candidates/conversation-bob';_,cp=call(port,token,'GET','/v1/advisory-candidates/capability');_,s=call(port,token,'GET',base+'/source/first');_,saved=call(port,token,'POST',base+'/proposals',definition(s['source'],cp));status,out=call(port,token,'POST',base+'/proposals/candidate-proposal/registrations',command(saved['proposal']));self.assertEqual(status,200,out);self.assertNotEqual(out['original_receipt']['candidate']['id'],created[0])
                    self.assertEqual(call(port,token,'GET','/v1/advisory-candidates/conversation-alice/proposals/candidate-proposal/registrations/registration-1')[0],403)

    def test_retained_budget_and_corrupted_private_proposal_failclosed(self):
        from forge.advisory_candidate_service import AdvisoryCandidateService
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'candidate';grant=setup(root,proposals=('candidate-proposal','other-proposal'))
            with qual.http(root) as port:
                token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice';_,cap=call(port,token,'GET','/v1/advisory-candidates/capability');_,s=call(port,token,'GET',base+'/source/first')
                # Owner-provisioned lower bound is retained even after a wider renewed grant.
                limited=root/'limited.private';grant.issue(principal_id='alice',project_id=cap['project_id'],repository_id=cap['repository_id'],conversation_id='conversation-alice',proposal_ids=['candidate-proposal'],expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),maximum_registrations=1,token_path=limited)
                _,saved=call(port,limited,'POST',base+'/proposals',definition(s['source'],cap));d=saved['proposal'];target=base+'/proposals/candidate-proposal/registrations';self.assertEqual(call(port,limited,'POST',target,command(d))[0],200)
                amendment=definition(s['source'],cap,expected=1);amendment['fields']['objective']='A newly amended user objective that does not reset consumed registration.'
                _,saved=call(port,token,'POST',base+'/proposals',amendment);self.assertEqual(call(port,token,'POST',target,command(saved['proposal'],'second'))[0],409)
                p=grant.authorize('Bearer '+token.read_text().strip());path=AdvisoryCandidateService(root/'runtime',grant)._path(p,'candidate-proposal');original=path.read_bytes();v=json.loads(original)
                for fault in ['allowance','revision','origin','source','digest']:
                    broken=json.loads(original)
                    if fault=='allowance':broken['maximum_registrations']=8
                    elif fault=='revision':broken['revisions'][0]['proposal_revision']=True
                    elif fault=='origin':broken['revisions'][0]['field_origins']['fields']='MODEL_INFERRED'
                    elif fault=='source':broken['revisions'][0]['source']['advice_summary']='A forged source summary.'
                    else:broken['revisions'][0]['proposal_digest']='sha256:'+'0'*64
                    path.write_text(json.dumps(broken));self.assertEqual(call(port,token,'GET',base+'/proposals/candidate-proposal')[0],503,fault);path.write_bytes(original)
                with closing(sqlite3.connect(root/'runtime'/'governance'/'candidates.sqlite')) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM candidates').fetchone()[0],1)
                    with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE advisory_candidate_intents SET document='{}'")
                self.assertEqual(call(port,token,'GET',target+'/registration-1')[0],200)

    def test_proposal_retention_and_revision_bounds_preserve_existing_readbacks(self):
        from forge.advisory_candidate_service import AdvisoryCandidateService
        from forge.workspace_review_grant import _write_private
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'candidate';grant=setup(root,proposals=('candidate-proposal','other-proposal'))
            with qual.http(root) as port:
                token=root/'candidate.private';base='/v1/advisory-candidates/conversation-alice';_,cap=call(port,token,'GET','/v1/advisory-candidates/capability');_,s=call(port,token,'GET',base+'/source/first');r=definition(s['source'],cap);_,saved=call(port,token,'POST',base+'/proposals',r)
                principal=grant.authorize('Bearer '+token.read_text().strip());service=AdvisoryCandidateService(root/'runtime',grant);path=service._path(principal,'candidate-proposal')
                # Declared disposable retention inputs, never successful proposal/Candidate records.
                for n in range(63):_write_private(path.parent/('capacity-input-'+str(n)+'.json'),b'{}')
                before={p.name:p.read_bytes() for p in path.parent.glob('*.json')}
                self.assertEqual(call(port,token,'POST',base+'/proposals',definition(s['source'],cap,proposal='other-proposal'))[0],409)
                self.assertEqual({p.name:p.read_bytes() for p in path.parent.glob('*.json')},before)
                for n in range(1,8):
                    body={**r,'expected_revision':n,'fields':{**r['fields'],'rationale':'User amended documentary rationale revision '+str(n+1)+'.'}}
                    status,saved=call(port,token,'POST',base+'/proposals',body);self.assertEqual(status,200,saved)
                self.assertEqual(call(port,token,'POST',base+'/proposals',{**r,'expected_revision':8})[0],409)
                self.assertEqual(call(port,token,'GET',base+'/proposals/candidate-proposal?revision=1')[0],200)
                self.assertFalse((root/'runtime'/'governance'/'candidates.sqlite').exists());self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

if __name__=='__main__':unittest.main()
