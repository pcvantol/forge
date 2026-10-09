"""Bind Workspace references to existing finite Forge conversation capabilities.

This is a correlation index, not a conversation/domain store or grant issuer.
Resolution invokes no provider and never reuses an occupied unbound transcript.
"""
import json
from .advisory_contract import digest, AdvisoryConflict
from .advisory_grant import conversation_path
from .approved_worklist import identifier
from .mission_concept_contract import CONTRACT
from .mission_concept_setup import MissionConceptSetup
from .workspace_review_grant import _locked, _private_bytes, _write_private


class MissionConceptResolver:
    def __init__(self, root, instance_id):
        self.setup = MissionConceptSetup(root, instance_id)
        self.path = self.setup.root / 'advisory' / 'workspace-bindings.json'

    def _read(self):
        if not self.path.exists() and not self.path.is_symlink():
            return {'contract_version': CONTRACT, 'bindings': [], 'operations': []}
        try:
            value = json.loads(_private_bytes(self.path))
        except (ValueError, OSError):
            raise RuntimeError('retained Workspace binding index unavailable') from None
        if (not isinstance(value, dict) or set(value) != {'contract_version', 'bindings', 'operations'}
                or value['contract_version'] != CONTRACT
                or any(not isinstance(value[k], list) or len(value[k]) > 64
                       for k in ('bindings', 'operations'))):
            raise RuntimeError('retained Workspace binding index unavailable')
        keys, slots, operations = set(), set(), set()
        for record in value['bindings']:
            names = {'principal_reference', 'scope', 'workspace_conversation_id',
                     'workspace_draft_id', 'conversation_id', 'binding_key'}
            if not isinstance(record, dict) or set(record) != names:
                raise RuntimeError('closed Workspace binding required')
            if (not isinstance(record['scope'], dict) or set(record['scope']) !=
                    {'instance_id', 'project_id', 'repository_id'}):
                raise RuntimeError('Workspace binding scope unavailable')
            for item in [record['principal_reference'], *record['scope'].values(), record['workspace_conversation_id'],
                         record['workspace_draft_id'], record['conversation_id']]:
                identifier(item)
            key = self.key(record['principal_reference'], record['scope'],
                           record['workspace_conversation_id'], record['workspace_draft_id'])
            slot = (record['principal_reference'], digest(record['scope']), record['conversation_id'])
            if record['binding_key'] != key or key in keys or slot in slots:
                raise RuntimeError('Workspace binding correlation differs')
            keys.add(key); slots.add(slot)
        for record in value['operations']:
            if not isinstance(record, dict) or set(record) != {'principal_reference', 'operation_id', 'binding_key'}:
                raise RuntimeError('closed Workspace resolution intent required')
            identifier(record['operation_id']); identifier(record['principal_reference'])
            operation = (record['principal_reference'], record['operation_id'])
            binding = next((b for b in value['bindings'] if b['binding_key'] == record['binding_key']), None)
            if (operation in operations or binding is None
                    or binding['principal_reference'] != record['principal_reference']):
                raise RuntimeError('Workspace resolution intent differs')
            operations.add(operation)
        return value

    @staticmethod
    def key(principal, scope, conversation_id, draft_id):
        return digest([principal, scope, conversation_id, draft_id])

    def resolve(self, authorization, body):
        if (not isinstance(body, dict) or set(body) != {'contract_version', 'operation_id',
                'workspace_conversation_id', 'workspace_draft_id'} or body['contract_version'] != CONTRACT):
            raise ValueError('closed Workspace resolution request required')
        for key in ('operation_id', 'workspace_conversation_id', 'workspace_draft_id'):
            identifier(body[key])
        principal, _, _ = self.setup.current(authorization)
        scope = {k: getattr(principal, k) for k in ('instance_id', 'project_id', 'repository_id')}
        key = self.key(principal.reference, scope, body['workspace_conversation_id'], body['workspace_draft_id'])
        with _locked(self.setup.grant.path), _locked(self.setup.path), _locked(self.path):
            principal, _, _ = self.setup.current(authorization)
            value = self._read()
            old = next((r for r in value['operations'] if r['principal_reference'] == principal.reference
                        and r['operation_id'] == body['operation_id']), None)
            if old is not None and old['binding_key'] != key:
                raise AdvisoryConflict('WORKSPACE_RESOLUTION_PAYLOAD_CHANGED')
            binding = next((r for r in value['bindings'] if r['binding_key'] == key), None)
            if binding is not None and binding['conversation_id'] not in principal.conversation_ids:
                raise PermissionError('original conversation outside current capability')
            if old is None:
                if len(value['operations']) >= 64:
                    raise AdvisoryConflict('WORKSPACE_RESOLUTION_CAPACITY_EXHAUSTED')
                if binding is None:
                    if len(value['bindings']) >= 64:
                        raise AdvisoryConflict('WORKSPACE_BINDING_CAPACITY_EXHAUSTED')
                    used = {r['conversation_id'] for r in value['bindings']
                            if r['principal_reference'] == principal.reference and r['scope'] == scope}
                    slot = None
                    for candidate in sorted(principal.conversation_ids):
                        if candidate in used:
                            continue
                        transcript = conversation_path(self.setup.root, principal.instance_id,
                            principal.project_id, principal.repository_id, candidate)
                        concept = transcript.with_name('concept-' + transcript.name)
                        if not any(p.exists() or p.is_symlink() for p in (transcript, concept)):
                            slot = candidate
                            break
                    if slot is None:
                        raise AdvisoryConflict('EXISTING_CONVERSATION_CAPACITY_EXHAUSTED')
                    binding = {'principal_reference': principal.reference, 'scope': scope,
                        'workspace_conversation_id': body['workspace_conversation_id'],
                        'workspace_draft_id': body['workspace_draft_id'],
                        'conversation_id': slot, 'binding_key': key}
                    value['bindings'].append(binding)
                value['operations'].append({'principal_reference': principal.reference,
                    'operation_id': body['operation_id'], 'binding_key': key})
                raw = json.dumps(value, sort_keys=True).encode()
                if len(raw) > 65536:
                    raise AdvisoryConflict('WORKSPACE_BINDING_BYTE_CAPACITY_EXHAUSTED')
                self.setup.current(authorization)
                _write_private(self.path, raw)
            self.setup.current(authorization)
            return {'contract_version': CONTRACT, 'operation_id': body['operation_id'],
                    'binding': binding, 'additional_model_calls': 0,
                    'grant_issued': False, 'budget_reset': False}
