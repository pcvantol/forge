from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
spec=spec_from_file_location('approved_release_chain',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_workset_release_chain.py')
chain=module_from_spec(spec);spec.loader.exec_module(chain)
class ApprovedReleaseChainTests(unittest.TestCase):
    def test_actual_pre_admitted_chat_a_b_runtime_final_acceptance_and_idle(self):
        with TemporaryDirectory() as tmp:
            result=chain.flow(Path(tmp)/'flow')
            self.assertEqual([s['status'] for s in result[-1]['states']],['COMPLETED','COMPLETED'])

    def test_real_cold_process_chain_restores_existing_claims_and_admissions(self):
        with TemporaryDirectory() as tmp:
            result=chain.flow(Path(tmp)/'process',phase_runner=chain.process_phase)
            self.assertEqual(result[-1]['allocations'],2)
            self.assertGreater(len({r['pid'] for r in result}),5)
            self.assertEqual(result[-1]['workset']['consumed_activations'],2)

    def test_real_original_release_grant_revocation_fails_positive_chain(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(AssertionError):
                chain.flow(Path(tmp)/'revoke',failure_control=True)

    def test_disarm_future_release_preserves_accepted_a_and_pre_admitted_b(self):
        with TemporaryDirectory() as tmp:
            result=chain.flow(Path(tmp)/'withdraw',disarm=True)
            self.assertEqual([s['status'] for s in result[-1]['states']],['COMPLETED','APPROVED_PLANNABLE'])
            self.assertEqual(result[-1]['workset']['consumed_activations'],1)

    def test_actual_documentation_and_design_effect_boundaries_survive_release_runtime(self):
        for scenario in ('effect-documentation','effect-design-report'):
            with self.subTest(scenario=scenario),TemporaryDirectory() as tmp:
                result=chain.flow(Path(tmp)/scenario,scenario)
                self.assertEqual([s['status'] for s in result[-1]['states']],['COMPLETED','COMPLETED'])

    def test_real_accepted_a_exhausts_single_activation_and_b_readback_matches_runtime(self):
        with TemporaryDirectory() as tmp:
            result=chain.flow(Path(tmp)/'finite-one',maximum_activations=1,phase_runner=chain.process_phase)
            self.assertEqual([s['status'] for s in result[-1]['states']],['COMPLETED','APPROVED_PLANNABLE'])
            self.assertEqual(result[-1]['read']['continuation']['state'],'BLOCKED')
