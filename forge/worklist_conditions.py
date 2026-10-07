"""Read-only exact completion/selector facts, shared by projection and activation."""
from typing import Any
from .models.criterion_observation import canonical_digest
from .governance_authority import _digest as stored_governance_digest
from .governed_continuation import FINAL_ACCEPTANCE_REQUIREMENT_CONTRACT


def completion_facts(db, state: dict[str,Any] | None) -> tuple[bool,str,list[dict[str,str]]]:
    """A green lifecycle alone cannot unlock dependent approved work."""
    if state is None:return False,'UNKNOWN',[]
    completion=state.get('completion');terminal=state.get('execution_evidence')
    if (not isinstance(completion,dict) or completion.get('all_required_criteria_proven') is not True
            or not isinstance(completion.get('criteria'),list) or not completion['criteria']
            or any(c.get('status')!='PROVEN' or not c.get('observations') for c in completion['criteria'])
            or not isinstance(terminal,dict) or terminal.get('outcome')!='complete'
            or not isinstance(terminal.get('receipt_id'),str)):
        return False,'UNKNOWN',[]
    repository=terminal.get('repository_evidence')
    if (not isinstance(repository,dict) or repository.get('mission_id')!=state.get('mission_id')
            or not isinstance(repository.get('report_id'),str) or not repository['report_id']
            or not isinstance(repository.get('content_digest'),str)
            or not repository['content_digest'].startswith('sha256:')
            or not isinstance(state.get('execution_history'),list)
            or not any(canonical_digest(item)==canonical_digest(terminal) for item in state['execution_history'])):
        return False,'UNKNOWN',[]
    for criterion in completion['criteria']:
        references=criterion.get('execution_evidence')
        if (not isinstance(references,list) or not references
                or not all(any(ref.get('receipt_id')==evidence.get('receipt_id')
                           and ref.get('action_id')==(evidence.get('repository_evidence') or {}).get('action_id')
                           and ref.get('report_id')==evidence.get('report_id')==(evidence.get('repository_evidence') or {}).get('report_id')
                           and ref.get('repository_revision')==(evidence.get('repository_evidence') or {}).get('repository_revision')
                           and ref.get('candidate_revision')==(evidence.get('repository_evidence') or {}).get('candidate_revision')
                           and (evidence.get('repository_evidence') or {}).get('mission_id')==state['mission_id']
                           and evidence.get('outcome')=='complete'
                           and ref.get('repository_evidence_digest')==(evidence.get('repository_evidence') or {}).get('content_digest')
                           for evidence in state['execution_history']) for ref in references)):
            return False,'UNKNOWN',[]
    refs=[{'kind':'MISSION_COMPLETION','subject_id':state['mission_id'],'digest':canonical_digest(completion)}]
    pause=state.get('pause_reason') or {}
    if pause.get('schema_version')==FINAL_ACCEPTANCE_REQUIREMENT_CONTRACT:
        return False,'WAITING',refs
    record=state.get('approval_record')
    if state.get('status')!='COMPLETED' or not isinstance(record,dict):return False,'UNKNOWN',refs
    row=db.execute('SELECT document,digest FROM governance_decisions WHERE decision_id=?',(record.get('approval_id'),)).fetchone()
    if row is None:return False,'UNKNOWN',refs
    import json
    decision=json.loads(row[0]);evidence=decision.get('evidence') or {}
    if (stored_governance_digest(decision)!=row[1] or decision.get('decision')!='accept'
            or decision.get('capability')!='BUSINESS_APPROVAL'
            or decision.get('subject_id')!=record.get('decision_reference')
            or decision.get('installation_id')!=(state.get('admission_contract') or {}).get('installation_id')
            or canonical_digest(decision)!=record.get('decision_digest')
            or evidence.get('mission_id')!=state['mission_id']
            or evidence.get('completion_digest')!=canonical_digest(completion)
            or evidence.get('terminal_evidence_digest')!=canonical_digest(terminal)):
        return False,'UNKNOWN',refs
    refs.append({'kind':'FINAL_BUSINESS_ACCEPTANCE','subject_id':record['approval_id'],'digest':record['decision_digest']})
    return True,'ACCEPTED',refs


def continuation(items: list[dict[str,Any]]) -> dict[str,Any]:
    """The producer's committed serial selector, never client-side inference."""
    selected=next((item for item in items if not item['completed']),None)
    if selected is None:
        return {'state':'IDLE','candidate_id':None,'mission_id':None,'committed_order':None,'reason_codes':['NO_REMAINING_APPROVED_WORK']}
    reasons=list(selected['blocking_reasons'])
    if selected['active']:reasons.append('MISSION_ACTIVE')
    state='READY' if not reasons else 'UNKNOWN' if reasons==['ACTIVATION_NOT_YET_QUALIFIED'] else 'BLOCKED'
    return {'state':state,'candidate_id':selected['candidate_id'],'mission_id':selected['mission_id'],
        'committed_order':selected['committed_order'],'reason_codes':list(dict.fromkeys(reasons))}

SNAPSHOT_FIELDS=('contract_version','instance_id','installation_id','scope','membership_revision','selector_revision',
                 'workset_revision','activation_support','completeness','items','continuation')

def snapshot_revision(document: dict[str,Any]) -> str:
    return canonical_digest({key:document[key] for key in SNAPSHOT_FIELDS})
