"""Real finite selector, canonical approval and independent read-capability boundaries."""
from copy import deepcopy
from datetime import UTC,datetime,timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from forge.approved_worklist import ApprovedWorklistService,CONTRACT,projection,identifier,timestamp
from forge.governed_candidate_intake import GovernedCandidateIntake
from forge.lifecycle import RecommendationLifecycleStore
from forge.server_runtime import existing_instance,ForgeServerRuntime
from forge.workspace_worklist_grant import WorkspaceWorklistGrant,main as grant_main
from tests import test_governed_candidate_intake as candidate_fixture

class ApprovedWorklistTests(unittest.TestCase):
    def setUp(self):
        self.fixture=candidate_fixture.GovernedCandidateIntakeTests()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;self.root=Path(f.runtime.data_root)
        original=f.root/'governance'/'lifecycle.sqlite';f.lifecycle.close()
        source=self.root/'governance'/'candidates.sqlite';source.parent.mkdir();original.rename(source)
        f.lifecycle=RecommendationLifecycleStore(source);self.addCleanup(f.lifecycle.close)
        f.bridge=GovernedCandidateIntake(f.lifecycle,f.runtime,f.bridge.profile)
        preview,planning=f.approved_input();self.preview,self.planning=preview,planning
        self.service=ApprovedWorklistService(f.runtime,f.lifecycle)
        self.expiry=(datetime.now(UTC)+timedelta(hours=1)).isoformat()
        self.definition={'contract_version':CONTRACT,'workset_id':'approved-set','profile_id':'duo',
            'expires_at':self.expiry,'maximum_activations':1,'members':[{
             'candidate_id':f.candidate.id,'subject_revision':f.bridge.decision_ids(f.candidate.id)[0],
             'mission':preview.to_dict(),'planning':planning.to_dict(),'dependencies':[],
             'truth':{},'progression_policy':{}}]}

    def prepare(self):
        self.fixture.approve(self.preview,self.planning)
        value=self.service.propose(self.definition)
        for role,actor in [('business','business_owner'),('architecture','platform_architect')]:
            value=self.service.decide('approved-set',expected_revision=value['revision'],role=role,actor=actor)
        return self.service.control('approved-set',expected_revision=value['revision'],operation='arm')

    def test_scoped_projection_is_read_only_and_never_claims_activation(self):
        value=self.prepare();instance=existing_instance(self.root)
        before=sha256((self.root/'forge.db').read_bytes()).hexdigest()
        read=projection(self.root,instance.instance_id,'approved-set','workspace-actor')
        self.assertEqual(read['activation_support'],'NOT_YET_QUALIFIED')
        self.assertTrue(read['items'][0]['approved']);self.assertIsNone(read['items'][0]['mission_id'])
        self.assertEqual(read['items'][0]['blocking_reasons'],['ACTIVATION_NOT_YET_QUALIFIED'])
        self.assertEqual(before,sha256((self.root/'forge.db').read_bytes()).hexdigest())
        repeated=projection(self.root,instance.instance_id,'approved-set','workspace-actor')
        self.assertEqual(read['snapshot_revision'],repeated['snapshot_revision'])
        self.assertEqual(self.fixture.database._connection.execute("SELECT COUNT(*) FROM mission_state").fetchone()[0],0)
        with self.assertRaises(PermissionError):projection(self.root,'foreign','approved-set','actor')
        with self.assertRaises(PermissionError):projection(self.root,instance.instance_id,'foreign','actor')

    def test_controls_revalidate_and_preserve_consumption(self):
        value=self.prepare()
        for operation in ['hold','unhold','disarm','arm','revoke']:
            value=self.service.control('approved-set',expected_revision=value['revision'],operation=operation)
        self.assertTrue(value['revoked']);self.assertEqual(value['consumed_activations'],0)
        with self.assertRaises(ValueError):self.service.control('approved-set',expected_revision=value['revision'],operation='arm')
        with self.assertRaises(ValueError):self.service.control('approved-set',expected_revision=1,operation='hold')
        with self.assertRaises(ValueError):self.service.control('approved-set',expected_revision=value['revision'],operation='invent')

    def test_proposals_are_exact_and_ordered_not_recommendations(self):
        value=self.service.propose(self.definition)
        self.assertEqual(value,self.service.propose(self.definition))
        with self.assertRaises(ValueError):self.service.propose({**self.definition,'maximum_activations':2})
        bad=deepcopy(self.definition);bad['members'][0]['dependencies']=['unknown']
        with self.assertRaises(ValueError):self.service.propose(bad)
        bad=deepcopy(self.definition);bad['members']*=2
        with self.assertRaises(ValueError):self.service.propose(bad)
        bad=deepcopy(self.definition);bad['members'][0]['subject_revision']='stale'
        with self.assertRaises(ValueError):self.service.propose(bad)
        bad=deepcopy(self.definition);bad['expires_at']='2000-01-01T00:00:00Z'
        with self.assertRaises(ValueError):self.service.propose(bad)
        with self.assertRaises(ValueError):self.service.propose({})
        with self.assertRaises(ValueError):self.service.propose({**self.definition,'maximum_activations':True})
        with self.assertRaises(ValueError):self.service.propose({**self.definition,'members':[]})

    def test_unapproved_and_wrong_roles_cannot_release(self):
        value=self.service.propose(self.definition)
        with self.assertRaises(ValueError):self.service.control('approved-set',expected_revision=1,operation='arm')
        with self.assertRaises(PermissionError):self.service.decide('approved-set',expected_revision=1,role='business',actor='platform_architect')
        with self.assertRaises(ValueError):self.service.decide('approved-set',expected_revision=1,role='invent',actor='business_owner')
        with self.assertRaises(ValueError):self.service.decide('approved-set',expected_revision=0,role='business',actor='business_owner')
        for role,actor in [('business','business_owner'),('architecture','platform_architect')]:
            value=self.service.decide('approved-set',expected_revision=value['revision'],role=role,actor=actor)
            self.assertEqual(value,self.service.decide('approved-set',expected_revision=value['revision'],role=role,actor=actor))
        with self.assertRaises(ValueError):self.service.control('approved-set',expected_revision=value['revision'],operation='arm')
        read=projection(self.root,existing_instance(self.root).instance_id,'approved-set','actor')
        self.assertFalse(read['items'][0]['approved']);self.assertIn('SUBJECT_UNAPPROVED',read['items'][0]['blocking_reasons'])

    def test_two_actors_grants_are_separate_revocable_and_no_mutation_capability(self):
        self.prepare();instance=existing_instance(self.root);grant=WorkspaceWorklistGrant(self.root,instance.instance_id)
        token=self.root/'read-token';r=grant.issue(principal_id='alice',workset_ids=('approved-set',),expires_at=self.expiry,token_path=token)
        auth='Bearer '+token.read_text().strip()
        self.assertEqual(grant.authenticate(auth).principal_id,'alice')
        for value in [None,'Basic x','Bearer ','Bearer wrong','Bearer '+('x'*257),'Bearer bad\n']:
            self.assertIsNone(grant.authenticate(value))
        grant.revoke(r['grant_id']);grant.revoke(r['grant_id']);self.assertIsNone(grant.authenticate(auth))
        with self.assertRaises(ValueError):grant.revoke('missing')
        with self.assertRaises(ValueError):grant.issue(principal_id='bob',workset_ids=(),expires_at=self.expiry,token_path=token)
        with self.assertRaises(ValueError):grant.issue(principal_id='bob',workset_ids=('set','set'),expires_at=self.expiry,token_path=token)
        with self.assertRaises(ValueError):grant.issue(principal_id='bob',workset_ids=('set',),expires_at='2000-01-01T00:00:00Z',token_path=token)
        foreign=WorkspaceWorklistGrant(self.root,'foreign');self.assertIsNone(foreign.authenticate(auth))
        self.assertEqual(grant_main(['--data-root',str(self.root),'issue','--principal-id','bob','--workset-id','approved-set','--expires-at',self.expiry,'--token-file',str(self.root/'bob-token')]),0)
        self.assertEqual(grant_main(['--data-root',str(self.root),'revoke','--grant-id','missing']),1)

    def test_real_http_read_grant_denies_mutation_and_foreign_scopes(self):
        from threading import Thread
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from jsonschema import Draft202012Validator,FormatChecker
        from forge.workspace_review_grant import WorkspaceReviewGrant
        self.prepare();instance=existing_instance(self.root)
        token=self.root/'http-read-token';grant=WorkspaceWorklistGrant(self.root,instance.instance_id)
        record=grant.issue(principal_id='alice',workset_ids=('approved-set',),expires_at=self.expiry,token_path=token)
        admin=self.root/'admin-token';admin.write_text('a'*48);admin.chmod(0o600)
        server=ForgeServerRuntime(data_root=self.root,credential_file=admin,host='127.0.0.1',port=0)
        thread=Thread(target=server.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server.server_close);self.addCleanup(thread.join,3);self.addCleanup(server.server.shutdown)
        endpoint=f'http://127.0.0.1:{server.server.server_address[1]}'
        auth='Bearer '+token.read_text().strip()
        def request(path,method='GET',authorization=auth):
            req=Request(endpoint+path,headers={'Authorization':authorization},method=method)
            try:
                with urlopen(req,timeout=3) as response:return response.status,json.load(response)
            except HTTPError as error:
                with error:return error.code,json.load(error)
        admitted=self.fixture.bridge.admit(self.fixture.candidate.id,self.preview,self.planning,occurred_at='2026-10-07T00:00:00Z')
        review=WorkspaceReviewGrant(self.root,instance.instance_id);review_token=self.root/'review-token'
        review.issue(principal_id='alice',mission_ids=(admitted.mission_id,),expires_at=(datetime.now(UTC)+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),token_path=review_token)
        before=sha256((self.root/'forge.db').read_bytes()).hexdigest()
        code,value=request('/v1/worksets/approved-set');self.assertEqual(code,200)
        schema=json.loads((Path(__file__).parents[1]/'forge/api/workspace-worklist-v1.json').read_text())
        Draft202012Validator(schema,format_checker=FormatChecker()).validate(value)
        self.assertEqual(request('/v1/worksets')[1]['workset_ids'],['approved-set'])
        self.assertEqual(request('/v1/worksets/foreign')[0],403)
        self.assertEqual(request('/v1/worksets/approved-set','POST')[0],403)
        self.assertEqual(request('/v1/worksets/approved-set/hold','POST')[0],403)
        self.assertEqual(request('/v1/missions')[0],403)
        self.assertEqual(request('/v1/status')[0],403)
        self.assertEqual(request('/v1/worksets/approved-set',authorization='Bearer wrong')[0],401)
        self.assertEqual(request('/v1/worksets/approved-set',authorization='Bearer '+review_token.read_text().strip())[0],403)
        self.assertEqual(before,sha256((self.root/'forge.db').read_bytes()).hexdigest())
        grant.revoke(record['grant_id']);self.assertEqual(request('/v1/worksets/approved-set')[0],401)

    def test_explicit_empty_scope_is_idle_without_phantom_allocation(self):
        definition={**self.definition,'workset_id':'empty','members':[],'maximum_activations':0}
        self.service.propose(definition)
        result=projection(self.root,existing_instance(self.root).instance_id,'empty','actor')
        self.assertEqual(result['items'],[])
        self.assertEqual(result['continuation']['state'],'IDLE')
        self.assertIsNone(result['continuation']['candidate_id'])
        self.assertEqual(self.fixture.database._connection.execute('SELECT COUNT(*) FROM mission_id_allocations').fetchone()[0],0)

    def test_identity_and_time_fail_closed(self):
        for value in ['../secret','',None,'x'*129]:
            with self.assertRaises(ValueError):identifier(value)
        for value in [None,'invalid','2026-01-01']:
            with self.assertRaises(ValueError):timestamp(value)

if __name__=='__main__':unittest.main()
