"""Read-only continuity of COMPLETE approvals under equivalent current access.

Credential identity and expiry are provenance, never semantic scope. This view
does not modify old setup, turns, packages, decisions or consumption records.
"""
from .advisory_contract import digest
from .approved_worklist import candidate_source
from .candidate_decision_contract import architecture_inputs
from .candidate_decision_service import CandidateDecisionService
from .governance import resolve_governance_profile
from .governed_candidate_intake import GovernedCandidateIntake
from .lifecycle import RecommendationLifecycleStore
from .mission_concept_registration import registration_receipt, registration_request
from .models.criterion_observation import canonical_digest
from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
from dataclasses import replace


def approval_basis(configuration, grant, records, grants, history):
    """Closed, type-sensitive V1 basis including declared and retained ceilings."""
    scope = configuration['scope']
    same = lambda r: (r['principal_id'] == configuration['principal_id']
                      and all(r[k] == scope[k] for k in scope))
    return {'version': 'mission-access-continuity/v1',
            'setup': {k: v for k, v in configuration.items()
                      if k not in {'grant_id', 'configuration_digest'}},
            'conversation_ids': grant['conversation_ids'],
            'grant_scope': {k: grant[k] for k in
                            ('principal_id', 'instance_id', 'project_id', 'repository_id')},
            'declared_maximum_turns': grant['maximum_turns'],
            'retained_maximum_turns': min(history['maximum_turns'],
                *(r['maximum_turns'] for r in grants if same(r))),
            'retained_maximum_missions': min(r['maximum_missions'] for r in records
                if r['principal_id'] == configuration['principal_id'] and r['scope'] == scope)}


def original_configuration(setup, principal, configuration, history, turn, revision):
    """Return old config ONLY after canonical completed-operation proof."""
    records, grants = setup._records(), setup.grant._records()
    original = next((r for r in records if r['grant_id'] == turn['grant_id']), None)
    old_grant = next((r for r in grants if r['grant_id'] == turn['grant_id']), None)
    current_grant = next((r for r in grants if r['grant_id'] == principal.grant_id), None)
    if (original is None or old_grant is None or current_grant is None
            or old_grant['state'] != 'ACTIVE'
            or original['principal_id'] != principal.principal_id
            or turn['context']['concept_configuration_revision'] != original['configuration_digest']
            or digest(approval_basis(original, old_grant, records, grants, history)) !=
               digest(approval_basis(configuration, current_grant, records, grants, history))):
        raise PermissionError('original approval authority is unavailable or changed')
    conversation = history['conversation_id']
    object_id = 'concept-' + digest([principal.reference, history['scope'], conversation])[7:39]
    key = digest([principal.reference, principal.project_id, principal.repository_id,
                  conversation, object_id, revision])
    with RecommendationLifecycleStore.read_only(candidate_source(setup.root)) as store, \
            InstalledDynamicMissionRuntime.open_for_governance_read(str(setup.root)) as runtime:
        receipt = store.candidate_registration(key, principal.reference)
        if receipt is None:
            raise PermissionError('replacement access cannot finish unregistered approval')
        intent = store.candidate_registration_intent(receipt['operation_id'], principal.reference)
        if intent is None:
            raise PermissionError('original approval intent is missing')
        proposal = intent['proposal']
        package = proposal['package']
        source = package['source']
        expected_request = {'contract_version': proposal['contract_version'],
            'operation_id': receipt['operation_id'],
            **{k: proposal[k] for k in ('instance_id', 'project_id', 'repository_id',
                'conversation_id', 'proposal_id', 'proposal_revision', 'proposal_digest')},
            'expected_conversation_revision': source['conversation_revision'],
            'context_revision': source['context_revision'], 'confirm': True}
        if (set(intent) != {'request', 'proposal', 'registered_at'}
                or digest(registration_request(intent['request'])) != digest(expected_request)):
            raise PermissionError('original exact approval request differs')
        expected = registration_receipt(principal.reference, receipt['operation_id'], key,
                                        proposal, intent['registered_at'])
        if (digest(receipt) != digest(expected)
                or package['authority']['configuration_digest'] != original['configuration_digest']
                or source['turn_id'] != turn['request']['turn_id']
                or source['request_digest'] != turn['request_digest']
                or source['result_digest'] != turn['outcome']['result_digest']
                or source['session_id'] != turn['session_id']
                or source['invocation_id'] != turn['invocation_id']):
            raise PermissionError('original approval provenance differs')
        candidate = store.get_candidate(receipt['candidate']['id'])
        if canonical_digest(candidate.to_dict()) != package['subject_revision']:
            raise PermissionError('original Candidate subject changed')
        bridge = GovernedCandidateIntake(store, runtime, resolve_governance_profile(original['profile_id']))
        for kind in ('business', 'architecture'):
            decision_id = bridge._decision_id(kind, candidate.id, package['subject_revision'])
            if CandidateDecisionService.checked_receipt(store, runtime, decision_id) is None:
                raise PermissionError('replacement access cannot finish pending decisions')
        preview, planning = architecture_inputs(package['mission_preview'], package['planning'])
        envelope = bridge.approved_envelope(candidate.id, preview, planning)
        allocation = store.allocation_for_recommendation(candidate.recommendation_id)
        if allocation is None:
            raise PermissionError('replacement access cannot finish pending admission')
        state = runtime.states.get(allocation.mission_id)
        mission = replace(preview, id=allocation.mission_id).to_dict()
        admission = {'installation_id': envelope.installation_id, 'candidate_id': candidate.id,
            'subject_revision': envelope.subject_revision,
            'business_decision_id': envelope.business_decision_id,
            'architecture_decision_id': envelope.architecture_decision_id,
            'planning': envelope.planning.to_dict(), 'envelope_digest': envelope.digest,
            'mission': mission, 'write_scope': 'NONE',
            'admission_version': 'canonical-governance-envelope-v1'}
        actual_allocation = runtime.database._connection.execute(
            'SELECT mission_id FROM mission_id_allocations WHERE source=?',
            ('canonical-governance-envelope:' + envelope.digest,)).fetchone()
        if (canonical_digest(dict(state.mission)) != canonical_digest(mission)
                or digest(state.admission_contract) != digest(admission)
                or allocation.candidate_id != candidate.id
                or allocation.recommendation_id != candidate.recommendation_id
                or allocation.installation_id != envelope.installation_id
                or allocation.envelope_digest != envelope.digest
                or allocation.business_decision_evidence_id != bridge._lifecycle_decision_id(
                    candidate.recommendation_id, 'business_decision')
                or allocation.architecture_decision_evidence_id != bridge._lifecycle_decision_id(
                    candidate.recommendation_id, 'architecture_decision')
                or actual_allocation is None or actual_allocation['mission_id'] != allocation.mission_id):
            raise PermissionError('original admission provenance differs')
    return original, package
