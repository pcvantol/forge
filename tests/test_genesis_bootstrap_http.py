"""Actual owning HTTP/CAS/source/grant tests; no target or execution service."""
import json
import time
import unittest
from copy import deepcopy
from datetime import UTC,datetime,timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import tests.test_proposal_content_http as content_tests
wire=content_tests.wire
from forge.genesis_bootstrap_grant import GenesisBootstrapGrant
from forge.genesis_bootstrap_service import GenesisBootstrapService
from forge.genesis_bootstrap_contract import CONTRACT,EFFECT_PURPOSE,EFFECTS

BASE='/v1/genesis-bootstrap'


class GenesisBootstrapHttpTest(unittest.TestCase):
    def setUp(self):
        self.owner=content_tests.ProposalContentHttpTest(); self.addCleanup(self.owner.doCleanups); self.owner.setUp()
        self.root=self.owner.root;self.setup=self.owner.setup;self.expiry=self.owner.expiry
        self.source,self.content=self.owner.prepare()
        self.grant=GenesisBootstrapGrant(self.root/'runtime',self.setup['instance_id']);self.grant.initialize()
        self.reader=self.issue('bootstrap','synthetic-service',['READ','PREPARE'])

    def issue(self,name,principal,permissions,plans=None,**extra):
        return self.grant.issue(principal_id=principal,audience='synthetic-workspace',proposal_principal_id='synthetic-service',dossier_ids=['synthetic-dossier'],source_plan_ids=[self.source['plan_id']],permissions=permissions,exact_plans=plans or [],expires_at=self.expiry,token_path=self.root/(name+'.private'),**extra)

    def call(self,method,path,body=None,token='bootstrap',**kwargs):
        answer=self.owner.call(method,path,body,token=token,**kwargs)
        if path.startswith(BASE):
            from jsonschema import Draft202012Validator
            schema=json.loads((content_tests.ROOT/'forge/api/genesis-bootstrap-v1.json').read_text())
            Draft202012Validator(schema).validate(answer[1])
            if body is not None and answer[0]==200:
                Draft202012Validator(schema).validate(body)
        return answer

    def approve_content(self):
        for role in ('BUSINESS','ARCHITECTURE'):
            status,self.content=self.owner.call('POST','/v1/project-proposal-decisions/decisions',wire.request_for(self.content,role,'content-'+role.lower()),token=role.lower())
            self.assertEqual(status,200,self.content)

    def request(self,**extra):
        return {'contract_version':CONTRACT,'instance_id':self.setup['instance_id'],'dossier_id':'synthetic-dossier','operation_id':'plan-original','source_plan_id':self.source['plan_id'],'source_subject':self.content['subject'],'expected_content_revision':self.content['decision_revision'],'target':{'ep_instance_id':'ep-test','placement_ref':'placement-test','target_ref':'new-test'},'effects':list(EFFECTS),'expires_at':self.expiry,'expected_plan_revision':0,'previous_plan_id':None,'blocking_open_points':[],**extra}

    def prepare(self,**extra):
        request=self.request(**extra);status,view=self.call('POST',BASE+'/plans',request);self.assertEqual(status,200,view)
        return request,view

    def effect(self,view,**extra):
        plan=view['plan']
        return {'contract_version':CONTRACT,'instance_id':self.setup['instance_id'],'dossier_id':'synthetic-dossier','operation_id':'effect-original','plan_id':plan['plan_id'],'plan_digest':plan['plan_digest'],'purpose':EFFECT_PURPOSE,'decision':'APPROVE_EFFECT','reason':'Synthetic technical confirmation of exact planned effects only.','expected_decision_revision':view['effect_decision_revision'],'previous_decision_id':view['effect_history'][-1]['decision_id'] if view['effect_history'] else None,**extra}

    def effect_grant(self,view,name='effect'):
        return self.issue(name,self.setup['human_principal_id'],['READ','DECIDE_EFFECT'],[{'plan_id':view['plan']['plan_id'],'plan_digest':view['plan']['plan_digest']}])

    def test_complete_exact_bytes_content_roles_distinct_effect_and_cli_private_readback(self):
        self.approve_content();before=(self.root/'runtime/onboarding/proposals/store.json').read_bytes()
        r,view=self.prepare();self.assertTrue(view['effect_decision_eligible']);self.effect_grant(view)
        status,done=self.call('POST',BASE+'/decisions',self.effect(view),token='effect');self.assertEqual(status,200,done)
        self.assertTrue(done['effect_decision_currently_applicable']);self.assertFalse(done['execution_authorized'])
        self.assertEqual(done['plan']['state'],'EP_ADMISSION_REQUIRED');self.assertEqual(done['plan']['identity_state'],'PROPOSED_NOT_RESERVED')
        self.assertEqual([{k:f[k] for k in ('path','mode','sha256','content')} for f in view['plan']['documents']['files']],self.source['result']['artifacts'])
        self.assertEqual((self.root/'runtime/onboarding/proposals/store.json').read_bytes(),before)
        for leaf,ref in [('plans',view['plan']['plan_id']),('intents',r['operation_id']),('decisions',done['original_decision']['decision_id']),('decision-intents','effect-original')]:
            status,read=self.call('GET',BASE+'/'+leaf+'/'+ref+'?dossier_id=synthetic-dossier',token='effect' if leaf=='decision-intents' else 'bootstrap');self.assertEqual(status,200,read);self.assertEqual(read['plan'],view['plan'])
        auth='Bearer '+(self.root/'bootstrap.private').read_text().strip()
        with self.grant.publication(auth,'synthetic-workspace',self.call('GET',BASE+'/plans/'+view['plan']['plan_id']+'?dossier_id=synthetic-dossier')[1]):pass
        self.assertEqual(self.call('GET',BASE+'/capability')[0],200)

    def test_preview_missing_content_role_then_current_content_change_invalidates_frozen_plan(self):
        _,view=self.prepare();self.assertFalse(view['effect_decision_eligible']);self.effect_grant(view)
        self.assertEqual(self.call('POST',BASE+'/decisions',self.effect(view),token='effect')[0],409)
        self.approve_content()
        status,old=self.call('GET',BASE+'/plans/'+view['plan']['plan_id']+'?dossier_id=synthetic-dossier');self.assertEqual(status,200,old)
        self.assertIn('SOURCE_CONTENT_CHANGED',old['inapplicability_reasons'])
        _,new=self.prepare(operation_id='new-content-plan',expected_plan_revision=1,previous_plan_id=view['plan']['plan_id'])
        self.assertTrue(new['effect_decision_eligible']);self.assertEqual(new['effect_history'],[])
        self.assertEqual(self.call('POST',BASE+'/decisions',self.effect(new),token='effect')[0],403)
        self.assertIn('PLAN_SUPERSEDED',self.call('GET',BASE+'/plans/'+view['plan']['plan_id']+'?dossier_id=synthetic-dossier')[1]['inapplicability_reasons'])

    def test_required_open_questions_block_effect_but_original_future_questions_remain(self):
        self.approve_content();points=self.source['input']['product']['open_questions'] if 'input' in self.source else self.owner.source['product']['open_questions']
        self.assertTrue(points)
        _,view=self.prepare(blocking_open_points=[points[0]])
        self.assertEqual(view['plan']['open_questions'],points);self.assertFalse(view['effect_decision_eligible'])
        self.effect_grant(view);self.assertEqual(self.call('POST',BASE+'/decisions',self.effect(view),token='effect')[0],409)
        status,changed=self.call('POST',BASE+'/decisions',self.effect(view,decision='REQUEST_CHANGES'),token='effect')
        self.assertEqual(status,200,changed);self.assertFalse(changed['effect_decision_currently_applicable'])

    def test_concurrent_identical_and_changed_operation_conflicts_commit_once(self):
        self.approve_content();request=self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:answers=list(pool.map(lambda _:self.call('POST',BASE+'/plans',request),range(2)))
        self.assertEqual([x[0] for x in answers],[200,200]);self.assertEqual(answers[0][1],answers[1][1]);view=answers[0][1]
        self.assertEqual(self.call('POST',BASE+'/plans',{**request,'blocking_open_points':['not originally supplied']})[0],409)
        self.effect_grant(view);d=self.effect(view)
        with ThreadPoolExecutor(max_workers=2) as pool:answers=list(pool.map(lambda _:self.call('POST',BASE+'/decisions',d,token='effect'),range(2)))
        self.assertEqual([x[0] for x in answers],[200,200]);self.assertEqual(answers[0][1],answers[1][1])
        self.assertEqual(self.call('POST',BASE+'/decisions',{**d,'reason':'Different reason same operation.'},token='effect')[0],409)
        self.assertEqual(self.call('POST',BASE+'/decisions',{**d,'operation_id':'stale'},token='effect')[0],409)
        self.assertEqual(len(self.grant._store()['records']),2)

    def test_closed_contract_scopes_headers_target_and_exact_effects(self):
        self.approve_content();r,view=self.prepare();self.effect_grant(view)
        for token in ('prepare','both','admin'):
            self.assertEqual(self.call('GET',BASE+'/capability',token=token)[0],403)
        self.assertEqual(self.call('POST',BASE+'/decisions',self.effect(view))[0],403)
        for key,value,expected in [('instance_id','foreign',403),('dossier_id','foreign',403),('target',{'ep_instance_id':'ep','placement_ref':'/tmp/not-opaque','target_ref':'x'},400),('effects',['WRITE_ANYTHING'],400),('actor','owner',400)]:
            status,out=self.call('POST',BASE+'/plans',{**r,'operation_id':'bad-'+key,key:value});self.assertEqual(status,expected,out)
        for field,value in [('plan_digest','f'*64),('purpose','CONTENT_BASELINE_ONLY/1.0'),('actor','forged')]:
            self.assertIn(self.call('POST',BASE+'/decisions',{**self.effect(view),field:value},token='effect')[0],(400,403,409))
        self.assertEqual(self.call('GET',BASE+'/capability',headers={'X-Actor':'forged'})[0],400)
        self.assertEqual(self.call('GET',BASE+'/capability',headers={'X-Role':'owner'})[0],400)
        self.assertEqual(self.call('GET',BASE+'/capability',audience='foreign')[0],403)
        self.assertEqual(self.call('GET','/v1/onboarding/capability')[0],403)
        for path in ('/unknown','/capability?unknown=yes','/plans/nope?dossier_id=synthetic-dossier','/plans/%2e?dossier_id=synthetic-dossier'):
            self.assertIn(self.call('GET',BASE+path)[0],(400,404))

    def test_grant_revoke_content_revoke_real_expiry_history_remains(self):
        self.approve_content();_,view=self.prepare();issued=self.effect_grant(view)
        status,done=self.call('POST',BASE+'/decisions',self.effect(view),token='effect');self.assertEqual(status,200,done)
        self.grant.revoke(issued['grant_id'])
        self.assertIn(self.call('GET',BASE+'/capability',token='effect')[0],(401,403))
        path=BASE+'/plans/'+view['plan']['plan_id']+'?dossier_id=synthetic-dossier'
        status,read=self.call('GET',path);self.assertEqual(status,200,read);self.assertFalse(read['effect_decision_currently_applicable']);self.assertEqual(read['effect_history'],done['effect_history'])
        self.owner.grant.revoke(self.owner.grants['business']['grant_id'])
        status,read=self.call('GET',path);self.assertEqual(status,200,read);self.assertFalse(read['effect_decision_eligible'])
        expiry=(datetime.now(UTC)+timedelta(seconds=1)).isoformat()
        old=self.expiry;self.expiry=expiry;self.issue('short','synthetic-service',['READ']);self.expiry=old
        deadline=time.monotonic()+2
        while datetime.now(UTC)<datetime.fromisoformat(expiry):
            self.assertLess(time.monotonic(),deadline);time.sleep(.02)
        self.assertIn(self.call('GET',BASE+'/capability',token='short')[0],(401,403))

    def test_source_own_storage_loss_and_corrupt_records_fail_closed_restoration_original(self):
        self.approve_content();_,view=self.prepare();path=BASE+'/plans/'+view['plan']['plan_id']+'?dossier_id=synthetic-dossier'
        for file in (self.grant.store,self.grant.witness,self.root/'runtime/onboarding/proposals/store.json',self.owner.grant.store):
            original=file.read_bytes()
            for missing in (True,False):
                if missing:file.unlink()
                else:file.write_bytes(b'{"corrupt":true}');file.chmod(0o600)
                self.assertNotIn(self.call('GET',path)[0],(200,404))
                file.write_bytes(original);file.chmod(0o600)
                self.assertEqual(self.call('GET',path)[0],200)
        store=self.grant._store();original=self.grant.store.read_bytes();store['records'][view['plan']['plan_id']]['document']['target']['target_ref']='tampered';self.grant.save_store(store)
        self.assertEqual(self.call('GET',BASE+'/capability')[0],503)
        self.grant.store.write_bytes(original);self.grant.store.chmod(0o600)
        self.assertEqual(self.call('GET',path)[1]['plan'],view['plan'])

    def test_revoke_or_new_decision_between_commit_and_publication_denies_late_body(self):
        self.approve_content();_,view=self.prepare();issued=self.effect_grant(view);original=GenesisBootstrapService.decide
        def revoke_after(service,*args):
            result=original(service,*args);self.grant.revoke(issued['grant_id']);return result
        with patch.object(GenesisBootstrapService,'decide',revoke_after):
            status,body=self.call('POST',BASE+'/decisions',self.effect(view),token='effect');self.assertNotEqual(status,200);self.assertNotIn('plan',body)
        self.assertEqual(len(self.grant._store()['records']),2)

    def test_cli_late_publication_failure_does_not_append_second_json(self):
        import io
        from forge.genesis_bootstrap_cli import main
        def interrupted(grant,auth,audience,document):
            print('{"partial":',end='');raise PermissionError('revoked after first chunk')
        output=io.StringIO()
        with patch('forge.genesis_bootstrap_cli.publish_cli',side_effect=interrupted),patch('sys.stdout',output):
            result=main(['--data-root',str(self.root/'runtime'),'capability','--token-file',str(self.root/'bootstrap.private'),'--audience','synthetic-workspace'])
        self.assertEqual(result,1);self.assertEqual(output.getvalue(),'{"partial":')
