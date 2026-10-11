"""Linked actual authority, dependencies, stale evidence and future-only guards."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from workset_order_fixture import order_case, call, shown, counts, command
from forge.workset_order_contract import CONTRACT
from forge.workset_order_grant import WorksetOrderGrant


class WorksetOrderDenialTests(unittest.TestCase):
    def test_real_hard_b_to_c_dependency_cannot_be_reordered_or_removed(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'edge', c_depends_on_b=True) as case:
            before = counts(case)
            status, output = call(case, 'POST', '/preview', {'contract_version': CONTRACT, 'proposed_order': case['proposed']})
            self.assertEqual(status, 409, output)
            self.assertEqual(output['error']['code'], 'HARD_DEPENDENCY_ORDER_CONFLICT')
            self.assertEqual(counts(case), before)

    def test_scope_wrong_types_member_changes_and_old_tokens_never_mutate(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'bindings') as case:
            preview = shown(case); request = command(preview); before = counts(case)
            for token in ('release.private', 'chat-owner.private', 'admin.private'):
                status, _ = call(case, 'POST', '/confirm', request, token)
                self.assertEqual(status, 403)
            for field, value in [('instance_id', 'other'), ('project_id', 'other'), ('repository_id', 'other'),
                                 ('confirm', 1), ('confirm', False), ('actor', 'server-admin')]:
                status, output = call(case, 'POST', '/confirm', {**request, field: value})
                self.assertIn(status, (403, 409), output)
            for proposed in (case['order'], list(reversed(case['order'])), case['proposed'][:-1],
                             [*case['proposed'][:-1], 'unreleased-D'], [True]):
                status, _ = call(case, 'POST', '/preview', {'contract_version': CONTRACT, 'proposed_order': proposed})
                self.assertEqual(status, 409)
            for field, changed in [('order_revision', True), ('workset_revision', 1.0),
                                   ('consumed_activations', False), ('expires_at', '2099-01-01T00:00:00Z')]:
                package = {**preview['package'], field: changed}
                from forge.advisory_contract import digest
                status, _ = call(case, 'POST', '/confirm', {**request, 'package': package, 'package_digest': digest(package)})
                self.assertEqual(status, 409)
            self.assertEqual(counts(case), before)

    def test_actual_hold_disarm_expiry_and_consumed_ceiling_deny_new_order(self):
        for action in ('hold', 'disarm', 'revoke'):
            with self.subTest(action=action), TemporaryDirectory() as tmp, order_case(Path(tmp) / action) as case:
                preview = shown(case)
                from forge.approved_worklist import ApprovedWorklistService, candidate_source
                from forge.lifecycle import RecommendationLifecycleStore
                with RecommendationLifecycleStore(candidate_source(case['root'] / 'runtime')) as lifecycle:
                    service = ApprovedWorklistService(case['runtime'], lifecycle)
                    value = service._get(case['key'])
                    service.control(case['key'], expected_revision=value['revision'], operation=action)
                before = counts(case)
                status, output = call(case, 'POST', '/confirm', command(preview))
                self.assertEqual(status, 409, output)
                self.assertEqual(counts(case), before)
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'ceiling', maximum_activations=1) as case:
            before = counts(case)
            status, _ = call(case, 'POST', '/preview', {'contract_version': CONTRACT, 'proposed_order': case['proposed']})
            self.assertEqual(status, 409)
            self.assertEqual(counts(case), before)

    def test_read_only_and_revoked_authority_are_distinct_and_get_never_finishes(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'authority') as case:
            preview = shown(case); grant = case['grant']; record = case['grant_record']
            fields = {k: record[k] for k in ('principal_id', 'project_id', 'repository_id', 'worksets', 'maximum_amendments', 'expires_at')}
            grant.issue(**fields, permissions=['READ'], token_path=case['root'] / 'order-read.private')
            before = counts(case)
            status, output = call(case, 'POST', '/confirm', command(preview), 'order-read.private')
            self.assertEqual(status, 403, output)
            status, _ = call(case, 'GET', '/operations/missing-operation', token='order-read.private')
            self.assertEqual(status, 404)
            status, _ = call(case, 'GET', token='order-read.private')
            self.assertEqual(status, 200)
            self.assertEqual(counts(case), before)
            with self.assertRaises(ValueError):
                grant.issue(**{**fields, 'maximum_amendments': 3}, permissions=['READ', 'REORDER'], token_path=case['root'] / 'replacement.private')
            grant.revoke(record['grant_id'])
            before = counts(case)
            status, _ = call(case, 'POST', '/confirm', command(preview))
            self.assertEqual(status, 401)
            self.assertEqual(counts(case), before)
