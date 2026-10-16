"""Frozen original R50 bundle fixtures; not EP admission or installed proof."""
from copy import deepcopy
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from forge.genesis_bootstrap_contract import frozen_bundle
from forge.project_bootstrap.service import digest
from forge.project_bootstrap.schema import canonical, ContractError


def original():
    basis=json.loads(Path('examples/project-bootstrap/authority-input.json').read_text())
    bundle=json.loads(Path('examples/project-bootstrap/authority-bundle.json').read_text())
    rows=[{'path':p,'mode':0o644,'sha256':v['sha256'],'content':v['utf8']} for p,v in sorted(bundle['files'].items())]
    return {'proposal_kind':'pb-render/1.0','input':basis,'result':{'input_digest':digest(canonical(basis)),'artifacts':rows}}


class FrozenGenesisBundleTests(TestCase):
    def test_original_bytes_and_mode_are_copied_without_a_second_render(self):
        record=original();before=deepcopy(record)
        with patch('forge.project_bootstrap.service.render',side_effect=AssertionError('no re-render')):
            value=frozen_bundle(record)
        self.assertEqual(record,before)
        self.assertEqual(len(value['files']),37)
        self.assertTrue(all(r['mode']==0o644 and r['expected_before']=='ABSENT' for r in value['files']))
        self.assertEqual(value['validation']['entrypoint'],'bash scripts/validate.sh')
        self.assertEqual(value['validation']['file_mode'],'0644')
        for old,new in zip(record['result']['artifacts'],value['files']):
            self.assertEqual(old['content'],new['content']);self.assertEqual(old['sha256'],new['sha256'])

    def test_changed_original_identity_bytes_or_additional_file_is_not_repaired(self):
        for choice in ('identity','bytes','extra'):
            record=original()
            if choice=='identity':record['input']['identity']['project_id']='other-project'
            elif choice=='bytes':record['result']['artifacts'][0]['content']+='changed'
            else:record['result']['artifacts'].append({'path':'unselected.txt','mode':0o644,'sha256':digest(b'added'),'content':'added'})
            with self.subTest(choice=choice),self.assertRaises(ContractError):frozen_bundle(record)

    def test_adoption_kind_and_managed_profile_are_not_new_target_plans(self):
        for kind in ('adoption','managed'):
            record=original()
            if kind=='adoption':record['proposal_kind']='pb-adoption-preview/1.0'
            else:record['input']['mode']='MANAGED'
            with self.subTest(kind=kind),self.assertRaises(ContractError):frozen_bundle(record)


def plan_fixture():
    from forge.genesis_bootstrap_contract import CONTRACT,EFFECTS,frozen_bundle
    record=original();record['plan_id']='proposal-synthetic-original'
    bundle=frozen_bundle(record)
    subject={'plan_id':record['plan_id'],'proposal_principal_id':'synthetic-source-owner','proposal_kind':'pb-render/1.0',
             'input_digest':record['result']['input_digest'],'result_digest':digest(canonical(record['result']['artifacts'])),
             'record_digest':digest(canonical(record)),'manifest_digest':bundle['manifest_digest'],
             'baseline':'portable-docs/1.0.0','profile_id':'CONTENT_BASELINE_ONLY/1.0',
             'source_references':record['input']['source_references'],'concept_revision':None}
    content={'subject':subject,'decision_revision':0,'history':[]}
    request={'contract_version':CONTRACT,'instance_id':'synthetic-forge','dossier_id':'synthetic-dossier','operation_id':'synthetic-genesis-plan',
             'source_plan_id':record['plan_id'],'source_subject':subject,'expected_content_revision':0,
             'target':{'ep_instance_id':'synthetic-ep','placement_ref':'synthetic-approved-placement','target_ref':'synthetic-new-target'},
             'effects':list(EFFECTS),'expires_at':'2026-10-17T00:00:00+00:00','expected_plan_revision':0,'previous_plan_id':None,'blocking_open_points':[]}
    principal={'principal_id':'synthetic-plan-owner','audience':'synthetic-workspace'}
    return record,content,request,principal


class FrozenGenesisPlanTests(TestCase):
    def test_pre_admission_plan_is_deterministic_original_bytes_no_approval_or_reserved_identity(self):
        from forge.genesis_bootstrap_contract import plan_document
        args=plan_fixture()
        with patch('forge.project_bootstrap.service.render',side_effect=AssertionError('no re-render')):
            one=plan_document(*args);two=plan_document(*args)
        self.assertEqual(one,two)
        self.assertEqual(one['plan_digest'],digest(canonical({k:v for k,v in one.items() if k!='plan_digest'})))
        self.assertEqual(one['state'],'EP_ADMISSION_REQUIRED');self.assertEqual(one['identity_state'],'PROPOSED_NOT_RESERVED')
        self.assertFalse(one['execution_authorized']);self.assertEqual(one['ep_credential'],'NOT_ISSUED')
        self.assertEqual(one['target']['absence_evidence'],'NOT_OBSERVED_BY_FORGE')
        self.assertEqual(one['documents']['bundle_digest'],digest(canonical(args[0]['result']['artifacts'])))

    def test_unknown_command_effect_path_or_source_revision_is_not_accepted(self):
        from forge.genesis_bootstrap_contract import plan_document
        for bad in ('effect','target','command','revision'):
            args=plan_fixture();request=args[2]
            if bad=='effect':request['effects'].append('RUN_USER_COMMAND')
            elif bad=='target':request['target']['target_ref']='/private/user/path'
            elif bad=='command':request['command']='bash anything.sh'
            else:request['expected_content_revision']=1
            with self.subTest(bad=bad),self.assertRaises(ValueError):plan_document(*args)

    def test_target_revision_creates_distinct_frozen_plan_without_inherited_effect_approval(self):
        from forge.genesis_bootstrap_contract import plan_document
        args=plan_fixture();first=plan_document(*args)
        args[2].update(operation_id='synthetic-genesis-plan-next',expected_plan_revision=1,previous_plan_id=first['plan_id'])
        args[2]['target']['target_ref']='synthetic-other-target'
        second=plan_document(*args)
        self.assertNotEqual(first['plan_id'],second['plan_id']);self.assertNotEqual(first['plan_digest'],second['plan_digest'])
        self.assertEqual(second['previous_plan_id'],first['plan_id']);self.assertEqual(second['plan_revision'],2)
        self.assertFalse(second['execution_authorized']);self.assertEqual(second['state'],'EP_ADMISSION_REQUIRED')

class GenesisJoinBindingTests(TestCase):
    def test_ep_envelope_and_original_array_digests_are_distinct_exact_bindings(self):
        record,content,request,principal=plan_fixture()
        bundle=frozen_bundle(record)
        original_envelope=json.loads(Path('examples/project-bootstrap/authority-bundle.json').read_text())
        self.assertEqual(bundle['ep_bundle_binding']['canonical_digest'],digest(canonical(original_envelope)))
        self.assertEqual(bundle['ep_bundle_binding']['canonical_digest'],'0c2c0fb41a68793be0960bb4289d7590060c8092ebb976852e1c4674b0f66b1d')
        self.assertNotEqual(bundle['ep_bundle_binding']['canonical_digest'],bundle['bundle_digest'])
        self.assertEqual(bundle['validation']['document_validation_phase'],'BEFORE_GIT_METADATA')
        self.assertEqual(bundle['validation']['target_entrypoint_qualification'],'NOT_ASSERTED_WITH_GIT_METADATA')

    def test_closed_finite_plan_and_effect_requests_reject_unbound_or_unbounded_input(self):
        from forge.genesis_bootstrap_contract import plan_request,effect_request,CONTRACT,EFFECT_PURPOSE
        _,_,request,_=plan_fixture()
        for update in ({'expected_plan_revision':True},{'expected_plan_revision':8},{'previous_plan_id':'unexpected'},
                       {'expected_plan_revision':1,'previous_plan_id':None},{'blocking_open_points':'not-a-list'},
                       {'target':{'ep_instance_id':'ep'}},{'source_subject':{}},{'expires_at':'no-time'}):
            with self.subTest(update=update),self.assertRaises((ValueError,TypeError)):
                plan_request({**request,**update})
        decision={'contract_version':CONTRACT,'instance_id':'instance','dossier_id':'dossier','operation_id':'operation',
                  'plan_id':'plan','plan_digest':'a'*64,'purpose':EFFECT_PURPOSE,'decision':'APPROVE_EFFECT','reason':'Exact synthetic confirmation.',
                  'expected_decision_revision':0,'previous_decision_id':None}
        effect_request(decision)
        for update in ({'purpose':'CONTENT_BASELINE_ONLY/1.0'},{'decision':'APPROVE_ANYTHING'},
                       {'expected_decision_revision':True},{'expected_decision_revision':8},
                       {'previous_decision_id':'unexpected'},{'expected_decision_revision':1,'previous_decision_id':None},
                       {'reason':''},{'plan_digest':'invalid'},{'actor':'forged'}):
            with self.subTest(update=update),self.assertRaises((ValueError,TypeError)):
                effect_request({**decision,**update})

    def test_frozen_profile_rejects_tampered_pins_input_manifest_and_declaration(self):
        from forge.project_bootstrap.service import BASE_PATH
        def change_manifest(record,mutate):
            row=next(r for r in record['result']['artifacts'] if r['path']=='engineering/bootstrap-manifest.json')
            value=json.loads(row['content']);mutate(value)
            value['manifest_digest']=digest(canonical({k:v for k,v in value.items() if k!='manifest_digest'}))
            row['content']=canonical(value).decode();row['sha256']=digest(row['content'].encode())
        for choice in ('empty','mode','baseline','input','inventory','entry-hash','declaration'):
            record=original();rows=record['result']['artifacts']
            if choice=='empty':record['result']['artifacts']=[]
            elif choice=='mode':rows[0]['mode']=0o755
            elif choice in ('baseline','input'):
                name=BASE_PATH+'/validate.py' if choice=='baseline' else 'engineering/render-input.json'
                row=next(r for r in rows if r['path']==name);row['content']+=' ';row['sha256']=digest(row['content'].encode())
            elif choice=='inventory':change_manifest(record,lambda m:m['artifacts'].pop())
            elif choice=='entry-hash':change_manifest(record,lambda m:m['artifacts'][0].update(expected_after_digest='f'*64))
            else:
                row=next(r for r in rows if r['path']=='.engineering-platform/repository.json')
                value=json.loads(row['content']);value['validation']['entrypoint']='bash untrusted.sh';row['content']=canonical(value).decode();row['sha256']=digest(row['content'].encode())
                change_manifest(record,lambda m:m['artifacts'][0].update(expected_after_digest=row['sha256'],bytes=len(row['content'].encode())))
            with self.subTest(choice=choice),self.assertRaises(ValueError):frozen_bundle(record)

    def test_expiry_is_bounded_rfc3339_before_any_persist(self):
        from forge.genesis_bootstrap_contract import plan_request,finite_expiry
        _,_,request,_=plan_fixture()
        for bad in ('2026-10-17T00:00:00.'+'1'*100+'+00:00','20261017T000000+0000','2026-10-17 00:00:00+00:00','2026-10-17T00:00:00','2026-13-17T00:00:00Z'):
            with self.subTest(value=bad),self.assertRaises(ValueError):plan_request({**request,'expires_at':bad})
        self.assertEqual(finite_expiry('2026-10-17T00:00:00Z'),finite_expiry('2026-10-17T00:00:00.000000+00:00'))
