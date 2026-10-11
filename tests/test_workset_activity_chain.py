"""The original producer chain supplies every positive effect; history only reads."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('activity_chain', ROOT / 'scripts/qualification/qualify_workset_activity_chain.py')
chain = module_from_spec(spec); spec.loader.exec_module(chain)


class ActivityChainTests(unittest.TestCase):
    def test_real_abcd_history_result_wait_acceptance_order_c_and_b(self):
        with TemporaryDirectory() as tmp:
            result = chain.flow(Path(tmp) / 'chain')
            self.assertTrue(result['read_only_activity'])
            self.assertGreater(result['unique_activity_events'], 20)
