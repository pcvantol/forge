"""Finite owner-issued content DECIDE scopes bound to existing human authority."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
import secrets
import sqlite3
import time
from .approved_worklist import identifier, timestamp
from .project_bootstrap.schema import canonical
from .project_proposal_grant import ProjectProposalGrant, operator_binding
from .workspace_review_grant import _private_bytes, _write_private, _new_token
from .candidate_decision_grant import signer
from .proposal_content_contract import CONTRACT, PROFILE_ID, ROLES, hash_value

@dataclass(frozen=True)
class ContentPrincipal:
    grant_id: str
    principal_id: str
    instance_id: str
    audience: str
    proposal_principal_id: str
    dossier_ids: tuple
    permissions: tuple
    roles: tuple
    profile_id: str
    human_binding: dict
    operator_binding: str

class ProposalContentGrant(ProjectProposalGrant):
    contract = CONTRACT
    def __init__(self, root, instance_id):
        super().__init__(root, instance_id)
        self.path = self.root/'credentials'/'proposal-content-decisions'/'grants.json'
        self.store = self.root/'onboarding'/'content-decisions'/'store.json'
        self.witness = self.store.parent/'initialized.json'

    @contextmanager
    def boundary(self, deadline=None):
        # Same lock order as R52: source grant, own grant, canonical writer.
        # Source proposal bytes are never written by this service.
        with ProjectProposalGrant(self.root, self.instance_id).lock_until(deadline):
            with super().boundary(deadline): yield

    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink(): return []
        import json
        value = json.loads(_private_bytes(self.path))
        if not isinstance(value, dict) or set(value) != {'contract_version','instance_id','records'} or value['contract_version'] != CONTRACT or value['instance_id'] != self.instance_id or not isinstance(value['records'], list) or len(value['records']) > 32:
            raise ValueError('finite content grants required')
        seen = set()
        for r in value['records']:
            if not isinstance(r, dict) or set(r) != set(ContentPrincipal.__dataclass_fields__) | {'token_digest','expires_at','state'}: raise ValueError('closed content grant required')
            for key in ('grant_id','principal_id','instance_id','audience','proposal_principal_id'): identifier(r[key])
            if r['instance_id'] != self.instance_id or r['profile_id'] != PROFILE_ID or r['state'] not in ('ACTIVE','REVOKED') or r['grant_id'] in seen: raise ValueError('grant binding invalid')
            self.bounds(r['dossier_ids'],r['permissions'],r['roles']);timestamp(r['expires_at'])
            hash_value(r['token_digest']);hash_value(r['operator_binding'])
            binding = r['human_binding']
            if not isinstance(binding,dict) or set(binding) != {'operator_id','operator_binding_version','installation_id'} or type(binding['operator_binding_version']) is not int or binding['operator_binding_version'] < 1: raise ValueError('human binding invalid')
            identifier(binding['operator_id']);identifier(binding['installation_id'])
            if 'DECIDE' in r['permissions'] and r['principal_id'] != binding['operator_id']: raise ValueError('human decision principal required')
            seen.add(r['grant_id'])
        return value['records']

    @staticmethod
    def bounds(dossiers, permissions, roles):
        if not isinstance(dossiers,(tuple,list)) or not 1 <= len(dossiers) <= 8 or len(set(dossiers)) != len(dossiers): raise ValueError('finite dossiers required')
        for d in dossiers: identifier(d)
        if not isinstance(permissions,(tuple,list)) or not permissions or len(set(permissions)) != len(permissions) or set(permissions)-{'READ','DECIDE'} or 'READ' not in permissions: raise ValueError('explicit content permissions required')
        if not isinstance(roles,(tuple,list)) or len(set(roles)) != len(roles) or set(roles)-set(ROLES) or bool(roles) != ('DECIDE' in permissions): raise ValueError('explicit content roles required')

    def save_records(self, records):
        raw=canonical({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records})
        if len(raw)>65536:raise ValueError('finite grant storage exceeded')
        _write_private(self.path, raw)

    def issue(self, *, principal_id, audience, proposal_principal_id, dossier_ids, permissions, roles, expires_at, token_path):
        for x in (principal_id,audience,proposal_principal_id):identifier(x)
        self.bounds(dossier_ids,permissions,roles)
        if not datetime.now(UTC) < timestamp(expires_at) <= datetime.now(UTC)+timedelta(days=30): raise ValueError('finite expiry required')
        token_path=Path(token_path)
        if token_path.resolve().is_relative_to((self.root/'onboarding').resolve()) or token_path.resolve()==self.path.resolve():raise ValueError('private token collision')
        with self.boundary():
            binding=signer(self.root,self.instance_id,'solo',('READ',*roles),principal_id)
            source=ProjectProposalGrant(self.root,self.instance_id)._store()
            for dossier in dossier_ids:
                owner=source['dossiers'].get(dossier)
                if owner is None or owner['principal_id']!=proposal_principal_id or owner['audience']!=audience:raise PermissionError('exact source dossier owner required')
            self._store(); records=self._records(True)
            if len(records)>=32:raise ValueError('grant capacity exhausted')
            token=secrets.token_urlsafe(48)
            r={'grant_id':'content-'+secrets.token_hex(16),'principal_id':principal_id,'instance_id':self.instance_id,'audience':audience,
               'proposal_principal_id':proposal_principal_id,'dossier_ids':sorted(dossier_ids),'permissions':sorted(permissions),'roles':sorted(roles),
               'profile_id':PROFILE_ID,'human_binding':binding,'operator_binding':operator_binding(self.root,self.instance_id),
               'expires_at':expires_at,'state':'ACTIVE','token_digest':sha256(token.encode()).hexdigest()}
            _new_token(token_path,token)
            try:self.save_records([*records,r])
            except BaseException:token_path.unlink(missing_ok=True);raise
            return {k:v for k,v in r.items() if k not in ('token_digest','operator_binding')}

    def authorize(self, authorization, *, audience=None, dossier_id=None, permission='READ', role=None):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '):raise PermissionError('content credential required')
        token=authorization[7:]
        if not 1<=len(token)<=256 or any(ord(c)<33 or ord(c)>126 for c in token):raise PermissionError('invalid content credential')
        rows=[r for r in self._records() if secrets.compare_digest(r['token_digest'],sha256(token.encode()).hexdigest())]
        if len(rows)!=1:raise PermissionError('content credential required')
        r=rows[0]
        if r['state']!='ACTIVE' or timestamp(r['expires_at'])<=datetime.now(UTC):raise PermissionError('content credential inactive')
        if r['operator_binding']!=operator_binding(self.root,self.instance_id):raise PermissionError('operator changed')
        if (audience is not None and audience!=r['audience']) or (dossier_id is not None and dossier_id not in r['dossier_ids']) or permission not in r['permissions'] or (role is not None and role not in r['roles']):raise PermissionError('content decision scope denied')
        current=signer(self.root,self.instance_id,'solo',('READ',*r['roles']),r['principal_id'])
        if current!=r['human_binding']:raise PermissionError('human authority changed')
        return ContentPrincipal(*(tuple(r[k]) if k in ('dossier_ids','permissions','roles') else r[k] for k in ContentPrincipal.__dataclass_fields__))

    @contextmanager
    def publication(self, authorization, audience, body, *, deadline=None):
        from .proposal_content_service import ProposalContentService
        with self.boundary(deadline):
            p=self.authorize(authorization,audience=audience,dossier_id=body.get('dossier_id'))
            if body.get('instance_id')!=p.instance_id or body.get('principal_id')!=p.principal_id:raise PermissionError('content publication scope denied')
            if body.get('plan_id') is not None:
                service=ProposalContentService(self);subject,points=service.subject(p,body['dossier_id'],body['plan_id'])
                history=service.history(self._store(),body['plan_id'])
                if subject!=body.get('subject') or len(history)!=body.get('decision_revision'):raise PermissionError('decision publication snapshot changed')
                if body.get('original_decision') is not None and body['original_decision'] not in history:raise PermissionError('original decision changed')
            if deadline is not None and time.monotonic()>=deadline:raise TimeoutError('bounded content publication deadline')
            yield

    def revoke(self, grant_id):
        identifier(grant_id)
        with self.boundary():
            records=self._records();r=next((r for r in records if r['grant_id']==grant_id),None)
            if r is None:raise ValueError('unknown content grant')
            r['state']='REVOKED';self.save_records(records)
            return {'grant_id':grant_id,'state':'REVOKED'}
