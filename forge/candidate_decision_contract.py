"""Explicit, separate Candidate approvals; no actor or execution request fields."""
import json
from .advisory_contract import digest, text
from .advisory_candidate_contract import hash_reference
from .approved_worklist import identifier
from .governance_authority import ArchitecturePlanningEvidence
from .models.architecture_mission import ArchitectureMission

CONTRACT = 'forge-candidate-decisions/v1'
KINDS = ('BUSINESS', 'ARCHITECTURE')
BASE = 'contract_version operation_id instance_id project_id repository_id candidate_id subject_revision kind rationale confirm'

def safe_document(value):
    """Closed model parsers still require safe bounded user-supplied leaf values."""
    if isinstance(value, str):
        if value:
            text(value, 2000)
    elif isinstance(value, list):
        if len(value) > 64:
            raise ValueError('bounded planning list required')
        for item in value:
            safe_document(item)
    elif isinstance(value, dict):
        if len(value) > 40:
            raise ValueError('bounded planning object required')
        for key, item in value.items():
            text(key, 128)
            safe_document(item)
    elif value is not None and type(value) is not int:
        raise ValueError('unsupported planning value')

def architecture_inputs(mission, planning):
    if not isinstance(mission, dict) or not isinstance(planning, dict):
        raise ValueError('explicit Architecture preview and planning required')
    safe_document(mission)
    safe_document(planning)
    for value,names in ((mission,'scope engineering_constraints acceptance_criteria technical_assumptions dependencies required_capabilities required_disciplines risks'),(planning,'scope write_scopes non_goals risk_inputs human_gates dependencies')):
        for key in names.split():
            items=value.get(key)
            if not isinstance(items,list) or len(items)>64 or any(not isinstance(item,str) for item in items):
                raise ValueError('explicit typed planning text lists required')
            for item in items:
                text(item,2000)
    for key in ('context_input_bound', 'context_output_bound'):
        if type(planning.get(key)) is not int or not 1 <= planning[key] <= 1000000:
            raise ValueError('exact positive planning bounds required')
    for value in (mission, planning):
        for key in ('maximum_actions', 'maximum_consecutive_no_progress_actions'):
            if key in value and (type(value[key]) is not int or not 1 <= value[key] <= 64):
                raise ValueError('bounded Action count required')
    preview = ArchitectureMission.from_dict(mission)
    evidence = ArchitecturePlanningEvidence.from_dict(planning)
    # Round-trip equality rejects unknown fields, ignored identity, implicit defaults
    # and unsupplied planning material. It does not manufacture planning inputs.
    if digest(preview.to_dict()) != digest(mission) or digest(evidence.to_dict()) != digest(planning):
        raise ValueError('closed canonical Architecture inputs required')
    if not preview.is_engineering_ready():
        raise ValueError('complete explicit Architecture preview required')
    return preview, evidence

def decision_request(value):
    if not isinstance(value, dict) or value.get('contract_version') != CONTRACT or value.get('kind') not in KINDS:
        raise ValueError('Candidate decision contract required')
    extra = 'human_gates' if value['kind'] == 'BUSINESS' else 'business_decision_id business_decision_digest mission_preview planning'
    if set(value) != set((BASE + ' ' + extra).split()) or value['confirm'] is not True:
        raise ValueError('closed explicit Candidate decision required')
    for key in ('operation_id', 'instance_id', 'project_id', 'repository_id', 'candidate_id'):
        identifier(value[key])
    hash_reference(value['subject_revision'])
    text(value['rationale'], 1000)
    if value['kind'] == 'BUSINESS':
        gates = value['human_gates']
        if not isinstance(gates, list) or not 1 <= len(gates) <= 8 or len(set(gates)) != len(gates):
            raise ValueError('explicit unique human gates required')
        for gate in gates:
            text(gate, 1000)
    else:
        identifier(value['business_decision_id'])
        hash_reference(value['business_decision_digest'])
        architecture_inputs(value['mission_preview'], value['planning'])
    return json.loads(json.dumps(value, sort_keys=True))
