"""Strict Forge consumer mapping for the EP producer readback v1.1 fixture."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping
from forge.models.execution_host import ExecutionEvidenceOutcome,ExecutionHostEvidence,ExecutionRepositoryEvidence

def terminal_evidence(readback: Mapping[str,Any], artifact: bytes, *, host_id: str) -> ExecutionHostEvidence:
 if readback.get('contract_version')!='1.1': raise ValueError('unsupported EP readback contract')
 evidence=readback.get('evidence',{}); terminal=evidence.get('terminal_artifact'); run=readback.get('run'); result=readback.get('result',{}); provenance=readback.get('provenance',{}).get('forge_execution')
 if not isinstance(terminal,dict) or not isinstance(run,dict) or not isinstance(provenance,dict) or result.get('terminal') is not True: raise ValueError('EP terminal evidence is incomplete')
 digest='sha256:'+hashlib.sha256(artifact).hexdigest()
 if terminal.get('digest')!=digest: raise ValueError('EP terminal artifact digest mismatch')
 try: document=json.loads(artifact)
 except (UnicodeDecodeError,json.JSONDecodeError) as e: raise ValueError('EP terminal artifact is invalid JSON') from e
 repo=document.get('repository',{}); outcome=ExecutionEvidenceOutcome(str(result.get('outcome')).lower())
 if not isinstance(repo.get('revision'),str) or not isinstance(document.get('report',{}).get('id'),str): raise ValueError('EP terminal artifact lacks repository evidence')
 correlation=readback['correlation']; prompt=provenance['runtime_prompt']; submission=readback['submission']
 repository=ExecutionRepositoryEvidence(str(correlation['mission_id']),str(provenance['intent_id']),str(provenance['intent_revision']),str(correlation['engineering_action_id']),str(prompt['id']),str(correlation['correlation_id']),str(run['id']),str(repo['id']),str(repo['revision']),str(document['report']['id']),digest)
 return ExecutionHostEvidence(host_id,str(correlation['correlation_id']),str(run['id']),str(document['report']['id']),outcome,repository,validation_references=tuple(str(x.get('command')) for x in document.get('references',{}).get('validation',()) if x.get('command')))
