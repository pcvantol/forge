"""Separate owner capability for one conversation and exact Candidate proposal IDs."""
from dataclasses import dataclass
from pathlib import Path
from datetime import UTC,datetime,timedelta
from hashlib import sha256
import argparse,json,secrets
from .advisory_candidate_contract import CONTRACT
from .advisory_grant import project_scope,conversation_path
from .approved_worklist import identifier,timestamp
from .workspace_review_grant import _locked,_private_bytes,_write_private,_new_token
from .workspace_worklist_control_grant import current_operator

@dataclass(frozen=True)
class CandidatePrincipal:
    principal_id:str
    instance_id:str
    project_id:str
    repository_id:str
    conversation_id:str
    proposal_ids:tuple
    grant_id:str
    maximum_registrations:int
    @property
    def reference(self):return self.instance_id+':'+self.principal_id
    @property
    def conversation_ids(self):return (self.conversation_id,)
    @property
    def maximum_turns(self):return 8

class AdvisoryCandidateGrant:
    def __init__(self,root,instance_id):
        self.root=Path(root);self.instance_id=identifier(instance_id);self.path=self.root/'credentials'/'advisory-candidate'/'grants.json'
    def _records(self,missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():return []
        v=json.loads(_private_bytes(self.path));names=set('principal_id instance_id project_id repository_id conversation_id proposal_ids grant_id maximum_registrations expires_at state token_digest'.split())
        if not isinstance(v,dict) or set(v)!={'contract_version','instance_id','records'} or v['contract_version']!=CONTRACT or v['instance_id']!=self.instance_id or not isinstance(v['records'],list) or len(v['records'])>64:raise ValueError('invalid Candidate grant store')
        records=v['records'];seen=set()
        for r in records:
            if not isinstance(r,dict) or set(r)!=names:raise ValueError('invalid Candidate grant')
            for k in ['principal_id','instance_id','project_id','repository_id','conversation_id','grant_id']:identifier(r[k])
            timestamp(r['expires_at'])
            if r['instance_id']!=self.instance_id or r['grant_id'] in seen or r['state'] not in {'ACTIVE','REVOKED'} or type(r['maximum_registrations']) is not int or not 1<=r['maximum_registrations']<=8:raise ValueError('invalid grant binding')
            if not isinstance(r['proposal_ids'],list) or not 1<=len(r['proposal_ids'])<=16 or sorted(set(r['proposal_ids']))!=r['proposal_ids']:raise ValueError('bounded proposal identities required')
            for v in r['proposal_ids']:identifier(v)
            h=r['token_digest']
            if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise ValueError('invalid token digest')
            seen.add(r['grant_id'])
        return records
    def _save(self,records):
        raw=json.dumps({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records},sort_keys=True).encode()
        if len(raw)>65536:raise ValueError('grant capacity exhausted')
        _write_private(self.path,raw)
    def issue(self,*,principal_id,project_id,repository_id,conversation_id,proposal_ids,expires_at,maximum_registrations,token_path):
        for v in [principal_id,project_id,repository_id,conversation_id]:identifier(v)
        if not isinstance(proposal_ids,(tuple,list)) or not 1<=len(proposal_ids)<=16 or len(set(proposal_ids))!=len(proposal_ids):raise ValueError('bounded proposals required')
        for v in proposal_ids:identifier(v)
        if type(maximum_registrations) is not int or not 1<=maximum_registrations<=8 or not datetime.now(UTC)<timestamp(expires_at)<=datetime.now(UTC)+timedelta(days=30):raise ValueError('bounded grant required')
        token_path=Path(token_path)
        if token_path.resolve()==self.path.resolve():raise ValueError('token/store collision')
        with _locked(self.path):
            current_operator(self.root,self.instance_id);scope=project_scope(self.root,self.instance_id)
            if (scope['project_id'],scope['repository_id'])!=(project_id,repository_id):raise PermissionError('foreign project')
            path=conversation_path(self.root,self.instance_id,project_id,repository_id,conversation_id)
            if path.exists() or path.is_symlink():
                if json.loads(_private_bytes(path))['principal_reference']!=self.instance_id+':'+principal_id:raise PermissionError('foreign advice owner')
            records=self._records(True)
            if len(records)>=64:raise ValueError('grant capacity exhausted')
            token=secrets.token_urlsafe(48);r={**scope,'principal_id':principal_id,'conversation_id':conversation_id,'proposal_ids':sorted(proposal_ids),'grant_id':'candidate-'+secrets.token_hex(16),'maximum_registrations':maximum_registrations,'expires_at':expires_at,'state':'ACTIVE','token_digest':sha256(token.encode()).hexdigest()}
            _new_token(token_path,token)
            try:self._save([*records,r])
            except Exception:token_path.unlink(missing_ok=True);raise
            return {k:v for k,v in r.items() if k!='token_digest'}
    def revoke(self,grant_id):
        identifier(grant_id)
        with _locked(self.path):
            current_operator(self.root,self.instance_id);records=self._records();r=next((r for r in records if r['grant_id']==grant_id),None)
            if r is None:raise ValueError('unknown grant')
            r['state']='REVOKED';self._save(records);return {'grant_id':grant_id,'state':'REVOKED'}
    def authenticate(self,authorization):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '):return None
        token=authorization[7:]
        if not token or len(token)>256 or any(ord(c)<33 or ord(c)>126 for c in token):return None
        try:
            r=next((r for r in self._records() if secrets.compare_digest(r['token_digest'],sha256(token.encode()).hexdigest())),None)
            if r is None or r['state']!='ACTIVE' or timestamp(r['expires_at'])<=datetime.now(UTC):return None
            return CandidatePrincipal(**{k:r[k] for k in CandidatePrincipal.__dataclass_fields__ if k!='proposal_ids'},proposal_ids=tuple(r['proposal_ids']))
        except (OSError,ValueError,KeyError,TypeError):return None
    def authorize(self,authorization,conversation_id=None,proposal_id=None):
        p=self.authenticate(authorization)
        if p is None:raise PermissionError('Candidate credential unavailable')
        current_operator(self.root,self.instance_id)
        if project_scope(self.root,self.instance_id)!={k:getattr(p,k) for k in ['instance_id','project_id','repository_id']}:raise PermissionError('project changed')
        if conversation_id is not None and conversation_id!=p.conversation_id or proposal_id is not None and proposal_id not in p.proposal_ids:raise PermissionError('foreign proposal scope')
        return p

def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-advisory-candidate-grant');parser.add_argument('--data-root',required=True);c=parser.add_subparsers(dest='action',required=True);i=c.add_parser('issue')
    for k in ['principal-id','project-id','repository-id','conversation-id','expires-at','token-file']:i.add_argument('--'+k,required=True)
    i.add_argument('--proposal-id',action='append',required=True);i.add_argument('--maximum-registrations',type=int,default=1);r=c.add_parser('revoke');r.add_argument('--grant-id',required=True);a=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(a.data_root);g=AdvisoryCandidateGrant(instance.data_root,instance.instance_id)
        out=g.revoke(a.grant_id) if a.action=='revoke' else g.issue(principal_id=a.principal_id,project_id=a.project_id,repository_id=a.repository_id,conversation_id=a.conversation_id,proposal_ids=a.proposal_id,expires_at=a.expires_at,maximum_registrations=a.maximum_registrations,token_path=a.token_file)
        print(json.dumps(out,sort_keys=True));return 0
    except (OSError,ValueError,RuntimeError,PermissionError):print(json.dumps({'contract_version':CONTRACT,'error':{'code':'CANDIDATE_GRANT_UNAVAILABLE'}}));return 1

if __name__=='__main__':raise SystemExit(main())
