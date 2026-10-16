"""Preserve primary command failures and detect only the exact restored authority fault."""
from copy import deepcopy
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

spec=spec_from_file_location('genesis_qualifier',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_installed_genesis_bootstrap.py')
qualification=module_from_spec(spec);spec.loader.exec_module(qualification)


class GenesisQualificationEvidenceTest(unittest.TestCase):
    def test_original_nonzero_and_timeout_reports_survive_capture_and_report_retention_errors(self):
        for primary in ({'category':'COMMAND_NONZERO','observed_exit':7},{'category':'COMMAND_TIMEOUT','observed_exit':None}):
            with TemporaryDirectory() as tmp:
                root=Path(tmp);report={'case':'original','primary_failure':primary,'capture_complete':False,'secondary_failures':[{'stage':'private-retention','category':'OSError'}]}
                with patch.object(qualification.C.BINDING.CAPTURE,'capture',return_value=(deepcopy(report),b'',b'')),patch.object(qualification.C.BINDING.CAPTURE,'retain',side_effect=OSError('synthetic report retention failure')):
                    with self.assertRaises(RuntimeError) as error:
                        qualification.capture_command(Path('/private/python'),['-m','forge'],root,root,'original')
                self.assertEqual(error.exception.capture_report['primary_failure'],primary)
                self.assertEqual(len(error.exception.capture_report['secondary_failures']),2)
                self.assertTrue(error.exception.__notes__)

    def test_success_report_is_private_and_no_primary_is_overwritten_by_late_report_failure(self):
        report={'case':'original','primary_failure':None,'capture_complete':True,'secondary_failures':[]}
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(qualification.C.BINDING.CAPTURE,'capture',return_value=(deepcopy(report),b'{"result":"original"}',b'')):
                self.assertEqual(qualification.capture_command(Path('/private/python'),['-m','forge'],root,root,'original'),{'result':'original'})
                self.assertEqual((root/'original.capture.private.json').stat().st_mode&0o777,0o600)
            with patch.object(qualification.C.BINDING.CAPTURE,'capture',return_value=(deepcopy(report),b'{}',b'')),patch.object(qualification.C.BINDING.CAPTURE,'retain',side_effect=OSError('report failure')):
                with self.assertRaises(OSError) as error:qualification.capture_command(Path('/private/python'),['-m','forge'],root,root,'original')
                self.assertIsNone(error.exception.capture_report['primary_failure'])

    def test_fault_red_requires_exact_original_get200_and_false_execution_authority_path(self):
        schema={'type':'object','properties':{'execution_authorized':{'const':False},'other':{'const':'good'}}}
        detector=next(Draft202012Validator(schema).iter_errors({'execution_authorized':True,'other':'good'}))
        observation={'path':'/original','status':200,'execution_authorized':True}
        self.assertTrue(qualification.exact_fault_red(detector,observation,'/original'))
        for bad in ({**observation,'status':403},{**observation,'status':503},{**observation,'execution_authorized':False},{**observation,'path':'/foreign'}):
            self.assertFalse(qualification.exact_fault_red(detector,bad,'/original'))
        other=next(Draft202012Validator(schema).iter_errors({'execution_authorized':False,'other':'bad'}))
        self.assertFalse(qualification.exact_fault_red(other,observation,'/original'))

    def test_exact_fault_detector_uses_actual_packaged_response_schema(self):
        import json
        from tests.test_genesis_bootstrap_contract import plan_fixture
        from forge.genesis_bootstrap_contract import plan_document,CONTRACT
        root=Path(__file__).resolve().parents[1]
        schema=json.loads((root/'forge/api/genesis-bootstrap-v1.json').read_text())
        response_schema={'$schema':schema['$schema'],'$defs':schema['$defs'],'$ref':'#/$defs/Response'}
        plan=plan_document(*plan_fixture())
        response={'summary':'Synthetic schema detector test only.','contract_version':CONTRACT,'instance_id':plan['instance_id'],'principal_id':plan['principal_id'],'audience':plan['audience'],'dossier_id':plan['dossier_id'],'plan':plan,'effect_decision_revision':0,'effect_history':[],'original_decision':None,'effect_decision_eligible':False,'inapplicability_reasons':['CURRENT_CONTENT_AUTHORITY_REQUIRED'],'effect_decision_currently_applicable':False,'state':'EP_ADMISSION_REQUIRED','execution_authorized':False,'target_write':'NOT_PERFORMED','ep_credential':'NOT_ISSUED'}
        Draft202012Validator(response_schema).validate(response)
        response['execution_authorized']=True
        with self.assertRaises(ValidationError) as caught:Draft202012Validator(response_schema).validate(response)
        self.assertTrue(qualification.exact_fault_red(caught.exception,{'path':'/original','status':200,'execution_authorized':True},'/original'))
        response['execution_authorized']=False;response['target_write']='UNRELATED_INVALID'
        with self.assertRaises(ValidationError) as caught:Draft202012Validator(response_schema).validate(response)
        self.assertFalse(qualification.exact_fault_red(caught.exception,{'path':'/original','status':200,'execution_authorized':True},'/original'))
