"""Exact closed producer receipt checks using synthetic, non-authoritative data."""
from copy import deepcopy
from importlib.resources import files
from unittest import TestCase
from forge.genesis_apply_contract import ep_request
from forge.genesis_apply_peer import receipt
from forge.project_bootstrap.schema import canonical, ContractError
from forge.project_bootstrap.service import digest
from tests.test_genesis_apply_contract import dispatch_fixture
from tests.test_genesis_apply_http import response_for


class GenesisReceiptBindingTests(TestCase):
    def setUp(self):
        original,self.plan,decision=dispatch_fixture()
        self.request,_=ep_request(original,self.plan,decision,'original-operation')
        self.pairing={'producer_schema_sha256':digest(files('forge').joinpath('api/ep-genesis-local-bootstrap-v1.schema.json').read_bytes()),
                      'producer_version':'2.3.123','ep_grant_id':'owner-grant','input_digest':original['result']['input_digest'],
                      'binding':{'instance_id':'synthetic-ep','host_id':'a'*64}}
        self.value=response_for(self.pairing,self.request,self.plan)

    def read(self,value):return receipt(canonical(value),self.pairing,self.request,self.plan['documents'])

    def test_bound_complete_and_partial_remain_technical_original_evidence(self):
        self.assertEqual(self.read(self.value),self.value)
        partial=response_for(self.pairing,self.request,self.plan,'PARTIAL')
        self.assertEqual(self.read(partial),partial)
        self.assertEqual(partial['forge_readiness'],'NOT_OWNED_BY_EP')

    def test_wrong_owning_identity_grant_plan_bundle_or_producer_never_read_as_success(self):
        for field in ('operation_id','request_digest','target_ref','authorization_ref','instance_id','host_id','bundle_digest',
                      'manifest_digest','input_digest','producer_version','effect_plan_binding','identity'):
            value=deepcopy(self.value)
            if field=='effect_plan_binding':value[field]['decision_digest']='f'*64
            elif field=='identity':value[field]['repository_id']='foreign'
            elif field in ('request_digest','host_id','bundle_digest','manifest_digest','input_digest'):value[field]='f'*64
            else:value[field]='foreign'
            with self.subTest(field=field),self.assertRaises(ValueError):self.read(value)

    def test_complete_requires_all_steps_exact_validator_commit_tree_and_registration(self):
        for field in ('completed_steps','commit','tree','identity','validation','validator_sha256'):
            value=deepcopy(self.value)
            if field=='completed_steps':value[field].pop()
            elif field=='identity':value[field]['state']='RESERVED'
            else:value[field]=None
            with self.subTest(field=field),self.assertRaises(ValueError):self.read(value)
        for field in ('validator_sha256','validation'):
            value=deepcopy(self.value)
            if field=='validation':value[field]['manifest_digest']='f'*64
            else:value[field]='f'*64
            with self.subTest(field=field),self.assertRaises(ValueError):self.read(value)

    def test_strict_schema_duplicates_bounds_and_private_fields_are_refused(self):
        for choice in ('unknown','duplicate','exit','time','null','oversize','asset'):
            value=deepcopy(self.value);pair=deepcopy(self.pairing)
            if choice=='unknown':value['private_path']='/private/owner'
            elif choice=='duplicate':value['completed_steps'].append(value['completed_steps'][0])
            elif choice=='exit':value['step_effects']=[dict(attempt_id='a'*32,step='CREATE_TARGET',outcome='STEP_COMPLETED',exit_code=256,private_evidence_ref='genesis-attempt:'+'a'*32)]
            elif choice=='time':value['observed_at']='not-a-time'
            elif choice=='null':value=None
            elif choice=='oversize':value['producer_version']='x'*524288
            else:pair['producer_schema_sha256']='f'*64
            with self.subTest(choice=choice),self.assertRaises((ValueError,TypeError)):
                receipt(canonical(value),pair,self.request,self.plan['documents'])
