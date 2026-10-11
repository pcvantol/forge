"""Real pending intents and original applied receipts remain distinct and inert."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest

from workset_order_fixture import order_case, shown, command
from workset_activity_fixture import setup, call, all_counts
from test_workset_order_process import child, wait_boundary, cleanup
from forge.workspace_review_grant import _write_private
from forge.workspace_worklist_control_grant import WorkspaceWorklistControlGrant
from forge.models.criterion_observation import canonical_digest


class ActivityRetainedTests(unittest.TestCase):
    def test_real_pending_order_intent_never_becomes_applied_from_reads_or_reconnect(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'pending') as case:
            setup(case); request = command(shown(case))
            _write_private(case['root'] / 'order-command.private.json', json.dumps(request).encode())
            process = subprocess.Popen(child(case['root'], 'confirm', 'after-intent'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                wait_boundary(process, case['root'], 'after-intent')
                process.kill(); process.communicate(timeout=5)
            finally:
                cleanup(process)
            before = all_counts(case)
            for _ in range(2):
                status, page = call(case); self.assertEqual(status, 200, page)
                facts = {e['fact'] for e in page['events']}
                self.assertIn('ORDER_INTENT_RECORDED', facts); self.assertNotIn('ORDER_APPLIED', facts)
                self.assertIn('ORDER_AMENDMENT_PENDING', page['current']['order_blocking_reasons'])
            self.assertEqual(all_counts(case), before)

    def test_actual_hold_unhold_receipts_unknown_intent_time_and_coherent_tamper(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'control') as case:
            setup(case)
            grant = WorkspaceWorklistControlGrant(case['grant'].root, case['grant'].instance_id)
            grant.issue(principal_id='activity-control-consumer', workset_ids=[case['key']],
                expires_at=(datetime.now(UTC) + timedelta(minutes=30)).isoformat(), token_path=case['root'] / 'control.private')
            db = case['runtime'].database._connection
            def value():
                return json.loads(db.execute('SELECT document FROM approved_worksets WHERE workset_id=?', (case['key'],)).fetchone()[0])
            for action in ('hold', 'unhold'):
                current = value()
                request = {'contract_version': 'forge-worklist-control-request/v1',
                    'operation_id': 'activity-' + action, 'intent': action, 'instance_id': case['grant'].instance_id,
                    'workset_id': case['key'], 'definition_revision': current['definition_digest'],
                    'expected_revision': current['revision'], 'hold_operation_id': 'activity-hold' if action == 'unhold' else None,
                    'expected_hold_revision': current.get('control_revision') if action == 'unhold' else None,
                    'reason_code': 'USER_REQUEST'}
                status, result = case['ready'].call(case['port'], case['root'] / 'control.private',
                    'POST', '/v1/workset-controls/' + case['key'] + '/commands', request)
                self.assertEqual(status, 200, result)
            before = all_counts(case)
            status, page = call(case); self.assertEqual(status, 200, page)
            self.assertTrue({'HOLD_APPLIED', 'UNHOLD_APPLIED'} <= {e['fact'] for e in page['events']})
            intents = [e for e in page['events'] if e['fact'] == 'CONTROL_INTENT_RECORDED']
            self.assertEqual(len(intents), 2)
            self.assertTrue(all(e['occurred_at'] is None and e['time_status'] == 'UNKNOWN' for e in intents))
            self.assertEqual(all_counts(case), before)
            original = value(); changed = deepcopy(original)
            stored = changed['control_operations']['activity-hold']; stored['receipt']['effect']['ongoing_work_cancelled'] = True
            stored['receipt_digest'] = canonical_digest(stored['receipt'])
            with db:
                db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?', (json.dumps(changed), case['key']))
            bad = all_counts(case); status, output = call(case); self.assertEqual(status, 503, output)
            self.assertEqual(output['completeness'], 'PARTIAL'); self.assertEqual(all_counts(case), bad)
            with db:
                db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?', (json.dumps(original), case['key']))
