"""Concrete, strict HTTP v1.1 Engineering Platform Execution Host adapter."""
from __future__ import annotations
import json
from dataclasses import dataclass
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from forge.models.execution_host import ExecutionDispatch,ExecutionHostTemporaryUnavailable,ExecutionRequest
from .ep_v11 import terminal_evidence

@dataclass(frozen=True)
class EngineeringPlatformHttpConfiguration:
 base_url:str; project_id:str; bearer_token:str; host_id:str='engineering-platform'; timeout:float=10

class EngineeringPlatformHttpExecutionHost:
 def __init__(self, config:EngineeringPlatformHttpConfiguration): self.config=config; self._submissions={}
 def _json(self,path,*,method='GET',body=None):
  data=None if body is None else json.dumps(body,sort_keys=True,separators=(',',':')).encode()
  request=Request(self.config.base_url.rstrip('/')+path,data=data,method=method,headers={'Authorization':'Bearer '+self.config.bearer_token,'Content-Type':'application/json'})
  try:
   with urlopen(request,timeout=self.config.timeout) as response:return json.loads(response.read())
  except HTTPError as error:
   if error.code>=500: raise ExecutionHostTemporaryUnavailable('EP temporarily unavailable') from error
   raise ValueError(f'EP rejected request: {error.code}') from error
  except (URLError,TimeoutError) as error: raise ExecutionHostTemporaryUnavailable('EP transport unavailable') from error
 def _payload(self,r):
  p=r.runtime_prompt; text=getattr(p,'rendered_text',None) or p.to_markdown()
  return {'repository_id':r.repository_id,'producer':{'id':'forge','type':'FORGE','version':'1.0'},'prompt':text,'idempotency_key':r.correlation_id,'correlation_id':r.correlation_id,'mission_id':r.mission_id,'engineering_action_id':r.action_id,'constraints':{'forge_execution':{'contract_version':'1.0','host_id':r.host_id,'repository_id':r.repository_id,'correlation_id':r.correlation_id,'mission_id':r.mission_id,'mission_revision':'1','intent_id':r.intent_id,'intent_revision':r.intent_revision,'action_id':r.action_id,'runtime_prompt':{'id':r.runtime_prompt.id,'content_digest':getattr(r.runtime_prompt,'source_digest',getattr(r.runtime_prompt,'generation_request_digest',None))},'retry_of_correlation_id':r.retry_of_correlation_id}}}
 def dispatch(self,r):
  accepted=self._json(f'/v1/projects/{self.config.project_id}/submissions',method='POST',body=self._payload(r)); sid=accepted.get('submission_id')
  if not isinstance(sid,str): raise ValueError('EP submission acknowledgement lacks submission_id')
  self._submissions[r.correlation_id]=sid
  return self.recover_dispatch(r) or (_ for _ in ()).throw(ExecutionHostTemporaryUnavailable('submission accepted but run unclaimed'))
 def recover_dispatch(self,r):
  sid=self._submissions.get(r.correlation_id)
  if not sid:return None
  readback=self._json(f'/v1/projects/{self.config.project_id}/submissions/{sid}')
  if readback.get('correlation',{}).get('correlation_id')!=r.correlation_id or readback.get('submission',{}).get('repository_id')!=r.repository_id: raise ValueError('EP readback does not bind persisted request')
  run=readback.get('run')
  return None if not isinstance(run,dict) else ExecutionDispatch(r,str(run['id']))
 def retrieve_evidence(self,d):
  sid=self._submissions.get(d.request.correlation_id)
  if not sid: raise ValueError('missing persisted submission identity')
  readback=self._json(f'/v1/projects/{self.config.project_id}/submissions/{sid}')
  if readback.get('run',{}).get('id')!=d.host_run_id:return None
  terminal=readback.get('evidence',{}).get('terminal_artifact')
  if not isinstance(terminal,dict): return None
  artifact=self._json(f"/v1/projects/{self.config.project_id}/artifacts/{terminal['id']}")
  raw=json.dumps(artifact,sort_keys=True,separators=(',',':')).encode()+b'\n'
  evidence=terminal_evidence(readback,raw,host_id=self.config.host_id)
  if (evidence.correlation_id,evidence.host_run_id,evidence.repository_evidence.runtime_prompt_id)!=(d.request.correlation_id,d.host_run_id,d.request.runtime_prompt.id): raise ValueError('EP artifact does not bind dispatch')
  return evidence
