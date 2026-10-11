"""Coherent owned reads across source drift, authority loss, and retained history."""
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from workset_order_fixture import order_case, shown, command
from workset_activity_fixture import setup, call, all_counts
from forge.workset_order_service import WorksetOrderService
from forge.workset_activity_service import BASE
from forge.workset_activity_cli import main as cli
from forge.workspace_review_grant import _private_bytes


class ActivityEdgesTests(unittest.TestCase):
    def test_completed_cursor_collects_real_late_older_order_records_and_cli_exports(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'late') as case:
            setup(case); before = all_counts(case)
            status, initial = call(case); self.assertEqual(status, 200, initial)
            self.assertFalse(initial['has_more'])
            self.assertEqual(all_counts(case), before)
            request = command(shown(case))
            with patch('forge.workset_order_service.now', return_value='2020-01-01T12:00:00+00:00'):
                status, output = case['ready'].call(case['port'], case['root'] / 'order.private',
                    'POST', '/v1/approved-workset-orders/' + case['key'] + '/confirm', request)
            self.assertEqual(status, 200, output)
            before = all_counts(case)
            suffix = '/pages/' + initial['cursor']
            status, delta = call(case, suffix); self.assertEqual(status, 200, delta)
            self.assertIn('ORDER_APPLIED', {e['fact'] for e in delta['events']})
            self.assertFalse({e['event_id'] for e in initial['events']} & {e['event_id'] for e in delta['events']})
            self.assertIn('2020-01-01T12:00:00+00:00', {e['occurred_at'] for e in delta['events']})
            for _ in range(2):
                status, replay = call(case, suffix); self.assertEqual(status, 200, replay)
                self.assertEqual(replay['events'], delta['events'])
            export = case['root'] / 'activity-export.private.json'
            args = ['--data-root', str(case['grant'].root), '--token-file', str(case['root'] / 'activity.private')]
            with redirect_stdout(StringIO()) as stdout:
                code = cli(args + ['pages', '--output', str(export)])
            self.assertEqual(code, 0, stdout.getvalue())
            self.assertEqual(json.loads(export.read_text())['contract_version'], 'forge-workset-activity/v1')
            with redirect_stdout(StringIO()) as stdout:
                code = cli(args + ['pages', '--cursor-file', str(export)])
            self.assertEqual(code, 0, stdout.getvalue())
            event = initial['events'][0]
            status, original = call(case, '/events/' + event['event_id'])
            self.assertEqual(status, 200, original); self.assertEqual(original['event'], event)
            self.assertEqual(all_counts(case), before)

    def test_mid_read_real_order_effect_forces_resync(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'race') as case:
            setup(case); request = command(shown(case))
            import forge.workset_activity_service as product
            original = product.projection; triggered = False
            def changed(*args, **kwargs):
                nonlocal triggered
                current = original(*args, **kwargs)
                if not triggered:
                    triggered = True
                    status, receipt = WorksetOrderService(case['grant'].root, case['grant']).handle(
                        'POST', '/v1/approved-workset-orders/' + case['key'] + '/confirm',
                        'Bearer ' + _private_bytes(case['root'] / 'order.private').decode().strip(), request)
                    self.assertEqual(status, 200, receipt)
                return current
            with patch.object(product, 'projection', side_effect=changed):
                status, result = call(case)
            self.assertEqual(status, 409, 'snapshot drift was accepted')
            self.assertEqual(result['error']['code'], 'RESYNC_REQUIRED')
            status, current = call(case); self.assertEqual(status, 200, current)
            self.assertEqual(current['current']['effective_order'], case['proposed'])

    def test_read_only_authority_scope_revocation_and_source_corruption_fail_closed(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'denials') as case:
            record = setup(case); status, initial = call(case); self.assertEqual(status, 200, initial)
            before = all_counts(case)
            for suffix in ('/pages/' + initial['cursor'][:-1] + 'x', '/pages?cursor=ignored', '/events/' + '0' * 64):
                status, body = call(case, suffix); self.assertIn(status, (400, 404, 409))
            status, body = case['ready'].call(case['port'], case['root'] / 'activity.private', 'GET', BASE + '/foreign-workset/pages')
            self.assertEqual(status, 403, body)
            request = command(shown(case))
            status, body = case['ready'].call(case['port'], case['root'] / 'activity.private',
                'POST', '/v1/approved-workset-orders/' + case['key'] + '/confirm', request)
            self.assertEqual(status, 403, body)
            status, body = case['ready'].call(case['port'], case['root'] / 'admin.private', 'GET', BASE)
            self.assertEqual(status, 403, body)
            self.assertEqual(all_counts(case), before)
            db = case['runtime'].database._connection
            original = db.execute('SELECT document FROM approved_worksets WHERE workset_id=?', (case['key'],)).fetchone()[0]
            for field, replacement in (('runtime_generation', True), ('revision', True), ('installation_id', 'foreign-installation')):
                value = json.loads(original); value[field] = replacement
                with db:
                    db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?', (json.dumps(value), case['key']))
                corrupted = all_counts(case)
                status, body = call(case); self.assertIn(status, (403, 409, 503), body)
                self.assertEqual(all_counts(case), corrupted)
            with db:
                db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?', (original, case['key']))
            case['grant'].revoke(record['grant_id'])
            revoked = all_counts(case)
            status, body = call(case, '/pages/' + initial['cursor']); self.assertEqual(status, 401, body)
            self.assertEqual(all_counts(case), revoked)
