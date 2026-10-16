"""Real Forge HTTP with synthetic peer responses; not installed EP qualification."""
from copy import deepcopy
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
import unittest
from unittest.mock import patch
import tests.test_genesis_bootstrap_http as bootstrap_tests
from forge.ep_inspection_peer import PeerError
from forge.genesis_apply_contract import CONTRACT, ep_request
from forge.genesis_apply_grant import GenesisApplyGrant
from forge.genesis_apply_pairing import GenesisApplyPairings
from forge.genesis_apply_service import GenesisApplyService, BASE
from forge.project_bootstrap.schema import canonical, load_json
from forge.project_bootstrap.service import digest


def response_for(pairing, ep, plan, state='COMPLETE'):
    schema = load_json(files('forge').joinpath('api/ep-genesis-local-bootstrap-v1.schema.json').read_bytes())['oneOf'][0]
    now = datetime.now(UTC).isoformat()
    return {'contract_version':'1.0', 'operation_kind':'CREATE_GENESIS_LOCAL', 'operation_id':ep['operation_id'],
        'producer_version':'2.3.123', 'execution_mode':'GENESIS', 'baseline':'portable-docs/1.0.0',
        'authorization_ref':pairing['ep_grant_id'], 'placement_precondition':'ABSENT_VERIFIED_AT_ADMISSION',
        'request_digest':digest(canonical(ep)), 'target_ref':ep['target_ref'], 'state':state,
        'effect_plan_binding':ep['effect_plan_binding'], 'bundle_digest':digest(canonical(ep['bundle'])),
        'manifest_digest':plan['documents']['manifest_digest'], 'input_digest':pairing['input_digest'],
        'instance_id':pairing['binding']['instance_id'], 'host_id':pairing['binding']['host_id'],
        'identity':{**plan['documents']['identity'], 'state':'REGISTERED' if state == 'COMPLETE' else 'RESERVED'},
        'completed_steps':schema['properties']['completed_steps']['items']['enum'] if state == 'COMPLETE' else [],
        'commit':'a'*40 if state == 'COMPLETE' else None, 'tree':'b'*40 if state == 'COMPLETE' else None,
        'step_effects':[], 'validator_sha256':plan['documents']['validation']['validator_sha256'] if state == 'COMPLETE' else None,
        'validation':{'state':'VALIDATED_PROPOSAL', 'manifest_digest':plan['documents']['manifest_digest'],
                      'product_code_coverage':'NOT_APPLICABLE_NO_PRODUCT_CODE','artifacts':37} if state == 'COMPLETE' else None,
        'last_error':None, 'source_updated_at':now, 'observed_at':now, 'forge_readiness':'NOT_OWNED_BY_EP',
        'remote_governance':'NOT_APPLICABLE_GENESIS', 'product_code_coverage':'NOT_APPLICABLE_NO_PRODUCT_CODE',
        'in_repository_validation_command':'NOT_QUALIFIED_AFTER_GIT_METADATA',
        'effect_result_semantics':'ORIGINAL_OPERATION_AS_OF_RECORDED_STEP_EVIDENCE'}


class GenesisApplyHttpTests(unittest.TestCase):
    def setUp(self):
        self.owner = bootstrap_tests.GenesisBootstrapHttpTest(); self.addCleanup(self.owner.doCleanups); self.owner.setUp()
        self.owner.approve_content(); _, view = self.owner.prepare(); self.owner.effect_grant(view)
        status, self.view = self.owner.call('POST', bootstrap_tests.BASE+'/decisions', self.owner.effect(view), token='effect')
        self.assertEqual(status, 200, self.view)
        self.grant = GenesisApplyGrant(self.owner.root/'runtime', self.owner.setup['instance_id']); self.grant.initialize()
        plan = self.view['plan']; decision = self.view['original_decision']
        self.request = dict(contract_version=CONTRACT, instance_id=plan['instance_id'], dossier_id=plan['dossier_id'],
                            operation_id='original-apply', plan_id=plan['plan_id'], plan_digest=plan['plan_digest'],
                            decision_id=decision['decision_id'], decision_digest=decision['decision_digest'], pairing_id='owner-pair')
        from forge.genesis_bootstrap_service import GenesisBootstrapService
        with self.owner.grant.boundary():
            source_principal = self.owner.grant.authorize("Bearer "+(self.owner.root/"bootstrap.private").read_text().strip())
            original, _, _ = GenesisBootstrapService(self.owner.grant).source(source_principal, plan["dossier_id"], plan["source_subject"]["plan_id"])
        self.ep, _ = ep_request(original, plan, decision, self.request['operation_id'])
        pins = {'producer_revision':'a'*40, 'producer_tree':'b'*40, 'producer_schema_sha256':digest(files('forge').joinpath('api/ep-genesis-local-bootstrap-v1.schema.json').read_bytes()), 'producer_version':'2.3.123'}
        self.pin = patch('forge.genesis_apply_peer.QUALIFIED_PRODUCER', pins); self.pin.start(); self.addCleanup(self.pin.stop)
        self.pairing = {**pins, 'pairing_id':'owner-pair', 'endpoint':'http://127.0.0.1:12345',
            'binding':{'instance_id':'ep-test','host_id':'c'*64,'consumer_id':'forge-test','principal':'test-owner','operation_id':'original-apply'},
            'ep_grant_id':'separate-ep-grant', 'expires_at':self.owner.expiry,
            **{k:self.request[k] for k in ('plan_id','plan_digest','decision_id','decision_digest')},
            'placement_ref':'placement-test','target_ref':'new-test','request_digest':digest(canonical(self.ep)),
            'input_digest':plan['source_subject']['input_digest']}
        credential = self.owner.root/'separate-ep.private'; credential.write_text('independent-synthetic-ep-token'); credential.chmod(0o600)
        GenesisApplyPairings(self.grant).bind(self.pairing, credential)
        self.issued = self.grant.issue(principal_id=self.owner.setup['human_principal_id'], audience='synthetic-workspace',
            proposal_principal_id='synthetic-service', dossier_ids=['synthetic-dossier'], source_plan_ids=[self.owner.source['plan_id']],
            permissions=['READ','REQUEST_APPLY','RESUME'], exact_plans=[{'plan_id':plan['plan_id'],'plan_digest':plan['plan_digest']}],
            expires_at=self.owner.expiry, token_path=self.owner.root/'apply.private')
        self.reply = response_for(self.pairing, self.ep, plan)
        self.peer_original = None; self.posts = 0; self.fail_get = False; self.lose_post = False
        self.revoke_before_send = False; self.deny_publication = False
        self.peer_patch = patch('forge.genesis_apply_service.exchange', side_effect=self.exchange)
        self.peer_patch.start(); self.addCleanup(self.peer_patch.stop)

    def exchange(self, pairing, method, *, body=None, resume=False, deadline=None, before_send=None):
        # This explicit test seam never substitutes for installed EP evidence.
        if method == 'POST' and self.revoke_before_send:
            self.grant.revoke(self.issued['grant_id'])
        if before_send is not None:
            import time
            before_send(time.monotonic()+30)
        if method == 'GET':
            if self.deny_publication and self.peer_original is not None: raise PeerError('EP_GENESIS_HTTP_401',424)
            if self.fail_get: raise PeerError('EP_GENESIS_TRANSPORT_UNCERTAIN')
            if self.peer_original is None: raise PeerError('EP_GENESIS_HTTP_404',424)
            return canonical(self.peer_original)
        self.posts += 1; self.peer_original = deepcopy(self.reply)
        if self.lose_post: raise PeerError('EP_GENESIS_TRANSPORT_UNCERTAIN')
        return canonical(self.peer_original)

    def call(self, method='POST', path=None, body=None, token='apply'):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        import json
        from jsonschema import Draft202012Validator
        value = self.request if body is None and method == 'POST' else body
        request = Request('http://127.0.0.1:'+str(self.owner.owner.server.server_port)+(path or BASE+'/operations'),
            method=method, data=canonical(value) if value is not None else None,
            headers={'Authorization':'Bearer '+(self.owner.root/(token+'.private')).read_text().strip(),
                     'X-Forge-Genesis-Apply-Audience':'synthetic-workspace','Content-Type':'application/json'})
        try:
            with urlopen(request,timeout=15) as response: status, answer = response.status,json.loads(response.read())
        except HTTPError as error:
            try: status,answer = error.code,json.loads(error.read())
            finally: error.close()
        if answer.get('contract_version') == CONTRACT:
            schema = load_json(files('forge').joinpath('api/genesis-apply-v1.json').read_bytes())
            Draft202012Validator(schema).validate(answer)
            if status == 200 and value is not None: Draft202012Validator(schema).validate(value)
        return status,answer

    def test_http_original_replay_read_no_second_post_and_cross_purpose_denial(self):
        owning_files=[self.owner.grant.store,self.owner.owner.grant.store,self.owner.grant.root/'onboarding/proposals/store.json']
        owning_before=[path.read_bytes() for path in owning_files]
        status, one = self.call(); self.assertEqual(status,200,one)
        self.assertEqual(one['state'],'COMPLETE'); self.assertEqual(one['project_readiness'],'NOT_ASSESSED')
        status, two = self.call(); self.assertEqual(status,200,two); self.assertEqual(one,two)
        status, read = self.call('GET', BASE+'/operations/original-apply?dossier_id=synthetic-dossier')
        self.assertEqual(status,200,read); self.assertEqual(one,read); self.assertEqual(self.posts,1)
        self.assertEqual(self.call(token='effect')[0],403)
        self.assertEqual(self.call('GET',bootstrap_tests.BASE+'/capability')[0],403)
        self.assertEqual(self.call('GET',BASE+'/operations/original-apply?dossier_id=foreign')[0],403)
        self.assertEqual([path.read_bytes() for path in owning_files],owning_before)

    def test_lost_accepted_reply_recreated_service_recovers_original_no_second_create(self):
        self.lose_post = True
        status, lost = self.call(); self.assertEqual(status,503,lost); self.assertEqual(self.posts,1)
        # Recreated service reads sealed original journal, not any process-local flag.
        service = GenesisApplyService(GenesisApplyGrant(self.grant.root,self.grant.instance_id))
        auth = 'Bearer '+(self.owner.root/'apply.private').read_text().strip()
        answer = service.submit(auth,'synthetic-workspace',self.request)
        self.assertEqual(answer['original_ep_operation'],self.reply); self.assertEqual(self.posts,1)

    def test_transient_failure_after_prepare_before_claim_can_recover_first_send(self):
        self.fail_get = True
        status, lost = self.call(); self.assertEqual(status,503,lost); self.assertEqual(self.posts,0)
        self.assertEqual(GenesisApplyService(self.grant).journal.store()['records']['original-apply']['attempts'],[])
        self.fail_get = False
        status, done = self.call(); self.assertEqual(status,200,done); self.assertEqual(self.posts,1)
        self.assertEqual(len(GenesisApplyService(self.grant).journal.store()['records']),1)

    def test_current_decision_or_local_pairing_revoke_stops_effect_and_disclosure(self):
        GenesisApplyPairings(self.grant).revoke('owner-pair')
        status, refused = self.call(); self.assertEqual(status,403,refused); self.assertEqual(self.posts,0)

    def test_original_applygrant_revoked_cannot_be_replaced_for_effect_resume(self):
        self.reply = response_for(self.pairing,self.ep,self.view['plan'],'PARTIAL')
        status, first = self.call(); self.assertEqual(status,200,first)
        self.grant.revoke(self.issued['grant_id'])
        self.grant.issue(principal_id=self.owner.setup['human_principal_id'], audience='synthetic-workspace',
            proposal_principal_id='synthetic-service', dossier_ids=['synthetic-dossier'],source_plan_ids=[self.owner.source['plan_id']],
            permissions=['READ','RESUME'],exact_plans=[{'plan_id':self.view['plan']['plan_id'],'plan_digest':self.view['plan']['plan_digest']}],
            expires_at=self.owner.expiry,token_path=self.owner.root/'replacement.private')
        request = dict(contract_version=CONTRACT,instance_id=self.grant.instance_id,dossier_id='synthetic-dossier',
                       operation_id='original-apply',attempt_id='explicit-resume',original_request_digest=first['original_request_digest'])
        status, refused = self.call('POST',BASE+'/operations/original-apply/resume',request,token='replacement')
        self.assertEqual(status,403,refused);self.assertEqual(self.posts,1)
        status, historical = self.call('GET',BASE+'/operations/original-apply?dossier_id=synthetic-dossier',token='replacement')
        self.assertEqual(status,200,historical);self.assertEqual(historical['state'],'PARTIAL');self.assertEqual(self.posts,1)

    def test_current_content_and_effect_revoke_and_changed_binding_deny_before_post(self):
        for update in ({'plan_digest':'f'*64},{'decision_digest':'f'*64},{'dossier_id':'foreign'},{'instance_id':'foreign'}):
            status, refused = self.call(body={**self.request,**update})
            self.assertIn(status,(403,409),refused)
        self.assertEqual(self.posts,0)
        self.owner.grant.revoke(next(r['grant_id'] for r in self.owner.grant._records() if 'DECIDE_EFFECT' in r['permissions']))
        status, refused = self.call();self.assertEqual(status,409,refused);self.assertEqual(self.posts,0)

    def test_cli_private_request_original_read_and_late_failure_no_second_json(self):
        import io,json
        from forge.genesis_apply_cli import main
        request_file = self.owner.root/'apply-request.private';request_file.write_bytes(canonical(self.request));request_file.chmod(0o600)
        common = ['--data-root',str(self.grant.root)]
        auth = ['--token-file',str(self.owner.root/'apply.private'),'--audience','synthetic-workspace']
        def cli(args):
            output=io.StringIO()
            with patch('sys.stdout',output): code=main([*common,*args])
            return code,output.getvalue()
        code,raw=cli(['request',*auth,'--request-file',str(request_file)])
        self.assertEqual(code,0,raw);first=json.loads(raw);self.assertEqual(self.posts,1)
        code,raw=cli(['read',*auth,'--operation-id','original-apply','--dossier-id','synthetic-dossier'])
        self.assertEqual(code,0,raw);self.assertEqual(json.loads(raw),first);self.assertEqual(self.posts,1)
        def interrupted(*args,**kwargs):
            print('{"partial":',end='');raise PermissionError('revoked after first chunk')
        with patch('forge.genesis_apply_cli.publish_cli',side_effect=interrupted):
            code,raw=cli(['read',*auth,'--operation-id','original-apply','--dossier-id','synthetic-dossier'])
        self.assertEqual(code,1);self.assertEqual(raw,'{"partial":')

    def test_revoke_during_connect_is_rechecked_before_effect_send(self):
        self.revoke_before_send=True
        status,refused=self.call();self.assertEqual(status,403,refused);self.assertEqual(self.posts,0)
        original=GenesisApplyService(self.grant).journal.store()['records']['original-apply']
        self.assertEqual(len(original['attempts']),1);self.assertIsNone(original['observation'])

    def test_peer_revoke_before_publication_withholds_original_success(self):
        self.deny_publication=True
        status,refused=self.call();self.assertEqual(status,403,refused);self.assertEqual(self.posts,1)
        self.assertNotIn('original_ep_operation',refused)
