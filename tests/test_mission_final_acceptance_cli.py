"""Supported setup/read/confirm/recover parity; derived inputs, no handwritten approval JSON."""
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from mission_final_acceptance_fixture import pending_a, state_counts
from forge.mission_final_acceptance_cli import main as consumer_cli
from forge.mission_final_acceptance_grant import main as grant_cli


def invoke(main, arguments):
    with patch('sys.stdout', new_callable=StringIO) as output:
        code = main(arguments)
    return code, json.loads(output.getvalue())


class MissionFinalAcceptanceCLITests(unittest.TestCase):
    def test_real_setup_derives_scope_and_revision_then_read_confirm_and_original_operation(self):
        with TemporaryDirectory() as temporary, pending_a(Path(temporary) / 'cli') as case:
            root = case['root']
            setup = ['--data-root', str(root / 'runtime')]
            before = state_counts(case)
            for action in ('identity', 'inspect'):
                extra = [] if action == 'identity' else ['--mission-id', case['mission_id']]
                code, result = invoke(grant_cli, setup + [action] + extra)
                self.assertEqual(0, code, result)
                self.assertTrue(result['read_only'])
                self.assertEqual(before, state_counts(case))
            code, issued = invoke(grant_cli, setup + ['issue', '--mission-id', case['mission_id'],
                '--permission', 'READ', '--permission', 'ACCEPT', '--maximum-acceptances', '1',
                '--expires-at', (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                '--token-file', str(root / 'cli.private')])
            self.assertEqual(0, code, issued)
            self.assertEqual(1, issued['maximum_acceptances'])
            self.assertEqual([case['mission_id']], [m['mission_id'] for m in issued['missions']])
            prefix = setup + ['--token-file', str(root / 'cli.private')]
            code, capability = invoke(consumer_cli, prefix + ['capability'])
            self.assertEqual(0, code, capability)
            self.assertTrue(capability['acceptance_supported'])
            shown = root / 'shown.private.json'
            code, detail = invoke(consumer_cli, prefix + ['show', '--mission-id', case['mission_id'], '--output', str(shown)])
            self.assertEqual(0, code, detail)
            self.assertEqual(before, state_counts(case))
            request = ['accept', '--shown-package', str(shown), '--operation-id', 'cli-accept',
                       '--reason', 'Accepteer de bewezen uitkomst zonder nieuwe scopegoedkeuring.']
            code, rejected = invoke(consumer_cli, prefix + request)
            self.assertEqual(1, code, rejected)
            self.assertEqual(before, state_counts(case))
            code, accepted = invoke(consumer_cli, prefix + request + ['--confirm'])
            self.assertEqual(0, code, accepted)
            self.assertEqual('COMPLETE', accepted['state'])
            after = state_counts(case)
            code, readback = invoke(consumer_cli, prefix + ['operation', '--mission-id', case['mission_id'], '--operation-id', 'cli-accept'])
            self.assertEqual(0, code, readback)
            self.assertEqual(accepted['original_receipt'], readback['original_receipt'])
            self.assertEqual(after, state_counts(case))
            code, revoked = invoke(grant_cli, setup + ['revoke', '--grant-id', issued['grant_id']])
            self.assertEqual(0, code, revoked)
            code, denied = invoke(consumer_cli, prefix + request + ['--confirm'])
            self.assertEqual(1, code, denied)
            self.assertEqual(after, state_counts(case))
            code, invalid = invoke(consumer_cli, setup + ['--token-file', str(root / 'missing.private'), 'capability'])
            self.assertEqual(1, code, invalid)
            code, invalid = invoke(grant_cli, setup + ['revoke', '--grant-id', 'unknown-grant'])
            self.assertEqual(1, code, invalid)
