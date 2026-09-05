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
    ProviderSubmissionAmbiguous, ProviderTokenPreflightBindingChanged,
    ProviderTokenPreflightFailed)
from forge.provider_security import (PlanningProviderInvocationPolicy,
    PlanningProviderSecurityService, SecretReference, SecretState)
from forge.runtime.database import RuntimeDatabase
from tests.test_action_derivation import input_model


class Resolver:
 def __init__(self, secret='test-secret'): self.secret=secret; self.status_calls=0; self.resolve_calls=0
 def status(self, reference): self.status_calls+=1; return SecretState.RESOLVABLE
 def resolve(self, reference): self.resolve_calls+=1; return SecretState.RESOLVABLE,self.secret

class Response:
 def __init__(self, body): self.body=body
 def read(self): return json.dumps(self.body).encode()
 def __enter__(self): return self
 def __exit__(self,*args): return None

def proposal():
 return {'kind':'proposals','proposals':[{'logical_action_id':'derive-contract','scope':'planner-contract','objective':'Implement bounded action derivation.','dependencies':[],'write_scopes':['forge/planner'],'expected_evidence':['unit test'],'validation_strategy':['unit test'],'priority':1,'postponed':False,'human_gates':['architecture-review'],'risk_inputs':['scope-drift'],'source_evidence_refs':['mission_state','repository_truth']}]}

class OpenAIActionDerivationTests(unittest.TestCase):
 def setUp(self): self.snapshot=PlanningSnapshot.from_planner_input(input_model())

 def adapter(self, opener, *, input_bound=64000, context_bound=128000, output_bound=16000):
  root=tempfile.TemporaryDirectory(); self.addCleanup(root.cleanup)
  db=RuntimeDatabase(Path(root.name),path=Path(root.name)/'runtime.db'); self.addCleanup(db.close)
  resolver=Resolver(); operators=InstallationOperatorService(db,lambda:NamedOperatorIdentity('token-test',501))
  service=PlanningProviderSecurityService(db,resolver,operators)
  service.configure(configuration_id='cfg',provider_id='openai-planning',reference=SecretReference('keychain','//forge.openai/planning'),operator_context=operators.first_bind(),model='gpt-5.6',timeout_seconds=120,input_token_bound=input_bound,context_token_bound=context_bound,output_token_bound=output_bound)
  resolver.status_calls=0; resolver.resolve_calls=0
  configuration=OpenAIPlanningProviderConfiguration.from_canonical_g011(service,'openai-planning')
  resolver.status_calls=0; resolver.resolve_calls=0
  request=ProviderDerivationRequest('derive-1',self.snapshot,'openai-planning','gpt-5.6')
  return OpenAIResponsesPlanningProvider(configuration,resolver,opener=opener),resolver,configuration,request

 def change_policy(self, configuration, **changes):
  service=configuration.policy_service; current=configuration.current_policy()
  service.configure(configuration_id='cfg',provider_id=current.provider_id,
                    reference=changes.get('reference',current.secret_reference),
                    operator_context=service.operator_service.context(),expected_version=current.version,
                    enabled=changes.get('enabled',True),model=changes.get('model',current.model),
                    timeout_seconds=changes.get('timeout_seconds',current.timeout_seconds),
                    input_token_bound=changes.get('input_token_bound',current.input_token_bound),
                    context_token_bound=changes.get('context_token_bound',current.context_token_bound),
                    output_token_bound=changes.get('output_token_bound',current.output_token_bound))

 def test_provider_authoritative_preflight_precedes_generation_and_matches_body(self):
  captured=[]
  def opener(request, timeout):
   captured.append(request)
   if request.full_url.endswith('/input_tokens'): return Response({'input_tokens':64000})
   return Response({'id':'resp_123','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]})
  adapter,resolver,configuration,request=self.adapter(opener)
  response=adapter.invoke(request)
  self.assertEqual(len(response.proposals or ()),1)
  self.assertEqual((configuration.current_policy().timeout_seconds,configuration.current_policy().input_token_bound,configuration.current_policy().context_token_bound,configuration.current_policy().output_token_bound),(120,64000,128000,16000))
  self.assertEqual([item.full_url for item in captured],['https://api.openai.com/v1/responses/input_tokens','https://api.openai.com/v1/responses'])
  self.assertEqual(captured[0].data,captured[1].data); self.assertEqual(resolver.resolve_calls,2)
  self.assertNotIn('test-secret',captured[0].data.decode())

 def test_over_bound_or_failed_preflight_never_generates(self):
  calls=[]
  def over(request, timeout): calls.append(request.full_url); return Response({'input_tokens':64001})
  adapter,resolver,_,request=self.adapter(over)
  with self.assertRaisesRegex(ValueError,'input token bound'): adapter.invoke(request)
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens']); self.assertEqual(resolver.resolve_calls,1)
  calls.clear()
  adapter,resolver,_,request=self.adapter(lambda request,timeout: (calls.append(request.full_url) or Response({'wrong':1})))
  with self.assertRaises(ProviderTokenPreflightFailed): adapter.invoke(request)
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens']); self.assertEqual(resolver.resolve_calls,1)

 def test_preflight_timeout_never_generates_or_retries(self):
  calls=[]
  def timeout(request, timeout): calls.append(request.full_url); raise URLError('timeout')
  adapter,resolver,_,request=self.adapter(timeout)
  with self.assertRaises(ProviderTokenPreflightFailed): adapter.invoke(request)
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens']); self.assertEqual(resolver.resolve_calls,1)

 def test_context_and_output_bounds_use_preflight_count(self):
  adapter,_,configuration,request=self.adapter(lambda *args,**kwargs: None)
  policy=PlanningProviderInvocationPolicy('openai-planning','gpt-5.6',SecretReference('keychain','//forge.openai/planning'),120,112001,128000,16000,1)
  body=adapter._body(request,policy)
  adapter._enforce_token_policy(body,policy,112000) # exact context boundary
  with self.assertRaisesRegex(ValueError,'context token bound'): adapter._enforce_token_policy(body,policy,112001)
  body['max_output_tokens']=16001
  with self.assertRaisesRegex(ValueError,'output token bound'): adapter._enforce_token_policy(body,configuration.current_policy(),1)

 def test_policy_change_during_preflight_denies_generation_for_every_authority_field(self):
  cases=(
   {'model':'gpt-5.6-replacement'}, {'enabled':False},
   {'reference':SecretReference('keychain','//forge.openai/rotated')},
   {'timeout_seconds':121}, {'input_token_bound':63999},
   {'context_token_bound':127999}, {'output_token_bound':15999}, {})
  for change in cases:
   with self.subTest(change=change):
    calls=[]; changed=False
    def opener(http_request, timeout):
     nonlocal changed
     calls.append(http_request.full_url)
     if not changed:
      changed=True; self.change_policy(configuration,**change)
      return Response({'input_tokens':1})
     self.fail('generation transport must not occur after G011 mutation')
    adapter,resolver,configuration,request=self.adapter(opener)
    with self.assertRaises((ProviderTokenPreflightBindingChanged,PermissionError)):
     adapter.invoke(request)
    self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens'])
    self.assertEqual(resolver.resolve_calls,1)

 def test_request_change_after_preflight_denies_generation(self):
  calls=[]
  def opener(http_request, timeout): calls.append(http_request.full_url); return Response({'input_tokens':1})
  adapter,resolver,_,request=self.adapter(opener)
  original=adapter._body; builds=0
  def changed_body(*args,**kwargs):
   nonlocal builds
   builds+=1; body=original(*args,**kwargs)
   if builds == 2: body['input'].append({'role':'user','content':[{'type':'input_text','text':'changed'}]})
   return body
  adapter._body=changed_body # type: ignore[method-assign]
  with self.assertRaises(ProviderTokenPreflightBindingChanged): adapter.invoke(request)
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens'])
  self.assertEqual(resolver.resolve_calls,1)

 def test_unchanged_preflight_binding_allows_one_generation_transport(self):
  calls=[]
  def opener(http_request, timeout):
   calls.append(http_request.full_url)
   return Response({'input_tokens':1}) if http_request.full_url.endswith('/input_tokens') else Response({'id':'resp','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]})
  adapter,resolver,_,request=self.adapter(opener)
  self.assertIsNotNone(adapter.invoke(request))
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens','https://api.openai.com/v1/responses'])
  self.assertEqual(resolver.resolve_calls,2)

 def test_no_caller_counter_or_encoding_override_and_no_local_estimate(self):
  adapter,_,configuration,_=self.adapter(lambda *args,**kwargs: None)
  with self.assertRaises(TypeError):
   OpenAIPlanningProviderConfiguration.from_canonical_g011(configuration.policy_service,'openai-planning',object()) # type: ignore[call-arg]
  with self.assertRaises(TypeError):
   OpenAIPlanningProviderConfiguration(configuration.policy_service,'openai-planning',_from_canonical_g011=True,model_encodings={'gpt-5.6':'forged'}) # type: ignore[call-arg]
  self.assertFalse(hasattr(adapter,'_token_counter')); self.assertFalse(hasattr(configuration,'token_counter'))

 def test_malformed_generation_output_and_generation_ambiguity_remain_fail_closed(self):
  def malformed(request,timeout):
   return Response({'input_tokens':1}) if request.full_url.endswith('/input_tokens') else Response({'id':'resp_bad','status':'completed','output':[{'content':[{'text':'not-json'}]}]})
  adapter,_,_,request=self.adapter(malformed)
  response=adapter.invoke(request)
  self.assertIsNone(response.proposals); self.assertIsNotNone(response.governance_refinement)
  calls=[]
  def generation_timeout(request,timeout):
   calls.append(request.full_url)
   if request.full_url.endswith('/input_tokens'): return Response({'input_tokens':1})
   raise URLError('network')
  adapter,_,_,request=self.adapter(generation_timeout)
  with self.assertRaises(ProviderSubmissionAmbiguous): adapter.invoke(request)
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens','https://api.openai.com/v1/responses'])

if __name__ == '__main__': unittest.main()
