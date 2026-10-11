"""Coherent synthetic corruption cannot change original intent or restore old order."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from workset_order_fixture import order_case, call, shown, counts, command
from forge.advisory_contract import digest
from forge.models.criterion_observation import canonical_digest


class WorksetOrderIntegrityTests(unittest.TestCase):
    def test_original_request_and_receipt_manipulation_or_orphan_history_fail_closed(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'integrity') as case:
            request = command(shown(case)); status, applied = call(case, 'POST', '/confirm', request)
            self.assertEqual(status, 200, applied)
            db = case['runtime'].database._connection
            original = json.loads(db.execute('SELECT document FROM approved_worksets WHERE workset_id=?', (case['key'],)).fetchone()[0])
            def changed_reason(value):
                intent = value['order_intents'][request['operation_id']]
                intent['request']['reason'] = 'Changed retrospective approval rationale.'
                intent['request_digest'] = digest(intent['request'])
            def lost_intents(value):
                value['order_intents'] = {}
            def fake_pending(value):
                intent = value['order_intents'][request['operation_id']]
                intent['state'] = 'PENDING'; intent['receipt'] = None
            def bool_receipt(value):
                amendment = value['order_amendments'][0]
                amendment['receipt']['fixed_prefix'] = True
                amendment['receipt_digest'] = canonical_digest(amendment['receipt'])
                value['order_intents'][request['operation_id']]['receipt'] = deepcopy(amendment['receipt'])
            def bool_revision(value):
                value['revision'] = True
            for mutation in (changed_reason, lost_intents, fake_pending, bool_receipt, bool_revision):
                with self.subTest(mutation=mutation.__name__):
                    value = deepcopy(original); mutation(value)
                    with db:
                        db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?', (json.dumps(value), case['key']))
                    before = counts(case)
                    status, _ = call(case, 'GET', '/operations/' + request['operation_id'])
                    self.assertIn(status, (409, 503))
                    status, _ = call(case, 'GET')
                    self.assertIn(status, (409, 503))
                    self.assertEqual(counts(case), before)
            with db:
                db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?', (json.dumps(original), case['key']))
            status, read = call(case, 'GET', '/operations/' + request['operation_id'])
            self.assertEqual(status, 200, read)
            self.assertEqual(read['original_receipt'], applied['original_receipt'])

    def test_same_operation_id_different_package_or_reason_conflicts_without_new_decisions(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'conflict') as case:
            request = command(shown(case)); status, applied = call(case, 'POST', '/confirm', request)
            self.assertEqual(status, 200, applied)
            before = counts(case)
            for changed in ({**request, 'reason': 'Another rationale.'}, {**request, 'package_digest': 'sha256:' + 'a' * 64}):
                status, _ = call(case, 'POST', '/confirm', changed)
                self.assertIn(status, (403, 409))
                self.assertEqual(counts(case), before)
