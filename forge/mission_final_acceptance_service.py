"""Explicit scoped Business acceptance through the existing governed runtime."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from urllib.parse import unquote

from .advisory_contract import digest, AdvisoryConflict
from .approved_worklist import identifier, timestamp
from .governed_continuation import (
    FINAL_ACCEPTANCE_DECISION_CONTRACT, GovernedContinuationService, _digest,
)
from .mission_final_acceptance_contract import CONTRACT, acceptance_request
from .mission_final_acceptance_journal import FinalAcceptanceJournal
from .mission_final_acceptance_package import prepare_package, proven_result, result_summary, source_basis
from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
from .runtime.service import RuntimeServiceLock, RuntimeServiceBusy
from .state import MissionExecutionStatus
from .governance_authority import _digest as canonical_governance_digest
from .workspace_review_grant import _locked
from .worklist_control import control_runtime

BASE = '/v1/mission-final-acceptances'


def decision_document(intent):
    requirement = intent['package']['requirement']
    return {'schema_version': FINAL_ACCEPTANCE_DECISION_CONTRACT,
            'decision_id': intent['decision_id'],
            **{key: requirement[key] for key in ('requirement_id', 'subject_digest',
                'mission_state_revision', 'completion_digest', 'terminal_evidence_digest', 'policy_revision')},
            'decision': 'accept', 'reason': intent['original_request']['reason']}


def consumer_binding(intent):
    return {key: intent[key] for key in ('grant_id', 'request_digest', 'package_digest')} | {
        'operation_id': intent['original_request']['operation_id']}


class MissionFinalAcceptanceService:
    def __init__(self, root, grant):
        self.root, self.grant = Path(root), grant

    def capability(self, token):
        principal = self.grant.authorize(token)
        can_accept = False
        if 'ACCEPT' in principal.permissions:
            try:
                self.grant.authorize(token, permission='ACCEPT')
                can_accept = True
            except PermissionError:
                pass
        return {'contract_version': CONTRACT, 'instance_id': principal.instance_id,
                'project_id': principal.project_id, 'repository_id': principal.repository_id,
                'permissions': list(principal.permissions), 'missions': list(principal.missions),
                'maximum_acceptances': principal.maximum_acceptances, 'expires_at': principal.expires_at,
                'acceptance_supported': can_accept, 'required_role': 'business_owner',
                'read_only': True, 'additional_model_calls': 0, 'execution_started': False}

    def detail(self, token, mission_id):
        principal = self.grant.authorize(token, mission_id)
        with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
            state = runtime.states.get(mission_id)
            try:
                package = prepare_package(runtime, principal, mission_id)
                blocked = []
            except (ValueError, TypeError, KeyError):
                package = None
                blocked = ['FINAL_ACCEPTANCE_EVIDENCE_UNAVAILABLE' if state.status is MissionExecutionStatus.AWAITING_APPROVAL
                           else 'FINAL_ACCEPTANCE_NOT_PENDING']
            can_accept = False
            if package is not None:
                try:
                    self.grant.authorize(token, mission_id, 'ACCEPT')
                    can_accept = True
                except PermissionError:
                    blocked.append('BUSINESS_ACCEPTANCE_AUTHORITY_UNAVAILABLE')
            output = {'contract_version': CONTRACT, 'mission_id': mission_id,
                'package': package, 'package_digest': digest(package) if package else None,
                'acceptance_supported': can_accept, 'blocking_reasons': blocked,
                'current': {'lifecycle': state.status.value, 'mission_state_revision': state.revision,
                            'result': result_summary(state)},
                'read_only': True, 'additional_model_calls': 0, 'execution_started': False}
        self.grant.authorize(token, mission_id)
        return output

    def _canonical(self, runtime, principal, intent):
        service = GovernedContinuationService(runtime.database, runtime.repository, runtime.states, runtime.clock)
        value = service._existing_decision(intent['decision_id'])
        if value is None:
            return None
        document = decision_document(intent)
        evidence = value.get('evidence')
        if (set(value) != {'decision_id', 'subject_id', 'subject_revision', 'capability', 'decision',
                'scope', 'gates', 'predecessor_digest', 'evidence', 'installation_id', 'operator_id', 'occurred_at'}
                or value.get('decision_id') != intent['decision_id']
                or value.get('predecessor_digest') is not None
                or value.get('gates') != [intent['package']['requirement']['reason']]
                or digest(value.get('scope')) != intent['package']['source_basis']['scope_digest']
                or value.get('subject_id') != document['requirement_id']
                or value.get('subject_revision') != document['subject_digest']
                or value.get('capability') != 'BUSINESS_APPROVAL' or value.get('decision') != 'accept'
                or value.get('operator_id') != principal.operator_id
                or value.get('installation_id') != principal.installation_id
                or not isinstance(evidence, dict)
                or set(evidence) != set(document) | {'mission_id', 'authenticated_principal_reference',
                    'consumer_repository_id', 'consumer_intent', 'required_role', 'required_role_actor'}
                or any(evidence.get(key) != item for key, item in document.items())
                or evidence.get('mission_id') != intent['package']['mission_id']
                or evidence.get('authenticated_principal_reference') != principal.reference
                or evidence.get('consumer_repository_id') != principal.repository_id
                or evidence.get('consumer_intent') != consumer_binding(intent)
                or evidence.get('required_role') != 'business_owner'
                or evidence.get('required_role_actor') != 'primary_operator'):
            raise AdvisoryConflict('FINAL_ACCEPTANCE_CANONICAL_RECEIPT_CONFLICT')
        timestamp(value['occurred_at'])
        return value

    def _original(self, runtime, principal, intent):
        state = runtime.states.get(intent['package']['mission_id'])
        if source_basis(state) != intent['package']['source_basis']:
            raise AdvisoryConflict('FINAL_ACCEPTANCE_ORIGINAL_EVIDENCE_CHANGED')
        proven_result(state)
        canonical = self._canonical(runtime, principal, intent)
        row = runtime.database._connection.execute(
            'SELECT status, active_mission_id FROM dispatcher_state WHERE singleton=1').fetchone()
        released = row is not None and not (row['status'] == 'ACTIVE' and row['active_mission_id'] == state.mission_id)
        if canonical is None or state.status is not MissionExecutionStatus.COMPLETED or not released:
            if intent['receipt'] is not None:
                raise AdvisoryConflict('FINAL_ACCEPTANCE_TERMINAL_RECEIPT_CHANGED')
            return None
        approval = state.approval_record
        if (not isinstance(approval, dict) or approval.get('approval_id') != intent['decision_id']
                or approval.get('decision_reference') != intent['package']['requirement']['requirement_id']
                or approval.get('decision_digest') != canonical_governance_digest(canonical)
                or approval.get('approved_by') != 'business_owner'):
            raise AdvisoryConflict('FINAL_ACCEPTANCE_TERMINAL_BINDING_CHANGED')
        receipt = self._receipt(principal, intent, canonical)
        if intent['receipt'] is not None and intent['receipt'] != receipt:
            raise AdvisoryConflict('FINAL_ACCEPTANCE_ORIGINAL_RECEIPT_CONFLICT')
        return receipt

    @staticmethod
    def _receipt(principal, intent, canonical):
        return {'contract_version': CONTRACT, 'mission_id': intent['package']['mission_id'],
            'original_operation_id': intent['original_request']['operation_id'],
            'principal_reference': principal.reference, 'grant_id': intent['grant_id'],
            'decision_id': intent['decision_id'], 'decision_digest': canonical_governance_digest(canonical),
            'requirement_id': intent['package']['requirement']['requirement_id'],
            'package_digest': intent['package_digest'], 'source_basis': intent['package']['source_basis'],
            'accepted_at': canonical['occurred_at'], 'lifecycle': 'COMPLETED', 'dispatcher_released': True}

    def operation(self, token, mission_id, operation_id):
        identifier(operation_id)
        principal = self.grant.authorize(token, mission_id)
        journal = FinalAcceptanceJournal(self.root, principal.reference)
        value = journal.read()
        operation = value['operations'].get(operation_id)
        if operation is None or operation['mission_id'] != mission_id:
            raise FileNotFoundError('unknown scoped Mission acceptance operation')
        intent = value['intents'][mission_id]
        with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
            state = runtime.states.get(mission_id)
            canonical = self._canonical(runtime, principal, intent)
            if intent['receipt'] is not None:
                if canonical is None or intent['receipt'] != self._receipt(principal, intent, canonical):
                    raise AdvisoryConflict('FINAL_ACCEPTANCE_ORIGINAL_RECEIPT_CONFLICT')
                original = intent['receipt']
            else:
                original = self._original(runtime, principal, intent)
            current = {'lifecycle': state.status.value, 'mission_state_revision': state.revision,
                       'result': result_summary(state), 'canonical_decision_recorded': canonical is not None,
                       'evidence_matches_original': source_basis(state) == intent['package']['source_basis']}
        self.grant.authorize(token, mission_id)
        return {'contract_version': CONTRACT, 'operation_id': operation_id, 'mission_id': mission_id,
            'state': 'COMPLETE' if intent['receipt'] is not None else 'PENDING',
            'original_request': operation['request'], 'original_receipt': intent['receipt'],
            'effects_observed_complete': original is not None, 'current': current,
            'read_only': True, 'additional_model_calls': 0, 'execution_started': False}

    def execute(self, token, body):
        request = acceptance_request(body)
        mission_id = request['mission_id']
        principal = self.grant.authorize(token, mission_id, 'ACCEPT')
        if any(request[key] != getattr(principal, key) for key in ('instance_id', 'project_id', 'repository_id')):
            raise PermissionError('foreign final-acceptance command scope')
        journal = FinalAcceptanceJournal(self.root, principal.reference)
        with RuntimeServiceLock(self.root / 'forge.db').acquire(), _locked(journal.path):
            value = journal.read()
            old_operation = value['operations'].get(request['operation_id'])
            if old_operation is not None and old_operation['request'] != request:
                raise AdvisoryConflict('FINAL_ACCEPTANCE_OPERATION_PAYLOAD_CONFLICT')
            intent = value['intents'].get(mission_id)
            if intent is not None:
                expected = {**intent['original_request'], 'operation_id': request['operation_id']}
                if expected != request or intent['grant_id'] != principal.grant_id:
                    raise AdvisoryConflict('FINAL_ACCEPTANCE_ORIGINAL_INTENT_CONFLICT')
            with control_runtime(self.root) as runtime:
                with _locked(self.grant.path), runtime.database._connection:
                    runtime.database._connection.execute('BEGIN IMMEDIATE')
                    principal = self.grant.authorize(token, mission_id, 'ACCEPT')
                    if intent is None:
                        if len(value['intents']) >= principal.maximum_acceptances:
                            raise AdvisoryConflict('FINAL_ACCEPTANCE_ALLOWANCE_EXHAUSTED')
                        package = prepare_package(runtime, principal, mission_id)
                        if digest(package) != request['package_digest']:
                            raise AdvisoryConflict('FINAL_ACCEPTANCE_PREVIEW_STALE')
                        intent = {'original_request': request, 'request_digest': digest(request),
                            'package': package, 'package_digest': digest(package), 'grant_id': principal.grant_id,
                            'decision_id': 'mission-final-acceptance-' + digest({'mission': mission_id,
                                'principal': principal.reference})[7:39],
                            'created_at': datetime.now(UTC).isoformat(), 'receipt': None, 'receipt_digest': None}
                        value['intents'][mission_id] = intent
                    value['operations'][request['operation_id']] = {
                        'request': request, 'request_digest': digest(request), 'mission_id': mission_id}
                    journal.save(value)

                @contextmanager
                def guard():
                    with _locked(self.grant.path):
                        current = self.grant.authorize(token, mission_id, 'ACCEPT')
                        if current != principal or current.grant_id != intent['grant_id']:
                            raise PermissionError('original final-acceptance capability changed')
                        state = runtime.states.get(mission_id)
                        if source_basis(state) != intent['package']['source_basis']:
                            raise AdvisoryConflict('FINAL_ACCEPTANCE_ORIGINAL_EVIDENCE_CHANGED')
                        proven_result(state)
                        self._canonical(runtime, current, intent)
                        yield

                runtime.accept_final_completion(mission_id, decision_document(intent),
                    authenticated_principal_reference=principal.reference, consumer_principal=principal,
                    consumer_intent=consumer_binding(intent), effect_guard=guard)
                with guard():
                    receipt = self._original(runtime, principal, intent)
                    if receipt is None:
                        raise AdvisoryConflict('FINAL_ACCEPTANCE_EFFECTS_INCOMPLETE')
                    intent['receipt'] = receipt
                    intent['receipt_digest'] = digest(receipt)
                    journal.save(value)
        return self.operation(token, mission_id, request['operation_id'])

    def handle(self, method, path, token, body=None):
        try:
            if method == 'GET' and path == BASE + '/capability':
                return 200, self.capability(token)
            parts = path.split('/')
            if len(parts) >= 4 and parts[:3] == ['', 'v1', 'mission-final-acceptances']:
                mission_id = unquote(parts[3])
                identifier(mission_id)
                if len(parts) == 4 and method == 'GET':
                    return 200, self.detail(token, mission_id)
                if len(parts) == 5 and parts[4] == 'accept' and method == 'POST':
                    if not isinstance(body, dict) or body.get('mission_id') != mission_id:
                        raise PermissionError('foreign final-acceptance command Mission')
                    return 200, self.execute(token, body)
                if len(parts) == 6 and parts[4] == 'operations' and method == 'GET':
                    return 200, self.operation(token, mission_id, unquote(parts[5]))
            raise PermissionError('final-acceptance route outside capability scope')
        except PermissionError:
            return 403, {'contract_version': CONTRACT, 'error': {'code': 'FINAL_ACCEPTANCE_SCOPE_DENIED'}}
        except FileNotFoundError:
            return 404, {'contract_version': CONTRACT, 'error': {'code': 'FINAL_ACCEPTANCE_OPERATION_UNKNOWN'}}
        except (ValueError, AdvisoryConflict, RuntimeServiceBusy) as error:
            return 409, {'contract_version': CONTRACT, 'error': {
                'code': getattr(error, 'code', 'FINAL_ACCEPTANCE_CONFLICT')}}
        except (OSError, sqlite3.Error, RuntimeError, TypeError, KeyError):
            return 503, {'contract_version': CONTRACT, 'error': {'code': 'FINAL_ACCEPTANCE_UNAVAILABLE'}}
