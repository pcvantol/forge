"""New generated-content lineage; historical EXPLICIT_USER records stay intact."""
import json
from .advisory_contract import digest
from .advisory_candidate_contract import revision, hash_reference
from .approved_worklist import identifier, timestamp
from .mission_concept_contract import CONTRACT
from .lifecycle import MissionRecommendation, MissionCandidate
from .models.criterion_observation import canonical_digest


def registration_request(value):
    fields = ('contract_version operation_id instance_id project_id repository_id '
              'conversation_id proposal_id proposal_revision proposal_digest '
              'expected_conversation_revision context_revision confirm')
    if (not isinstance(value, dict) or set(value) != set(fields.split())
            or value['contract_version'] != CONTRACT or value['confirm'] is not True):
        raise ValueError('exact generated registration intent required')
    for key in ('operation_id', 'instance_id', 'project_id', 'repository_id',
                'conversation_id', 'proposal_id'):
        identifier(value[key])
    if revision(value['proposal_revision']) < 1:
        raise ValueError('concept revision required')
    revision(value['expected_conversation_revision'])
    hash_reference(value['proposal_digest']); hash_reference(value['context_revision'])
    return json.loads(json.dumps(value))


def candidate_objects(proposal, key, occurred_at):
    if (proposal.get('contract_version') != CONTRACT
            or proposal.get('field_origins') != {'definition': 'VALIDATED_MODEL_PROPOSAL',
                                                'planning': 'TRUSTED_OWNER_CONFIGURATION'}
            or proposal['proposal_digest'] != digest({k: v for k, v in proposal.items()
                                                      if k != 'proposal_digest'})):
        raise ValueError('generated provenance differs')
    package = proposal['package']
    candidate = MissionCandidate.from_dict(package['candidate'])
    source, definition = package['source'], package['definition']
    if (canonical_digest(candidate.to_dict()) != package['subject_revision']
            or any(source[k] != proposal[k] for k in
                   ('instance_id', 'project_id', 'repository_id', 'conversation_id'))
            or source['object_id'] != proposal['proposal_id']
            or source['revision'] != proposal['proposal_revision']
            or package['authority']['principal_reference'] != proposal['principal_reference']):
        raise ValueError('frozen Candidate source differs')
    recommendation = MissionRecommendation(
        id=candidate.recommendation_id, title=candidate.title, mission_origin='architecture',
        business_summary=definition['objective'], engineering_summary=definition['expected_result'],
        business_value=definition['business_value'], engineering_value=definition['expected_result'],
        architectural_value='; '.join(candidate.architecture_constraints),
        repository_evidence=(source['context_revision'],),
        decision_evidence_reference=digest(package), dependencies=candidate.dependencies,
        alternatives=(), confidence=None, recommendation_timestamp=occurred_at,
        recommendation_type='generated_mission_concept', expected_outcome=definition['expected_result'],
        known_constraints=tuple(definition['exclusions']),
        evidence_references=(source['request_digest'], source['result_digest']))
    return recommendation, candidate


def registration_receipt(principal, operation_id, key, proposal, occurred_at):
    timestamp(occurred_at)
    if (proposal['principal_reference'] != principal or key != digest([
            principal, proposal['project_id'], proposal['repository_id'],
            proposal['conversation_id'], proposal['proposal_id'], proposal['proposal_revision']])):
        raise ValueError('generated registration correlation differs')
    rec, candidate = candidate_objects(proposal, key, occurred_at)
    return {'contract_version': CONTRACT, 'operation_id': identifier(operation_id),
            'principal_reference': principal, 'registration_key': key,
            'proposal_digest': proposal['proposal_digest'],
            'proposal_revision': proposal['proposal_revision'], 'source': proposal['source'],
            'candidate': candidate.to_dict(), 'recommendation_id': rec.id,
            'candidate_digest': digest(candidate.to_dict()), 'recommendation_digest': digest(rec.to_dict()),
            'registered_at': occurred_at, 'status_at_registration': 'RECOMMENDED',
            'rationale': 'Explicit approval of the exact generated definition and trusted planning.'}
