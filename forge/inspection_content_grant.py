"""Separate finite owner-issued R55 content purpose; existing grants gain no right."""
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
import json
import secrets
import time
from .approved_worklist import identifier, timestamp
from .project_bootstrap.schema import canonical
from .project_proposal_grant import ProjectProposalGrant, operator_binding
from .workspace_review_grant import _private_bytes, _write_private, _new_token
from .candidate_decision_grant import signer
from .ep_inspection_grant import InspectionAdoptionGrant
from .ep_inspection_service import InspectionAdoptionService
from .proposal_content_grant import ProposalContentGrant
from .inspection_content_contract import CONTRACT, PROFILE_ID, ROLES, hash_value, subject


@dataclass(frozen=True)
class InspectionContentPrincipal:
    grant_id: str
    principal_id: str
    instance_id: str
    audience: str
    dossier_id: str
    plan_id: str
    subject_digest: str
    roles: tuple
    permissions: tuple
    human_binding: dict
    operator_binding: str
    source_reader: dict


class InspectionContentGrant(ProjectProposalGrant):
    contract = CONTRACT

    def __init__(self, root, instance_id):
        super().__init__(root, instance_id)
        self.path = self.root/'credentials'/'inspection-content-decisions'/'grants.json'
        self.store = self.root/'onboarding'/'inspection-content-decisions'/'store.json'
        self.witness = self.store.parent/'initialized.json'
        self.source = InspectionAdoptionGrant(root, instance_id)

    @contextmanager
    def boundary(self, deadline=None):
        with self.source.lock_until(deadline):
            with super().boundary(deadline):
                yield

    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():
            return []
        value = json.loads(_private_bytes(self.path))
        if not isinstance(value, dict) or set(value) != {'contract_version','instance_id','records'} or value['contract_version'] != CONTRACT or value['instance_id'] != self.instance_id or not isinstance(value['records'],list) or len(value['records']) > 32:
            raise ValueError('finite inspection-content grants required')
        seen = set()
        for r in value['records']:
            if not isinstance(r,dict) or set(r) != set(InspectionContentPrincipal.__dataclass_fields__) | {'token_digest','expires_at','state','profile_id','source_credential'}:
                raise ValueError('closed inspection-content grant required')
            for k in ('grant_id','principal_id','instance_id','audience','dossier_id','plan_id'):
                identifier(r[k])
            if r['instance_id'] != self.instance_id or r['profile_id'] != PROFILE_ID or r['state'] not in ('ACTIVE','REVOKED') or r['grant_id'] in seen:
                raise ValueError('content grant binding invalid')
            ProposalContentGrant.bounds([r['dossier_id']],r['permissions'],r['roles'])
            if len(r['roles']) > 1:
                raise ValueError('one separately issued role purpose per grant')
            for key in ('token_digest','operator_binding','subject_digest'):
                hash_value(r[key])
            timestamp(r['expires_at'])
            if not isinstance(r['source_credential'],str) or not 1 <= len(r['source_credential']) <= 256 or any(ord(c)<33 or ord(c)>126 for c in r['source_credential']):
                raise ValueError('private source authority required')
            if not isinstance(r['source_reader'],dict) or not isinstance(r['human_binding'],dict):
                raise ValueError('current human/source binding required')
            seen.add(r['grant_id'])
        return value['records']

    def save_records(self, rows):
        raw = canonical({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':rows})
        if len(raw) > 131072:
            raise ValueError('finite grant storage exceeded')
        _write_private(self.path,raw)

    def issue(self, *, principal_id, audience, dossier_id, plan_id, permissions, roles, source_token_file, expires_at, token_path):
        for x in (principal_id,audience,dossier_id,plan_id):
            identifier(x)
        ProposalContentGrant.bounds([dossier_id],permissions,roles)
        if len(roles) > 1 or not datetime.now(UTC) < timestamp(expires_at) <= datetime.now(UTC)+timedelta(days=30):
            raise ValueError('finite separate role grant required')
        token_path = Path(token_path)
        if token_path.resolve().is_relative_to((self.root/'onboarding').resolve()) or token_path.resolve().is_relative_to((self.root/'credentials').resolve()) or token_path.resolve() == Path(source_token_file).resolve():
            raise ValueError('private output token collision')
        credential = _private_bytes(Path(source_token_file)).decode('ascii').strip()
        source_p = self.source.authorize('Bearer '+credential,audience=audience,dossier_id=dossier_id)
        InspectionAdoptionService(self.source)._peer(source_p)  # No authority lock across EP wait.
        with self.boundary():
            if self.source.authorize('Bearer '+credential,audience=audience,dossier_id=dossier_id) != source_p:
                raise PermissionError('late source grant changed')
            original = self.original(source_p,dossier_id,plan_id)
            bound, _, _ = subject(original)
            human = signer(self.root,self.instance_id,'solo',('READ',*roles),principal_id)
            self._store()
            rows = self._records(True)
            if len(rows) >= 32:
                raise ValueError('grant capacity exhausted')
            token = secrets.token_urlsafe(48)
            row = {'grant_id':'inspection-content-'+secrets.token_hex(16),'principal_id':principal_id,
                   'instance_id':self.instance_id,'audience':audience,'dossier_id':dossier_id,'plan_id':plan_id,
                   'subject_digest':bound['subject_digest'],'permissions':sorted(permissions),'roles':sorted(roles),
                   'human_binding':human,'operator_binding':operator_binding(self.root,self.instance_id),
                   'source_reader':json.loads(canonical(asdict(source_p))),'source_credential':credential,
                   'profile_id':PROFILE_ID,'expires_at':expires_at,'state':'ACTIVE','token_digest':sha256(token.encode()).hexdigest()}
            _new_token(token_path,token)
            try:
                self.save_records([*rows,row])
            except BaseException:
                token_path.unlink(missing_ok=True)
                raise
            return {k:v for k,v in row.items() if k not in ('source_credential','token_digest','operator_binding')}

    def original(self, source_p, dossier, plan):
        service = InspectionAdoptionService(self.source)
        record = service._record(self.source._store(),plan)
        if record is None:
            raise FileNotFoundError('original R55 proposal unavailable')
        service._authorize_record(source_p,dossier,record)
        return record

    def current(self, r):
        if r['state'] != 'ACTIVE' or timestamp(r['expires_at']) <= datetime.now(UTC) or r['operator_binding'] != operator_binding(self.root,self.instance_id):
            raise PermissionError('current content authority lost')
        if signer(self.root,self.instance_id,'solo',('READ',*r['roles']),r['principal_id']) != r['human_binding']:
            raise PermissionError('current canonical human role changed')
        source_p = self.source.authorize('Bearer '+r['source_credential'],audience=r['audience'],dossier_id=r['dossier_id'])
        if json.loads(canonical(asdict(source_p))) != r['source_reader']:
            raise PermissionError('source grant epoch changed')
        return source_p

    def authorize(self, authorization, *, audience=None, dossier_id=None, permission='READ', role=None, plan_id=None):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '):
            raise PermissionError('separate inspection-content credential required')
        token = authorization[7:]
        if not 1 <= len(token) <= 256 or any(ord(c)<33 or ord(c)>126 for c in token):
            raise PermissionError('finite private credential required')
        rows = [r for r in self._records() if secrets.compare_digest(r['token_digest'],sha256(token.encode()).hexdigest())]
        if len(rows) != 1:
            raise PermissionError('separate content purpose required')
        r = rows[0]
        self.current(r)
        if (audience is not None and audience != r['audience']) or (dossier_id is not None and dossier_id != r['dossier_id']) or (plan_id is not None and plan_id != r['plan_id']) or permission not in r['permissions'] or (role is not None and role not in r['roles']):
            raise PermissionError('exact content role/subject scope denied')
        return InspectionContentPrincipal(*(tuple(r[k]) if k in ('roles','permissions') else r[k] for k in InspectionContentPrincipal.__dataclass_fields__))

    def source_principal(self, p):
        row = next(r for r in self._records() if r['grant_id'] == p.grant_id)
        return self.current(row)

    def applicable(self, record):
        row = next((r for r in self._records() if r['grant_id'] == record['grant_id']),None)
        if row is None:
            return False
        try:
            self.current(row)
        except PermissionError:
            return False
        r = record['request']
        return (row['principal_id'] == record['principal_id'] and row['human_binding'] == record['human_binding'] and
                row['subject_digest'] == r['subject_digest'] and row['plan_id'] == r['plan_id'] and
                row['dossier_id'] == r['dossier_id'] and row['audience'] == record['audience'] and
                'DECIDE' in row['permissions'] and r['role'] in row['roles'])

    def revoke(self, grant_id):
        identifier(grant_id)
        with self.boundary():
            rows = self._records()
            row = next((r for r in rows if r['grant_id'] == grant_id),None)
            if row is None:
                raise ValueError('unknown content grant')
            row['state'] = 'REVOKED'
            self.save_records(rows)
            return {'grant_id':grant_id,'state':'REVOKED'}

    @contextmanager
    def publication(self, authorization, audience, body, *, deadline=None):
        from .inspection_content_service import InspectionContentService
        service = InspectionContentService(self)
        p, bound, points, blockers = service.checked_source(authorization,audience,deadline=deadline)
        with self.boundary(deadline):
            if self.authorize(authorization,audience=audience) != p or service.local_subject(p,self.source_principal(p)) != (bound,points,blockers):
                raise PermissionError('late publication authority changed')
            if 'plan_id' in body:
                expected = service.view(p,bound,points,blockers,self._store(),body.get('intent_id'))
                if expected != body:
                    raise PermissionError('content publication snapshot changed')
            elif body != service.capability(p):
                raise PermissionError('content capability changed')
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError('bounded content publication deadline')
            yield
