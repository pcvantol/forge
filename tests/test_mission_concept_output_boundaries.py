"""Rejected external model outputs preserve the exact prior approved definition."""
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from forge.mission_concept_contract import CONTRACT

spec=spec_from_file_location('mission_output_recovery',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_mission_concept_recovery.py')
driver=module_from_spec(spec);spec.loader.exec_module(driver)


class MissionConceptOutputBoundaryTests(unittest.TestCase):
    def test_malformed_injected_foreign_incomplete_outputs_preserve_approved_version(self):
        ready,content=driver.cases();q=ready.qual
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'outputs';body=driver.prepare_case(root,'approval')
            with q.http(root) as port:
                token=root/'owner.private';base='/v1/mission-concepts/recovery-chat'
                status,approved=ready.call(port,token,'POST',base+'/approve',body)
                self.assertEqual(status,200,approved)
                _,original=ready.call(port,token,'GET',base+'/operations/approve-recovery')
                original_counts=driver.counts(root)
                definition=content.MissionConceptContractTests().output()['definition']
                bad_outputs=[{**definition,'actor':'primary_operator'},
                    {**definition,'work_kind':'UNBOUNDED_ADMIN'},
                    {**definition,'dependencies':['foreign-candidate'],
                     'dependency_reasons':{'foreign-candidate':'Invented external predecessor not authorized here.'}},
                    {**definition,'acceptance_criteria':[],'questions':[]},
                    {**definition,'objective':'Bearer abcdefghijklmnop'},
                    {**definition,'effect_policy':{'mode':'UNRESTRICTED'}}]
                _,history=ready.call(port,token,'GET',base)
                ledger_revision=history['revision']
                for index,bad in enumerate(bad_outputs):
                    with self.subTest(index=index):
                        ready.model_output(root,bad)
                        _,context=ready.call(port,token,'GET',base+'/context')
                        request={k:context['context'][k] for k in ('instance_id','project_id','repository_id')}
                        request.update(contract_version=CONTRACT,conversation_id='recovery-chat',
                            turn_id='invalid-'+str(index),expected_revision=ledger_revision,
                            context_revision=context['context_revision'],selected_sources=[],
                            advisor_kind='ARCHITECTURE',objective='Refine the current portal acceptance criteria.')
                        status,result=ready.call(port,token,'POST',base+'/turns',request)
                        self.assertEqual(status,200,result)
                        self.assertEqual(result['original_turn']['status'],'FAILED')
                        self.assertIsNone(result['original_turn']['outcome']['output'])
                        ledger_revision=result['current_revision']
                        _,current=ready.call(port,token,'GET',base+'/operations/approve-recovery')
                        self.assertEqual(current['state'],'COMPLETE')
                        self.assertTrue(current['source_fresh'])
                        self.assertEqual(current['frozen_package'],original['frozen_package'])
                        status,package=ready.call(port,token,'GET',base+'/package')
                        self.assertEqual(status,200,package)
                        self.assertEqual(package['package_digest'],body['package_digest'])
                        self.assertEqual(driver.counts(root),original_counts)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),7)
