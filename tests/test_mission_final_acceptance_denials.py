"""Current proof/authority and original identity failures on the real A/B chain."""
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sqlite3
from contextlib import closing
import unittest

from mission_final_acceptance_fixture import pending_a, state_counts
from forge.mission_final_acceptance_service import BASE
from forge.mission_final_acceptance_journal import FinalAcceptanceJournal
from forge.advisory_contract import digest


class MissionFinalAcceptanceDenialTests(unittest.TestCase):
    def test_wrong_actor_scope_typed_payload_unproven_mission_and_read_have_zero_effects(self):
        with TemporaryDirectory() as temporary, pending_a(Path(temporary) / 'deny') as case:
            root, ready, port = case['root'], case['ready'], case['port']
            path = BASE + '/' + case['mission_id'] + '/accept'
            token = root / 'accept.private'
            baseline = state_counts(case)
            for field, value in [('instance_id', 'other'), ('project_id', 'other'), ('repository_id', 'other'),
                    ('mission_id', case['mission_b']), ('confirm', 1), ('package_digest', 'sha256:' + '0' * 64),
                    ('actor', 'business_owner'), ('decision', 'approve'), ('mission_state_revision', True)]:
                with self.subTest(field=field):
                    status, response = ready.call(port, token, 'POST', path, {**case['request'], field: value})
                    self.assertIn(status, (403, 409), response)
                    self.assertEqual(baseline, state_counts(case))
            for credential in ('accept-read.private', 'release.private', 'admin.private', 'chat-owner.private'):
                status, response = ready.call(port, root / credential, 'POST', path, case['request'])
                self.assertEqual(403, status, response)
            status, detail = ready.call(port, token, 'GET', BASE + '/' + case['mission_b'])
            self.assertEqual(200, status, detail)
            self.assertFalse(detail['acceptance_supported'])
            self.assertIsNone(detail['package'])
            self.assertEqual(baseline, state_counts(case))
            status, response = ready.call(port, token, 'POST', '/v1/reviews/missions/' + case['mission_id'] + '/decisions', case['request'])
            self.assertEqual(403, status, response)
            self.assertEqual(baseline, state_counts(case))

    def test_actual_grant_revocation_and_expiry_deny_before_first_effect(self):
        for mode in ('revoke', 'expiry'):
            with self.subTest(mode=mode), TemporaryDirectory() as temporary, pending_a(Path(temporary) / mode) as case:
                root = case['root']
                if mode == 'revoke':
                    case['grant'].revoke(case['grant_record']['grant_id'])
                else:
                    records = case['grant']._records()
                    original = next(r for r in records if r['grant_id'] == case['grant_record']['grant_id'])
                    original['expires_at'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
                    case['grant']._save(records)
                before = state_counts(case)
                status, response = case['ready'].call(case['port'], root / 'accept.private', 'POST',
                    BASE + '/' + case['mission_id'] + '/accept', case['request'])
                self.assertEqual(401, status, response)
                self.assertEqual(before, state_counts(case))
                self.assertFalse((root / 'runtime/governance/mission-final-acceptance').exists())

    def test_revoke_between_canonical_and_terminal_stops_remaining_mutations_and_alias_keys(self):
        import forge.mission_final_acceptance_service as product
        with TemporaryDirectory() as temporary, pending_a(Path(temporary) / 'partial') as case:
            root, grant, runtime = case['root'], case['grant'], case['runtime']
            original_lock = product._locked
            revoked = False
            @contextmanager
            def at_actual_guard(path):
                nonlocal revoked
                if path.resolve() == grant.path.resolve() and not revoked:
                    with closing(sqlite3.connect(runtime.database.path.as_uri() + '?mode=ro', uri=True)) as observer:
                        row = observer.execute("SELECT 1 FROM governance_decisions WHERE json_extract(document, '$.decision')='accept' LIMIT 1").fetchone()
                    if row is not None:
                        grant.revoke(case['grant_record']['grant_id'])
                        revoked = True
                with original_lock(path):
                    yield
            before = state_counts(case)
            with patch.object(product, '_locked', at_actual_guard):
                status, response = case['ready'].call(case['port'], root / 'accept.private', 'POST',
                    BASE + '/' + case['mission_id'] + '/accept', case['request'])
            self.assertEqual(403, status, response)
            self.assertTrue(revoked)
            after = state_counts(case)
            self.assertEqual(before['governance'] + 1, after['governance'])
            self.assertEqual(before['a'], after['a'])
            self.assertEqual(before['b'], after['b'])
            self.assertEqual(before['dispatcher'], after['dispatcher'])
            self.assertEqual(before['ep_requests'], after['ep_requests'])
            token = 'Bearer ' + (root / 'accept-read.private').read_text().strip()
            principal = grant.authorize(token, case['mission_id'])
            journal = FinalAcceptanceJournal(root / 'runtime', principal.reference)
            saved = journal.path.read_bytes()
            for _ in range(2):
                status, read = case['ready'].call(case['port'], root / 'accept-read.private', 'GET',
                    BASE + '/' + case['mission_id'] + '/operations/accept-a')
                self.assertEqual(200, status, read)
                self.assertEqual('PENDING', read['state'])
                self.assertTrue(read['current']['canonical_decision_recorded'])
                self.assertIsNone(read['original_receipt'])
                self.assertEqual(saved, journal.path.read_bytes())
                self.assertEqual(after, state_counts(case))
            records = grant._records()
            original = next(r for r in records if r['grant_id'] == case['grant_record']['grant_id'])
            replacement = grant.issue(**{key: original[key] for key in ('principal_id', 'project_id', 'repository_id',
                'profile_id', 'permissions', 'missions', 'maximum_acceptances', 'expires_at')}, token_path=root / 'replacement.private')
            self.assertNotEqual(original['grant_id'], replacement['grant_id'])
            for operation in ('accept-a', 'new-key-after-revoke'):
                status, response = case['ready'].call(case['port'], root / 'replacement.private', 'POST',
                    BASE + '/' + case['mission_id'] + '/accept', {**case['request'], 'operation_id': operation})
                self.assertEqual(409, status, response)
                self.assertEqual(saved, journal.path.read_bytes())
                self.assertEqual(after, state_counts(case))

    def test_changed_mission_criteria_completion_terminal_policy_and_revision_are_stale(self):
        def change(document, field):
            if field == 'mission':
                document['mission']['summary'] += ' Changed after preview.'
            elif field == 'criteria':
                document['mission']['acceptance_criteria'][0] += ' New criterion scope.'
            elif field == 'completion':
                document['completion']['all_required_criteria_proven'] = False
            elif field == 'terminal':
                document['execution_evidence']['outcome'] = 'incomplete'
            elif field == 'policy':
                document['execution_policy']['policy_revision'] = 'unsupported-new-policy'
            elif field == 'revision':
                document['revision'] += 1
            elif field == 'boolean-revision':
                document['revision'] = True
            elif field == 'missing-terminal-lineage':
                document['execution_evidence']['repository_evidence'].pop('report_id', None)
        for field in ('mission', 'criteria', 'completion', 'terminal', 'policy', 'revision', 'boolean-revision', 'missing-terminal-lineage'):
            with self.subTest(field=field), TemporaryDirectory() as temporary, pending_a(Path(temporary) / field) as case:
                runtime = case['runtime']
                document = runtime.database.get_document('mission_state', case['mission_id'])
                change(document, field)
                # Deliberate negative corruption/drift after a real completion;
                # no synthetic successful record is inserted.
                with runtime.database._connection:
                    runtime.database._connection.execute('UPDATE mission_state SET document=? WHERE mission_id=?',
                        (json.dumps(document), case['mission_id']))
                before = state_counts(case)
                status, response = case['ready'].call(case['port'], case['root'] / 'accept.private', 'POST',
                    BASE + '/' + case['mission_id'] + '/accept', case['request'])
                self.assertIn(status, (409, 503), response)
                self.assertEqual(before, state_counts(case))
                self.assertFalse(FinalAcceptanceJournal(case['root'] / 'runtime',
                    case['grant'].authorize('Bearer ' + (case['root'] / 'accept.private').read_text().strip()).reference).path.exists())

    def test_current_operator_revoke_and_foreign_os_actor_deny_all_mutations(self):
        for mode in ('revoke-operator', 'foreign-os-actor'):
            with self.subTest(mode=mode), TemporaryDirectory() as temporary, pending_a(Path(temporary) / mode) as case:
                runtime = case['runtime']
                if mode == 'revoke-operator':
                    runtime.repository.operators.revoke(runtime.repository.operators.context())
                before = state_counts(case)
                if mode == 'foreign-os-actor':
                    from forge.operator_identity import NamedOperatorIdentity
                    from forge.runtime.dynamic_mission import MacOSGeneratedUIDIdentityAdapter
                    with patch.object(MacOSGeneratedUIDIdentityAdapter, 'resolve',
                            return_value=NamedOperatorIdentity('separate-foreign-test-actor', 502)):
                        status, response = case['ready'].call(case['port'], case['root'] / 'accept.private', 'POST',
                            BASE + '/' + case['mission_id'] + '/accept', case['request'])
                else:
                    status, response = case['ready'].call(case['port'], case['root'] / 'accept.private', 'POST',
                        BASE + '/' + case['mission_id'] + '/accept', case['request'])
                self.assertIn(status, (403, 409, 503), response)
                self.assertEqual(before, state_counts(case))

    def test_coherently_changed_canonical_receipt_is_conflict_and_never_overwritten(self):
        for field, changed in [('decision_id', 'foreign-decision'), ('subject_revision', 'sha256:' + 'a' * 64),
                               ('scope', ['foreign-scope']), ('decision', 'approve'), ('gates', ['foreign-policy'])]:
            with self.subTest(field=field), TemporaryDirectory() as temporary, pending_a(Path(temporary) / field) as case:
                runtime = case['runtime']
                path = BASE + '/' + case['mission_id'] + '/accept'
                status, accepted = case['ready'].call(case['port'], case['root'] / 'accept.private', 'POST', path, case['request'])
                self.assertEqual(200, status, accepted)
                decision_id = accepted['original_receipt']['decision_id']
                row = runtime.database._connection.execute('SELECT document FROM governance_decisions WHERE decision_id=?', (decision_id,)).fetchone()
                canonical = json.loads(row['document'])
                canonical[field] = changed
                from forge.governance_authority import _digest as producer_digest
                # Normal product immutability stays enforced. Deliberately
                # corrupt only this disposable test DB offline, and restore
                # the exact trigger before the actual product/readback probe.
                with closing(sqlite3.connect(runtime.database.path)) as corruption:
                    trigger = corruption.execute("SELECT sql FROM sqlite_master WHERE name='governance_decisions_immutable_update'").fetchone()[0]
                    with corruption:
                        corruption.execute('DROP TRIGGER governance_decisions_immutable_update')
                        corruption.execute('UPDATE governance_decisions SET document=?, digest=? WHERE decision_id=?',
                            (json.dumps(canonical), producer_digest(canonical), decision_id))
                        corruption.execute(trigger)
                before = state_counts(case)
                status, conflict = case['ready'].call(case['port'], case['root'] / 'accept.private', 'POST', path, case['request'])
                self.assertEqual(409, status, conflict)
                status, conflict = case['ready'].call(case['port'], case['root'] / 'accept-read.private', 'GET',
                    BASE + '/' + case['mission_id'] + '/operations/accept-a')
                self.assertEqual(409, status, conflict)
                self.assertEqual(before, state_counts(case))

    def test_expiry_after_canonical_stops_terminal_effect_and_read_is_not_reauthorization(self):
        import forge.mission_final_acceptance_service as product
        with TemporaryDirectory() as temporary, pending_a(Path(temporary) / 'expiry-partial') as case:
            grant, runtime = case['grant'], case['runtime']
            original_lock = product._locked
            expired = False
            @contextmanager
            def expire_at_actual_boundary(path):
                nonlocal expired
                if path.resolve() == grant.path.resolve() and not expired:
                    with closing(sqlite3.connect(runtime.database.path.as_uri() + '?mode=ro', uri=True)) as observer:
                        found = observer.execute("SELECT 1 FROM governance_decisions WHERE json_extract(document, '$.decision')='accept'").fetchone()
                    if found:
                        records = grant._records()
                        record = next(r for r in records if r['grant_id'] == case['grant_record']['grant_id'])
                        record['expires_at'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
                        grant._save(records)
                        expired = True
                with original_lock(path):
                    yield
            before = state_counts(case)
            with patch.object(product, '_locked', expire_at_actual_boundary):
                status, response = case['ready'].call(case['port'], case['root'] / 'accept.private', 'POST',
                    BASE + '/' + case['mission_id'] + '/accept', case['request'])
            self.assertEqual(403, status, response)
            self.assertTrue(expired)
            after = state_counts(case)
            self.assertEqual(before['governance'] + 1, after['governance'])
            self.assertEqual(before['a'], after['a'])
            self.assertEqual(before['dispatcher'], after['dispatcher'])
            status, read = case['ready'].call(case['port'], case['root'] / 'accept-read.private', 'GET',
                BASE + '/' + case['mission_id'] + '/operations/accept-a')
            self.assertEqual(200, status, read)
            self.assertEqual('PENDING', read['state'])
            self.assertEqual(after, state_counts(case))

    def test_original_completed_receipt_remains_distinct_from_changed_current_evidence(self):
        with TemporaryDirectory() as temporary, pending_a(Path(temporary) / 'original-current') as case:
            status, accepted = case['ready'].call(case['port'], case['root'] / 'accept.private', 'POST',
                BASE + '/' + case['mission_id'] + '/accept', case['request'])
            self.assertEqual(200, status, accepted)
            runtime = case['runtime']
            document = runtime.database.get_document('mission_state', case['mission_id'])
            document['execution_evidence']['outcome'] = 'incomplete'
            with runtime.database._connection:
                runtime.database._connection.execute('UPDATE mission_state SET document=? WHERE mission_id=?',
                    (json.dumps(document), case['mission_id']))
            before = state_counts(case)
            status, read = case['ready'].call(case['port'], case['root'] / 'accept-read.private', 'GET',
                BASE + '/' + case['mission_id'] + '/operations/accept-a')
            self.assertEqual(200, status, read)
            self.assertEqual(accepted['original_receipt'], read['original_receipt'])
            self.assertFalse(read['current']['evidence_matches_original'])
            self.assertFalse(read['current']['result']['completion_proven'])
            status, replay = case['ready'].call(case['port'], case['root'] / 'accept.private', 'POST',
                BASE + '/' + case['mission_id'] + '/accept', case['request'])
            self.assertEqual(409, status, replay)
            self.assertEqual(before, state_counts(case))
