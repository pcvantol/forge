"""Accepting A preserves every independent B release/hold/authority/limit gate."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mission_final_acceptance_fixture import pending_a, state_counts, chain
from forge.mission_final_acceptance_service import BASE
from forge.workset_release_grant import WorksetReleaseGrant
from forge.server_runtime import existing_instance
from forge.approved_worklist import ApprovedWorklistService, candidate_source
from forge.lifecycle import RecommendationLifecycleStore


class MissionFinalAcceptanceDependencyTests(unittest.TestCase):
    def test_a_acceptance_never_removes_b_hold_disarm_revocation_scope_or_limit(self):
        for mode, expected in [('hold', 'WORKSET_HELD'), ('disarm', 'NOT_RELEASED'),
                ('revoked-release', 'RELEASE_CAPABILITY_UNAVAILABLE'),
                ('expired-release', 'RELEASE_CAPABILITY_UNAVAILABLE'),
                ('missing-b-scope', 'RELEASE_CAPABILITY_UNAVAILABLE'),
                ('limit', 'ACTIVATION_LIMIT_EXHAUSTED')]:
            with self.subTest(mode=mode), TemporaryDirectory() as temporary, pending_a(
                    Path(temporary) / mode, maximum_activations=1 if mode == 'limit' else 2) as case:
                runtime, root = case['runtime'], case['root']
                key = case['data']['workset_id']
                if mode == 'hold':
                    with RecommendationLifecycleStore(candidate_source(root / 'runtime')) as lifecycle:
                        worklists = ApprovedWorklistService(runtime, lifecycle)
                        current = worklists._get(key)
                        worklists.control(key, expected_revision=current['revision'], operation='hold')
                elif mode == 'disarm':
                    chain.phase(root, case['scenario'], 'disarm', case['endpoint'])
                elif mode in ('revoked-release', 'expired-release', 'missing-b-scope'):
                    grant = WorksetReleaseGrant(root / 'runtime', existing_instance(root / 'runtime').instance_id)
                    if mode == 'revoked-release':
                        grant.revoke(case['data']['grant_id'])
                    else:
                        records = grant._records()
                        record = next(r for r in records if r['grant_id'] == case['data']['grant_id'])
                        if mode == 'expired-release':
                            record['expires_at'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
                        else:
                            record['subjects'] = record['subjects'][:1]  # deliberate narrower current authority
                        grant._save(records)
                status, accepted = case['ready'].call(case['port'], root / 'accept.private', 'POST',
                    BASE + '/' + case['mission_id'] + '/accept', case['request'])
                self.assertEqual(200, status, accepted)
                self.assertEqual('COMPLETE', accepted['state'])
                before = state_counts(case)
                blocked = chain.phase(root, case['scenario'], 'tick', case['endpoint'])
                self.assertEqual('COMPLETED', blocked['states'][0]['status'])
                self.assertEqual('APPROVED_PLANNABLE', blocked['states'][1]['status'])
                self.assertIn(expected, blocked['read']['items'][1]['blocking_reasons'], blocked['read'])
                self.assertEqual(1, blocked['provider_invocations'])
                self.assertEqual(1, blocked['workset']['consumed_activations'])
                self.assertEqual(2, blocked['allocations'])
                after = state_counts(case)
                self.assertEqual(before['submissions'], after['submissions'])
                self.assertEqual(before['ep_requests'], after['ep_requests'])
                self.assertEqual(before['b'], after['b'])
                self.assertEqual(before['provider_requests'], after['provider_requests'])

    def test_genuinely_approved_unreleased_c_remains_outside_acceptance_scope_and_runtime_selection(self):
        with TemporaryDirectory() as temporary, pending_a(Path(temporary) / 'approved-c', approve_unreleased_c=True) as case:
            root = case['root']
            data = chain.utils.fixture._read(root / 'release-case.private.json')
            c = data['unreleased_mission_id']
            before_c = case['runtime'].database.get_document('mission_state', c)
            self.assertEqual('APPROVED_PLANNABLE', before_c['status'])
            self.assertEqual(3, state_counts(case)['allocations'])
            status, response = case['ready'].call(case['port'], root / 'accept.private', 'GET', BASE + '/' + c)
            self.assertEqual(403, status, response)
            status, accepted = case['ready'].call(case['port'], root / 'accept.private', 'POST',
                BASE + '/' + case['mission_id'] + '/accept', case['request'])
            self.assertEqual(200, status, accepted)
            result = chain.phase(root, case['scenario'], 'tick', case['endpoint'])
            self.assertEqual(3, result['allocations'])
            self.assertEqual(2, result['provider_invocations'])
            self.assertEqual(2, result['workset']['consumed_activations'])
            self.assertEqual(before_c, case['runtime'].database.get_document('mission_state', c))
            selected = [item['mission_id'] for item in result['read']['items']]
            self.assertNotIn(c, selected)
            self.assertEqual([case['mission_id'], case['mission_b']], selected)
