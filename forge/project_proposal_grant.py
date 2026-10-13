"""Explicit owner-issued finite PREPARE/READ capability; no project registration."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import argparse
import json
from pathlib import Path
import secrets
from .approved_worklist import identifier, timestamp
from .project_bootstrap.schema import canonical
from .workspace_review_grant import _locked, _new_token, _private_bytes, _write_private
from .project_proposal_storage import read, write

CONTRACT = 'forge-project-proposal-http/v1'
KINDS = ('pb-render/1.0', 'pb-adoption-preview/1.0')


def operator_binding(root, instance_id):
    from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
    with InstalledDynamicMissionRuntime.open_for_governance_read(str(root)) as runtime:
        if runtime.database.runtime_identity.runtime_id != instance_id: raise PermissionError('foreign instance')
        operators = runtime.repository.operators; context = operators.context()
        if not operators.authorize(context): raise PermissionError('current owner required')
        return sha256(canonical([context.installation_id, context.generated_uid, context.binding_version])).hexdigest()


@dataclass(frozen=True)
class ProposalPrincipal:
    grant_id: str
    principal_id: str
    instance_id: str
    audience: str
    dossier_ids: tuple[str, ...]
    permissions: tuple[str, ...]
    kinds: tuple[str, ...]
    maximum_records: int
    operator_binding: str


class ProjectProposalGrant:
    def __init__(self, root, instance_id):
        self.root = Path(root); self.instance_id = identifier(instance_id)
        self.path = self.root / 'credentials' / 'project-proposal' / 'grants.json'
        self.store = self.root / 'onboarding' / 'proposals' / 'store.json'

    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink(): return []
        value = json.loads(_private_bytes(self.path))
        if set(value) != {'contract_version','instance_id','records'} or value['contract_version'] != CONTRACT or value['instance_id'] != self.instance_id or not isinstance(value['records'],list) or len(value['records']) > 32:
            raise ValueError('proposal grant store invalid')
        seen = set()
        for r in value['records']:
            if not isinstance(r,dict) or set(r) != {'grant_id','principal_id','instance_id','audience','dossier_ids','permissions','kinds','maximum_records','operator_binding','expires_at','state','token_digest'}:
                raise ValueError('proposal grant invalid')
            for k in ['grant_id','principal_id','instance_id','audience']: identifier(r[k])
            timestamp(r['expires_at'])
            if r['instance_id'] != self.instance_id or r['grant_id'] in seen or r['state'] not in ['ACTIVE','REVOKED'] or type(r['maximum_records']) is not int or not 1 <= r['maximum_records'] <= 8:
                raise ValueError('proposal grant bounds invalid')
            for key,allowed in [('dossier_ids',None),('permissions',('READ','PREPARE')),('kinds',KINDS)]:
                values = r[key]
                if not isinstance(values,list) or not 1 <= len(values) <= 8 or values != sorted(set(values)) or (allowed and any(x not in allowed for x in values)):
                    raise ValueError('proposal grant scope invalid')
                for x in values: identifier(x) if key == 'dossier_ids' else None
            if 'READ' not in r['permissions']: raise ValueError('content transfer requires READ')
            for key in ['token_digest','operator_binding']:
                if not isinstance(r[key],str) or len(r[key]) != 64 or any(x not in '0123456789abcdef' for x in r[key]): raise ValueError('proposal grant binding invalid')
            seen.add(r['grant_id'])
        return value['records']

    def initialize(self):
        operator_binding(self.root,self.instance_id)
        if self.store.exists() or self.store.is_symlink():
            self._store(); return
        if self.path.exists() or self.path.is_symlink(): raise ValueError('initialized proposal storage lost')
        self.store.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        write(self.store,{'contract_version':CONTRACT,'instance_id':self.instance_id,'dossiers':{},'records':{}},create=True)

    def _store(self):
        value = read(self.store)
        if not isinstance(value,dict) or set(value) != {'contract_version','instance_id','dossiers','records'} or value['contract_version'] != CONTRACT or value['instance_id'] != self.instance_id or not isinstance(value['dossiers'],dict) or len(value['dossiers']) > 32 or not isinstance(value['records'],dict) or len(value['records']) > 64:
            raise ValueError('proposal store invalid')
        return value

    def issue(self, *, principal_id, audience, dossier_ids, permissions, kinds, maximum_records, expires_at, token_path):
        identifier(principal_id); identifier(audience)
        if not isinstance(dossier_ids,(list,tuple)) or not 1 <= len(dossier_ids) <= 8 or len(set(dossier_ids)) != len(dossier_ids): raise ValueError('finite dossier scope required')
        for x in dossier_ids: identifier(x)
        if set(permissions) - {'READ','PREPARE'} or 'READ' not in permissions or not kinds or set(kinds) - set(KINDS) or type(maximum_records) is not int or not 1 <= maximum_records <= 8:
            raise ValueError('proposal permissions invalid')
        if not datetime.now(UTC) < timestamp(expires_at) <= datetime.now(UTC) + timedelta(days=30): raise ValueError('finite expiry required')
        token_path = Path(token_path)
        if token_path.resolve().is_relative_to(self.store.parent.resolve()) or token_path.resolve() == self.path.resolve(): raise ValueError('token storage collision')
        with _locked(self.path):
            binding = operator_binding(self.root,self.instance_id); records = self._records(True); store = self._store()
            if len(records) >= 32: raise ValueError('grant capacity exhausted')
            for key in dossier_ids:
                existing = store['dossiers'].get(key)
                proposed = {'principal_id':principal_id,'audience':audience,'maximum_records':maximum_records}
                if existing is not None and existing != proposed: raise PermissionError('dossier binding immutable')
                store['dossiers'][key] = proposed
            if len(store['dossiers']) > 32: raise ValueError('dossier capacity exhausted')
            write(self.store,store)
            token = secrets.token_urlsafe(48)
            r={'grant_id':'proposal-'+secrets.token_hex(16),'principal_id':principal_id,'instance_id':self.instance_id,'audience':audience,
               'dossier_ids':sorted(dossier_ids),'permissions':sorted(set(permissions)),'kinds':sorted(set(kinds)),'maximum_records':maximum_records,
               'operator_binding':binding,'expires_at':expires_at,'state':'ACTIVE','token_digest':sha256(token.encode()).hexdigest()}
            _new_token(token_path,token)
            try: _write_private(self.path,canonical({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':[*records,r]}))
            except Exception:
                token_path.unlink(missing_ok=True); raise
            return {k:v for k,v in r.items() if k not in {'token_digest','operator_binding'}}

    def authenticate(self, authorization):
        try: return self.authorize(authorization)
        except (OSError,ValueError,TypeError,KeyError,PermissionError): return None

    def authorize(self, authorization, *, audience=None, dossier_id=None, permission='READ', kind=None):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '): raise PermissionError('authentication required')
        token = authorization[7:]
        if not 1 <= len(token) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in token): raise PermissionError('authentication required')
        matched = [r for r in self._records() if secrets.compare_digest(r['token_digest'],sha256(token.encode()).hexdigest())]
        if len(matched) != 1: raise PermissionError('authentication required')
        r = matched[0]
        if r['state'] != 'ACTIVE' or timestamp(r['expires_at']) <= datetime.now(UTC): raise PermissionError('authentication required')
        if r['operator_binding'] != operator_binding(self.root,self.instance_id): raise PermissionError('owner binding changed')
        if (audience is not None and r['audience'] != audience) or (dossier_id is not None and dossier_id not in r['dossier_ids']) or permission not in r['permissions'] or (kind is not None and kind not in r['kinds']): raise PermissionError('proposal scope denied')
        return ProposalPrincipal(*(r[k] if k not in {'dossier_ids','permissions','kinds'} else tuple(r[k]) for k in ProposalPrincipal.__dataclass_fields__))

    @contextmanager
    def publication(self, authorization, audience, body):
        with _locked(self.path):
            p = self.authorize(authorization,audience=audience)
            if body.get('dossier_id') is not None:
                self.authorize(authorization,audience=audience,dossier_id=body['dossier_id'],kind=body.get('proposal_kind'))
                if body.get('principal_id') != p.principal_id or body.get('instance_id') != p.instance_id: raise PermissionError('publication scope denied')
            yield

    def revoke(self, grant_id):
        identifier(grant_id)
        with _locked(self.path):
            operator_binding(self.root,self.instance_id); records = self._records()
            r = next((r for r in records if r['grant_id'] == grant_id),None)
            if r is None: raise ValueError('unknown proposal grant')
            r['state'] = 'REVOKED'; _write_private(self.path,canonical({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records}))
            return {'grant_id':grant_id,'state':'REVOKED'}


def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-project-proposal-grant');parser.add_argument('--data-root',required=True)
    commands=parser.add_subparsers(dest='action',required=True);commands.add_parser('init')
    issue=commands.add_parser('issue')
    for name in ['principal-id','audience','expires-at','token-file']:issue.add_argument('--'+name,required=True)
    for name in ['dossier-id','permission','kind']:issue.add_argument('--'+name,action='append',required=True)
    issue.add_argument('--maximum-records',type=int,required=True)
    revoke=commands.add_parser('revoke');revoke.add_argument('--grant-id',required=True)
    args=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(args.data_root); grant=ProjectProposalGrant(instance.data_root,instance.instance_id)
        if args.action=='init':
            from .runtime.bootstrap import RuntimeBootstrap
            from .operator_identity import InstallationOperatorService, MacOSGeneratedUIDIdentityAdapter
            from ._version import canonical_version
            with RuntimeBootstrap(data_root=instance.data_root,forge_version=canonical_version()).open() as database:
                owner=InstallationOperatorService(database,MacOSGeneratedUIDIdentityAdapter().resolve)
                if not database._connection.execute('SELECT 1 FROM installation_operator_binding').fetchone():owner.first_bind()
                else:owner.context()
            grant.initialize();result={'contract_version':CONTRACT,'state':'PRIVATE_PROPOSAL_STORAGE_INITIALIZED'}
        elif args.action=='revoke':result=grant.revoke(args.grant_id)
        else:result=grant.issue(principal_id=args.principal_id,audience=args.audience,dossier_ids=args.dossier_id,permissions=args.permission,kinds=args.kind,maximum_records=args.maximum_records,expires_at=args.expires_at,token_path=args.token_file)
        print(json.dumps(result,sort_keys=True));return 0
    except (OSError,ValueError,TypeError,RuntimeError,PermissionError):
        print(json.dumps({'error':{'code':'PROPOSAL_GRANT_INVALID'}}));return 1

if __name__=='__main__':raise SystemExit(main())
