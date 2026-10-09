"""Current canonical readiness facts; approval labels never stand in for proof."""
import json
from pathlib import Path
from .models.criterion_observation import canonical_digest
from .approved_worklist import projection
from .worklist_conditions import completion_facts


def current_readiness(runtime, store, package, state, principal):
    candidate_id = package['candidate']['id']
    current = store.get_candidate(candidate_id)
    if canonical_digest(current.to_dict()) != package['subject_revision']:
        raise RuntimeError('readiness subject differs from frozen definition')
    blockers, dependency_facts = [], []
    for binding in package['dependency_bindings']:
        predecessor = store.get_candidate(binding['candidate_id'])
        if canonical_digest(predecessor.to_dict()) != binding['subject_revision']:
            blockers.append('DEPENDENCY_SUBJECT_CHANGED')
            proven = False
        else:
            allocation = store.allocation_for_recommendation(predecessor.recommendation_id)
            document = runtime.database.get_document('mission_state', allocation.mission_id) if allocation else None
            proven, _, _ = completion_facts(runtime.database._connection, document)
        if not proven:
            blockers.append('DEPENDENCY_NOT_PROVEN')
        dependency_facts.append({'candidate_id':binding['candidate_id'],
                                 'subject_revision':binding['subject_revision'],'proven':proven})
    matching = []
    for row in runtime.database._connection.execute('SELECT document FROM approved_worksets'):
        workset = json.loads(row[0])
        if any(m['candidate_id'] == candidate_id for m in workset['definition']['members']):
            snapshot = projection(Path(runtime.data_root), runtime.database.runtime_identity.runtime_id,
                                  workset['definition']['workset_id'], principal.principal_id)
            member = next(m for m in snapshot['items'] if m['candidate_id'] == candidate_id)
            if member['subject_revision'] != package['subject_revision']:
                blockers.append('WORKSET_SUBJECT_CHANGED')
            if workset['held']:
                blockers.append('WORKSET_HELD')
            matching.append({'workset_id':workset['definition']['workset_id'],
                'snapshot_revision':snapshot['snapshot_revision'],'eligible':member['eligibility']=='ELIGIBLE',
                'selected_next':snapshot['continuation']['candidate_id']==candidate_id and
                                snapshot['continuation']['state']=='READY',
                'blocking_reasons':member['blocking_reasons']})
    if not matching:
        blockers.append('EXPLICIT_WORKSET_RELEASE_REQUIRED')
    elif len(matching) != 1:
        blockers.append('WORKSET_SELECTION_AMBIGUOUS')
    else:
        blockers.extend(matching[0]['blocking_reasons'])
        if not matching[0]['eligible'] or not matching[0]['selected_next']:
            blockers.append('NOT_CURRENT_ELIGIBLE_WORKSET_HEAD')
    # Existing worklist eligibility is logical admission to its owning next step.
    # It does not observe physical EP resources or start the controller.
    return {'state':'READY_FOR_GOVERNED_ACTIVATION' if not blockers else 'APPROVED_WAITING',
            'mission_status':state.status.value,'blockers':list(dict.fromkeys(blockers)),
            'readiness_owner':'FORGE_APPROVED_WORKLIST', 'dependency_facts':dependency_facts,
            'workset_facts':matching,'execution_resources':'NOT_OBSERVED',
            'execution_ready':False, 'subject_revision':package['subject_revision']}
