"""Explicit finite Genesis purpose; no execution-host credential or old grant upgrade."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
import json
import secrets
import time
from .approved_worklist import identifier, timestamp
from .project_bootstrap.schema import canonical
from .project_proposal_grant import ProjectProposalGrant, operator_binding
from .proposal_content_grant import ProposalContentGrant
from .candidate_decision_grant import signer
from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
from .workspace_review_grant import _private_bytes, _write_private, _new_token
from .proposal_content_contract import hash_value
from .genesis_bootstrap_contract import CONTRACT, EFFECT_PURPOSE


def human(root, instance, principal, decide):
    binding = signer(root, instance, 'solo', ('READ',), principal)
    if decide:
        if principal != binding['operator_id']:
            raise PermissionError('actual human effect principal required')
        with InstalledDynamicMissionRuntime.open_for_governance_read(str(root)) as runtime:
            row = runtime.database._connection.execute(
                'SELECT 1 FROM governance_authority WHERE installation_id=? AND operator_id=? AND capability=?',
                (binding['installation_id'], principal, 'OWNER_PROGRAMME_AUTHORIZATION')).fetchone()
            if row is None:
                raise PermissionError('current programme effect authority required')
    return binding


@dataclass(frozen=True)
class BootstrapPrincipal:
    grant_id: str
    principal_id: str
    instance_id: str
    audience: str
    proposal_principal_id: str
    dossier_ids: tuple
    source_plan_ids: tuple
    permissions: tuple
    exact_plans: tuple
    purpose: str
    human_binding: dict
    operator_binding: str


class GenesisBootstrapGrant(ProjectProposalGrant):
    contract = CONTRACT

    def __init__(self, root, instance_id):
        super().__init__(root, instance_id)
        self.path = self.root/'credentials'/'genesis-bootstrap'/'grants.json'
        self.store = self.root/'onboarding'/'genesis-bootstrap'/'store.json'
        self.witness = self.store.parent/'initialized.json'

    @contextmanager
    def boundary(self, deadline=None):
        # Global order: owning original proposal, content, Genesis, canonical DB.
        with ProjectProposalGrant(self.root, self.instance_id).lock_until(deadline):
            with ProposalContentGrant(self.root, self.instance_id).lock_until(deadline):
                with super().boundary(deadline):
                    yield

    @staticmethod
    def bounds(dossiers, sources, permissions, plans):
        for values in (dossiers, sources):
            if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 8 or len(set(values)) != len(values):
                raise ValueError('finite exact source scope required')
            for value in values:
                identifier(value)
        if not isinstance(permissions, (list, tuple)) or not permissions or 'READ' not in permissions or len(set(permissions)) != len(permissions) or set(permissions)-{'READ','PREPARE','DECIDE_EFFECT'}:
            raise ValueError('explicit Genesis permissions required')
        if not isinstance(plans, (list, tuple)) or len(plans) > 8 or bool(plans) != ('DECIDE_EFFECT' in permissions):
            raise ValueError('decision requires finite already frozen plans')
        seen = set()
        for plan in plans:
            if not isinstance(plan, dict) or set(plan) != {'plan_id','plan_digest'}:
                raise ValueError('exact plan and digest required')
            identifier(plan['plan_id']); hash_value(plan['plan_digest'])
            if plan['plan_id'] in seen:
                raise ValueError('duplicate exact plan')
            seen.add(plan['plan_id'])

    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():
            return []
        value = json.loads(_private_bytes(self.path))
        if not isinstance(value, dict) or set(value) != {'contract_version','instance_id','records'} or value['contract_version'] != CONTRACT or value['instance_id'] != self.instance_id or not isinstance(value['records'], list) or len(value['records']) > 32:
            raise ValueError('closed finite Genesis grant store required')
        seen = set()
        for row in value['records']:
            if not isinstance(row, dict) or set(row) != set(BootstrapPrincipal.__dataclass_fields__) | {'token_digest','expires_at','state'}:
                raise ValueError('closed Genesis grant required')
            for key in ('grant_id','principal_id','instance_id','audience','proposal_principal_id'):
                identifier(row[key])
            self.bounds(row['dossier_ids'], row['source_plan_ids'], row['permissions'], row['exact_plans'])
            timestamp(row['expires_at']); hash_value(row['operator_binding']); hash_value(row['token_digest'])
            binding = row['human_binding']
            if not isinstance(binding, dict) or set(binding) != {'operator_id','operator_binding_version','installation_id'} or type(binding['operator_binding_version']) is not int or binding['operator_binding_version'] < 1:
                raise ValueError('original human binding required')
            identifier(binding['operator_id']); identifier(binding['installation_id'])
            if row['instance_id'] != self.instance_id or row['purpose'] != EFFECT_PURPOSE or row['state'] not in ('ACTIVE','REVOKED') or row['grant_id'] in seen or ('DECIDE_EFFECT' in row['permissions'] and row['principal_id'] != binding['operator_id']):
                raise ValueError('Genesis grant binding invalid')
            seen.add(row['grant_id'])
        return value['records']

    def save_records(self, records):
        raw = canonical({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records})
        if len(raw) > 131072:
            raise ValueError('finite Genesis grant capacity exceeded')
        _write_private(self.path, raw)

    def issue(self, *, principal_id, audience, proposal_principal_id, dossier_ids, source_plan_ids, permissions, exact_plans, expires_at, token_path):
        for value in (principal_id, audience, proposal_principal_id):
            identifier(value)
        self.bounds(dossier_ids, source_plan_ids, permissions, exact_plans)
        if not datetime.now(UTC) < timestamp(expires_at) <= datetime.now(UTC)+timedelta(days=30):
            raise ValueError('finite Genesis grant expiry required')
        token_path = Path(token_path)
        # Credentials cannot overwrite any runtime state, other grants or evidence.
        if token_path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('external private token destination required')
        with self.boundary():
            binding = human(self.root, self.instance_id, principal_id, 'DECIDE_EFFECT' in permissions)
            source = ProjectProposalGrant(self.root, self.instance_id)
            from .project_proposal_service import ProjectProposalService
            store = source._store()
            for source_id in source_plan_ids:
                record = ProjectProposalService(source)._record(store, source_id)
                if record is None or record['dossier_id'] not in dossier_ids or record['principal_id'] != proposal_principal_id or record['audience'] != audience:
                    raise PermissionError('exact original source scope required')
            own = self._store()
            for plan in exact_plans:
                row = own['records'].get(plan['plan_id'])
                if row is None or row['kind'] != 'PLAN':
                    raise PermissionError('already frozen plan required')
                doc = row['document']
                if doc['plan_digest'] != plan['plan_digest'] or doc['source_subject']['plan_id'] not in source_plan_ids or doc['dossier_id'] not in dossier_ids or doc['audience'] != audience or doc['source_subject']['proposal_principal_id'] != proposal_principal_id:
                    raise PermissionError('exact effect plan scope required')
            rows = self._records(True)
            if len(rows) >= 32:
                raise ValueError('finite Genesis grant capacity exhausted')
            token = secrets.token_urlsafe(48)
            row = {'grant_id':'bootstrap-'+secrets.token_hex(16),'principal_id':principal_id,'instance_id':self.instance_id,'audience':audience,
                   'proposal_principal_id':proposal_principal_id,'dossier_ids':sorted(dossier_ids),'source_plan_ids':sorted(source_plan_ids),
                   'permissions':sorted(permissions),'exact_plans':list(exact_plans),'purpose':EFFECT_PURPOSE,'human_binding':binding,
                   'operator_binding':operator_binding(self.root,self.instance_id),'expires_at':expires_at,'state':'ACTIVE','token_digest':sha256(token.encode()).hexdigest()}
            _new_token(token_path, token)
            try:
                self.save_records([*rows, row])
            except BaseException:
                token_path.unlink(missing_ok=True)
                raise
            return {k:v for k,v in row.items() if k not in ('operator_binding','token_digest')}

    def current(self, row):
        if row['state'] != 'ACTIVE' or timestamp(row['expires_at']) <= datetime.now(UTC) or row['operator_binding'] != operator_binding(self.root,self.instance_id):
            raise PermissionError('Genesis grant inactive')
        if human(self.root,self.instance_id,row['principal_id'],'DECIDE_EFFECT' in row['permissions']) != row['human_binding']:
            raise PermissionError('current human binding changed')

    def authorize(self, authorization, *, audience=None, dossier_id=None, permission='READ', source_plan_id=None, plan=None):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '):
            raise PermissionError('separate Genesis credential required')
        token = authorization[7:]
        if not 1 <= len(token) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise PermissionError('invalid Genesis credential')
        rows = [r for r in self._records() if secrets.compare_digest(r['token_digest'],sha256(token.encode()).hexdigest())]
        if len(rows) != 1:
            raise PermissionError('Genesis credential required')
        row = rows[0]; self.current(row)
        if (audience is not None and audience != row['audience']) or (dossier_id is not None and dossier_id not in row['dossier_ids']) or permission not in row['permissions'] or (source_plan_id is not None and source_plan_id not in row['source_plan_ids']):
            raise PermissionError('Genesis scope denied')
        if plan is not None and permission == 'DECIDE_EFFECT' and {'plan_id':plan['plan_id'],'plan_digest':plan['plan_digest']} not in row['exact_plans']:
            raise PermissionError('exact effect plan required')
        return BootstrapPrincipal(*(tuple(row[k]) if k in ('dossier_ids','source_plan_ids','permissions','exact_plans') else row[k] for k in BootstrapPrincipal.__dataclass_fields__))

    @contextmanager
    def publication(self, authorization, audience, body, *, deadline=None):
        from .genesis_bootstrap_service import GenesisBootstrapService
        with self.boundary(deadline):
            p = self.authorize(authorization,audience=audience,dossier_id=body.get('dossier_id'))
            service = GenesisBootstrapService(self)
            if body.get('plan') is not None:
                expected = service.view(p, self._store(), body['plan']['plan_id'], body.get('original_decision'))
            else:
                expected = service.capability(p)
            if body != expected:
                raise PermissionError('Genesis publication snapshot changed')
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError('bounded Genesis publication deadline')
            yield

    def revoke(self, grant_id):
        identifier(grant_id)
        with self.boundary():
            rows = self._records(); row = next((r for r in rows if r['grant_id']==grant_id),None)
            if row is None:
                raise ValueError('unknown Genesis grant')
            row['state']='REVOKED'; self.save_records(rows)
            return {'grant_id':grant_id,'state':'REVOKED'}
