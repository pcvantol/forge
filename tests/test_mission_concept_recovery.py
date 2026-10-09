"""Actual kill/restart of generation and compound approval across durable stores."""
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

spec=spec_from_file_location('mission_recovery',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_mission_concept_recovery.py')
driver=module_from_spec(spec);spec.loader.exec_module(driver)


class MissionConceptRecoveryTests(unittest.TestCase):
    def test_real_os_crashes_and_lost_response_generation(self):
        for stage in ('crash-before-provider','crash-after-result','lost-response'):
            with self.subTest(stage=stage),TemporaryDirectory() as tmp:
                result=driver.process_case(Path(tmp)/'generation',stage,'generation')
                self.assertEqual(result['result'],'PASS')

    def test_real_os_crashes_between_compound_effects_and_lost_response(self):
        for stage in ('crash-before-registration','crash-after-registration','crash-business-between-stores','crash-after-business',
                      'crash-architecture-between-stores','crash-after-architecture','crash-after-intake','lost-response'):
            with self.subTest(stage=stage),TemporaryDirectory() as tmp:
                result=driver.process_case(Path(tmp)/'approval',stage,'approval')
                self.assertEqual(result['result'],'PASS')

    def test_current_os_signer_drift_between_effects_stops_and_recovers_original_intent(self):
        from unittest.mock import patch
        from forge.operator_identity import NamedOperatorIdentity
        ready,_=driver.cases();q=ready.qual
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'signer-drift';body=driver.prepare_case(root,'approval')
            with q.http(root) as port:
                def identity():
                    return (NamedOperatorIdentity('different-current-operator',502)
                            if driver.counts(root)['governance_decisions'] else q.utils.fixture.IDENTITY)
                with patch.object(q.utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity):
                    status,out=ready.call(port,root/'owner.private','POST','/v1/mission-concepts/recovery-chat/approve',body)
                self.assertEqual(status,403,out)
                actual=driver.counts(root)
                self.assertEqual(actual['governance_decisions'],1)
                self.assertEqual(actual['candidate_decision_receipts'],0)
                self.assertEqual(actual['mission_state'],0)
                status,pending=ready.call(port,root/'owner.private','GET','/v1/mission-concepts/recovery-chat/operations/approve-recovery')
                self.assertEqual(status,200,pending);self.assertEqual(pending['state'],'PENDING')
                status,restored=ready.call(port,root/'owner.private','POST','/v1/mission-concepts/recovery-chat/approve',body)
                self.assertEqual(status,200,restored)
                self.assertEqual(driver.counts(root)['governance_decisions'],2)
                self.assertEqual(driver.counts(root)['mission_state'],1)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_concurrent_confirmation_rejects_contender_without_duplicate_effects(self):
        from unittest.mock import patch
        from threading import Event,Thread
        import time
        ready,_=driver.cases();q=ready.qual
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'concurrent';body=driver.prepare_case(root,'approval')
            arrived,release=Event(),Event();result=[]
            with q.http(root) as port:
                def identity():
                    if driver.counts(root)['advisory_candidate_intents'] and not arrived.is_set():
                        arrived.set();self.assertTrue(release.wait(10))
                    return q.utils.fixture.IDENTITY
                with patch.object(q.utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity):
                    worker=Thread(target=lambda:result.append(ready.call(port,root/'owner.private','POST',
                        '/v1/mission-concepts/recovery-chat/approve',body)))
                    worker.start()
                    try:
                        self.assertTrue(arrived.wait(10));started=time.monotonic()
                        status,out=ready.call(port,root/'owner.private','POST','/v1/mission-concepts/recovery-chat/approve',
                                             {**body,'operation_id':'contender'})
                        self.assertEqual(status,409,out);self.assertLess(time.monotonic()-started,1)
                    finally:
                        release.set();worker.join(15)
                self.assertFalse(worker.is_alive());self.assertEqual(result[0][0],200,result)
                actual=driver.counts(root)
                self.assertEqual(actual['advisory_candidate_intents'],1)
                self.assertEqual(actual['governance_decisions'],2)
                self.assertEqual(actual['mission_state'],1)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
