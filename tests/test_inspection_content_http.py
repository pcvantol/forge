"""Actual Forge HTTP decision boundaries; EP modeled here, installed proof separate."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json
import unittest
import test_ep_inspection_adoption_http as r55
from forge.inspection_content_grant import InspectionContentGrant
from forge.inspection_content_contract import BASE, CONTRACT, PROFILE_ID
from forge.project_bootstrap.schema import canonical


def request_for(view, role, operation):
    return {'contract_version':CONTRACT,'profile_id':PROFILE_ID,'instance_id':view['instance_id'],
            'dossier_id':view['dossier_id'],'plan_id':view['plan_id'],'operation_id':operation,
            'subject_digest':view['subject']['subject_digest'],'role':role,'decision':'APPROVE_CONTENT',
            'reason':'SYNTHETIC_TEST_NOT_PETER_APPROVAL: review exact historical content only.',
            'expected_decision_revision':view['decision_revision'],
            'previous_decision_id':view['history'][-1]['decision_id'] if view['history'] else None,
            'acknowledged_review_digest':view['review_digest']}


class InspectionContentHTTPTests(unittest.TestCase):
    setUpSource = r55.InspectionAdoptionHTTPTests.setUp
    stop_peer = r55.InspectionAdoptionHTTPTests.stop_peer
    stop_forge = r55.InspectionAdoptionHTTPTests.stop_forge

    def setUp(self):
        self.setUpSource()
        self.base_snapshot = deepcopy(self.snapshot)
        self.plan = r55.InspectionAdoptionHTTPTests.prepare(self)
        self.content = InspectionContentGrant(self.root/'runtime',self.setup['instance_id'])
        self.content.initialize()
        self.issued_roles = {}
        for name,roles in [('business',['BUSINESS']),('architecture',['ARCHITECTURE']),('reader',[])]:
            self.issued_roles[name] = self.content.issue(principal_id=self.setup['human_principal_id'] if roles else 'observer',
                audience='synthetic-workspace',dossier_id='synthetic-dossier',plan_id=self.plan['plan_id'],
                permissions=['READ','DECIDE'] if roles else ['READ'],roles=roles,source_token_file=self.root/'new.private',
                expires_at=(datetime.now(UTC)+timedelta(minutes=10)).isoformat(),token_path=self.root/(name+'.private'))
        self.target = BASE+'/proposals/'+self.plan['plan_id']+'?dossier_id=synthetic-dossier'

    def call(self,method,path,body=None,token='new',audience='synthetic-workspace',headers=None):
        req = Request('http://127.0.0.1:'+str(self.runtime.server.server_port)+path,method=method,
            data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+(self.root/(token+'.private')).read_text().strip(),
                'X-Forge-Inspection-Content-Audience':audience,'Content-Type':'application/json',**(headers or {})})
        try:
            with urlopen(req,timeout=15) as response:
                status,value = response.status,json.loads(response.read())
        except HTTPError as error:
            try: status,value = error.code,json.loads(error.read())
            finally: error.close()
        if path.startswith(BASE):
            from jsonschema import Draft202012Validator
            from pathlib import Path
            schema=json.loads((Path(__file__).resolve().parents[1]/'forge/api/inspection-adoption-decisions-v1.json').read_text())
            Draft202012Validator(schema).validate(value)
            if body is not None and status==200:Draft202012Validator(schema).validate(body)
        return status,value

    def view(self,token='business'):
        status,view = self.call('GET',self.target,token=token)
        self.assertEqual(status,200,view)
        return view

    def test_two_separate_roles_exact_history_replay_change_and_revoke(self):
        before = self.grant.store.read_bytes()
        view = self.view()
        self.assertEqual(view['blockers'],[])
        self.assertTrue(view['review']['limitations'])  # Unknown roadmap is explicitly optional, still visible.
        business = request_for(view,'BUSINESS','business-original')
        code,partial = self.call('POST',BASE+'/decisions',business,token='business')
        self.assertEqual(code,200,partial)
        self.assertEqual(partial['state'],'DECISION_NEEDED')
        architecture = request_for(partial,'ARCHITECTURE','architecture-original')
        code,full = self.call('POST',BASE+'/decisions',architecture,token='architecture')
        self.assertEqual(code,200,full)
        self.assertEqual(full['state'],'CONTENT_APPROVED_ONLY')
        self.assertFalse(full['effects_authorized'])
        code,replay = self.call('POST',BASE+'/decisions',business,token='business')
        self.assertEqual(code,200,replay)
        self.assertEqual(replay['original_decision'],partial['original_decision'])
        self.assertEqual(len(replay['history']),2)
        decision_target = BASE+'/decisions/'+partial['original_decision']['decision_id']+'?dossier_id=synthetic-dossier'
        self.assertEqual(self.call('GET',decision_target,token='architecture')[1]['original_decision'],partial['original_decision'])
        self.assertEqual(self.call('GET',BASE+'/decisions/unknown?dossier_id=synthetic-dossier',token='business')[0],404)

        self.content.revoke(self.issued_roles['business']['grant_id'])
        current = self.view('architecture')
        self.assertEqual(current['state'],'DECISION_NEEDED')
        self.assertFalse(current['role_status']['BUSINESS']['currently_applicable'])
        self.assertEqual(len(current['history']),2)
        self.assertEqual(self.grant.store.read_bytes(),before)
        self.assertTrue(all(method=='GET' for method,_ in self.requests))

    def test_purpose_scope_roles_exact_subject_and_cas(self):
        view = self.view(); request = request_for(view,'BUSINESS','intent')
        for token in ('new','prepare','admin','reader','architecture'):
            self.assertIn(self.call('POST',BASE+'/decisions',request,token=token)[0],(401,403))
        for key,value,expected in [('subject_digest','f'*64,409),('dossier_id','foreign',403),('plan_id','foreign',403),('instance_id','foreign',409),('acknowledged_review_digest','f'*64,409),('actor','invented',400)]:
            self.assertEqual(self.call('POST',BASE+'/decisions',{**request,key:value},token='business')[0],expected)
        self.assertEqual(self.call('POST',BASE+'/decisions',request,token='business',headers={'X-Role':'BUSINESS'})[0],400)
        self.assertEqual(self.call('GET',self.target,token='business',audience='other')[0],403)
        code,first = self.call('POST',BASE+'/decisions',request,token='business');self.assertEqual(code,200,first)
        self.assertEqual(self.call('POST',BASE+'/decisions',{**request,'reason':'Different immutable bytes'},token='business')[0],409)
        self.assertEqual(self.call('POST',BASE+'/decisions',{**request,'operation_id':'stale'},token='business')[0],409)
        change = request_for(first,'ARCHITECTURE','request-changes');change.update(decision='REQUEST_CHANGES',reason='Clarify the audience.')
        code,changed = self.call('POST',BASE+'/decisions',change,token='architecture');self.assertEqual(code,200,changed)
        self.assertEqual(changed['state'],'CHANGES_REQUESTED')
        self.assertEqual(self.call('GET','/v1/onboarding/capability',token='business')[0],403)

    def test_identical_race_and_distinct_role_cas(self):
        r = request_for(self.view(),'BUSINESS','same-race')
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.call('POST',BASE+'/decisions',r,token='business'),range(2)))
        self.assertEqual([s for s,_ in replies],[200,200],replies)
        self.assertEqual(replies[0][1]['original_decision'],replies[1][1]['original_decision'])
        view = self.view()
        requests = [(request_for(view,role,'race-'+role.lower()),token) for role,token in [('BUSINESS','business'),('ARCHITECTURE','architecture')]]
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda item:self.call('POST',BASE+'/decisions',item[0],token=item[1]),requests))
        self.assertEqual(sorted(s for s,_ in replies),[200,409],replies)
        self.assertEqual(len(self.content._store()['records']),2)

    def test_original_readback_missing_corrupt_store_and_source_loss(self):
        r = request_for(self.view(),'BUSINESS','original')
        status,first = self.call('POST',BASE+'/decisions',r,token='business');self.assertEqual(status,200,first)
        target = BASE+'/intents/original?dossier_id=synthetic-dossier'
        self.assertEqual(self.call('GET',target,token='business')[1]['original_decision'],first['original_decision'])
        for path in [self.content.store,self.content.witness,self.grant.store,self.grant.witness]:
            original = path.read_bytes()
            try:
                for mode in ('missing','corrupt'):
                    if mode == 'missing':path.unlink()
                    else:path.write_bytes(b'broken')
                    code,value = self.call('GET',target,token='business')
                    self.assertNotEqual(code,200,value)
                    self.assertNotIn('history',value)
                    path.write_bytes(original)
            finally:path.write_bytes(original)
        self.peer_status = 403
        code,value = self.call('GET',target,token='business');self.assertNotEqual(code,200,value)
        self.assertNotIn('history',value)
        self.peer_status = 200
        self.grant.revoke(self.issued['grant_id'])
        self.assertNotEqual(self.call('GET',target,token='business')[0],200)

    def test_cli_private_owner_setup_current_read_decide_intent_and_decision_parity(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from forge.inspection_content_cli import main
        def cli(*args):
            output=StringIO()
            with redirect_stdout(output):code=main(['--data-root',str(self.root/'runtime'),*map(str,args)])
            return code,json.loads(output.getvalue()) if output.getvalue() else None
        self.assertEqual(cli('init')[0],0)
        common=['--token-file',self.root/'business.private','--audience','synthetic-workspace']
        code,cap=cli('capability',*common);self.assertEqual(code,0);self.assertEqual(cap['roles'],['BUSINESS'])
        code,view=cli('read',*common,'--plan-id',self.plan['plan_id'],'--dossier-id','synthetic-dossier');self.assertEqual(code,0)
        request=request_for(view,'BUSINESS','cli-original')
        path=self.root/'decision-request.private';path.write_bytes(canonical(request));path.chmod(0o600)
        code,original=cli('decide',*common,'--request-file',path);self.assertEqual(code,0,original)
        for action,key,value in [('intent','--operation-id','cli-original'),('decision','--decision-id',original['original_decision']['decision_id'])]:
            code,readback=cli(action,*common,key,value,'--dossier-id','synthetic-dossier')
            self.assertEqual(code,0,readback);self.assertEqual(readback['original_decision'],original['original_decision'])
        self.assertEqual(cli('issue','--principal-id','observer','--plan-id',self.plan['plan_id'],'--dossier-id','synthetic-dossier','--source-token-file',self.root/'new.private','--audience','synthetic-workspace','--permission','READ','--expires-at',(datetime.now(UTC)+timedelta(minutes=1)).isoformat(),'--token-file',self.root/'cli-reader.private')[0],0)
        self.assertEqual(cli('revoke','--grant-id',self.issued_roles['business']['grant_id'])[0],0)
        self.assertEqual(cli('read',*common,'--plan-id',self.plan['plan_id'],'--dossier-id','synthetic-dossier')[0],1)
        self.assertEqual(cli('revoke','--grant-id','missing')[0],1)

    def test_actual_expiry_old_r54_purpose_and_canonical_human_revoke(self):
        import time
        from forge.proposal_content_grant import ProposalContentGrant
        old=ProposalContentGrant(self.root/'runtime',self.setup['instance_id']);old.initialize()
        old.issue(principal_id=self.setup['human_principal_id'],audience='synthetic-workspace',proposal_principal_id='synthetic-service',dossier_ids=['synthetic-dossier'],permissions=['READ','DECIDE'],roles=['BUSINESS'],expires_at=(datetime.now(UTC)+timedelta(minutes=1)).isoformat(),token_path=self.root/'r54.private')
        self.assertEqual(self.call('GET',self.target,token='r54')[0],403)
        self.content.issue(principal_id='short-reader',audience='synthetic-workspace',dossier_id='synthetic-dossier',plan_id=self.plan['plan_id'],permissions=['READ'],roles=[],source_token_file=self.root/'new.private',expires_at=(datetime.now(UTC)+timedelta(seconds=10)).isoformat(),token_path=self.root/'short.private')
        self.assertEqual(self.call('GET',self.target,token='short')[0],200)
        time.sleep(10.05)
        self.assertIn(self.call('GET',self.target,token='short')[0],(401,403))
        from forge.runtime.bootstrap import RuntimeBootstrap
        from forge.operator_identity import InstallationOperatorService, MacOSGeneratedUIDIdentityAdapter
        with RuntimeBootstrap(data_root=self.root/'runtime',forge_version='synthetic-test').open() as db:
            owner=InstallationOperatorService(db,MacOSGeneratedUIDIdentityAdapter().resolve)
            owner.revoke(owner.context())
        self.assertIn(self.call('GET',self.target,token='business')[0],(401,403))

    def test_source_wait_holds_no_authority_lock_and_late_revoke_denies_private_bytes(self):
        self.block=True
        with ThreadPoolExecutor(max_workers=1) as pool:
            response=pool.submit(self.call,'GET',self.target,token='business')
            self.assertTrue(self.entered.wait(3))
            try:self.content.revoke(self.issued_roles['business']['grant_id'])
            finally:self.release.set()
            code,out=response.result(15)
        self.assertNotEqual(code,200,out)
        self.assertNotIn('review',out)
        self.assertNotIn('history',out)

    def test_commit_then_revoke_before_publication_denies_original_response(self):
        from unittest.mock import patch
        from forge.inspection_content_service import InspectionContentService
        original=InspectionContentService.submit
        def revoke_after(service,*args):
            response=original(service,*args)
            self.content.revoke(self.issued_roles['business']['grant_id'])
            return response
        r=request_for(self.view(),'BUSINESS','late-commit')
        with patch.object(InspectionContentService,'submit',revoke_after):
            code,out=self.call('POST',BASE+'/decisions',r,token='business')
        self.assertNotEqual(code,200,out)
        self.assertNotIn('original_decision',out)
        self.assertEqual(len(self.content._store()['records']),1)
        view=self.view('architecture')
        self.assertEqual(view['state'],'DECISION_NEEDED')
        self.assertEqual(len(view['history']),1)

    def test_precommit_peer_denial_retains_pending_intent_and_exact_recovery(self):
        from forge.inspection_content_service import InspectionContentService
        r=request_for(self.view(),'BUSINESS','pending-original')
        self.peer_status=403
        code,out=self.call('POST',BASE+'/decisions',r,token='business')
        self.assertNotEqual(code,200,out)
        store=self.content._store()
        self.assertEqual(len(store['records']),0)
        self.assertEqual(len(store['dossiers']),1)
        self.peer_status=200
        target=BASE+'/intents/pending-original?dossier_id=synthetic-dossier'
        code,view=self.call('GET',target,token='business')
        self.assertEqual(code,200,view);self.assertEqual(view['intent_state'],'PENDING')
        code,committed=self.call('POST',BASE+'/decisions',r,token='business')
        self.assertEqual(code,200,committed);self.assertEqual(committed['intent_state'],'COMMITTED')
        self.assertEqual(len(committed['history']),1)

    def variant(self, name, *, roadmap=None, vision_missing=False):
        from hashlib import sha256
        from forge.ep_inspection_contract import CONTRACT as SOURCE_CONTRACT
        changed = deepcopy(self.base_snapshot)
        changed['operation_id'] = 'inspection-'+name
        if roadmap is not None:
            changed['observation']['selection'].append('docs/roadmap/ROADMAP.md')
            content = None if roadmap == 'metadata' else 'x'*17000
            changed['observation']['documents'].append({'path':'docs/roadmap/ROADMAP.md','state':'PRESENT','content':content,'sha256':sha256(('known unavailable' if content is None else content).encode()).hexdigest()})
        if vision_missing:
            changed['observation']['documents'][0]['content'] = None
        self.snapshot = changed
        pair = deepcopy(self.pair);pair['pairing_id'] = 'pair-'+name
        pair['snapshot_digest'] = sha256(canonical(changed)).hexdigest()
        pair['binding']['operation_id'] = changed['operation_id']
        pair['binding']['paths'] = changed['observation']['selection']
        if roadmap == 'oversize':pair['binding']['content_paths'].append('docs/roadmap/ROADMAP.md')
        self.grant.bind(pair,self.root/'ep.private')
        self.grant.issue(principal_id='synthetic-service',audience='synthetic-workspace',dossier_ids=['synthetic-dossier'],permissions=['READ','PREPARE'],pairing_id=pair['pairing_id'],maximum_records=4,expires_at=(datetime.now(UTC)+timedelta(minutes=10)).isoformat(),token_path=self.root/(name+'-source.private'))
        body = deepcopy(self.body);body.update(operation_id=name,pairing_id=pair['pairing_id'])
        code,plan = self.call('POST','/v1/inspection-adoptions/plans',body,token=name+'-source');self.assertEqual(code,200,plan)
        self.content.issue(principal_id=self.setup['human_principal_id'],audience='synthetic-workspace',dossier_id='synthetic-dossier',plan_id=plan['plan_id'],permissions=['READ','DECIDE'],roles=['BUSINESS'],source_token_file=self.root/(name+'-source.private'),expires_at=(datetime.now(UTC)+timedelta(minutes=10)).isoformat(),token_path=self.root/(name+'.private'))
        code,view = self.call('GET',BASE+'/proposals/'+plan['plan_id']+'?dossier_id=synthetic-dossier',token=name)
        self.assertEqual(code,200,view)
        return view

    def test_metadata_only_and_overlimit_roadmap_cannot_be_content_approved(self):
        for name in ('metadata','oversize'):
            with self.subTest(name=name):
                view = self.variant(name,roadmap=name)
                request = request_for(view,'BUSINESS','reject-'+name)
                code,out = self.call('POST',BASE+'/decisions',request,token=name)
                self.assertEqual(code,409,out)
                self.assertEqual(out['error']['code'],'INSPECTION_CONTENT_BLOCKED')

    def test_unknown_relevant_vision_blocks_and_new_subject_has_no_history(self):
        original = self.view();r = request_for(original,'BUSINESS','old-original')
        code,first = self.call('POST',BASE+'/decisions',r,token='business');self.assertEqual(code,200,first)
        saved_snapshot = deepcopy(self.snapshot)
        new = self.variant('missing-vision',vision_missing=True)
        self.assertNotEqual(new['subject']['subject_digest'],original['subject']['subject_digest'])
        self.assertEqual(new['history'],[])
        self.assertTrue(new['blockers'])
        self.assertEqual(self.call('POST',BASE+'/decisions',request_for(new,'BUSINESS','deny-missing'),token='missing-vision')[0],409)
        self.snapshot = saved_snapshot
        self.assertEqual(self.view()['history'][0]['decision_id'],first['original_decision']['decision_id'])

    def test_positive_cannot_bypass_source_blockers_and_new_subject_gets_no_history(self):
        # New actual owning preview with explicit missing source bytes. Never mutate a prior approved proposal.
        self.snapshot['observation']['documents'][0]['content'] = None
        self.assertNotEqual(self.call('GET',self.target,token='business')[0],200)  # Whole snapshot changed.


if __name__ == '__main__':unittest.main()
