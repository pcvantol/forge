from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from test_workset_release_chain import chain
class ApprovedReleaseConcurrencyTests(unittest.TestCase):
    def test_true_concurrent_process_confirmations_keep_one_exact_workset(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(chain.race(Path(tmp)/'release')['result'],'REAL_PROCESS_RACE_PASS')
    def test_true_concurrent_scheduler_processes_keep_one_activation_claim_and_submit(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(chain.race(Path(tmp)/'activation',activation=True)['consumed_activations'],1)
    def test_original_grant_revocation_wins_before_actual_start_without_resetting_claim(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(chain.race(Path(tmp)/'revoke',activation=True,revoke_before_start=True)['consumed_activations'],1)

    def test_real_concurrent_disarm_and_cold_same_key_retry_preserve_one_receipt(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(chain.race(Path(tmp)/'withdraw',withdraw=True)['result'],'REAL_PROCESS_RACE_PASS')
