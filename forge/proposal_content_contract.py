"""Finite content-baseline decisions; never authority for effects or execution."""
import json
from .approved_worklist import identifier
from .project_bootstrap.schema import canonical
from .project_bootstrap.service import digest
from .advisory_contract import text as safe_text

CONTRACT = 'forge-project-proposal-content-decision/v1'
PROFILE_ID = 'CONTENT_BASELINE_ONLY/1.0'
ROLES = ('BUSINESS', 'ARCHITECTURE')
PROFILE = {'profile_id': PROFILE_ID, 'meaning': 'CONTENT_BASELINE_ONLY',
           'required_roles': list(ROLES), 'proposal_kind': 'pb-render/1.0',
           'baseline': 'portable-docs/1.0.0', 'role': 'authority', 'mode': 'GENESIS',
           'host_profile': 'LOCAL_POSIX', 'effects': False,
           'mandatory_controls': ['EXACT_SOURCE_AND_ARTIFACT_BINDING', 'SUPPORTED_DOCUMENT_ONLY_PROFILE',
                                  'CURRENT_HUMAN_ROLE_AUTHORITY', 'REASON_REQUIRED', 'OPEN_POINTS_ACKNOWLEDGED'],
           'open_points': 'Visible future engineering questions are not automatic document-baseline blockers; approval acknowledges all supplied open questions.',
           'not_assessed': ['physical_target', 'repository_quality', 'security', 'TDE', 'execution_readiness'],
           'not_authorized': ['registration', 'repository_effect', 'risk_waiver', 'execution_plan', 'Action', 'Mission']}
LIMITS = {'request_bytes': 65536, 'records_per_proposal': 8, 'global_records': 64, 'store_bytes': 1048576}

class ContentConflict(ValueError):
    def __init__(self, code): self.code = code; super().__init__(code)

def hash_value(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('exact digest required')
    return value

def decision_request(value):
    fields = {'contract_version', 'instance_id', 'dossier_id', 'operation_id', 'plan_id', 'subject',
              'profile_id', 'role', 'decision', 'expected_decision_revision', 'previous_decision_id',
              'reason', 'acknowledged_open_points'}
    if not isinstance(value, dict) or set(value) != fields or value['contract_version'] != CONTRACT or value['profile_id'] != PROFILE_ID or len(canonical(value)) > LIMITS['request_bytes']:
        raise ValueError('closed finite content decision required')
    for k in ('instance_id', 'dossier_id', 'operation_id', 'plan_id'): identifier(value[k])
    if value['role'] not in ROLES or value['decision'] not in ('APPROVE_CONTENT', 'REQUEST_CHANGES'):
        raise ValueError('content decision role/type invalid')
    n = value['expected_decision_revision']
    if type(n) is not int or not 0 <= n < LIMITS['records_per_proposal']: raise ValueError('finite decision revision required')
    if n == 0:
        if value['previous_decision_id'] is not None: raise ValueError('first decision has no predecessor')
    else: identifier(value['previous_decision_id'])
    safe_text(value['reason'], 2000)
    points = value['acknowledged_open_points']
    if not isinstance(points, list) or len(points) > 32 or len(set(points)) != len(points): raise ValueError('finite open points required')
    for point in points: safe_text(point, 1024)
    subject = value['subject']
    if not isinstance(subject, dict) or set(subject) != {'plan_id', 'proposal_principal_id', 'proposal_kind', 'input_digest', 'result_digest', 'record_digest', 'manifest_digest', 'baseline', 'profile_id', 'source_references', 'concept_revision'}:
        raise ValueError('closed original subject required')
    for key in ('input_digest', 'result_digest', 'record_digest', 'manifest_digest'): hash_value(subject[key])
    identifier(subject['proposal_principal_id'])
    if subject['plan_id'] != value['plan_id'] or subject['profile_id'] != PROFILE_ID or subject['baseline'] != PROFILE['baseline'] or subject['proposal_kind'] != PROFILE['proposal_kind'] or subject['concept_revision'] is not None:
        raise ValueError('unsupported subject binding')
    refs = subject['source_references']
    if not isinstance(refs, list) or not 1 <= len(refs) <= 32: raise ValueError('finite supplied sources required')
    for ref in refs:
        if not isinstance(ref,dict) or set(ref)!={'reference','owner','digest'}:raise ValueError('exact supplied source reference required')
        safe_text(ref['reference'],1024);safe_text(ref['owner'],128);hash_value(ref['digest'])
    return json.loads(canonical(value)), digest(canonical(value))
