"""Finite owner-issued release authority, separate from chat/read/hold grants."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
import argparse, json, secrets
from .advisory_grant import project_scope
from .approved_worklist import identifier, timestamp
from .advisory_candidate_contract import hash_reference
from .candidate_decision_grant import signer
from .workspace_worklist_control_grant import current_operator
from .workspace_review_grant import _locked, _private_bytes, _write_private, _new_token
from .workset_release_subjects import approved_subject

CONTRACT='forge-approved-workset-release/v1'
PERMISSIONS=('READ','RELEASE','DISARM')

@dataclass(frozen=True)
class ReleasePrincipal:
    principal_id: str
    instance_id: str
    project_id: str
    repository_id: str
    grant_id: str
    profile_id: str
    permissions: tuple
    subjects: tuple
    maximum_releases: int
    maximum_activations: int
    operator_id: str
    operator_binding_version: int
    installation_id: str
    expires_at: str

    @property
    def reference(self):return self.instance_id+':'+self.principal_id


def bounds(permissions,subjects,maximum_releases,maximum_activations):
    if (not isinstance(permissions,(list,tuple)) or not permissions
            or len(set(permissions))!=len(permissions) or any(p not in PERMISSIONS for p in permissions)
            or 'READ' not in permissions):raise ValueError('invalid release permissions')
    if (not isinstance(subjects,(list,tuple)) or not 1<=len(subjects)<=16
            or type(maximum_releases) is not int or not 1<=maximum_releases<=8
            or type(maximum_activations) is not int or not 1<=maximum_activations<=16):
        raise ValueError('finite release limits required')
    seen=set()
    for s in subjects:
        if not isinstance(s,dict) or set(s)!={'candidate_id','subject_revision'}:
            raise ValueError('closed release subject required')
        identifier(s['candidate_id']);hash_reference(s['subject_revision'])
        if s['candidate_id'] in seen:raise ValueError('duplicate release subject')
        seen.add(s['candidate_id'])


class WorksetReleaseGrant:
    def __init__(self,root,instance_id):
        self.root=Path(root);self.instance_id=identifier(instance_id)
        self.path=self.root/'credentials'/'approved-workset-release'/'grants.json'

    def _records(self,missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():return []
        value=json.loads(_private_bytes(self.path))
        if (not isinstance(value,dict) or set(value)!={'contract_version','instance_id','records'}
                or value['contract_version']!=CONTRACT or value['instance_id']!=self.instance_id
                or not isinstance(value['records'],list) or len(value['records'])>64):
            raise ValueError('release grant store invalid')
        seen=set()
        for r in value['records']:
            if not isinstance(r,dict) or set(r)!=set(ReleasePrincipal.__dataclass_fields__)|{'token_digest','state'}:
                raise ValueError('release grant shape invalid')
            for k in ('principal_id','instance_id','project_id','repository_id','grant_id','operator_id','installation_id'):identifier(r[k])
            bounds(r['permissions'],r['subjects'],r['maximum_releases'],r['maximum_activations'])
            timestamp(r['expires_at'])
            if (r['instance_id']!=self.instance_id or r['profile_id']!='solo'
                    or r['principal_id']!=r['operator_id'] or type(r['operator_binding_version']) is not int
                    or r['operator_binding_version']<1 or r['state'] not in ('ACTIVE','REVOKED')
                    or len(r['token_digest'])!=64 or any(c not in '0123456789abcdef' for c in r['token_digest'])
                    or r['grant_id'] in seen):raise ValueError('release grant binding invalid')
            seen.add(r['grant_id'])
        return value['records']

    def _save(self,records):
        raw=json.dumps({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records},sort_keys=True).encode()
        if len(raw)>65536:raise ValueError('release grant capacity exhausted')
        _write_private(self.path,raw)

    def issue(self,*,principal_id,project_id,repository_id,permissions,subjects,
              maximum_releases,maximum_activations,expires_at,token_path):
        bounds(permissions,subjects,maximum_releases,maximum_activations);identifier(principal_id)
        if not datetime.now(UTC)<timestamp(expires_at)<=datetime.now(UTC)+timedelta(days=30):
            raise ValueError('release validity must be within30days')
        token_path=Path(token_path)
        if token_path.resolve()==self.path.resolve():raise ValueError('token/store collision')
        with _locked(self.path):
            current_operator(self.root,self.instance_id)
            binding=signer(self.root,self.instance_id,'solo',('BUSINESS','ARCHITECTURE'),principal_id)
            scope=project_scope(self.root,self.instance_id)
            if (scope['project_id'],scope['repository_id'])!=(project_id,repository_id):
                raise PermissionError('foreign release project')
            for s in subjects:approved_subject(self.root,scope,**s)
            records=self._records(True)
            if len(records)>=64:raise ValueError('release grant capacity exhausted')
            token=secrets.token_urlsafe(48)
            r={**scope,**binding,'principal_id':principal_id,'grant_id':'release-'+secrets.token_hex(16),
                'profile_id':'solo','permissions':sorted(permissions),'subjects':list(subjects),
                'maximum_releases':maximum_releases,'maximum_activations':maximum_activations,
                'expires_at':expires_at,'token_digest':sha256(token.encode()).hexdigest(),'state':'ACTIVE'}
            _new_token(token_path,token)
            try:self._save([*records,r])
            except Exception:
                token_path.unlink(missing_ok=True);raise
            return {k:v for k,v in r.items() if k!='token_digest'}

    def revoke(self,grant_id):
        identifier(grant_id)
        with _locked(self.path):
            current_operator(self.root,self.instance_id)
            records=self._records();r=next((r for r in records if r['grant_id']==grant_id),None)
            if r is None:raise ValueError('unknown release grant')
            r['state']='REVOKED';self._save(records)
            return {'grant_id':grant_id,'state':'REVOKED'}

    def authenticate(self,authorization):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '):return None
        token=authorization[7:]
        if not token or len(token)>256 or any(ord(c)<33 or ord(c)>126 for c in token):return None
        try:
            found=[r for r in self._records() if secrets.compare_digest(r['token_digest'],sha256(token.encode()).hexdigest())]
            if len(found)!=1 or found[0]['state']!='ACTIVE' or timestamp(found[0]['expires_at'])<=datetime.now(UTC):return None
            r=found[0]
            return ReleasePrincipal(**{k:tuple(r[k]) if k in ('permissions','subjects') else r[k]
                                      for k in ReleasePrincipal.__dataclass_fields__})
        except (OSError,ValueError,KeyError,TypeError):return None

    def authorize(self,authorization,permission='READ'):
        p=self.authenticate(authorization)
        if p is None or permission not in p.permissions:raise PermissionError('release capability unavailable')
        current_operator(self.root,self.instance_id)
        binding=signer(self.root,self.instance_id,p.profile_id,('READ',) if permission=='READ' else ('BUSINESS','ARCHITECTURE'),p.principal_id)
        if (any(binding[k]!=getattr(p,k) for k in binding)
                or project_scope(self.root,self.instance_id)!={k:getattr(p,k) for k in ('instance_id','project_id','repository_id')}):
            raise PermissionError('current release signer/project drift')
        return p

    def allowance(self,p):
        # Reissue/alias/restart never resets the retained principal/project ceiling.
        rows=[r for r in self._records() if all(r[k]==getattr(p,k) for k in
              ('principal_id','instance_id','project_id','repository_id','installation_id'))]
        return {k:min(r[k] for r in rows) for k in ('maximum_releases','maximum_activations')}


def validate_activation_authority(root,value):
    """Current original release capability gates future claims/start, not old work."""
    authority=value.get('release_capability')
    if authority is None:
        # The reserved release ID and durable receipts identify new lineage even
        # when capability metadata is removed or nulled by storage corruption.
        if (value['definition']['workset_id'].startswith('released-')
                or value.get('release_commands') or 'release_capability' in value):
            raise PermissionError('original release capability metadata unavailable')
        return  # Genuine separately qualified legacy owner worksets.
    if not isinstance(authority,dict):raise PermissionError('invalid original release capability')
    from .workset_release_journal import ReleaseJournal
    from .models.criterion_observation import canonical_digest
    # Runtime identity is supplied by canonical metadata, never the repository ID.
    from .server_runtime import existing_instance
    instance=existing_instance(root)
    grant=WorksetReleaseGrant(root,instance.instance_id)
    record=next((r for r in grant._records() if r['grant_id']==authority['grant_id']),None)
    if (record is None or record['state']!='ACTIVE' or timestamp(record['expires_at'])<=datetime.now(UTC)
            or 'RELEASE' not in record['permissions']):raise PermissionError('original release capability revoked/expired')
    p=ReleasePrincipal(**{k:tuple(record[k]) if k in ('permissions','subjects') else record[k]
                          for k in ReleasePrincipal.__dataclass_fields__})
    current_operator(root,p.instance_id)
    binding=signer(root,p.instance_id,p.profile_id,('BUSINESS','ARCHITECTURE'),p.principal_id)
    if (p.reference!=authority['principal_reference'] or any(binding[k]!=getattr(p,k) for k in binding)
            or project_scope(root,p.instance_id)!={k:getattr(p,k) for k in ('instance_id','project_id','repository_id')}
            or any(s not in p.subjects for s in authority['subjects'])):
        raise PermissionError('original release signer/project/subjects drifted')
    d=ReleaseJournal(Path(root),p.reference).read()
    intent=next((i for i in d['intents'].values() if i['package_digest']==authority['package_digest']),None)
    if (intent is None or intent['grant_id']!=p.grant_id
            or intent['package']['selection']['subjects']!=authority['subjects']
            or canonical_digest(intent['package']['definition'])!=value['definition_digest']):
        raise PermissionError('original exact release intent unavailable')


def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-workset-release-grant')
    parser.add_argument('--data-root',required=True)
    sub=parser.add_subparsers(dest='action',required=True)
    issue=sub.add_parser('issue')
    for key in ('principal-id','project-id','repository-id','expires-at','token-file','subjects-file'):
        issue.add_argument('--'+key,required=True)
    issue.add_argument('--permission',action='append',required=True)
    issue.add_argument('--maximum-releases',type=int,required=True)
    issue.add_argument('--maximum-activations',type=int,required=True)
    sub.add_parser('revoke').add_argument('--grant-id',required=True)
    args=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(args.data_root);grant=WorksetReleaseGrant(instance.data_root,instance.instance_id)
        if args.action=='issue':
            subjects=json.loads(_private_bytes(Path(args.subjects_file)))
            result=grant.issue(principal_id=args.principal_id,project_id=args.project_id,repository_id=args.repository_id,
                permissions=args.permission,subjects=subjects,maximum_releases=args.maximum_releases,
                maximum_activations=args.maximum_activations,expires_at=args.expires_at,token_path=args.token_file)
        else:result=grant.revoke(args.grant_id)
        print(json.dumps(result,sort_keys=True));return 0
    except (OSError,ValueError,RuntimeError,PermissionError,KeyError,TypeError):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'RELEASE_OWNER_SETUP_DENIED'}}));return 1
