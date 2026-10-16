"""Synthetic binding checks; these fixtures confer no real effect authority."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from tests.test_genesis_bootstrap_contract import plan_fixture
from forge.genesis_bootstrap_contract import plan_document, EFFECT_PURPOSE, CONTRACT as PLAN_CONTRACT
from forge.genesis_apply_contract import CONTRACT, apply_request, ep_request
from forge.project_bootstrap.schema import canonical, ContractError
from forge.project_bootstrap.service import digest


def dispatch_fixture():
    args = plan_fixture()
    plan = plan_document(*args)
    decision = dict(contract_version=PLAN_CONTRACT, purpose=EFFECT_PURPOSE, decision='APPROVE_EFFECT',
                    instance_id=plan['instance_id'], dossier_id=plan['dossier_id'], audience=plan['audience'],
                    plan_id=plan['plan_id'], plan_digest=plan['plan_digest'],
                    decision_id='synthetic-effect-decision', principal_id='synthetic-human-owner')
    decision['decision_digest'] = digest(canonical(decision))
    return args[0], plan, decision


class GenesisDispatchBindingTests(TestCase):
    def test_exact_original_bytes_and_distinct_digests_without_render(self):
        args = dispatch_fixture(); before = deepcopy(args)
        with patch('forge.project_bootstrap.service.render', side_effect=AssertionError('no second renderer')):
            request, request_digest = ep_request(*args, 'synthetic-original-operation')
        self.assertEqual(args, before)
        self.assertEqual(request_digest, digest(canonical(request)))
        self.assertEqual(len(request['bundle']['files']), 37)
        self.assertEqual(digest(canonical(request['bundle'])), '0c2c0fb41a68793be0960bb4289d7590060c8092ebb976852e1c4674b0f66b1d')
        self.assertEqual(request['effect_plan_binding']['proposal_digest'], args[1]['source_subject']['result_digest'])
        self.assertNotEqual(request['effect_plan_binding']['proposal_digest'], digest(canonical(request['bundle'])))
        self.assertEqual(request['effect_plan_binding']['source_actor_id'], args[2]['principal_id'])
        for row in args[0]['result']['artifacts']:
            self.assertEqual(request['bundle']['files'][row['path']], {'sha256': row['sha256'], 'utf8': row['content']})

    def test_changed_original_plan_decision_and_scope_rejected(self):
        for choice in ('plan', 'decision', 'bytes', 'source', 'negative', 'purpose', 'scope', 'actor'):
            original, plan, decision = dispatch_fixture()
            if choice == 'plan': plan['target']['target_ref'] = 'changed'
            elif choice == 'decision': decision['decision_id'] = 'changed'
            elif choice == 'bytes': original['result']['artifacts'][0]['content'] += 'changed'
            elif choice == 'source': original['plan_id'] = 'changed'
            else:
                field, value = {'negative': ('decision', 'REQUEST_CHANGES'), 'purpose': ('purpose', 'CONTENT_ONLY'),
                                'scope': ('dossier_id', 'foreign'), 'actor': ('principal_id', '/private/credential')}[choice]
                decision[field] = value
                decision['decision_digest'] = digest(canonical({k: v for k, v in decision.items() if k != 'decision_digest'}))
            with self.subTest(choice=choice), self.assertRaises(ValueError):
                ep_request(original, plan, decision, 'synthetic-original-operation')

    def test_closed_input_references_only(self):
        _, plan, decision = dispatch_fixture()
        value = dict(contract_version=CONTRACT, instance_id=plan['instance_id'], dossier_id=plan['dossier_id'],
                     operation_id='synthetic-original-operation', plan_id=plan['plan_id'], plan_digest=plan['plan_digest'],
                     decision_id=decision['decision_id'], decision_digest=decision['decision_digest'], pairing_id='owner-pairing')
        self.assertEqual(apply_request(value), (value, digest(canonical(value))))
        for update in ({'credential': 'secret'}, {'target_ref': '/tmp/target'}, {'operation_id': '/tmp/path'},
                       {'plan_digest': 'wrong'}, {'contract_version': 'other'}, {'pairing_id': 'x\r\nHeader:bad'}):
            with self.subTest(update=update), self.assertRaises(ValueError): apply_request({**value, **update})
