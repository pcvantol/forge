"""Closed byte/type/source boundaries; these are negative metadata unit probes."""
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import base64
import hashlib
import json
import sqlite3
import os
import unittest

from forge.workset_activity_cursor import page, checkpoint, resume, ActivityResync, MAX_EVENTS, MAX_CURSOR
from forge.workset_activity_projection import Sources, ActivityUnavailable, MAX_DOCUMENT_BYTES, public_label
from forge.workset_activity_cli import main as cli
from forge.workset_activity_grant import main as grant_cli
from workset_order_fixture import order_case
from workset_activity_fixture import setup, all_counts, call


class ActivityBoundsTests(unittest.TestCase):
    def test_cursor_typed_fields_bounds_duplicates_and_page_bytes(self):
        key = b'unit-negative-key'; context = {'dataset': 1}
        item = {'event_id': 'a' * 64, 'field': 'value'}
        for records in ([item, item], [{'event_id': hashlib.sha256(str(i).encode()).hexdigest()} for i in range(MAX_EVENTS + 1)],
                        [{**item, 'field': 'x' * 40000}]):
            with self.assertRaises(ValueError):page(key, context, records)
        for bad in ('', 'x' * (MAX_CURSOR + 1), 'a.b.c', 'not-base64.signature', 42):
            with self.assertRaises(ActivityResync):resume(key, bad, context)
        for changed in ({'x': '0' * 64}, {'a' * 64: 'invalid'}):
            value = checkpoint(key, context, 'b' * 64, changed, True)
            with self.assertRaises(ActivityResync):resume(key, value, context)
        with self.assertRaises(ValueError):checkpoint(key, context, 'b' * 64, {'a' * 64: 'x' * MAX_CURSOR}, True)

    def test_public_labels_remove_credentials_and_private_paths(self):
        label = public_label('Werk /Users/private-owner/project api_key=example-secret')
        self.assertNotIn('/Users/', label); self.assertNotIn('private-owner', label)
        self.assertNotIn('example-secret', label)
        self.assertEqual(public_label('Veilige missie'), 'Veilige missie')

    def test_source_reader_rejects_missing_oversize_malformed_and_nonobject(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE negative_sources (key TEXT PRIMARY KEY,document TEXT)')
            source = Sources(db)
            self.assertIsNone(source.document('negative_sources', 'key', 'missing', required=False))
            with self.assertRaises(ActivityUnavailable):source.document('negative_sources', 'key', 'missing')
            for index, body in enumerate(('{broken', '[]', '"' + 'x' * (MAX_DOCUMENT_BYTES + 1) + '"')):
                db.execute('INSERT INTO negative_sources VALUES (?,?)', (str(index), body))
                with self.assertRaises(ActivityUnavailable):source.document('negative_sources', 'key', str(index))

    def test_setup_identity_read_cli_errors_and_protected_export_collision(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'cli') as case:
            record = setup(case); token = case['root'] / 'activity.private'; before_bytes = token.read_bytes()
            args = ['--data-root', str(case['grant'].root), '--token-file', str(token)]
            for extra in (['pages', '--output', str(token)], ['pages', '--output', str(case['grant'].root / 'forge.db')],
                          ['event', '--event-id', 'invalid']):
                before = all_counts(case)
                with redirect_stdout(StringIO()) as output:code = cli(args + extra)
                self.assertEqual(code, 1, output.getvalue()); self.assertEqual(token.read_bytes(), before_bytes)
                self.assertEqual(all_counts(case), before)
            with redirect_stdout(StringIO()) as output:code = cli(args + ['capability'])
            self.assertEqual(code, 0, output.getvalue()); self.assertTrue(json.loads(output.getvalue())['supported'])
            with redirect_stdout(StringIO()) as output:code = grant_cli(['--data-root', str(case['grant'].root), 'identity'])
            self.assertEqual(code, 0, output.getvalue()); self.assertTrue(json.loads(output.getvalue())['history_supported'])
            with redirect_stdout(StringIO()) as output:code = grant_cli(['--data-root', str(case['grant'].root), 'revoke', '--grant-id', record['grant_id']])
            self.assertEqual(code, 0, output.getvalue()); self.assertEqual(json.loads(output.getvalue())['state'], 'REVOKED')
            with redirect_stdout(StringIO()) as output:code = cli(args + ['pages'])
            self.assertEqual(code, 1, output.getvalue())

    def test_actual_generation_change_and_expired_read_do_not_reuse_cursor_access(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'generation') as case:
            setup(case); status, first = call(case); self.assertEqual(status, 200, first)
            db = case['runtime'].database._connection
            original = case['grant'].root / 'forge.db'
            replacement = case['grant'].root / 'replacement.fixture.db'
            retained = case['grant'].root / 'original.fixture.db'
            with closing(sqlite3.connect(replacement)) as destination:
                db.backup(destination)
            os.replace(original, retained); os.replace(replacement, original)
            try:
                before = all_counts(case); status, result = call(case, '/pages/' + first['cursor'])
                self.assertEqual(status, 409, result); self.assertEqual(result['error']['code'], 'RESYNC_REQUIRED')
                self.assertEqual(all_counts(case), before)
            finally:
                original.unlink(); os.replace(retained, original)
            records = case['grant']._records()
            for record in records:
                if record['permissions'] == ['READ']:record['expires_at'] = '2000-01-01T00:00:00+00:00'
            case['grant']._save(records)
            before = all_counts(case); status, result = call(case, '/pages/' + first['cursor'])
            self.assertEqual(status, 401, result); self.assertEqual(all_counts(case), before)
