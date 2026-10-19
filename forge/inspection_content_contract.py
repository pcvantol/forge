"""Exact historical R55 content subjects; no target or effect authority."""
import json
from .approved_worklist import identifier
from .project_bootstrap.schema import canonical
from .project_bootstrap.service import digest
from .proposal_content_contract import ContentConflict, ROLES, hash_value
from .advisory_contract import text

CONTRACT = 'forge-inspection-adoption-content-decision/v1'
PROFILE_ID = 'INSPECTION_ADOPTION_CONTENT_ONLY/1.0'
BASE = '/v1/inspection-adoption-decisions'
LIMITS = {'request_bytes': 65536, 'records_per_proposal': 8, 'global_records': 32, 'store_bytes': 1048576}
PROFILE = {'profile_id': PROFILE_ID, 'required_roles': list(ROLES),
           'proposal_kind': 'ep-inspection-adoption-preview/1.0', 'effects': False,
           'freshness': 'AS_OF_OBSERVATION_NOT_CONTINUOUS',
           'optional_unresolved_artifacts': ['docs/roadmap/ROADMAP.md'],
           'not_authorized': ['EP_WRITE', 'GIT', 'B8R', 'GENESIS_EFFECT', 'PROJECT_READY', 'Mission', 'Action']}


def subject(record):
    """Only called with an integrity-checked owning R55 record, never client JSON."""
    if record['state'] != 'PREPARED':
        raise ContentConflict('INSPECTION_CONTENT_SOURCE_PENDING')
    result = record['result']
    artifacts = {a['path']: a for a in result['artifacts']}
    if set(artifacts) != {'README.md', 'proposal.json'}:
        raise ValueError('exact R55 result artifacts required')
    proposal = json.loads(artifacts['proposal.json']['content'])
    unsigned = {k: v for k, v in proposal.items() if k != 'proposal_digest'}
    if (proposal['contract_version'] != PROFILE['proposal_kind'] or
            proposal['proposal_digest'] != digest(canonical(unsigned)) or
            proposal['source_observation'] != result['source_binding'] or
            result['source_binding']['snapshot_digest'] != record['source']['response_digest'] or
            result['result_digest'] != digest(canonical(result['artifacts']))):
        raise ValueError('original R55 content binding invalid')
    value = {'plan_id': record['plan_id'], 'operation_id': record['operation_id'],
             'proposal_principal_id': record['principal_id'], 'proposal_kind': PROFILE['proposal_kind'],
             'profile_id': PROFILE_ID, 'input_digest': result['input_digest'],
             'request_digest': record['request_digest'], 'result_digest': result['result_digest'],
             'proposal_digest': proposal['proposal_digest'], 'manifest_digest': proposal['r50_render_digest'],
             'record_digest': digest(canonical(record)), 'source_binding': result['source_binding'],
             'source_raw_digest': record['source']['raw_sha256'], 'pairing_digest': record['pairing_digest'],
             'mappings_digest': digest(canonical(record['input']['mappings'])),
             'artifacts': [{k: a[k] for k in ('path', 'mode', 'sha256')} for a in result['artifacts']],
             'concept_revision': None}
    value['subject_digest'] = digest(canonical(value))
    limitations = []
    blockers = []
    for entry in proposal['entries']:
        if entry['operation'] in ('CONFLICT', 'INSUFFICIENT_INFORMATION'):
            limitation = {'artifact_path': entry['artifact_path'], 'operation': entry['operation'],
                          'reason': entry['reason'], 'source_path': entry['source_path'],
                          'blocking': not (entry['operation'] == 'INSUFFICIENT_INFORMATION' and
                              entry['artifact_path'] in PROFILE['optional_unresolved_artifacts'] and
                              entry['reason'] == 'EXCLUDED_OR_UNCOVERED' and entry['before'] == {'status':'UNKNOWN'} and
                              not entry['mapping_source'])}
            limitations.append(limitation)
            if limitation['blocking']:
                blockers.append(limitation)
    points = {'source_freshness': PROFILE['freshness'], 'observed_at': result['source_binding']['observed_at'],
              'limitations': limitations, 'proposal_decisions': proposal['decisions'],
              'product_questions': record['input']['bootstrap_input']['product']['open_questions'],
              'documents': proposal['entries'], 'original_summary': result['summary']}
    return value, points, blockers


def decision_request(value):
    keys = {'contract_version', 'profile_id', 'instance_id', 'dossier_id', 'plan_id', 'operation_id',
            'subject_digest', 'role', 'decision', 'reason', 'expected_decision_revision',
            'previous_decision_id', 'acknowledged_review_digest'}
    if not isinstance(value, dict) or set(value) != keys or value['contract_version'] != CONTRACT or value['profile_id'] != PROFILE_ID or len(canonical(value)) > LIMITS['request_bytes']:
        raise ValueError('closed finite inspection-content decision required')
    for key in ('instance_id', 'dossier_id', 'plan_id', 'operation_id'):
        identifier(value[key])
    for key in ('subject_digest', 'acknowledged_review_digest'):
        hash_value(value[key])
    if value['role'] not in ROLES or value['decision'] not in ('APPROVE_CONTENT', 'REQUEST_CHANGES'):
        raise ValueError('explicit content role/decision required')
    n = value['expected_decision_revision']
    if type(n) is not int or not 0 <= n < LIMITS['records_per_proposal']:
        raise ValueError('bounded decision revision required')
    if n == 0:
        if value['previous_decision_id'] is not None:
            raise ValueError('initial decision cannot have predecessor')
    else:
        identifier(value['previous_decision_id'])
    text(value['reason'], 2000)
    return json.loads(canonical(value)), digest(canonical(value))
