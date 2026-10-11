"""Supported owner setup and numbered CLI; no handwritten governance packages."""
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from workset_order_fixture import order_case, counts
from forge.workset_order_cli import main as cli
from forge.workset_order_grant import main as setup


def invoke(main, arguments):
    with redirect_stdout(StringIO()) as stream:
        code = main(arguments)
    return code, json.loads(stream.getvalue())


class WorksetOrderCLIGrantTests(unittest.TestCase):
    def test_actual_setup_numbered_preview_explicit_confirmation_original_and_current_order(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'cli') as case:
            root = case['root']; key = case['key']
            owner = ['--data-root', str(root / 'runtime')]
            before = counts(case)
            for action in (['identity'], ['inspect', '--workset-id', key]):
                code, output = invoke(setup, owner + action)
                self.assertEqual(code, 0, output)
            token = root / 'cli-order.private'
            code, record = invoke(setup, owner + ['issue', '--workset-id', key, '--permission', 'READ',
                '--permission', 'REORDER', '--maximum-amendments', '2', '--expires-at', case['grant_record']['expires_at'],
                '--token-file', str(token)])
            self.assertEqual(code, 0, record)
            self.assertEqual(counts(case), before)
            prefix = owner + ['--token-file', str(token)]
            for action in (['capability'], ['show']):
                code, output = invoke(cli, prefix + action); self.assertEqual(code, 0, output)
            preview = root / 'shown.private.json'
            code, output = invoke(cli, prefix + ['preview', '--positions', '2', '1', '--output', str(preview)])
            self.assertEqual(code, 0, output)
            self.assertEqual(counts(case), before)
            arguments = prefix + ['confirm', '--shown-package', str(preview), '--operation-id', 'cli-order',
                                  '--reason', 'Eerst C, daarna B; behoud vóórwaarden.']
            code, output = invoke(cli, arguments)
            self.assertEqual(code, 1, output)
            self.assertEqual(counts(case), before)
            code, original = invoke(cli, arguments + ['--confirm'])
            self.assertEqual(code, 0, original)
            code, observed = invoke(cli, prefix + ['operation', '--operation-id', 'cli-order'])
            self.assertEqual(code, 0, observed)
            self.assertEqual(observed['original_receipt'], original['original_receipt'])
            # A later explicit amendment is a new authorised intent, not rollback.
            second = root / 'second.private.json'
            code, output = invoke(cli, prefix + ['preview', '--positions', '2', '1', '--output', str(second)])
            self.assertEqual(code, 0, output)
            code, restored = invoke(cli, prefix + ['confirm', '--shown-package', str(second), '--operation-id', 'restore-order',
                '--reason', 'Expliciet terug naar B vóór C.', '--confirm'])
            self.assertEqual(code, 0, restored)
            self.assertEqual(restored['current']['current_order'], case['order'])
            final = counts(case)
            code, observed = invoke(cli, prefix + ['operation', '--operation-id', 'cli-order'])
            self.assertEqual(code, 0, observed)
            self.assertEqual(observed['original_receipt'], original['original_receipt'])
            self.assertEqual(observed['current']['order_revision'], 2)
            self.assertEqual(counts(case), final)
            code, limits = invoke(cli, prefix + ['capability'])
            self.assertEqual(code, 0, limits)
            self.assertEqual(limits['consumed_amendments'], 2)
            self.assertEqual(limits['remaining_amendments'], 0)
            code, output = invoke(cli, prefix + ['preview', '--positions', '2', '1', '--output', str(root / 'denied.private')])
            self.assertEqual(code, 0, output)
            self.assertFalse(output['reorder_supported'])
            self.assertIn('ORDER_ALLOWANCE_EXHAUSTED', output['blocking_reasons'])
            code, output = invoke(cli, prefix + ['confirm', '--shown-package', str(root / 'denied.private'), '--operation-id', 'over-limit',
                '--reason', 'Cannot extend the original ceiling.', '--confirm'])
            self.assertEqual(code, 1, output)
            self.assertEqual(counts(case), final)
            code, output = invoke(setup, owner + ['revoke', '--grant-id', record['grant_id']])
            self.assertEqual(code, 0, output)
            code, output = invoke(cli, prefix + ['show'])
            self.assertEqual(code, 1, output)

    def test_actual_private_grant_bounds_integrity_and_operator_revocation_fail_closed(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'grant') as case:
            grant = case['grant']; root = case['root']; record = case['grant_record']
            token = 'Bearer ' + (root / 'order.private').read_text().strip()
            fields = {k: record[k] for k in ('principal_id', 'project_id', 'repository_id', 'worksets', 'maximum_amendments', 'expires_at')}
            self.assertEqual(grant.authorize(token, case['key'], 'REORDER').grant_id, record['grant_id'])
            for invalid in (None, 'Basic x', 'Bearer ', 'Bearer bad\nvalue', 'Bearer ' + 'x' * 257):
                self.assertIsNone(grant.authenticate(invalid))
            for changed in ({'principal_id': 'unassigned-actor'}, {'project_id': 'foreign'}, {'repository_id': 'foreign'},
                            {'worksets': [{'workset_id': 'outside', 'definition_digest': 'sha256:' + 'a' * 64}]}):
                with self.subTest(changed=changed), self.assertRaises(PermissionError):
                    grant.issue(**{**fields, **changed}, permissions=['READ', 'REORDER'], token_path=root / 'wrong.private')
            for expires in ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                            (datetime.now(UTC) + timedelta(days=31)).isoformat(),
                            (datetime.now(UTC) + timedelta(hours=2)).isoformat()):
                with self.subTest(expires=expires), self.assertRaises(ValueError):
                    grant.issue(**{**fields, 'expires_at': expires}, permissions=['READ', 'REORDER'], token_path=root / 'wrong.private')
            with self.assertRaises(ValueError):
                grant.issue(**fields, permissions=['READ'], token_path=grant.path)
            with self.assertRaises(ValueError):
                grant.revoke('unknown')
            with self.assertRaises(PermissionError):
                grant.authorize(token, 'outside')
            with self.assertRaises(PermissionError):
                grant.authorize(token, case['key'], 'RELEASE')
            original = grant.path.read_bytes()
            # Only negative corruption of this fresh synthetic credential store.
            for field, changed in [('operator_binding_version', True), ('maximum_amendments', True),
                                   ('profile_id', 'foreign'), ('token_digest', 'bad'), ('instance_id', 'foreign')]:
                document = json.loads(original); document['records'][0][field] = changed
                grant.path.write_text(json.dumps(document)); self.assertIsNone(grant.authenticate(token))
            grant.path.write_bytes(original)
            document = json.loads(original); document['records'][0]['expires_at'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            grant.path.write_text(json.dumps(document)); self.assertIsNone(grant.authenticate(token)); grant.path.write_bytes(original)
            before = counts(case)
            with patch.object(grant, '_save', side_effect=OSError('own failed grant publication')):
                with self.assertRaises(OSError):
                    grant.issue(**fields, permissions=['READ'], token_path=root / 'failed-token.private')
            self.assertFalse((root / 'failed-token.private').exists())
            self.assertEqual(counts(case), before)
            context = case['runtime'].repository.operators.context()
            case['runtime'].repository.operators.revoke(context)
            with self.assertRaises(PermissionError):
                grant.authorize(token, case['key'], 'REORDER')
