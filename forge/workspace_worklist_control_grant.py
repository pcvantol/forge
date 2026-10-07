"""Private owner-provisioned capability for exact workset hold/unhold only."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import argparse
import json
from pathlib import Path
import secrets
from .approved_worklist import identifier, timestamp, projection
from .workspace_review_grant import _locked, _new_token, _private_bytes, _write_private

CONTRACT='forge-workspace-worklist-control-grant/v1'

@dataclass(frozen=True)
class ControlPrincipal:
    principal_id: str
    instance_id: str
    workset_ids: tuple[str,...]
    grant_id: str

    @property
    def reference(self):
        return self.instance_id+':'+self.grant_id+':'+self.principal_id

def current_operator(root, instance_id):
    from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
    with InstalledDynamicMissionRuntime.open_for_governance_read(str(root)) as runtime:
        if runtime.database.runtime_identity.runtime_id!=instance_id:
            raise PermissionError('foreign control instance')
        operators=runtime.repository.operators
        if not operators.authorize(operators.context()):
            raise PermissionError('current operator required')

class WorkspaceWorklistControlGrant:
    def __init__(self, root, instance_id):
        self.root,self.instance_id=Path(root),identifier(instance_id)
        self.path=self.root/'credentials'/'workspace-worklist-control'/'grants.json'

    def _records(self, missing_ok=False):
        if missing_ok and not self.path.exists() and not self.path.is_symlink():return []
        value=json.loads(_private_bytes(self.path))
        if (not isinstance(value,dict) or set(value)!={'contract_version','instance_id','records'}
                or value['contract_version']!=CONTRACT or value['instance_id']!=self.instance_id
                or not isinstance(value['records'],list) or len(value['records'])>64):
            raise ValueError('invalid control grant store')
        seen=set()
        for r in value['records']:
            if not isinstance(r,dict) or set(r)!={'grant_id','principal_id','instance_id','workset_ids','expires_at','token_sha256','state','revision'}:
                raise ValueError('invalid control grant shape')
            identifier(r['grant_id']);identifier(r['principal_id']);timestamp(r['expires_at'])
            if (r['instance_id']!=self.instance_id or r['state'] not in {'ACTIVE','REVOKED'}
                    or type(r['revision']) is not int or r['revision']<1
                    or not isinstance(r['token_sha256'],str) or len(r['token_sha256'])!=64
                    or any(c not in '0123456789abcdef' for c in r['token_sha256'])
                    or not isinstance(r['workset_ids'],list) or not 1<=len(r['workset_ids'])<=16
                    or any(not isinstance(k,str) for k in r['workset_ids'])
                    or r['workset_ids']!=sorted(set(r['workset_ids'])) or r['grant_id'] in seen):
                raise ValueError('invalid control grant')
            for k in r['workset_ids']:identifier(k)
            seen.add(r['grant_id'])
        return value['records']

    def _save(self, records):
        raw=json.dumps({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records},sort_keys=True).encode()
        if len(raw)>65536:raise ValueError('control grant capacity exhausted')
        _write_private(self.path,raw)

    def issue(self, *, principal_id, workset_ids, expires_at, token_path):
        identifier(principal_id);token_path=Path(token_path)
        if token_path.resolve()==self.path.resolve():raise ValueError('token conflicts with grant store')
        if not isinstance(workset_ids,(tuple,list)) or not 1<=len(workset_ids)<=16:
            raise ValueError('invalid control scope')
        for key in workset_ids:identifier(key)
        if len(set(workset_ids))!=len(workset_ids):raise ValueError('duplicate control scope')
        if not datetime.now(UTC)<timestamp(expires_at)<=datetime.now(UTC)+timedelta(days=90):
            raise ValueError('control expiry must be future and within90days')
        with _locked(self.path):
            current_operator(self.root,self.instance_id)
            for key in workset_ids:projection(self.root,self.instance_id,key,principal_id)
            records=self._records(True)
            if len(records)>=64:raise ValueError('control grant capacity exhausted')
            token=secrets.token_urlsafe(48)
            r={'grant_id':'control-'+secrets.token_hex(16),'principal_id':principal_id,
               'instance_id':self.instance_id,'workset_ids':sorted(workset_ids),'expires_at':expires_at,
               'token_sha256':sha256(token.encode()).hexdigest(),'state':'ACTIVE','revision':1}
            _new_token(token_path,token)
            try:self._save([*records,r])
            except Exception:
                token_path.unlink(missing_ok=True);raise
            return {k:v for k,v in r.items() if k!='token_sha256'}

    def revoke(self, grant_id):
        identifier(grant_id)
        with _locked(self.path):
            current_operator(self.root,self.instance_id)
            records=self._records();r=next((r for r in records if r['grant_id']==grant_id),None)
            if r is None:raise ValueError('unknown control grant')
            if r['state']=='ACTIVE':r['state']='REVOKED';r['revision']+=1;self._save(records)
            return {'grant_id':grant_id,'state':r['state'],'revision':r['revision']}

    def authenticate(self, authorization):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '):return None
        token=authorization[7:]
        if not token or len(token)>256 or any(ord(c)<33 or ord(c)>126 for c in token):return None
        try:records=self._records()
        except (OSError,ValueError,TypeError,KeyError):return None
        found=[r for r in records if secrets.compare_digest(r['token_sha256'],sha256(token.encode()).hexdigest())]
        if len(found)!=1:return None
        r=found[0]
        if r['state']!='ACTIVE' or timestamp(r['expires_at'])<=datetime.now(UTC):return None
        return ControlPrincipal(r['principal_id'],r['instance_id'],tuple(r['workset_ids']),r['grant_id'])

def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-workspace-worklist-control-grant')
    parser.add_argument('--data-root',required=True)
    commands=parser.add_subparsers(dest='action',required=True)
    issue=commands.add_parser('issue');issue.add_argument('--principal-id',required=True)
    issue.add_argument('--workset-id',action='append',required=True);issue.add_argument('--expires-at',required=True)
    issue.add_argument('--token-file',required=True)
    revoke=commands.add_parser('revoke');revoke.add_argument('--grant-id',required=True)
    args=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(args.data_root);grant=WorkspaceWorklistControlGrant(instance.data_root,instance.instance_id)
        result=(grant.issue(principal_id=args.principal_id,workset_ids=tuple(args.workset_id),expires_at=args.expires_at,
                           token_path=Path(args.token_file)) if args.action=='issue' else grant.revoke(args.grant_id))
        print(json.dumps(result,sort_keys=True));return 0
    except (OSError,ValueError,RuntimeError,PermissionError):
        print(json.dumps({'status':'ERROR','code':'WORKLIST_CONTROL_GRANT_INVALID'}));return 1

if __name__=='__main__':raise SystemExit(main())
