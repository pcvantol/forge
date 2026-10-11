"""Explicit durable order amendment using existing governance and mutation lease."""
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

from .advisory_contract import digest
from .approved_worklist import ApprovedWorklistService, candidate_source, identifier, projection, timestamp
from .governance_authority import GovernanceCapability, GovernanceDecision
from .lifecycle import RecommendationLifecycleStore
from .models.criterion_observation import canonical_digest
from .operations_read_api import InstalledOperationsReadService
from .runtime.service import RuntimeServiceLock, RuntimeServiceBusy
from .workspace_review_grant import _locked
from .worklist_control import control_runtime
from .workset_order import (PACKAGE_FIELDS, effective_order, fixed_prefix, validate_order_intent,
                            canonical_intent_effects)
from .workset_order_contract import CONTRACT, OrderConflict, confirm_request, permutation

BASE = '/v1/approved-workset-orders'


def now():
    return datetime.now(UTC).isoformat()


def read_value(root, workset_id):
    with InstalledOperationsReadService(root)._runtime_snapshot() as (db, _):
        row = db.execute('SELECT document FROM approved_worksets WHERE workset_id=?', (workset_id,)).fetchone()
        if row is None:
            raise PermissionError('workset unavailable')
        value = json.loads(row[0])
        if (type(value['revision']) is not int or value['revision'] < 1
                or type(value['held']) is not bool or type(value['revoked']) is not bool
                or value['release'] not in ('DISARMED', 'AUTO_WHEN_ELIGIBLE')):
            raise OrderConflict('CURRENT_ORDER_STATE_INVALID')
        order, revision, order_digest = effective_order(value, db)
        states = {}
        db.execute('ATTACH DATABASE ? AS candidates', (candidate_source(Path(root)).resolve().as_uri() + '?mode=ro',))
        for candidate in order:
            allocation = db.execute('SELECT document FROM candidates.allocations WHERE candidate_id=?', (candidate,)).fetchone()
            mission_id = (value['claims'].get(candidate) or {}).get('mission_id')
            if mission_id is None and allocation:
                mission_id = json.loads(allocation[0])['mission_id']
            state = db.execute('SELECT document FROM mission_state WHERE mission_id=?', (mission_id,)).fetchone() if mission_id else None
            states[candidate] = json.loads(state[0]) if state else None
    return value, order, revision, order_digest, states


class WorksetOrderService:
    def __init__(self, root, grant):
        self.root, self.grant = Path(root), grant

    def capability(self, token):
        p = self.grant.authorize(token)
        supported = False
        if 'REORDER' in p.permissions:
            try:
                self.grant.authorize(token, permission='REORDER'); supported = True
            except PermissionError:
                pass
        with InstalledOperationsReadService(self.root)._runtime_snapshot() as (db, _):
            consumed = sum(sum(i['principal_reference'] == p.reference for i in json.loads(row[0]).get('order_intents', {}).values())
                           for row in db.execute('SELECT document FROM approved_worksets'))
        return {'contract_version': CONTRACT, 'scope': {k: getattr(p, k) for k in
            ('instance_id', 'project_id', 'repository_id')}, 'worksets': list(p.worksets),
            'permissions': list(p.permissions), 'maximum_amendments': p.maximum_amendments,
            'consumed_amendments': consumed, 'remaining_amendments': max(0, p.maximum_amendments - consumed),
            'expires_at': p.expires_at, 'reorder_supported': supported,
            'required_roles': ['business_owner', 'platform_architect'], 'read_only': True}

    def current(self, token, workset_id):
        p = self.grant.authorize(token, workset_id)
        value, order, revision, order_digest, states = read_value(self.root, workset_id)
        prefix = fixed_prefix(value, states)
        read = projection(self.root, p.instance_id, workset_id, p.principal_id, include_order=True)
        result = {'contract_version': CONTRACT, 'workset_id': workset_id,
            'current': read, 'order_revision': revision, 'order_digest': order_digest,
            'current_order': order, 'fixed_prefix': prefix,
            'members': [{'candidate_id': c, 'title': next(m['mission']['title'] for m in value['definition']['members']
                if m['candidate_id'] == c), 'mission_id': states[c]['mission_id'] if states[c] else None,
                'position': index + 1, 'remaining_position': index - prefix + 1 if index >= prefix else None,
                'dependencies': next(m['dependencies'] for m in value['definition']['members'] if m['candidate_id'] == c),
                'claimed': c in value['claims']} for index, c in enumerate(order)], 'read_only': True,
            'additional_model_calls': 0, 'execution_started': False}
        self.grant.authorize(token, workset_id)
        return result

    def _preview(self, principal, workset_id, proposed, *, own_intent=None):
        value, order, revision, order_digest, states = read_value(self.root, workset_id)
        members = {m['candidate_id']: m for m in value['definition']['members']}
        fixed = fixed_prefix(value, states)
        new = permutation(order, proposed, fixed, members)
        if (value['revoked'] or value['held'] or value['release'] != 'AUTO_WHEN_ELIGIBLE'
                or timestamp(value['definition']['expires_at']) <= datetime.now(UTC)
                or value['consumed_activations'] >= value['definition']['maximum_activations']):
            raise OrderConflict('FUTURE_RELEASE_NOT_ELIGIBLE')
        pending = value.get('order_intents', {})
        if any(i['state'] != 'APPLIED' and key != own_intent for key, i in pending.items()):
            raise OrderConflict('ANOTHER_ORDER_INTENT_PENDING')
        read = projection(self.root, principal.instance_id, workset_id, principal.principal_id, include_order=True)
        permitted = {'DEPENDENCY_NOT_PROVEN', 'ACTIVATION_NOT_YET_QUALIFIED'}
        if own_intent:
            permitted.add('ORDER_AMENDMENT_PENDING')
        for item in read['items']:
            allowed = permitted | ({'FINAL_ACCEPTANCE_REQUIRED', 'PROGRESSION_REVIEW_REQUIRED'}
                                   if item['candidate_id'] in value['claims'] else set())
            if set(item['blocking_reasons']) - allowed:
                raise OrderConflict('CURRENT_SUBJECT_OR_AUTHORITY_UNAVAILABLE')
        return {'contract_version': CONTRACT, **{k: getattr(principal, k) for k in
            ('instance_id', 'project_id', 'repository_id')}, 'workset_id': workset_id,
            'definition_digest': value['definition_digest'], 'authority_digest': value['authority_digest'],
            'workset_revision': value['revision'], 'order_revision': revision,
            'previous_order_digest': order_digest, 'current_order': order, 'proposed_order': new,
            'fixed_prefix': fixed, 'subjects': [{'candidate_id': m['candidate_id'], 'subject_revision': m['subject_revision']}
                                              for m in value['definition']['members']],
            'expires_at': value['definition']['expires_at'],
            'maximum_activations': value['definition']['maximum_activations'],
            'consumed_activations': value['consumed_activations']}

    def preview(self, token, workset_id, body):
        if type(body) is not dict or set(body) != {'contract_version', 'proposed_order'} or body['contract_version'] != CONTRACT:
            raise ValueError('closed order preview required')
        p = self.grant.authorize(token, workset_id)
        package = self._preview(p, workset_id, body['proposed_order'])
        supported = True
        try:
            self.grant.authorize(token, workset_id, 'REORDER')
        except PermissionError:
            supported = False
        blocked = [] if supported else ['ORDER_AUTHORITY_UNAVAILABLE']
        if self.capability(token)['remaining_amendments'] == 0:
            supported = False; blocked.append('ORDER_ALLOWANCE_EXHAUSTED')
        current = self.current(token, workset_id)
        if (current['current']['workset_revision'] != package['workset_revision']
                or current['order_digest'] != package['previous_order_digest']):
            raise OrderConflict('ORDER_PREVIEW_STALE')
        titles = {member['candidate_id']: member['title'] for member in current['members']}
        display = {kind: [{'position': index + 1, 'candidate_id': candidate, 'title': titles[candidate]}
                          for index, candidate in enumerate(package[field])]
                   for kind, field in (('current', 'current_order'), ('proposed', 'proposed_order'))}
        return {'contract_version': CONTRACT, 'package': package, 'package_digest': digest(package),
            'current': current, 'display_orders': display, 'reorder_supported': supported,
            'blocking_reasons': blocked,
            'consequences': ['ONLY_UNCLAIMED_ORDER_CHANGES', 'NO_NEW_MISSION_OR_START_ALLOWANCE',
                             'BUSINESS_AND_ARCHITECTURE_ORDER_DECISIONS'],
            'read_only': True, 'additional_model_calls': 0, 'execution_started': False}

    def operation(self, token, workset_id, operation_id):
        identifier(operation_id)
        p = self.grant.authorize(token, workset_id)
        value, _, _, _, _ = read_value(self.root, workset_id)
        intent = value.get('order_intents', {}).get(operation_id)
        if intent is None:
            raise FileNotFoundError('unknown order operation')
        if intent['principal_reference'] != p.reference:
            raise PermissionError('original order operation belongs to another principal')
        self._validate_intent(intent, operation_id)
        with InstalledOperationsReadService(self.root)._runtime_snapshot() as (db, _):
            observed_decisions = canonical_intent_effects(db, intent)
        if intent['state'] == 'APPLIED':
            amendment = next((a for a in value.get('order_amendments', [])
                              if a['receipt']['operation_id'] == operation_id), None)
            if (amendment is None or amendment['receipt'] != intent['receipt']
                    or amendment['package'] != intent['request']['package']
                    or amendment['grant_id'] != intent['grant_id']
                    or amendment['principal_reference'] != intent['principal_reference']):
                raise OrderConflict('ORIGINAL_ORDER_RECEIPT_CONFLICT')
        return {'contract_version': CONTRACT, 'operation_id': operation_id, 'state': intent['state'],
            'original_request': intent['request'], 'original_receipt': intent['receipt'],
            'canonical_decisions_observed': observed_decisions,
            'current': self.current(token, workset_id), 'read_only': True,
            'additional_model_calls': 0, 'execution_started': False}

    @staticmethod
    def _validate_intent(intent, operation_id):
        validate_order_intent(intent, operation_id)

    def execute(self, token, body):
        request = confirm_request(body)
        package = request['package']; key = request['workset_id']; operation = request['operation_id']
        p = self.grant.authorize(token, key, 'REORDER')
        if (set(package) != PACKAGE_FIELDS or digest(package) != request['package_digest']
                or any(request[k] != getattr(p, k) or package[k] != getattr(p, k)
                       for k in ('instance_id', 'project_id', 'repository_id')) or package['workset_id'] != key):
            raise PermissionError('foreign or changed exact order package')
        with RuntimeServiceLock(self.root / 'forge.db').acquire(), control_runtime(self.root) as runtime, \
                RecommendationLifecycleStore(candidate_source(self.root)) as lifecycle:
            service = ApprovedWorklistService(runtime, lifecycle)
            value = service._get(key); intents = value.get('order_intents', {}); intent = intents.get(operation)
            if intent is not None:
                self._validate_intent(intent, operation)
                if intent['request'] != request or intent['grant_id'] != p.grant_id or intent['principal_reference'] != p.reference:
                    raise OrderConflict('ORIGINAL_ORDER_INTENT_CONFLICT')
                if intent['state'] == 'APPLIED':
                    effective_order(value, service.db)
                    return self.operation(token, key, operation)
            else:
                with _locked(self.grant.path), service.db:
                    service.db.execute('BEGIN IMMEDIATE')
                    p = self.grant.authorize(token, key, 'REORDER')
                    if self._preview(p, key, package['proposed_order']) != package:
                        raise OrderConflict('ORDER_PREVIEW_STALE')
                    consumed = 0
                    for row in service.db.execute('SELECT document FROM approved_worksets'):
                        consumed += sum(i['principal_reference'] == p.reference for i in json.loads(row[0]).get('order_intents', {}).values())
                    if consumed >= p.maximum_amendments or len(intents) >= 64:
                        raise OrderConflict('ORDER_ALLOWANCE_EXHAUSTED')
                    intent = {'request': request, 'request_digest': digest(request),
                        'principal_reference': p.reference, 'grant_id': p.grant_id, 'operator_id': p.operator_id,
                        'installation_id': p.installation_id, 'created_at': now(),
                        'phase_revision': value['revision'] + 1, 'state': 'PENDING', 'decisions': {}, 'receipt': None}
                    value.setdefault('order_intents', {})[operation] = intent
                    service._save(value, value['revision'])
            for role, capability in (('business', GovernanceCapability.BUSINESS_APPROVAL),
                                     ('architecture', GovernanceCapability.ARCHITECTURE_APPROVAL), ('apply', None)):
                with _locked(self.grant.path), service.db:
                    service.db.execute('BEGIN IMMEDIATE')
                    p = self.grant.authorize(token, key, 'REORDER')
                    value = service._get(key); intent = value['order_intents'][operation]
                    self._validate_intent(intent, operation)
                    if p.grant_id != intent['grant_id'] or p.operator_id != intent['operator_id'] or p.installation_id != intent['installation_id']:
                        raise PermissionError('original order authority changed')
                    if value['revision'] != intent['phase_revision']:
                        raise OrderConflict('ORDER_EFFECT_REVISION_CONFLICT')
                    current = self._preview(p, key, package['proposed_order'], own_intent=operation)
                    current['workset_revision'] = package['workset_revision']
                    if current != package:
                        raise OrderConflict('ORDER_EFFECT_PREFIX_OR_EVIDENCE_CHANGED')
                    if role != 'apply':
                        decision_id = 'order:' + digest([p.reference, key, request['package_digest'], role])[7:]
                        expected = {'subject_id': 'workset-order:' + key, 'subject_revision': request['package_digest'],
                            'capability': capability.value, 'decision': 'approved', 'scope': sorted(package['current_order']),
                            'gates': ['EXACT_REMAINING_ORDER', 'UNCHANGED_CLAIMED_PREFIX'], 'installation_id': p.installation_id,
                            'operator_id': p.operator_id, 'evidence': {'actor': 'primary_operator', 'grant_id': p.grant_id,
                                'principal_reference': p.reference, 'package_digest': request['package_digest'],
                                'order_revision': package['order_revision'] + 1, 'request_digest': intent['request_digest'],
                                'original_operation_id': operation}}
                        if service.db.execute('SELECT 1 FROM governance_decisions WHERE decision_id=?', (decision_id,)).fetchone():
                            actual = runtime.repository.decision(decision_id)
                            if any(actual[k] != v for k, v in expected.items()):
                                raise OrderConflict('ORIGINAL_CANONICAL_ORDER_DECISION_CHANGED')
                        else:
                            runtime.repository.record(GovernanceDecision(decision_id, expected['subject_id'], expected['subject_revision'],
                                capability, 'approved', tuple(package['current_order']), tuple(expected['gates']),
                                evidence=expected['evidence']), runtime.repository.operators.context())
                        intent['decisions'][role] = decision_id
                    else:
                        receipt = {'contract_version': CONTRACT, 'operation_id': operation, 'workset_id': key,
                            'package_digest': request['package_digest'], 'order_revision': package['order_revision'] + 1,
                            'original_order': package['current_order'], 'applied_order': package['proposed_order'],
                            'fixed_prefix': package['fixed_prefix'], 'decisions': dict(intent['decisions']),
                            'consumed_activations': value['consumed_activations'], 'applied_at': now()}
                        value.setdefault('order_amendments', []).append({'package': package,
                            'package_digest': request['package_digest'], 'grant_id': p.grant_id,
                            'principal_reference': p.reference, 'operator_id': p.operator_id,
                            'installation_id': p.installation_id, 'decisions': dict(intent['decisions']),
                            'receipt': receipt, 'receipt_digest': canonical_digest(receipt)})
                        intent['state'] = 'APPLIED'; intent['receipt'] = receipt
                        effective_order(value, service.db)
                    # Canonical governance commits independently. Re-establish
                    # the database write boundary and current authority before
                    # publishing the phase/receipt into the workset row.
                    if not service.db.in_transaction:
                        service.db.execute('BEGIN IMMEDIATE')
                    current_principal = self.grant.authorize(token, key, 'REORDER')
                    if current_principal != p:
                        raise PermissionError('order authority changed at publication')
                    intent['phase_revision'] = value['revision'] + 1
                    service._save(value, value['revision'])
        return self.operation(token, key, operation)

    def handle(self, method, path, token, body=None):
        try:
            if method == 'GET' and path == BASE + '/capability':
                return 200, self.capability(token)
            segments = path.removeprefix(BASE + '/').split('/')
            if not path.startswith(BASE + '/') or not 1 <= len(segments) <= 3:
                raise PermissionError('order endpoint outside scope')
            key = identifier(segments[0])
            if method == 'GET' and len(segments) == 1:
                return 200, self.current(token, key)
            if method == 'POST' and segments[1:] == ['preview']:
                return 200, self.preview(token, key, body)
            if method == 'POST' and segments[1:] == ['confirm']:
                if type(body) is not dict or body.get('workset_id') != key:
                    raise PermissionError('foreign command workset')
                return 200, self.execute(token, body)
            if method == 'GET' and len(segments) == 3 and segments[1] == 'operations':
                return 200, self.operation(token, key, segments[2])
            raise PermissionError('order endpoint outside scope')
        except PermissionError:
            return 403, {'contract_version': CONTRACT, 'error': {'code': 'ORDER_SCOPE_DENIED'}}
        except FileNotFoundError:
            return 404, {'contract_version': CONTRACT, 'error': {'code': 'ORDER_OPERATION_UNKNOWN'}}
        except (ValueError, RuntimeServiceBusy) as error:
            return 409, {'contract_version': CONTRACT, 'error': {'code': str(error) if isinstance(error, OrderConflict) else 'ORDER_CONFLICT'}}
        except (OSError, sqlite3.Error, RuntimeError, KeyError, TypeError):
            return 503, {'contract_version': CONTRACT, 'error': {'code': 'ORDER_UNAVAILABLE'}}
