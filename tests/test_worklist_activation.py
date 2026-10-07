from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

spec=spec_from_file_location('worklist_activation_qualification',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_installed_worklist_activation.py')
qual=module_from_spec(spec);spec.loader.exec_module(qual)

class WorklistActivationTests(unittest.TestCase):
    def test_real_two_candidates_released_before_a_then_serial_activation_final_acceptance_idle(self):
        for scenario in qual.utils._EFFECT_BASE_SCENARIOS:
            with self.subTest(scenario=scenario),TemporaryDirectory() as tmp:
                records=qual.source_flow(Path(tmp)/'flow',scenario)
                self.assertEqual(records[-1]['workset']['consumed_activations'],2)
                self.assertEqual([s['status'] for s in records[-1]['states']],['COMPLETED','COMPLETED'])

    def test_current_authority_scope_release_and_expiry_denials_have_zero_effects(self):
        for case in ('unapproved','expired','hold','revoke','disarm','stale','operator-revoked'):
            with self.subTest(case=case),TemporaryDirectory() as tmp:
                record=qual.source_denial(Path(tmp)/'denial',case)
                self.assertEqual(record['after']['allocations'],0)

    def test_lost_ep_acknowledgement_preserves_one_submission_per_mission(self):
        with TemporaryDirectory() as tmp:
            records=qual.source_flow(Path(tmp)/'lost-ack','effect-read-only-lost-ack')
            self.assertEqual(records[-1]['provider_invocations'],2)

    def test_positive_qualification_gate_rejects_revoked_before_b(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(AssertionError):
                qual.source_flow(Path(tmp)/'controlled-failure','effect-read-only',failure_control=True)

    def test_explicit_empty_workset_is_bounded_idle_with_only_advisory_candidates(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(qual.empty_flow(Path(tmp)/'empty')['allocations'],0)

    def test_finite_allowance_does_not_unlock_b_or_refresh_consumed_claims(self):
        with TemporaryDirectory() as tmp:
            records=qual.source_flow(Path(tmp)/'budget','effect-read-only',budget=True)
            self.assertEqual(records[-1]['workset']['consumed_activations'],1)

    def test_failed_or_tampered_evidence_cannot_unlock_preapproved_b(self):
        for case in ('failed-evidence','tampered-evidence'):
            with self.subTest(case=case),TemporaryDirectory() as tmp:
                self.assertEqual(qual.evidence_denial(Path(tmp)/case,case)['allocations'],1)
