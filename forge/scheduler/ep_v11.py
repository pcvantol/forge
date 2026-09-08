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
 if not isinstance(repo,dict) or not isinstance(document.get('report',{}).get('id'),str): raise ValueError('EP terminal artifact lacks repository evidence')
 correlation=readback['correlation']; prompt=provenance['runtime_prompt']; submission=readback['submission']
 # A hash only proves the returned bytes came from *some* registered object.
 # Bind their internal subject to the readback before mapping it to Forge.
 artifact_correlation=document.get('correlation',{}); artifact_provenance=document.get('provenance',{}); artifact_run=document.get('run',{}); artifact_submission=document.get('submission',{}); artifact_producer=document.get('producer',{})
 if not all(isinstance(value,dict) for value in (artifact_correlation,artifact_provenance,artifact_run,artifact_submission,artifact_producer)):
  raise ValueError('EP terminal artifact lacks binding fields')
 if artifact_correlation != correlation or artifact_producer != readback.get('producer'):
  raise ValueError('EP terminal artifact identity differs from readback')
 expected_provenance={key: provenance.get(key) for key in ('action_id','contract_version','correlation_id','host_id','intent_id','intent_revision','mission_id','mission_revision','repository_id','retry_of_correlation_id','runtime_prompt')}
 if artifact_provenance != expected_provenance or artifact_run.get('id') != run.get('id') or artifact_submission.get('id') != submission.get('id') or artifact_submission.get('project_id') != submission.get('project_id') or artifact_submission.get('repository_id') != submission.get('repository_id') or artifact_submission.get('accepted_request_digest') != submission.get('accepted_request_digest'):
  raise ValueError('EP terminal artifact does not bind readback run and submission')
 revision=repo.get('revision')
 if revision is not None and not isinstance(revision,str): raise ValueError('EP terminal artifact revision is invalid')
 if outcome is ExecutionEvidenceOutcome.COMPLETE and (not revision or document.get('run',{}).get('delivery_qualified') is not True or repo.get('revision_required') is not True): raise ValueError('EP complete terminal artifact lacks qualified delivery revision')
 if repo.get('id') != readback.get('evidence',{}).get('repository',{}).get('id') or revision != readback.get('evidence',{}).get('repository',{}).get('revision'): raise ValueError('EP terminal artifact repository differs from readback')
 repository=ExecutionRepositoryEvidence(str(correlation['mission_id']),str(provenance['intent_id']),str(provenance['intent_revision']),str(correlation['engineering_action_id']),str(prompt['id']),str(correlation['correlation_id']),str(run['id']),str(repo['id']),revision,str(document['report']['id']),digest)
 return ExecutionHostEvidence(host_id,str(correlation['correlation_id']),str(run['id']),str(document['report']['id']),outcome,repository,validation_references=tuple(str(x.get('command')) for x in document.get('references',{}).get('validation',()) if x.get('command')))
