"""Security qualification for the bounded OpenAI Responses adapter."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
from urllib.error import HTTPError, URLError

from forge.models import PlanningSnapshot
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.planner import (OpenAIPlanningProviderConfiguration,
    OpenAIResponsesPlanningProvider, ProviderDerivationRequest,
    ProviderSubmissionAmbiguous, ProviderTokenPreflightBindingChanged,
    ProviderTokenPreflightFailed, CanonicalTokenPreflightAuthority, TokenPreflightBoundary)
from forge.provider_security import (PlanningProviderInvocationPolicy,
    PlanningProviderSecurityService, SecretReference, SecretState)
from forge.runtime.database import RuntimeDatabase
from tests.test_action_derivation import input_model


class Resolver:
 def __init__(self, secret='test-secret'): self.secret=secret; self.status_calls=0; self.resolve_calls=0; self.on_generation_resolve=None
 def status(self, reference): self.status_calls+=1; return SecretState.RESOLVABLE
 def resolve(self, reference):
  self.resolve_calls+=1
  if self.resolve_calls == 2 and self.on_generation_resolve: self.on_generation_resolve()
  return SecretState.RESOLVABLE,self.secret

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
  db.save_mission_state({'mission_id':self.snapshot.mission_id,'status':'APPROVED_PLANNABLE',
                         'progress':{'percent_complete':0},'resume':{},
                         'execution_policy':{'mode':'planning-only'}})
  resolver=Resolver(); operators=InstallationOperatorService(db,lambda:NamedOperatorIdentity('token-test',501))
  service=PlanningProviderSecurityService(db,resolver,operators)
  service.configure(configuration_id='cfg',provider_id='openai-planning',reference=SecretReference('keychain','//forge.openai/planning'),operator_context=operators.first_bind(),model='gpt-5.6',timeout_seconds=120,input_token_bound=input_bound,context_token_bound=context_bound,output_token_bound=output_bound)
  resolver.status_calls=0; resolver.resolve_calls=0
  configuration=OpenAIPlanningProviderConfiguration._for_test(
   service,'openai-planning',CanonicalTokenPreflightAuthority._for_test(
    db,lambda _: TokenPreflightBoundary('a' * 40,'sha256:evidence','sha256:contract')))
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

 def generate(self, adapter, request):
  context=adapter.configuration.policy_service.operator_service.context()
  receipt=adapter.preflight(request,operator_context=context)
  return adapter.invoke(request,receipt_id=receipt['receipt_id'])

 def test_provider_authoritative_preflight_precedes_generation_and_preserves_token_relevant_body(self):
  captured=[]
  def opener(request, timeout):
   captured.append(request)
   if request.full_url.endswith('/input_tokens'): return Response({'input_tokens':64000})
   return Response({'id':'resp_123','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]})
  adapter,resolver,configuration,request=self.adapter(opener)
  response=self.generate(adapter,request)
  self.assertEqual(len(response.proposals or ()),1)
  self.assertEqual((configuration.current_policy().timeout_seconds,configuration.current_policy().input_token_bound,configuration.current_policy().context_token_bound,configuration.current_policy().output_token_bound),(120,64000,128000,16000))
  self.assertEqual([item.full_url for item in captured],['https://api.openai.com/v1/responses/input_tokens','https://api.openai.com/v1/responses'])
  preflight_body,generation_body=(json.loads(item.data) for item in captured)
  self.assertEqual(set(preflight_body),{'model','truncation','input','text'})
  self.assertNotIn('store',preflight_body); self.assertNotIn('max_output_tokens',preflight_body)
  for field in ('model','truncation','input','text'): self.assertEqual(preflight_body[field],generation_body[field])
  self.assertEqual(resolver.resolve_calls,2)
  self.assertNotIn('test-secret',captured[0].data.decode())

 def test_unknown_generation_field_fails_closed_before_secret_resolution_or_transport(self):
  calls=[]
  adapter,resolver,_,request=self.adapter(lambda http_request,timeout: calls.append(http_request.full_url))
  original=adapter._body
  def altered_body(*args,**kwargs):
   body=original(*args,**kwargs); body['unaccounted_future_field']='forbidden'; return body
  adapter._body=altered_body # type: ignore[method-assign]
  with self.assertRaisesRegex(ValueError,'cannot be bound'):
   self.generate(adapter,request)
  self.assertEqual(calls,[]); self.assertEqual(resolver.resolve_calls,0)

 def test_over_bound_or_failed_preflight_never_generates(self):
  calls=[]
  def over(request, timeout): calls.append(request.full_url); return Response({'input_tokens':64001})
  adapter,resolver,_,request=self.adapter(over)
  with self.assertRaisesRegex(ValueError,'input token bound'): adapter.preflight(request,operator_context=adapter.configuration.policy_service.operator_service.context())
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens']); self.assertEqual(resolver.resolve_calls,1)
  calls.clear()
  adapter,resolver,_,request=self.adapter(lambda request,timeout: (calls.append(request.full_url) or Response({'wrong':1})))
  with self.assertRaises(ProviderTokenPreflightFailed): adapter.preflight(request,operator_context=adapter.configuration.policy_service.operator_service.context())
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens']); self.assertEqual(resolver.resolve_calls,1)

 def test_preflight_timeout_never_generates_or_retries(self):
  calls=[]
  def timeout(request, timeout): calls.append(request.full_url); raise URLError('timeout')
  adapter,resolver,_,request=self.adapter(timeout)
  with self.assertRaises(ProviderTokenPreflightFailed): adapter.preflight(request,operator_context=adapter.configuration.policy_service.operator_service.context())
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens']); self.assertEqual(resolver.resolve_calls,1)

 def test_preflight_transport_failure_has_no_request_or_secret_material(self):
  adapter,resolver,_,request=self.adapter(lambda request,timeout: (_ for _ in ()).throw(URLError(OSError(61,'refused'))))
  with self.assertRaises(ProviderTokenPreflightFailed) as raised: adapter.preflight(request,operator_context=adapter.configuration.policy_service.operator_service.context())
  failure=raised.exception
  self.assertEqual((failure.layer,failure.transport_errno),('TRANSPORT',61))
  self.assertIn(failure.transport_kind,('ConnectionRefusedError','OSError'))
  self.assertNotIn('refused',str(failure)); self.assertEqual(resolver.resolve_calls,1)

 def test_preflight_http_rejection_exposes_only_bounded_safe_metadata(self):
  calls=[]
  def rejected(request, timeout):
   calls.append(request.full_url)
   raise HTTPError(request.full_url, 400, 'bad request', {'x-request-id':'req_safe'},
                   BytesIO(b'{"error":{"type":"invalid_request_error","code":"unsupported_parameter","message":"ignored"}}'))
  adapter,resolver,_,request=self.adapter(rejected)
  with self.assertRaises(ProviderTokenPreflightFailed) as raised: adapter.preflight(request,operator_context=adapter.configuration.policy_service.operator_service.context())
  failure=raised.exception
  self.assertEqual((failure.status,failure.provider_type,failure.provider_code,failure.request_id),
                   (400,'invalid_request_error','unsupported_parameter','req_safe'))
  self.assertNotIn('ignored',str(failure)); self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens'])
  self.assertEqual(resolver.resolve_calls,1)

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
    with self.assertRaises((ProviderTokenPreflightBindingChanged, PermissionError, ValueError)):
     self.generate(adapter,request)
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
  with self.assertRaises(ProviderTokenPreflightBindingChanged): self.generate(adapter,request)
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens'])
  self.assertEqual(resolver.resolve_calls,1)

 def test_policy_change_after_final_validation_denies_generation_for_every_authority_field(self):
  cases=(
   {'model':'gpt-5.6-replacement'}, {'enabled':False},
   {'reference':SecretReference('keychain','//forge.openai/rotated')},
   {'timeout_seconds':121}, {'input_token_bound':63999},
   {'context_token_bound':127999}, {'output_token_bound':15999}, {})
  for change in cases:
   with self.subTest(change=change):
    calls=[]
    def opener(http_request, timeout):
     calls.append(http_request.full_url); return Response({'input_tokens':1})
    adapter,resolver,configuration,request=self.adapter(opener)
    resolver.on_generation_resolve=lambda: self.change_policy(configuration,**change)
    with self.assertRaises(PermissionError): self.generate(adapter,request)
    self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens'])
    self.assertEqual(resolver.resolve_calls,2)

 def test_unchanged_preflight_binding_allows_one_generation_transport(self):
  calls=[]
  def opener(http_request, timeout):
   calls.append(http_request.full_url)
   return Response({'input_tokens':1}) if http_request.full_url.endswith('/input_tokens') else Response({'id':'resp','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]})
  adapter,resolver,_,request=self.adapter(opener)
  self.assertIsNotNone(self.generate(adapter,request))
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens','https://api.openai.com/v1/responses'])
  self.assertEqual(resolver.resolve_calls,2)

 def test_persisted_receipt_is_required_exact_and_single_use(self):
  calls=[]
  def opener(http_request, timeout):
   calls.append(http_request.full_url)
   if http_request.full_url.endswith('/input_tokens'): return Response({'input_tokens':1})
   return Response({'id':'resp','status':'completed','output':[{'content':[{'text':json.dumps(proposal())}]}]})
  adapter,resolver,configuration,request=self.adapter(opener)
  with self.assertRaises(ProviderTokenPreflightBindingChanged):
   adapter.invoke(request,receipt_id='missing')
  self.assertEqual((calls,resolver.resolve_calls),([],0))
  receipt=adapter.preflight(request,operator_context=configuration.policy_service.operator_service.context())
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens'])
  self.assertEqual(configuration.policy_service.db._connection.execute('SELECT COUNT(*) FROM action_derivations').fetchone()[0],0)
  adapter.configuration.preflight_authority._boundary_reader=lambda _: TokenPreflightBoundary('a' * 40,'sha256:changed','sha256:contract')
  with self.assertRaises(ProviderTokenPreflightBindingChanged):
   adapter.invoke(request,receipt_id=receipt['receipt_id'])
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens'])
  adapter.configuration.preflight_authority._boundary_reader=lambda _: TokenPreflightBoundary('a' * 40,'sha256:evidence','sha256:contract')
  adapter.invoke(request,receipt_id=receipt['receipt_id'])
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens','https://api.openai.com/v1/responses'])
  with self.assertRaises(ProviderTokenPreflightBindingChanged):
   adapter.invoke(request,receipt_id=receipt['receipt_id'])
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens','https://api.openai.com/v1/responses'])

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
  response=self.generate(adapter,request)
  self.assertIsNone(response.proposals); self.assertIsNotNone(response.governance_refinement)
  calls=[]
  def generation_timeout(request,timeout):
   calls.append(request.full_url)
   if request.full_url.endswith('/input_tokens'): return Response({'input_tokens':1})
   raise URLError('network')
  adapter,_,_,request=self.adapter(generation_timeout)
  with self.assertRaises(ProviderSubmissionAmbiguous): self.generate(adapter,request)
  self.assertEqual(calls,['https://api.openai.com/v1/responses/input_tokens','https://api.openai.com/v1/responses'])

 def test_reasoning_output_before_strict_message_is_not_a_parse_failure(self):
  def response(request,timeout):
   if request.full_url.endswith('/input_tokens'): return Response({'input_tokens':1})
   return Response({'id':'resp_reasoning','status':'completed','output':[
    {'type':'reasoning','summary':[]},
    {'type':'message','content':[{'type':'output_text','text':json.dumps(proposal())}]},
   ]})
  adapter,_,_,request=self.adapter(response)
  result=self.generate(adapter,request)
  self.assertEqual(len(result.proposals or ()),1)

if __name__ == '__main__': unittest.main()
