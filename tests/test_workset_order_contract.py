"""Real closed order guards: fixed claims, identity and hard edges."""
import unittest
import sqlite3
from contextlib import closing

from forge.workset_order_contract import (CONTRACT, OrderConflict, confirm_request,
                                         exact_order, grant_bounds, permutation)
from forge.workset_order import effective_order, fixed_prefix


class WorksetOrderContractTests(unittest.TestCase):
    def setUp(self):
        self.members = {'A': {'dependencies': []}, 'B': {'dependencies': ['A']},
                        'C': {'dependencies': ['A']}}

    def test_exact_remaining_permutation_keeps_active_a_and_hard_edges(self):
        self.assertEqual(permutation(['A', 'B', 'C'], ['A', 'C', 'B'], 1, self.members),
                         ['A', 'C', 'B'])
        self.assertEqual(self.members['C']['dependencies'], ['A'])
        for proposed in (['C', 'A', 'B'], ['A', 'B', 'D'], ['A', 'B'], ['A', 'B', 'C']):
            with self.subTest(proposed=proposed), self.assertRaises(ValueError):
                permutation(['A', 'B', 'C'], proposed, 1, self.members)
        self.members['C']['dependencies'] = ['B']
        with self.assertRaisesRegex(OrderConflict, 'HARD_DEPENDENCY'):
            permutation(['A', 'B', 'C'], ['A', 'C', 'B'], 1, self.members)

    def test_prefix_and_order_types_fail_closed(self):
        for prefix in (True, False, 1.0, -1, 4):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                permutation(['A', 'B', 'C'], ['A', 'C', 'B'], prefix, self.members)
        for order in ([], ['A', 'A'], ['A', True], ('A', 'B'), ['secret=token']):
            with self.subTest(order=order), self.assertRaises(ValueError):
                exact_order(order)
        self.members['C']['dependencies'] = [True]
        with self.assertRaises(ValueError):
            permutation(['A', 'B', 'C'], ['A', 'C', 'B'], 1, self.members)

    def test_explicit_confirmation_is_closed_and_server_bound(self):
        package = {'contract_version': CONTRACT, 'instance_id': 'instance', 'project_id': 'project',
            'repository_id': 'repository', 'workset_id': 'workset', 'definition_digest': 'sha256:' + 'a' * 64,
            'authority_digest': 'sha256:' + 'b' * 64, 'workset_revision': 1, 'order_revision': 0,
            'previous_order_digest': 'sha256:' + 'c' * 64, 'current_order': ['A', 'B', 'C'],
            'proposed_order': ['A', 'C', 'B'], 'fixed_prefix': 1, 'maximum_activations': 3,
            'consumed_activations': 1, 'expires_at': '2099-01-01T00:00:00Z',
            'subjects': [{'candidate_id': c, 'subject_revision': 'sha256:' + 'd' * 64} for c in ('A', 'B', 'C')]}
        body = {'contract_version': CONTRACT, 'operation_id': 'operation', 'instance_id': 'instance',
                'project_id': 'project', 'repository_id': 'repository', 'workset_id': 'workset',
                'package_digest': 'sha256:' + 'a' * 64, 'package': package, 'reason': 'Run C before B.', 'confirm': True}
        self.assertEqual(confirm_request(body), body)
        for changed in ({**body, 'confirm': 1}, {**body, 'confirm': False},
                        {**body, 'actor': 'admin'}, {**body, 'package_digest': 'invalid'},
                        {**body, 'reason': ''}, {**body, 'operation_id': '../escape'}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                confirm_request(changed)
        for field in ('fixed_prefix', 'order_revision', 'workset_revision', 'consumed_activations', 'maximum_activations'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                confirm_request({**body, 'package': {**package, field: True}})

    def test_finite_distinct_grant_scope_and_typed_allowance(self):
        scope = [{'workset_id': 'workset', 'definition_digest': 'sha256:' + 'b' * 64}]
        grant_bounds(['READ', 'REORDER'], scope, 1)
        for permissions, worksets, ceiling in ((['REORDER'], scope, 1), (['READ', 'RELEASE'], scope, 1),
            (['READ', 'READ'], scope, 1), (['READ'], [], 1), (['READ'], scope, True),
            (['READ'], scope, 1.0), (['READ'], scope, 17), (['READ'], scope * 2, 1),
            (['READ'], [{'workset_id': 'workset', 'definition_digest': 'x'}], 1)):
            with self.subTest(permissions=permissions, ceiling=ceiling), self.assertRaises(ValueError):
                grant_bounds(permissions, worksets, ceiling)

    def test_canonical_intake_is_not_activation_and_claimed_prefix_is_fixed(self):
        value = {'definition': {'workset_id': 'workset', 'members': [{'candidate_id': c} for c in ('A', 'B', 'C')]},
                 'claims': {'A': {'mission_id': 'MISSION-A'}}, 'consumed_activations': 1}
        states = {'A': {'status': 'WAITING_FOR_EVIDENCE'},
                  'B': {'status': 'APPROVED_PLANNABLE'}, 'C': {'status': 'APPROVED_PLANNABLE'}}
        self.assertEqual(fixed_prefix(value, states), 1)
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE governance_decisions(subject_id TEXT, document TEXT)')
            self.assertEqual(effective_order(value, db)[0], ['A', 'B', 'C'])
        states['B'] = {'status': 'ACTIVE'}
        with self.assertRaisesRegex(OrderConflict, 'UNCLAIMED_STARTED'):
            fixed_prefix(value, states)
        states['B'] = {'status': 'APPROVED_PLANNABLE'}
        value['claims']['C'] = {'mission_id': None}
        value['consumed_activations'] = 2
        with self.assertRaisesRegex(OrderConflict, 'NON_SERIAL'):
            fixed_prefix(value, states)

    def test_ambiguous_consumption_and_forged_history_never_fallback(self):
        value = {'definition': {'workset_id': 'workset', 'members': [{'candidate_id': 'A'}]},
                 'claims': {}, 'consumed_activations': True}
        with self.assertRaisesRegex(OrderConflict, 'CONSUMPTION'):
            fixed_prefix(value, {'A': {'status': 'APPROVED_PLANNABLE'}})
        value['consumed_activations'] = 0
        with self.assertRaisesRegex(OrderConflict, 'INCOMPLETE'):
            fixed_prefix(value, {})
        value['order_amendments'] = [{'proposed_order': ['A']}]
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE governance_decisions(subject_id TEXT, document TEXT)')
            with self.assertRaisesRegex(ValueError, 'shape'):
                effective_order(value, db)
