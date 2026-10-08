"""Private owner-issued instance/project/repository/conversation capabilities."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import argparse
import json
import secrets
from hashlib import sha256
from .advisory_contract import CONTRACT, digest
from .approved_worklist import identifier, timestamp
from .operations_read_api import InstalledOperationsReadService
from .workspace_review_grant import _locked, _private_bytes, _write_private, _new_token
from .workspace_worklist_control_grant import current_operator


def project_scope(root, instance_id):
    value=InstalledOperationsReadService(root).project_index()
    if value['instance_id'] != instance_id or value['availability'] != 'AVAILABLE' or len(value['projects']) != 1:
        raise PermissionError('existing configured project required')
    p=value['projects'][0]
    scope={'instance_id':instance_id,'project_id':p['project_id'],'repository_id':p['repository_id']}
    for v in scope.values():identifier(v)
    return scope

def conversation_path(root,instance_id,project_id,repository_id,conversation_id):
    return Path(root)/'advisory'/'transcripts'/(digest([instance_id,project_id,repository_id,conversation_id])[7:]+'.json')

@dataclass(frozen=True)
class AdvisoryPrincipal:
    principal_id: str
    instance_id: str
    project_id: str
    repository_id: str
    conversation_ids: tuple[str,...]
    grant_id: str
    maximum_turns: int

    @property
    def reference(self):
        return self.instance_id+':'+self.principal_id

class AdvisoryGrant:
    def __init__(self, root, instance_id):
        self.root=Path(root);self.instance_id=identifier(instance_id)
        self.path=self.root/'credentials'/'advisory-conversation'/'grants.json'

    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():return []
        v=json.loads(_private_bytes(self.path))
        if not isinstance(v,dict) or set(v)!={'contract_version','instance_id','records'} or v['contract_version']!=CONTRACT or v['instance_id']!=self.instance_id or not isinstance(v['records'],list) or len(v['records'])>64:
            raise ValueError('invalid advisory grants')
        seen=set()
        fields={'principal_id','instance_id','project_id','repository_id','conversation_ids','grant_id','maximum_turns','expires_at','state','token_digest'}
        for r in v['records']:
            if not isinstance(r,dict) or set(r)!=fields:raise ValueError('invalid grant shape')
            for k in ['principal_id','instance_id','project_id','repository_id','grant_id']:identifier(r[k])
            timestamp(r['expires_at'])
            if (r['instance_id']!=self.instance_id or type(r['maximum_turns']) is not int or not 1<=r['maximum_turns']<=8
                    or r['state'] not in ('ACTIVE','REVOKED') or r['grant_id'] in seen
                    or not isinstance(r['token_digest'],str) or len(r['token_digest'])!=64 or any(c not in '0123456789abcdef' for c in r['token_digest'])
                    or not isinstance(r['conversation_ids'],list) or not 1<=len(r['conversation_ids'])<=16):
                raise ValueError('invalid grant scope')
            for key in r['conversation_ids']:
                identifier(key)
                if key=='capability':raise ValueError('reserved conversation')
            if r['conversation_ids']!=sorted(set(r['conversation_ids'])):raise ValueError('duplicate scope')
            seen.add(r['grant_id'])
        return v['records']

    def _save(self, records):
        raw=json.dumps({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records},sort_keys=True).encode()
        if len(raw)>65536:raise ValueError('grant capacity exhausted')
        _write_private(self.path,raw)

    def issue(self, *, principal_id, project_id, repository_id, conversation_ids, expires_at, maximum_turns, token_path):
        for v in [principal_id,project_id,repository_id]:identifier(v)
        if not isinstance(conversation_ids,(list,tuple)) or not 1<=len(conversation_ids)<=16:raise ValueError('bounded conversations required')
        for v in conversation_ids:
            identifier(v)
            if v=='capability':raise ValueError('reserved conversation identity')
        if len(set(conversation_ids))!=len(conversation_ids) or type(maximum_turns) is not int or not 1<=maximum_turns<=8:raise ValueError('invalid bounds')
        if not datetime.now(UTC)<timestamp(expires_at)<=datetime.now(UTC)+timedelta(days=30):raise ValueError('bounded expiry required')
        token_path=Path(token_path)
        if token_path.resolve()==self.path.resolve():raise ValueError('token/store collision')
        with _locked(self.path):
            current_operator(self.root,self.instance_id)
            p=project_scope(self.root,self.instance_id)
            if p['project_id']!=project_id or p['repository_id']!=repository_id:raise PermissionError('foreign project')
            for conversation_id in conversation_ids:
                path=conversation_path(self.root,self.instance_id,project_id,repository_id,conversation_id)
                if path.exists() or path.is_symlink():
                    existing=json.loads(_private_bytes(path))
                    if existing.get('principal_reference')!=self.instance_id+':'+principal_id:raise PermissionError('conversation belongs to another principal')
            records=self._records(True)
            if len(records)>=64:raise ValueError('grant capacity exhausted')
            token=secrets.token_urlsafe(48)
            r={**p,'principal_id':principal_id,'conversation_ids':sorted(conversation_ids),'grant_id':'advice-'+secrets.token_hex(16),
               'maximum_turns':maximum_turns,'expires_at':expires_at,'state':'ACTIVE','token_digest':sha256(token.encode()).hexdigest()}
            _new_token(token_path,token)
            try:self._save([*records,r])
            except Exception:token_path.unlink(missing_ok=True);raise
            return {k:v for k,v in r.items() if k!='token_digest'}

    def revoke(self, grant_id):
        identifier(grant_id)
        with _locked(self.path):
            current_operator(self.root,self.instance_id);records=self._records()
            r=next((r for r in records if r['grant_id']==grant_id),None)
            if r is None:raise ValueError('unknown grant')
            r['state']='REVOKED';self._save(records)
            return {'grant_id':grant_id,'state':'REVOKED'}

    def authenticate(self, authorization):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '):return None
        token=authorization[7:]
        if not token or len(token)>256 or any(ord(c)<33 or ord(c)>126 for c in token):return None
        try:
            records=self._records();found=[r for r in records if secrets.compare_digest(r['token_digest'],sha256(token.encode()).hexdigest())]
            if len(found)!=1:return None
            r=found[0]
            if r['state']!='ACTIVE' or timestamp(r['expires_at'])<=datetime.now(UTC):return None
            return AdvisoryPrincipal(**{k:r[k] for k in AdvisoryPrincipal.__dataclass_fields__ if k!='conversation_ids'},conversation_ids=tuple(r['conversation_ids']))
        except (OSError,ValueError,TypeError,KeyError):return None

    def authorize(self, authorization, conversation_id=None):
        p=self.authenticate(authorization)
        if p is None:raise PermissionError('advisory credential unavailable')
        current_operator(self.root,self.instance_id)
        if project_scope(self.root,self.instance_id)!={'instance_id':p.instance_id,'project_id':p.project_id,'repository_id':p.repository_id}:
            raise PermissionError('project access changed')
        if conversation_id is not None and conversation_id not in p.conversation_ids:raise PermissionError('foreign conversation')
        return p

def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-advisory-grant');parser.add_argument('--data-root',required=True)
    commands=parser.add_subparsers(dest='action',required=True);i=commands.add_parser('issue')
    for name in ['principal-id','project-id','repository-id','expires-at','token-file']:i.add_argument('--'+name,required=True)
    i.add_argument('--conversation-id',action='append',required=True);i.add_argument('--maximum-turns',type=int,default=8)
    r=commands.add_parser('revoke');r.add_argument('--grant-id',required=True);a=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(a.data_root);g=AdvisoryGrant(instance.data_root,instance.instance_id)
        v=g.revoke(a.grant_id) if a.action=='revoke' else g.issue(principal_id=a.principal_id,project_id=a.project_id,repository_id=a.repository_id,conversation_ids=a.conversation_id,expires_at=a.expires_at,maximum_turns=a.maximum_turns,token_path=Path(a.token_file))
        print(json.dumps(v,sort_keys=True));return 0
    except (OSError,ValueError,RuntimeError,PermissionError):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'ADVISORY_GRANT_UNAVAILABLE'}}));return 1

if __name__=='__main__':raise SystemExit(main())
