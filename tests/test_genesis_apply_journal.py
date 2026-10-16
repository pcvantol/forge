"""Durable intent rules; a memory store is not installed EP evidence."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from forge.genesis_apply_contract import CONTRACT, ep_request
from forge.genesis_apply_journal import GenesisDispatchJournal
from tests.test_genesis_apply_contract import dispatch_fixture


class MemoryStore:
    def __init__(self): self.value = {'records': {}}
    def _store(self): return deepcopy(self.value)
    def save_store(self, value): self.value = deepcopy(value)


class GenesisJournalTests(TestCase):
    def setUp(self):
        self.store = MemoryStore(); self.journal = GenesisDispatchJournal(self.store)
        original, plan, decision = dispatch_fixture()
        self.request = dict(contract_version=CONTRACT, instance_id=plan['instance_id'], dossier_id=plan['dossier_id'],
                            operation_id='original-operation', plan_id=plan['plan_id'], plan_digest=plan['plan_digest'],
                            decision_id=decision['decision_id'], decision_digest=decision['decision_digest'], pairing_id='owner-pairing')
        self.ep, _ = ep_request(original, plan, decision, 'original-operation')
        self.principal = SimpleNamespace(principal_id='requester', audience='consumer', grant_id='grant')

    def prepare(self, **updates):
        return self.journal.prepare({**self.request, **updates}, self.principal, 'a'*64, self.ep)

    def test_original_intent_and_send_claim_survive_recreated_coordinator(self):
        one, new = self.prepare(); self.assertTrue(new); self.assertEqual(one['attempts'], [])
        claim, send = self.journal.claim('original-operation', attempt_id='original-create')
        self.assertTrue(send)
        self.journal = GenesisDispatchJournal(self.store)
        replay, new = self.prepare(); self.assertFalse(new)
        self.assertEqual(replay['ep_request'], self.ep)
        self.assertEqual(self.journal.claim('original-operation', attempt_id='original-create'), (claim, False))
        self.assertEqual(self.journal.claim('original-operation', attempt_id='different-create'), (claim, False))
        self.assertEqual(len(self.store.value['records']), 1)

    def test_conflicting_input_or_principal_or_ep_bytes_cannot_rebind_original(self):
        self.prepare()
        for choice in ('plan', 'principal', 'ep'):
            with self.subTest(choice=choice):
                journal = GenesisDispatchJournal(self.store)
                p = deepcopy(self.principal); ep = deepcopy(self.ep); request = deepcopy(self.request)
                if choice == 'plan': request['plan_digest'] = 'f'*64
                elif choice == 'principal': p.principal_id = 'foreign'
                else: ep['target_ref'] = 'other'
                with self.assertRaisesRegex(ValueError, 'GENESIS_ORIGINAL_INTENT_CONFLICT'):
                    journal.prepare(request, p, 'a'*64, ep)

    def test_explicit_resume_fences_late_response_and_replay_never_resends(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'GENESIS_ORIGINAL_ADMISSION_REQUIRED'):
            self.journal.claim('original-operation', attempt_id='resume', resume=True)
        first, _ = self.journal.claim('original-operation', attempt_id='create')
        second, new = self.journal.claim('original-operation', attempt_id='resume', resume=True)
        self.assertTrue(new); self.assertNotEqual(first, second)
        self.assertEqual(self.journal.claim('original-operation', attempt_id='resume', resume=True), (second, False))
        with self.assertRaisesRegex(ValueError, 'GENESIS_ATTEMPT_KIND_CONFLICT'):
            self.journal.claim('original-operation', attempt_id='resume')
        with self.assertRaisesRegex(ValueError, 'GENESIS_LATE_RESPONSE_FENCED'):
            self.journal.observe('original-operation', first, {'state': 'COMPLETE'})
        result = self.journal.observe('original-operation', second, {'state': 'PARTIAL'})
        self.assertEqual(result['observation']['response']['state'], 'PARTIAL')
        self.assertEqual(self.journal.store()['records']['original-operation'], result)

    def test_corrupt_original_is_unavailable_not_empty(self):
        self.prepare(); original = deepcopy(self.store.value)
        for choice in ('fields', 'digest', 'ep', 'attempt', 'observation'):
            self.store.value = deepcopy(original); row = self.store.value['records']['original-operation']
            if choice == 'fields': row['extra'] = True
            elif choice == 'digest': row['request_digest'] = '0'*64
            elif choice == 'ep': row['ep_request']['operation_id'] = 'other'
            elif choice == 'attempt': row['attempts'] = [{'attempt_id': 'a', 'kind': 'RESUME', 'claim': 'claim'}]
            else: row['observation'] = {'claim': 'unknown', 'response': {}, 'response_digest': '0'*64}
            with self.subTest(choice=choice), self.assertRaisesRegex(RuntimeError, 'unavailable'): self.journal.store()
