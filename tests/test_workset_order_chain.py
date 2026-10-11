from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.util import spec_from_file_location, module_from_spec
import unittest

spec = spec_from_file_location('actual_order_chain', Path(__file__).resolve().parents[1] /
                              'scripts/qualification/qualify_workset_order_chain.py')
order_chain = module_from_spec(spec); spec.loader.exec_module(order_chain)


class WorksetOrderChainTests(unittest.TestCase):
    def test_actual_a_c_b_same_ids_consumption_decisions_and_idle(self):
        with TemporaryDirectory() as tmp:
            records = order_chain.flow(Path(tmp) / 'a-c-b')
            self.assertEqual([s['status'] for s in records[-1]['states']], ['COMPLETED'] * 3)

    def test_revoked_order_authority_keeps_running_a_and_blocks_future_without_fallback(self):
        with TemporaryDirectory() as tmp:
            records = order_chain.flow(Path(tmp) / 'revoke', revoke_order=True)
            self.assertEqual(records[-1]['states'][0]['status'], 'COMPLETED')
            self.assertEqual(records[-1]['workset']['consumed_activations'], 1)

    def test_reorder_does_not_create_fresh_activation_allowance(self):
        with TemporaryDirectory() as tmp:
            records = order_chain.flow(Path(tmp) / 'finite', ceiling=2)
            self.assertEqual(records[-1]['workset']['consumed_activations'], 2)
            self.assertEqual(records[-1]['states'][1]['status'], 'APPROVED_PLANNABLE')
