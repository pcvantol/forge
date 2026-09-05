"""Deterministic security tests for the bounded OpenAI Responses adapter."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from forge.models import PlanningSnapshot
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.planner import (OpenAIPlanningProviderConfiguration, OpenAIResponsesPlanningProvider,
    ProviderDerivationRequest, ProviderSubmissionAmbiguous, TokenCountingUnavailable)
from forge.provider_security import (PlanningProviderInvocationPolicy,
    PlanningProviderSecurityService, SecretReference, SecretState)
from forge.runtime.database import RuntimeDatabase
from tests.test_action_derivation import input_model


class Resolver:
 def __init__(self, secret='test-secret'): self.secret=secret; self.calls=0
 def status(self, reference): return SecretState.RESOLVABLE
 def resolve(self, reference): self.calls+=1; return SecretState.RESOLVABLE,self.secret

class Counter:
 def __init__(self, tokens): self.tokens=tokens; self.calls=[]
 def count(self, *, model, input_texts): self.calls.append((model,input_texts)); return self.tokens

class UnknownCounter:
 def count(self, *, model, input_texts): raise TokenCountingUnavailable('unknown model')

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

 def adapter(self, opener, *, tokens=12, input_bound=64000, context_bound=128000,
             output_bound=16000, counter=None):
  root=tempfile.TemporaryDirectory(); self.addCleanup(root.cleanup)
  db=RuntimeDatabase(Path(root.name),path=Path(root.name)/'runtime.db'); self.addCleanup(db.close)
  resolver=Resolver(); operators=InstallationOperatorService(db,lambda:NamedOperatorIdentity('token-test',501))
  service=PlanningProviderSecurityService(db,resolver,operators)
  service.configure(configuration_id='cfg',provider_id='openai-planning',
                    reference=SecretReference('keychain','//forge.openai/planning'),
                    operator_context=operators.first_bind(),model='gpt-test',timeout_seconds=120,
                    input_token_bound=input_bound,context_token_bound=context_bound,
                    output_token_bound=output_bound)
  configuration=OpenAIPlanningProviderConfiguration.from_canonical_g011(service,'openai-planning',counter or Counter(tokens))
  return OpenAIResponsesPlanningProvider(configuration,resolver,opener=opener), resolver, configuration

 def test_strict_structured_output_bounded_redacted_provenance(self):
  captured=[]
  def opener(request, timeout):
   captured.append(request); return Response({'id':'resp_123','status':'completed','usage':{'input_tokens':12,'output_tokens':34},'output':[{'content':[{'text':json.dumps(proposal())}]}]})
  adapter,_,configuration=self.adapter(opener)
  response=adapter.invoke(self.request)
  self.assertEqual(len(response.proposals or ()),2); self.assertEqual(response.evidence.response_id,'resp_123')
  policy=configuration.current_policy()
  self.assertEqual((policy.timeout_seconds,policy.input_token_bound,policy.context_token_bound,policy.output_token_bound),(120,64000,128000,16000))
  wire=captured[0].data.decode(); headers=dict(captured[0].header_items())
  self.assertNotIn('test-secret',wire); self.assertIn('"store":false',wire); self.assertIn('json_schema',wire); self.assertNotIn('Authorization',wire)
  self.assertIn('Bearer test-secret',headers.get('Authorization',''))

 def test_input_token_boundary_is_local_and_precedes_secret_resolution(self):
  calls=[]
  adapter,resolver,_=self.adapter(lambda *args,**kwargs: (calls.append(1) or Response({'id':'resp','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]})),tokens=64000)
  self.assertIsNotNone(adapter.invoke(self.request)); self.assertEqual(calls,[1]); self.assertEqual(resolver.calls,1)
  calls.clear(); adapter,resolver,_=self.adapter(lambda *args,**kwargs: calls.append(1),tokens=64001)
  with self.assertRaisesRegex(ValueError,'input token bound'): adapter.invoke(self.request)
  self.assertEqual(calls,[]); self.assertEqual(resolver.calls,0)

 def test_context_token_boundary_is_local(self):
  calls=[]
  # A dedicated canonical policy lets the context invariant be exercised
  # independently of the narrower 64k input policy.
  adapter,_,_=self.adapter(lambda *args,**kwargs: (calls.append(1) or Response({'id':'resp','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]})),tokens=112000,input_bound=112000,context_bound=128000,output_bound=16000)
  self.assertIsNotNone(adapter.invoke(self.request)); self.assertEqual(calls,[1])
  # A malformed persisted policy is denied by G011.  This privileged fixture
  # exercises the adapter's independent local context check against a
  # corrupted in-memory policy without making such a policy constructible by
  # production callers.
  calls.clear(); resolver=Resolver()
  policy=PlanningProviderInvocationPolicy('openai-planning','gpt-test',SecretReference('keychain','//forge.openai/planning'),120,112001,128000,16000,1)
  adapter,_,_=self.adapter(lambda *args,**kwargs: calls.append(1),tokens=112001,input_bound=112000,context_bound=128000,output_bound=16000)
  body=adapter._body(self.request,policy)
  with self.assertRaisesRegex(ValueError,'context token bound'): adapter._enforce_token_policy(body,policy)
  self.assertEqual(calls,[]); self.assertEqual(resolver.calls,0)
  return

 def test_output_bound_is_canonical_and_cannot_be_caller_overridden(self):
  adapter,_,configuration=self.adapter(lambda *args,**kwargs: Response({'id':'resp','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]}))
  self.assertEqual(configuration.current_policy().output_token_bound,16000)
  with self.assertRaises(TypeError):
   OpenAIPlanningProviderConfiguration('openai-planning','gpt-test',SecretReference('keychain','//forge.openai/planning'),max_output_tokens=16001) # type: ignore[call-arg]
  with self.assertRaises(AttributeError):
   configuration.max_output_tokens=16001 # type: ignore[misc]
  body=adapter._body(self.request)
  body['max_output_tokens']=16001
  with self.assertRaisesRegex(ValueError,'output token bound'):
   adapter._enforce_token_policy(body,configuration.current_policy())
  self.assertIsNotNone(adapter.invoke(self.request))

 def test_unknown_counter_and_unicode_never_fall_back_to_characters(self):
  calls=[]
  adapter,resolver,_=self.adapter(lambda *args,**kwargs: calls.append(1),counter=UnknownCounter())
  with self.assertRaises(TokenCountingUnavailable): adapter.invoke(self.request)
  self.assertEqual(calls,[]); self.assertEqual(resolver.calls,0)
  counter=Counter(7); adapter,_,_=self.adapter(lambda *args,**kwargs: Response({'id':'resp','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]}),counter=counter)
  body=adapter._body(self.request)
  body['input'][1]['content'][0]['text']='é😊' # exact submitted text item, deliberately not character counted
  adapter._enforce_token_policy(body,adapter.configuration.current_policy())
  self.assertEqual(counter.calls[-1][1][-1],'é😊')

 def test_model_mismatch_and_malformed_output_fail_closed(self):
  adapter,_,_=self.adapter(lambda *_: None)
  wrong=ProviderDerivationRequest('derive-1',self.snapshot,'openai-planning','other-model')
  with self.assertRaises(ValueError): adapter.invoke(wrong)
  adapter,_,_=self.adapter(lambda *args,**kwargs: Response({'id':'resp_bad','status':'completed','output':[{'content':[{'text':'not-json'}]}]}))
  response=adapter.invoke(self.request)
  self.assertIsNone(response.proposals); self.assertIsNotNone(response.governance_refinement); self.assertEqual(response.evidence.status,'contract_invalid')

 def test_ambiguous_submission_is_never_retried(self):
  calls=[]
  def opener(*args,**kwargs): calls.append(1); raise URLError('network')
  adapter,_,_=self.adapter(opener)
  with self.assertRaises(ProviderSubmissionAmbiguous): adapter.invoke(self.request)
  self.assertEqual(calls,[1])

if __name__ == '__main__': unittest.main()
