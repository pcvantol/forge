"""Separate finite pre-project advice grants; reuse private storage/owner boundary."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from hashlib import sha256
from contextlib import contextmanager
import secrets
from .project_proposal_grant import ProjectProposalGrant, operator_binding
from .workspace_review_grant import _private_bytes, _new_token, _write_private
from .project_bootstrap.schema import canonical, load_json
from .approved_worklist import identifier, timestamp
from .concept_advisory_contract import CONTRACT


@dataclass(frozen=True)
class ConceptPrincipal:
    grant_id: str
    principal_id: str
    instance_id: str
    audience: str
    dossier_ids: tuple
    conversation_ids: tuple
    permissions: tuple
    maximum_turns: int
    maximum_tokens: int
    provider_id: str
    transfer_policy_digest: str


class ConceptAdvisoryGrant(ProjectProposalGrant):
    contract = CONTRACT

    def __init__(self, root, instance_id):
        super().__init__(root, instance_id)
        self.path = self.root / 'credentials' / 'concept-advisory' / 'grants.json'
        self.store = self.root / 'onboarding' / 'concept-advisory' / 'store.json'
        self.witness = self.store.parent / 'initialized.json'

    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():
            return []
        value = load_json(_private_bytes(self.path))
        if not isinstance(value, dict) or set(value) != {'contract_version', 'instance_id', 'records'} or value['contract_version'] != CONTRACT or value['instance_id'] != self.instance_id or not isinstance(value['records'], list) or len(value['records']) > 32:
            raise ValueError('concept grant store invalid')
        fields = set(ConceptPrincipal.__dataclass_fields__) | {'operator_binding', 'expires_at', 'state', 'token_digest'}
        seen = set()
        for record in value['records']:
            if not isinstance(record, dict) or set(record) != fields:
                raise ValueError('concept grant record invalid')
            for key in ('grant_id', 'principal_id', 'instance_id', 'audience', 'provider_id'):
                identifier(record[key])
            if record['instance_id'] != self.instance_id or record['grant_id'] in seen or record['state'] not in ('ACTIVE', 'REVOKED'):
                raise ValueError('concept grant identity invalid')
            for key in ('dossier_ids', 'conversation_ids'):
                values = record[key]
                if not isinstance(values, list) or not 1 <= len(values) <= 8 or values != sorted(set(values)):
                    raise ValueError('finite concept scope required')
                for item in values:
                    identifier(item)
            if record['permissions'] not in (['READ'], ['ADVISE', 'READ']):
                raise ValueError('concept rights invalid')
            if type(record['maximum_turns']) is not int or not 1 <= record['maximum_turns'] <= 8 or type(record['maximum_tokens']) is not int or not 1 <= record['maximum_tokens'] <= 384000:
                raise ValueError('concept quota invalid')
            for key in ('token_digest', 'operator_binding'):
                if not isinstance(record[key], str) or len(record[key]) != 64 or any(c not in '0123456789abcdef' for c in record[key]):
                    raise ValueError('concept grant binding invalid')
            binding = record['transfer_policy_digest']
            if not isinstance(binding, str) or len(binding) != 71 or not binding.startswith('sha256:') or any(c not in '0123456789abcdef' for c in binding[7:]):
                raise ValueError('transfer policy binding invalid')
            timestamp(record['expires_at']); seen.add(record['grant_id'])
        return value['records']

    def issue(self, *, principal_id, audience, dossier_ids, conversation_ids, permissions,
              maximum_turns, maximum_tokens, provider_id, transfer_policy_digest, expires_at, token_path):
        from .concept_advisory_service import provider_profile
        for key in (principal_id, audience, provider_id):
            identifier(key)
        for values in (dossier_ids, conversation_ids):
            if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 8 or len(set(values)) != len(values):
                raise ValueError('finite concept scope required')
            for item in values:
                identifier(item)
        if sorted(set(permissions)) not in (['READ'], ['ADVISE', 'READ']):
            raise ValueError('explicit advice/transfer rights required')
        if type(maximum_turns) is not int or not 1 <= maximum_turns <= 8 or type(maximum_tokens) is not int or not 1 <= maximum_tokens <= 384000:
            raise ValueError('finite concept quota required')
        if not datetime.now(UTC) < timestamp(expires_at) <= datetime.now(UTC) + timedelta(days=30):
            raise ValueError('finite expiry required')
        profile = provider_profile(self.root, provider_id)
        if transfer_policy_digest != profile['transfer_policy_digest']:
            raise PermissionError('explicit current provider transfer binding required')
        token_path = Path(token_path)
        if token_path.resolve().is_relative_to(self.store.parent.resolve()) or token_path.resolve() == self.path.resolve():
            raise ValueError('token storage collision')
        with self.boundary():
            records = self._records(True); store = self._store()
            if any(r['principal_id'] == principal_id and (r['maximum_turns'] != maximum_turns or r['maximum_tokens'] != maximum_tokens) for r in records):
                raise PermissionError('retained principal quota immutable')
            if len(records) >= 32:
                raise ValueError('finite grants exhausted')
            scope = {'principal_id': principal_id, 'audience': audience,
                     'maximum_records': maximum_turns, 'maximum_tokens': maximum_tokens}
            for dossier in dossier_ids:
                existing = store['dossiers'].get(dossier)
                if existing is not None and existing != scope:
                    raise PermissionError('retained dossier quota immutable')
                store['dossiers'][dossier] = scope
            if len(store['dossiers']) > 32:
                raise ValueError('finite dossiers exhausted')
            self.save_store(store)
            token = secrets.token_urlsafe(48)
            record = dict(grant_id='concept-'+secrets.token_hex(16), principal_id=principal_id,
                          instance_id=self.instance_id, audience=audience, dossier_ids=sorted(dossier_ids),
                          conversation_ids=sorted(conversation_ids), permissions=sorted(set(permissions)),
                          maximum_turns=maximum_turns, maximum_tokens=maximum_tokens, provider_id=provider_id,
                          transfer_policy_digest=transfer_policy_digest, operator_binding=operator_binding(self.root, self.instance_id),
                          expires_at=expires_at, state='ACTIVE', token_digest=sha256(token.encode()).hexdigest())
            _new_token(token_path, token)
            try:
                _write_private(self.path, canonical({'contract_version': CONTRACT, 'instance_id': self.instance_id, 'records': records+[record]}))
            except Exception:
                token_path.unlink(missing_ok=True); raise
            return {k: v for k, v in record.items() if k not in ('token_digest', 'operator_binding')}

    def authorize(self, authorization, *, audience=None, dossier_id=None, conversation_id=None, permission='READ', **unused):
        if not isinstance(authorization, str) or not authorization.startswith('Bearer '):
            raise PermissionError('authentication required')
        token = authorization[7:]
        if not 1 <= len(token) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise PermissionError('authentication required')
        records = [r for r in self._records() if secrets.compare_digest(r['token_digest'], sha256(token.encode()).hexdigest())]
        if len(records) != 1:
            raise PermissionError('authentication required')
        r = records[0]
        if r['state'] != 'ACTIVE' or timestamp(r['expires_at']) <= datetime.now(UTC) or r['operator_binding'] != operator_binding(self.root, self.instance_id):
            raise PermissionError('current concept grant required')
        if (audience is not None and r['audience'] != audience) or (dossier_id is not None and dossier_id not in r['dossier_ids']) or (conversation_id is not None and conversation_id not in r['conversation_ids']) or permission not in r['permissions']:
            raise PermissionError('concept scope denied')
        return ConceptPrincipal(*(tuple(r[k]) if k in ('dossier_ids', 'conversation_ids', 'permissions') else r[k] for k in ConceptPrincipal.__dataclass_fields__))

    @contextmanager
    def publication(self, authorization, audience, body, *, deadline=None):
        with self.boundary(deadline):
            p = self.authorize(authorization, audience=audience, dossier_id=body.get('dossier_id'), conversation_id=body.get('conversation_id'))
            if body.get('instance_id') != p.instance_id or body.get('principal_id') != p.principal_id:
                raise PermissionError('concept publication scope denied')
            yield
