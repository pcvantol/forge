"""Lossless Genesis dispatch binding from owning private source snapshots.

These pure checks confer no authority. The coordinator must obtain snapshots
from the owning services and recheck current grants before any network effect.
"""
from .approved_worklist import identifier
from .genesis_bootstrap_contract import CONTRACT as PLAN_CONTRACT, EFFECT_PURPOSE, frozen_bundle
from .project_bootstrap.schema import canonical, load_json, ContractError
from .project_bootstrap.service import digest

CONTRACT = 'forge-genesis-apply/v1'


def apply_request(value):
    """Closed user input contains opaque references only; never EP credentials."""
    fields = {'contract_version', 'instance_id', 'dossier_id', 'operation_id',
              'plan_id', 'plan_digest', 'decision_id', 'decision_digest', 'pairing_id'}
    if not isinstance(value, dict) or set(value) != fields or value['contract_version'] != CONTRACT:
        raise ContractError('closed Genesis execution request required')
    from .proposal_content_contract import hash_value
    for key in fields - {'contract_version'}:
        (hash_value if key.endswith('_digest') else identifier)(value[key])
    return load_json(canonical(value)), digest(canonical(value))


def ep_request(original, plan, decision, operation_id):
    """Copy original document bytes into EP's distinct envelope, without render."""
    identifier(operation_id)
    if (plan['contract_version'] != PLAN_CONTRACT
            or plan['plan_digest'] != digest(canonical({k: v for k, v in plan.items() if k != 'plan_digest'}))
            or decision['decision_digest'] != digest(canonical({k: v for k, v in decision.items() if k != 'decision_digest'}))):
        raise ContractError('original plan or decision digest differs')
    if (decision['contract_version'] != PLAN_CONTRACT or decision['purpose'] != EFFECT_PURPOSE
            or decision['decision'] != 'APPROVE_EFFECT'
            or (decision['instance_id'], decision['dossier_id'], decision['audience'], decision['plan_id'], decision['plan_digest'])
            != (plan['instance_id'], plan['dossier_id'], plan['audience'], plan['plan_id'], plan['plan_digest'])):
        raise ContractError('exact original positive effect decision required')
    documents = frozen_bundle(original)
    if (documents != plan['documents'] or original['plan_id'] != plan['source_subject']['plan_id']
            or digest(canonical(original['result']['artifacts'])) != plan['source_subject']['result_digest']):
        raise ContractError('original frozen proposal differs')
    envelope = {'contract_version': 'pb-render/1.0', 'kind': 'RENDERED_PROPOSAL_EXAMPLE',
                'files': {row['path']: {'sha256': row['sha256'], 'utf8': row['content']} for row in documents['files']}}
    if digest(canonical(envelope)) != documents['ep_bundle_binding']['canonical_digest']:
        raise ContractError('EP envelope differs from frozen original')
    binding = {'plan_id': plan['plan_id'], 'plan_revision': plan['plan_revision'], 'plan_digest': plan['plan_digest'],
               'decision_id': decision['decision_id'], 'decision_digest': decision['decision_digest'],
               'proposal_id': original['plan_id'], 'proposal_digest': plan['source_subject']['result_digest'],
               'source_instance_id': plan['instance_id'], 'source_actor_id': decision['principal_id'],
               'context_id': plan['dossier_id']}
    from .proposal_content_contract import hash_value
    for key, value in binding.items():
        if key != 'plan_revision':
            (hash_value if key.endswith('_digest') else identifier)(value)
    if type(binding['plan_revision']) is not int or not 1 <= binding['plan_revision'] <= 8:
        raise ContractError('finite original plan revision required')
    identifier(plan['target']['target_ref'])
    result = {'contract_version': '1.0', 'operation_id': operation_id,
              'target_ref': plan['target']['target_ref'], 'effect_plan_binding': binding, 'bundle': envelope}
    if len(canonical(result)) > 524288:
        raise ContractError('finite EP request required')
    return result, digest(canonical(result))
