"""Owner-selected immutable public repository snapshots with current private ACL."""
from pathlib import Path
from hashlib import sha256
import argparse
import json
import re
from .advisory_contract import CONTRACT, digest, text, AdvisoryConflict
from .advisory_grant import project_scope
from .approved_worklist import identifier
from .completion.repository_observer import GitHubRepositoryArtifactReader
from .execution_host_configuration import read_peer_configuration
from .workspace_worklist_control_grant import current_operator
from .workspace_review_grant import _locked, _private_bytes, _write_private, _private_directory

class AdvisoryContext:
    def __init__(self,root,instance_id):
        self.root=Path(root);self.instance_id=instance_id;self.path=self.root/'advisory'/'sources'/'catalog.json'

    def _read(self,missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():return []
        try:records=json.loads(_private_bytes(self.path))
        except (ValueError,OSError):raise RuntimeError('context catalog unavailable') from None
        fields={'source_id','scope','state','repository','revision','path','content','content_digest','version'}
        if not isinstance(records,list) or len(records)>16:raise RuntimeError('context catalog invalid')
        seen=set()
        for r in records:
            if not isinstance(r,dict) or set(r)!=fields or r['state'] not in ('ACTIVE','REVOKED'):raise RuntimeError('context shape invalid')
            try:identifier(r['source_id']);text(r['content'],2048)
            except (ValueError,TypeError):raise RuntimeError('context content invalid') from None
            if r['source_id'] in seen or r['content_digest']!='sha256:'+sha256(r['content'].encode()).hexdigest() or r['version']!=digest({k:v for k,v in r.items() if k not in ('state','version')}):raise RuntimeError('context provenance invalid')
            seen.add(r['source_id'])
        return records

    def publish(self,*,source_id,revision,path):
        identifier(source_id)
        if not isinstance(revision,str) or re.fullmatch('[0-9a-f]{40}',revision) is None:raise ValueError('immutable revision required')
        if not isinstance(path,str) or re.fullmatch(r'(?:docs|knowledge)/[A-Za-z0-9_./-]+\.(?:md|txt|json)',path) is None or '..' in path.split('/') or '//' in path:raise ValueError('bounded documentary path required')
        _private_directory(self.path.parent.parent,create=True)
        with _locked(self.path):
            current_operator(self.root,self.instance_id);scope=project_scope(self.root,self.instance_id)
            binding=read_peer_configuration(self.root).configuration
            if binding is None or binding.ep_project_id!=scope['project_id'] or binding.ep_repository_id!=scope['repository_id']:raise PermissionError('source binding unavailable')
            content=GitHubRepositoryArtifactReader().read(binding.repository_identity,revision,path).decode('utf-8')
            text(content,2048);records=self._read(True)
            if any(r['source_id']==source_id for r in records) or len(records)>=16:raise ValueError('immutable source exists or capacity exhausted')
            r={'source_id':source_id,'scope':scope,'state':'ACTIVE','repository':binding.repository_identity,
               'revision':revision,'path':path,'content':content,'content_digest':'sha256:'+sha256(content.encode()).hexdigest()}
            r['version']=digest({k:v for k,v in r.items() if k!='state'});self._save([*records,r]);return self.metadata(r)

    def revoke(self,source_id):
        identifier(source_id)
        with _locked(self.path):
            current_operator(self.root,self.instance_id);records=self._read();r=next((r for r in records if r['source_id']==source_id),None)
            if r is None:raise ValueError('unknown source')
            r['state']='REVOKED';self._save(records);return self.metadata(r)

    def _save(self,records):
        raw=json.dumps(records,sort_keys=True,ensure_ascii=True).encode()
        if len(raw)>65536:raise ValueError('context retention capacity exhausted')
        _write_private(self.path,raw)

    @staticmethod
    def metadata(r):return {k:v for k,v in r.items() if k not in ('content','scope')}

    def available(self,p):
        scope={k:getattr(p,k) for k in ['instance_id','project_id','repository_id']}
        return [self.metadata(r) for r in self._read(True) if r['scope']==scope and r['state']=='ACTIVE']

    def selected(self,p,selections):
        if not isinstance(selections,list) or len(selections)>2:raise ValueError('at most two explicit sources')
        records={r['source_id']:r for r in self._read(True)};out=[];seen=set()
        for s in selections:
            if not isinstance(s,dict) or set(s)!={'source_id','version'}:raise ValueError('source reference invalid')
            identifier(s['source_id'])
            if s['source_id'] in seen:raise ValueError('duplicate source')
            seen.add(s['source_id']);r=records.get(s['source_id'])
            if r is None or r['state']!='ACTIVE' or r['scope']!={k:getattr(p,k) for k in ['instance_id','project_id','repository_id']}:
                raise PermissionError('source currently inaccessible')
            if s['version']!=r['version']:raise AdvisoryConflict('CONTEXT_STALE')
            out.append(r)
        return out

def main(argv=None):
    p=argparse.ArgumentParser(prog='forge-advisory-context');p.add_argument('--data-root',required=True)
    c=p.add_subparsers(dest='action',required=True);i=c.add_parser('publish')
    for name in ['source-id','revision','path']:i.add_argument('--'+name,required=True)
    r=c.add_parser('revoke');r.add_argument('--source-id',required=True);a=p.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(a.data_root);s=AdvisoryContext(instance.data_root,instance.instance_id)
        out=s.publish(source_id=a.source_id,revision=a.revision,path=a.path) if a.action=='publish' else s.revoke(a.source_id)
        print(json.dumps(out,sort_keys=True));return 0
    except (OSError,ValueError,RuntimeError,PermissionError):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'ADVISORY_CONTEXT_UNAVAILABLE'}}));return 1

if __name__=='__main__':raise SystemExit(main())
