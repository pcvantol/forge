"""Independent, bounded workset read capability; no status/review escalation."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import argparse
import json
from pathlib import Path
import secrets
from .approved_worklist import identifier, timestamp
from .workspace_review_grant import _locked, _new_token, _private_bytes, _write_private

CONTRACT='forge-workspace-worklist-grant/v1'

@dataclass(frozen=True)
class WorklistPrincipal:
    principal_id: str
    instance_id: str
    workset_ids: tuple[str,...]
    expires_at: str

class WorkspaceWorklistGrant:
    def __init__(self, root: Path, instance_id: str):
        self.root,self.instance_id=root,instance_id
        self.path=root/'credentials'/'workspace-worklist'/'grants.json'

    def _records(self, missing_ok=False):
        if missing_ok and not self.path.exists() and not self.path.is_symlink():return []
        value=json.loads(_private_bytes(self.path))
        if (set(value)!={'contract_version','instance_id','records'} or value['contract_version']!=CONTRACT
                or value['instance_id']!=self.instance_id or not isinstance(value['records'],list)
                or len(value['records'])>64):raise ValueError('invalid worklist grant store')
        seen=set()
        for r in value['records']:
            if set(r)!={'grant_id','principal_id','instance_id','workset_ids','expires_at','token_sha256','state','revision'}:
                raise ValueError('invalid worklist grant shape')
            identifier(r['grant_id']);identifier(r['principal_id']);timestamp(r['expires_at'])
            if (r['instance_id']!=self.instance_id or r['state'] not in {'ACTIVE','REVOKED'}
                    or type(r['revision']) is not int or r['revision']<1
                    or not isinstance(r['token_sha256'],str) or len(r['token_sha256'])!=64
                    or any(c not in '0123456789abcdef' for c in r['token_sha256'])
                    or not isinstance(r['workset_ids'],list) or not 1<=len(r['workset_ids'])<=16
                    or r['workset_ids']!=sorted(set(r['workset_ids'])) or r['grant_id'] in seen):
                raise ValueError('invalid worklist grant')
            for item in r['workset_ids']:identifier(item)
            seen.add(r['grant_id'])
        return value['records']

    def _save(self,records):
        raw=json.dumps({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records},sort_keys=True).encode()
        if len(raw)>65536:raise ValueError('worklist grant store capacity exhausted')
        _write_private(self.path,raw)

    def issue(self,*,principal_id:str,workset_ids:tuple[str,...],expires_at:str,token_path:Path):
        identifier(principal_id)
        if token_path.resolve()==self.path.resolve():raise ValueError('token output conflicts with grant store')
        if not 1<=len(workset_ids)<=16 or len(set(workset_ids))!=len(workset_ids):
            raise ValueError('invalid workset grant scope')
        for key in workset_ids:identifier(key)
        if not datetime.now(UTC)<timestamp(expires_at)<=datetime.now(UTC)+timedelta(days=90):raise ValueError('grant expiry must be future and within90days')
        with _locked(self.path):
            records=self._records(True)
            if len(records)>=64:raise ValueError('worklist grant capacity exhausted')
            token=secrets.token_urlsafe(48)
            r={'grant_id':'worklist-'+secrets.token_hex(16),'principal_id':principal_id,
               'instance_id':self.instance_id,'workset_ids':sorted(workset_ids),'expires_at':expires_at,
               'token_sha256':sha256(token.encode()).hexdigest(),'state':'ACTIVE','revision':1}
            _new_token(token_path,token)
            try:self._save([*records,r])
            except Exception:
                token_path.unlink(missing_ok=True);raise
            return {k:v for k,v in r.items() if k!='token_sha256'}

    def revoke(self,grant_id:str):
        identifier(grant_id)
        with _locked(self.path):
            records=self._records();r=next((r for r in records if r['grant_id']==grant_id),None)
            if r is None:raise ValueError('unknown worklist grant')
            if r['state']=='ACTIVE':r['state']='REVOKED';r['revision']+=1;self._save(records)
            return {'grant_id':grant_id,'state':r['state'],'revision':r['revision']}

    def authenticate(self,authorization):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '):return None
        token=authorization[7:]
        if not token or len(token)>256 or any(ord(c)<33 or ord(c)>126 for c in token):return None
        try:records=self._records()
        except (OSError,ValueError,TypeError):return None
        found=[r for r in records if secrets.compare_digest(r['token_sha256'],sha256(token.encode()).hexdigest())]
        if len(found)!=1:return None
        r=found[0]
        if r['state']!='ACTIVE' or timestamp(r['expires_at'])<=datetime.now(UTC):return None
        return WorklistPrincipal(r['principal_id'],r['instance_id'],tuple(r['workset_ids']),r['expires_at'])

def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-workspace-worklist-grant')
    parser.add_argument('--data-root',required=True)
    commands=parser.add_subparsers(dest='action',required=True)
    issue=commands.add_parser('issue');issue.add_argument('--principal-id',required=True)
    issue.add_argument('--workset-id',action='append',required=True);issue.add_argument('--expires-at',required=True)
    issue.add_argument('--token-file',required=True)
    revoke=commands.add_parser('revoke');revoke.add_argument('--grant-id',required=True)
    args=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(args.data_root)
        grant=WorkspaceWorklistGrant(Path(instance.data_root),instance.instance_id)
        result=(grant.issue(principal_id=args.principal_id,workset_ids=tuple(args.workset_id),expires_at=args.expires_at,
                            token_path=Path(args.token_file)) if args.action=='issue' else grant.revoke(args.grant_id))
        print(json.dumps(result,sort_keys=True));return 0
    except (OSError,ValueError,RuntimeError):
        print(json.dumps({'status':'ERROR','code':'WORKLIST_GRANT_INVALID'}));return 1

if __name__=='__main__':raise SystemExit(main())
