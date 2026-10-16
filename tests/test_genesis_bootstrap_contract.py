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
