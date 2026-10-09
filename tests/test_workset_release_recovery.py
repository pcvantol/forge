from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from test_workset_release_chain import chain
class ApprovedReleaseRecoveryTests(unittest.TestCase):
    def test_true_process_termination_at_canonical_business_split_recovers_once(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(chain.crash_recovery(Path(tmp)/'split','crash-business-between-stores')['result'],'COLD_RECOVERY_PASS')
    def test_business_effect_preserved_when_original_grant_revoked_before_recovery(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(chain.crash_recovery(Path(tmp)/'revoke','crash-after-business',revoke_between=True)['result'],'WITHDRAWN_OR_REVOKED_REMAINDER_DENIED')
    def test_disarm_preempts_incomplete_release_without_restoring_it(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(chain.crash_recovery(Path(tmp)/'withdraw','crash-after-business',withdraw_between=True)['result'],'WITHDRAWN_OR_REVOKED_REMAINDER_DENIED')

    def test_true_process_crash_and_lost_reply_at_each_remaining_effect_boundary(self):
        for stage in ('crash-before-intent','crash-after-intent','crash-after-propose',
                      'crash-before-business','crash-after-business','crash-architecture-between-stores',
                      'crash-after-architecture','crash-after-arm','lost-response'):
            with self.subTest(stage=stage),TemporaryDirectory() as tmp:
                self.assertEqual(chain.crash_recovery(Path(tmp)/stage,stage)['result'],'COLD_RECOVERY_PASS')
