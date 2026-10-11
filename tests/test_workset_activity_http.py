"""Actual canonical ABC/D owner services; activity cannot mutate them."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from workset_order_fixture import order_case, counts

BASE = '/v1/approved-workset-activity'


class ActivityHTTPTests(unittest.TestCase):
    def test_initial_activity_uses_actual_scoped_read_and_leaves_all_effects_unchanged(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'activity') as case:
            from forge.workset_activity_grant import provision_key
            provision_key(case['grant'].root, case['grant'].instance_id)
            before = counts(case)
            status, output = case['ready'].call(case['port'], case['root'] / 'order.private',
                                               'GET', BASE + '/' + case['key'] + '/pages')
            self.assertEqual(status, 200, output)
            self.assertEqual(output['contract_version'], 'forge-workset-activity/v1')
            self.assertTrue(output['read_only'])
            self.assertTrue(output['events'])
            self.assertEqual(counts(case), before)

    def test_missing_capability_key_stays_unsupported_without_provisioning_on_read(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'unsupported') as case:
            from forge.workset_activity_grant import key_path
            before = counts(case)
            status, capability = case['ready'].call(case['port'], case['root'] / 'order.private', 'GET', BASE)
            self.assertEqual(status, 200, capability); self.assertFalse(capability['supported'])
            status, result = case['ready'].call(case['port'], case['root'] / 'order.private', 'GET', BASE + '/' + case['key'] + '/pages')
            self.assertEqual(status, 503, result); self.assertEqual(result['completeness'], 'PARTIAL')
            self.assertFalse(key_path(case['grant'].root).exists()); self.assertEqual(counts(case), before)
