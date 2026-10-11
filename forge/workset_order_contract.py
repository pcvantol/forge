"""Closed consumer intent for reprioritising an existing finite workset."""
import json

from .advisory_contract import text
from .advisory_candidate_contract import hash_reference
from .approved_worklist import identifier, timestamp

CONTRACT = 'forge-workset-order/v1'
READ_CONTRACT = 'forge-workspace-worklist/v2'
PERMISSIONS = ('READ', 'REORDER')
PACKAGE_FIELDS = frozenset({'contract_version', 'instance_id', 'project_id', 'repository_id',
    'workset_id', 'definition_digest', 'authority_digest', 'workset_revision', 'order_revision',
    'previous_order_digest', 'current_order', 'proposed_order', 'fixed_prefix', 'subjects',
    'expires_at', 'maximum_activations', 'consumed_activations'})


class OrderConflict(ValueError):
    pass


class OrderVersionRequired(ValueError):
    def __init__(self):
        super().__init__('WORKSET_ORDER_V2_REQUIRED')


def exact_order(value):
    if (type(value) is not list or not 1 <= len(value) <= 64
            or any(type(item) is not str for item in value)
            or len(set(value)) != len(value)):
        raise ValueError('finite unique exact Candidate order required')
    for item in value:
        identifier(item)
    return list(value)


def confirm_request(value):
    fields = {'contract_version', 'operation_id', 'instance_id', 'project_id',
              'repository_id', 'workset_id', 'package_digest', 'package', 'reason', 'confirm'}
    if (type(value) is not dict or set(value) != fields
            or value['contract_version'] != CONTRACT or value['confirm'] is not True):
        raise ValueError('closed explicit order confirmation required')
    for key in ('operation_id', 'instance_id', 'project_id', 'repository_id', 'workset_id'):
        identifier(value[key])
    hash_reference(value['package_digest'])
    validate_package(value['package'])
    text(value['reason'], 1000)
    return json.loads(json.dumps(value, sort_keys=True))


def validate_package(package):
    if type(package) is not dict or set(package) != PACKAGE_FIELDS or package['contract_version'] != CONTRACT:
        raise ValueError('closed shown order package required')
    for key in ('instance_id', 'project_id', 'repository_id', 'workset_id'):
        identifier(package[key])
    for key in ('definition_digest', 'authority_digest', 'previous_order_digest'):
        hash_reference(package[key])
    old, new = exact_order(package['current_order']), exact_order(package['proposed_order'])
    if set(old) != set(new) or old == new:
        raise ValueError('exact changed permutation required')
    for key, minimum, maximum in (('workset_revision', 1, 2**63-1), ('order_revision', 0, 63),
            ('fixed_prefix', 0, len(old)), ('maximum_activations', 1, len(old)),
            ('consumed_activations', 0, package['maximum_activations'])):
        if type(package[key]) is not int or not minimum <= package[key] <= maximum:
            raise ValueError('typed finite order package revisions and consumption required')
    if old[:package['fixed_prefix']] != new[:package['fixed_prefix']]:
        raise ValueError('shown fixed prefix changed')
    timestamp(package['expires_at'])
    subjects = package['subjects']
    if type(subjects) is not list or len(subjects) != len(old):
        raise ValueError('exact shown subjects required')
    seen = set()
    for subject in subjects:
        if type(subject) is not dict or set(subject) != {'candidate_id', 'subject_revision'}:
            raise ValueError('closed shown subject required')
        identifier(subject['candidate_id']); hash_reference(subject['subject_revision'])
        if subject['candidate_id'] in seen:
            raise ValueError('duplicate shown subject')
        seen.add(subject['candidate_id'])
    if seen != set(old):
        raise ValueError('shown subject set changed')


def permutation(current, proposed, fixed_prefix, members):
    """Compare exact existing subjects; never rewrite membership or dependencies."""
    old, new = exact_order(current), exact_order(proposed)
    if type(fixed_prefix) is not int or not 0 <= fixed_prefix <= len(old):
        raise ValueError('typed fixed prefix required')
    if set(old) != set(new) or set(members) != set(old):
        raise OrderConflict('ORDER_MEMBERSHIP_CHANGED')
    if old[:fixed_prefix] != new[:fixed_prefix]:
        raise OrderConflict('CLAIMED_PREFIX_CHANGED')
    seen = set()
    for candidate in new:
        dependencies = members[candidate]['dependencies']
        if (type(dependencies) is not list
                or any(type(dep) is not str for dep in dependencies)
                or len(set(dependencies)) != len(dependencies)
                or any(dep not in seen for dep in dependencies)):
            raise OrderConflict('HARD_DEPENDENCY_ORDER_CONFLICT')
        seen.add(candidate)
    if new == old:
        raise OrderConflict('ORDER_UNCHANGED')
    return new


def grant_bounds(permissions, worksets, maximum_amendments):
    if (type(permissions) not in (list, tuple) or 'READ' not in permissions
            or any(type(p) is not str or p not in PERMISSIONS for p in permissions)
            or len(set(permissions)) != len(permissions)):
        raise ValueError('separate explicit order permissions required')
    if (type(worksets) not in (list, tuple) or not 1 <= len(worksets) <= 16
            or type(maximum_amendments) is not int or not 1 <= maximum_amendments <= 16):
        raise ValueError('finite typed order scope and allowance required')
    seen = set()
    for workset in worksets:
        if type(workset) is not dict or set(workset) != {'workset_id', 'definition_digest'}:
            raise ValueError('exact original workset scope required')
        identifier(workset['workset_id'])
        hash_reference(workset['definition_digest'])
        if workset['workset_id'] in seen:
            raise ValueError('duplicate workset scope')
        seen.add(workset['workset_id'])
