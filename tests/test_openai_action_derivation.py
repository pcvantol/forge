"""Security qualification for the bounded OpenAI Responses adapter."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from forge.models import PlanningSnapshot
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.planner import (OpenAIPlanningProviderConfiguration,
    OpenAIResponsesPlanningProvider, ProviderDerivationRequest,
    ProviderSubmissionAmbiguous)
from forge.planner.token_accounting import TokenAccountingUnavailable
from forge.provider_security import (PlanningProviderInvocationPolicy,
    PlanningProviderSecurityService, SecretReference, SecretState)
from forge.runtime.database import RuntimeDatabase
from tests.test_action_derivation import input_model


class Resolver:
 def __init__(self, secret='test-secret'): self.secret=secret; self.status_calls=0; self.resolve_calls=0
 def status(self, reference): self.status_calls+=1; return SecretState.RESOLVABLE
 def resolve(self, reference): self.resolve_calls+=1; return SecretState.RESOLVABLE,self.secret

class FixedCounter:
 """Private test seam; production configuration has no counter parameter."""
 def __init__(self, tokens): self.tokens=tokens
 def count(self, **kwargs): return self.tokens

class Response:
 def __init__(self, body): self.body=body
 def read(self): return json.dumps(self.body).encode()
 def __enter__(self): return self
 def __exit__(self,*args): return None

def proposal():
 return {'kind':'proposals','proposals':[{'logical_action_id':'derive-contract','scope':'planner-contract','objective':'Implement bounded action derivation.','dependencies':[],'write_scopes':['forge/planner'],'expected_evidence':['unit test'],'validation_strategy':['unit test'],'priority':1,'postponed':False,'human_gates':['architecture-review'],'risk_inputs':['scope-drift'],'source_evidence_refs':['mission_state','repository_truth']}]}

class OpenAIActionDerivationTests(unittest.TestCase):
 def setUp(self):
  self.snapshot=PlanningSnapshot.from_planner_input(input_model())

 def adapter(self, opener, *, model='gpt-5.6', input_bound=64000,
             context_bound=128000, output_bound=16000):
  root=tempfile.TemporaryDirectory(); self.addCleanup(root.cleanup)
  db=RuntimeDatabase(Path(root.name),path=Path(root.name)/'runtime.db'); self.addCleanup(db.close)
  resolver=Resolver(); operators=InstallationOperatorService(db,lambda:NamedOperatorIdentity('token-test',501))
  service=PlanningProviderSecurityService(db,resolver,operators)
  service.configure(configuration_id='cfg',provider_id='openai-planning',
                    reference=SecretReference('keychain','//forge.openai/planning'),
                    operator_context=operators.first_bind(),model=model,timeout_seconds=120,
                    input_token_bound=input_bound,context_token_bound=context_bound,
                    output_token_bound=output_bound)
  # Configuration construction proves only canonical policy shape; reset the
  # test secure-store observation before adapter invocation.
  resolver.status_calls=0; resolver.resolve_calls=0
  configuration=OpenAIPlanningProviderConfiguration.from_canonical_g011(service,'openai-planning')
  resolver.status_calls=0; resolver.resolve_calls=0
  request=ProviderDerivationRequest('derive-1',self.snapshot,'openai-planning',model)
  return OpenAIResponsesPlanningProvider(configuration,resolver,opener=opener), resolver, configuration, request

 def test_complete_canonical_request_is_accounted_before_secret_resolution(self):
  captured=[]
  def opener(request, timeout):
   captured.append(request); return Response({'id':'resp_123','status':'completed','usage':{'input_tokens':12,'output_tokens':34},'output':[{'content':[{'text':json.dumps(proposal())}]}]})
  adapter,resolver,configuration,request=self.adapter(opener)
  response=adapter.invoke(request)
  self.assertEqual(len(response.proposals or ()),1)
  self.assertEqual((configuration.current_policy().timeout_seconds,configuration.current_policy().input_token_bound,configuration.current_policy().context_token_bound,configuration.current_policy().output_token_bound),(120,64000,128000,16000))
  self.assertEqual(resolver.status_calls,0); self.assertEqual(resolver.resolve_calls,1)
  wire=captured[0].data.decode(); headers=dict(captured[0].header_items())
  self.assertNotIn('test-secret',wire); self.assertIn('"store":false',wire); self.assertIn('json_schema',wire); self.assertNotIn('Authorization',wire)
  self.assertIn('Bearer test-secret',headers.get('Authorization',''))

 def test_over_bound_and_unknown_accounting_never_touch_secure_store(self):
  calls=[]
  adapter,resolver,_,request=self.adapter(lambda *args,**kwargs: calls.append(1))
  adapter._token_counter=FixedCounter(64001) # private test seam only
  with self.assertRaisesRegex(ValueError,'input token bound'): adapter.invoke(request)
  self.assertEqual((resolver.status_calls,resolver.resolve_calls,calls),(0,0,[]))
  adapter,resolver,_,request=self.adapter(lambda *args,**kwargs: calls.append(1),model='unknown-model')
  with self.assertRaises(TokenAccountingUnavailable): adapter.invoke(request)
  self.assertEqual((resolver.status_calls,resolver.resolve_calls,calls),(0,0,[]))

 def test_configuration_rejects_counter_or_encoding_injection(self):
  adapter,_,configuration,_=self.adapter(lambda *args,**kwargs: None)
  with self.assertRaises(TypeError):
   OpenAIPlanningProviderConfiguration.from_canonical_g011(configuration.policy_service,'openai-planning',FixedCounter(1)) # type: ignore[call-arg]
  with self.assertRaises(TypeError):
   OpenAIPlanningProviderConfiguration(configuration.policy_service,'openai-planning',_from_canonical_g011=True,model_encodings={'gpt-5.6':'forged'}) # type: ignore[call-arg]
  self.assertFalse(hasattr(configuration,'token_counter')); self.assertFalse(hasattr(adapter,'model_encodings'))

 def test_full_request_accounting_includes_protocol_schema_and_unicode(self):
  adapter,_,_,request=self.adapter(lambda *args,**kwargs: None)
  body=adapter._body(request)
  base=adapter._token_counter.count(model='gpt-5.6',request_body=body)
  self.assertIn('text',body); self.assertIn('schema',body['text']['format'])
  body['metadata']={'qualification':'é😊'}
  expanded=adapter._token_counter.count(model='gpt-5.6',request_body=body)
  self.assertGreater(expanded,base)
  self.assertGreater(expanded-base,len('é😊'))

 def test_exact_boundaries_context_and_output_are_local(self):
  calls=[]
  response=lambda *args,**kwargs: (calls.append(1) or Response({'id':'resp','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]}))
  adapter,resolver,configuration,request=self.adapter(response)
  adapter._token_counter=FixedCounter(64000)
  self.assertIsNotNone(adapter.invoke(request)); self.assertEqual((resolver.resolve_calls,calls),(1,[1]))
  adapter,resolver,configuration,request=self.adapter(lambda *args,**kwargs: calls.append(1))
  adapter._token_counter=FixedCounter(64001)
  with self.assertRaisesRegex(ValueError,'input token bound'): adapter.invoke(request)
  self.assertEqual(resolver.resolve_calls,0)
  policy=PlanningProviderInvocationPolicy('openai-planning','gpt-5.6',SecretReference('keychain','//forge.openai/planning'),120,112001,128000,16000,1)
  body=adapter._body(request,policy); adapter._token_counter=FixedCounter(112001)
  with self.assertRaisesRegex(ValueError,'context token bound'): adapter._enforce_token_policy(body,policy)
  body['max_output_tokens']=16001
  with self.assertRaisesRegex(ValueError,'output token bound'): adapter._enforce_token_policy(body,configuration.current_policy())

 def test_model_mismatch_malformed_output_and_ambiguity_remain_fail_closed(self):
  adapter,_,_,request=self.adapter(lambda *_: None)
  wrong=ProviderDerivationRequest('derive-1',self.snapshot,'openai-planning','other-model')
  with self.assertRaises(ValueError): adapter.invoke(wrong)
  adapter,_,_,request=self.adapter(lambda *args,**kwargs: Response({'id':'resp_bad','status':'completed','output':[{'content':[{'text':'not-json'}]}]}))
  response=adapter.invoke(request)
  self.assertIsNone(response.proposals); self.assertIsNotNone(response.governance_refinement)
  calls=[]
  def opener(*args,**kwargs): calls.append(1); raise URLError('network')
  adapter,_,_,request=self.adapter(opener)
  with self.assertRaises(ProviderSubmissionAmbiguous): adapter.invoke(request)
  self.assertEqual(calls,[1])

if __name__ == '__main__': unittest.main()
