"""Typed EP evidence entrance to the existing R50 renderer and R51 adoption engine."""
from copy import deepcopy
from .ep_inspection_contract import KIND, EP_REVISION, EP_TREE, EP_SCHEMA_SHA256, document_observations
from .project_bootstrap.schema import canonical, ContractError, validate
from .project_bootstrap.service import check_input as check_basis, digest
from .project_adoption.service import schema as adoption_schema, preview_observed, readable, document_path, FIXED_PATH


def check_input(value):
    old = adoption_schema('input.schema.json')['properties']
    props = {key: old[key] for key in ('bootstrap_input', 'requested_artifacts', 'mappings')}
    validate(value, {'type':'object','additionalProperties':False,'required':list(props),'properties':props})
    check_basis(value['bootstrap_input'])
    basis = value['bootstrap_input']
    if basis['role'] != 'authority' or basis['mode'] != 'GENESIS' or basis['host_profile'] != 'LOCAL_POSIX':
        raise ContractError('first EP adoption profile is portable local Genesis authority only')
    paths = value['requested_artifacts']
    if len(set(paths)) != len(paths):
        raise ContractError('duplicate requested artifact')
    mapped = set()
    for choice in value['mappings']:
        document_path(choice['source_path'])
        if choice['artifact_path'] not in paths or choice['artifact_path'] in mapped:
            raise ContractError('mapping artifact mismatch')
        if choice['artifact_path'] == FIXED_PATH and choice['source_path'] != FIXED_PATH:
            raise ContractError('B8R declaration path is fixed')
        if choice['choice'] == 'PROPOSE_REPLACEMENT' and choice['source_path'] != choice['artifact_path']:
            raise ContractError('cross-path replacement lacks original before')
        mapped.add(choice['artifact_path'])
    for path in paths:
        document_path(path)
    if len(canonical(value)) > 131072:
        raise ContractError('finite adoption input required')
    return deepcopy(value)


def result(value, snapshot, binding):
    value = check_input(value)
    source = {'producer_revision':EP_REVISION,'producer_tree':EP_TREE,'schema_sha256':EP_SCHEMA_SHA256,
              **{key:binding[key] for key in ('instance_id','host_id','consumer_id','principal','audience','source_ref','operation_id')},
              'snapshot_digest':digest(canonical(snapshot)),
              'observed_at':snapshot['observation']['observed_at'],
              'source_fingerprint':snapshot['observation']['source_fingerprint'],
              'completeness':snapshot['observation']['completeness'],'freshness':snapshot['freshness'],
              'selection':snapshot['observation']['selection'],'exclusions':snapshot['observation']['exclusions'],
              'git':snapshot['observation']['git'],'canonical_declaration':snapshot['observation']['canonical_declaration']}
    evidence = {**snapshot['observation'], 'documents':document_observations(snapshot), 'source_binding':source}
    proposal = preview_observed(value, evidence)
    artifacts = {'proposal.json':canonical(proposal),'README.md':readable(proposal)}
    rows = [{'path':path,'mode':0o644,'sha256':digest(raw),'content':raw.decode('utf-8')} for path,raw in sorted(artifacts.items())]
    document = {'state':'PROPOSED_NOT_APPROVED','original_contract_version':KIND,
                'input_digest':digest(canonical(value)),'summary':artifacts['README.md'].decode('utf-8'),
                'artifacts':rows,'result_digest':digest(canonical(rows)),
                'observations':'AUTHENTICATED_EP_HISTORICAL_WITHIN_SELECTION','repository_quality':'NOT_ASSESSED',
                'source_binding':source,'approval':'NOT_PERFORMED','registration':'NOT_PERFORMED'}
    if len(canonical(document)) > 1048576:
        raise ContractError('finite private proposal result required')
    return document
