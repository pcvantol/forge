"""Deterministic security tests for the OpenAI Action Derivation transport."""
from __future__ import annotations
import json
import unittest
from urllib.error import URLError
from forge.models import PlanningSnapshot
from forge.planner import (OpenAIPlanningProviderConfiguration, OpenAIResponsesPlanningProvider,
    ProviderDerivationRequest, ProviderSubmissionAmbiguous)
from forge.provider_security import SecretReference, SecretState
from tests.test_action_derivation import input_model

class Resolver:
 def __init__(self, secret='test-secret'): self.secret=secret
 def resolve(self, reference): return SecretState.RESOLVABLE,self.secret
class Response:
 def __init__(self, body): self.body=body
 def read(self): return json.dumps(self.body).encode()
 def __enter__(self): return self
 def __exit__(self,*args): return None
def proposal():
 return {'kind':'proposals','proposals':[{'logical_action_id':'derive-contract','scope':'planner-contract','objective':'Implement bounded action derivation.','dependencies':[],'write_scopes':['forge/planner'],'expected_evidence':['unit test'],'validation_strategy':['unit test'],'priority':1,'postponed':False,'human_gates':['architecture-review'],'risk_inputs':['scope-drift'],'source_evidence_refs':['mission_state','repository_truth']},{'logical_action_id':'derive-docs','scope':'planner-docs','objective':'Document bounded derivation.','dependencies':['derive-contract'],'write_scopes':['forge/planner'],'expected_evidence':['unit test'],'validation_strategy':['unit test'],'priority':2,'postponed':False,'human_gates':['architecture-review'],'risk_inputs':['scope-drift'],'source_evidence_refs':['mission_state','repository_truth']}]}
class OpenAIActionDerivationTests(unittest.TestCase):
 def setUp(self):
  self.snapshot=PlanningSnapshot.from_planner_input(input_model())
  self.request=ProviderDerivationRequest('derive-1',self.snapshot,'openai-planning','gpt-test')
 def adapter(self, opener, enabled=True):
  return OpenAIResponsesPlanningProvider(OpenAIPlanningProviderConfiguration('openai-planning','gpt-test',SecretReference('keychain','//forge.openai/planning'),enabled=enabled),Resolver(),opener=opener)
 def test_strict_structured_output_bounded_redacted_provenance(self):
  captured=[]
  def opener(request, timeout):
   captured.append(request); return Response({'id':'resp_123','status':'completed','usage':{'input_tokens':12,'output_tokens':34},'output':[{'content':[{'text':json.dumps(proposal())}]}]})
  response=self.adapter(opener).invoke(self.request)
  self.assertEqual(len(response.proposals or ()),2); self.assertEqual(response.evidence.response_id,'resp_123')
  wire=captured[0].data.decode(); headers=dict(captured[0].header_items())
  self.assertNotIn('test-secret',wire); self.assertIn('"store":false',wire); self.assertIn('json_schema',wire); self.assertNotIn('Authorization',wire)
  self.assertIn('Bearer test-secret',headers.get('Authorization',''))
 def test_disabled_model_mismatch_and_malformed_output_fail_closed(self):
  with self.assertRaises(PermissionError): self.adapter(lambda *_: None,enabled=False).invoke(self.request)
  wrong=ProviderDerivationRequest('derive-1',self.snapshot,'openai-planning','other-model')
  with self.assertRaises(ValueError): self.adapter(lambda *_: None).invoke(wrong)
  response=self.adapter(lambda *args,**kwargs: Response({'id':'resp_bad','status':'completed','output':[{'content':[{'text':'not-json'}]}]})).invoke(self.request)
  self.assertIsNone(response.proposals); self.assertIsNotNone(response.governance_refinement); self.assertEqual(response.evidence.status,'contract_invalid')
 def test_ambiguous_submission_is_never_retried(self):
  calls=[]
  def opener(*args,**kwargs): calls.append(1); raise URLError('network')
  with self.assertRaises(ProviderSubmissionAmbiguous): self.adapter(opener).invoke(self.request)
  self.assertEqual(calls,[1])
if __name__ == '__main__': unittest.main()
