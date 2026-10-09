"""Canonical private admitted turns; only explicit submit crosses provider boundary."""
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
try:
    import fcntl
except ImportError:
    fcntl=None
import json
import os
import sqlite3
from urllib.parse import urlsplit, parse_qs
from .advisory_contract import CONTRACT, MODES, digest, request, result, AdvisoryConflict, AdvisoryUnsupported
from .advisory_grant import project_scope,conversation_path
from .advisory_provider import AdvisoryProvider, AdvisoryNotStarted, AdvisoryProviderUnavailable
from .advisory_context import AdvisoryContext
from .approved_worklist import identifier
from .operations_read_api import InstalledOperationsReadService
from .workspace_review_grant import _private_bytes, _private_directory, _write_private, _locked
from .worklist_control import control_runtime


@contextmanager
def conversation_lock(path):
    if fcntl is None:raise RuntimeError('advisory mutation locking unavailable')
    _private_directory(path.parent.parent,create=True)
    _private_directory(path.parent,create=True)
    fd=os.open(path.with_suffix('.lock'),os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as e:raise AdvisoryConflict('CONVERSATION_BUSY') from e
        yield
    finally:os.close(fd)

class AdvisoryService:
    contract = CONTRACT
    provider_type = AdvisoryProvider

    @staticmethod
    def parse_request(document):
        return request(document)

    @staticmethod
    def validate_result(document, admitted, references):
        return result(document, admitted, references)

    def __init__(self, root, grant, provider_id):
        self.root=Path(root);self.grant=grant;self.provider_id=provider_id

    def turn_context(self, principal, request):
        return self.context(principal, request['selected_sources'])

    def context(self, p, selections=None):
        scope=project_scope(self.root,p.instance_id)
        with InstalledOperationsReadService(self.root)._runtime_snapshot() as (c,_):
            row=c.execute('SELECT dataset_generation,state FROM operational_reset_state WHERE singleton=1').fetchone()
            if row is None or row[1]!='IDLE':raise PermissionError('runtime generation unavailable')
            generation=row[0]
        selected=AdvisoryContext(self.root,p.instance_id).selected(p,selections or [])
        value={**scope,'dataset_generation':generation,'included_sources':['PROJECT_BINDING',*[r['source_id'] for r in selected]],'selected_sources':[{'source_id':r['source_id'],'version':r['version']} for r in selected],
               'missing_sources':['LIVE_REPOSITORY_CONTENT','CANONICAL_VISION','CANONICAL_PORTFOLIO','CANONICAL_ROADMAP'],
               'freshness':'CURRENT_CONFIGURED_BINDING','evidence_references':['project-binding:'+digest(scope)],
               'limitations':['Explicit owner-published public immutable repository snapshots only; no harvesting or inferred facts.']}
        value['evidence_references'] += ['advisory-source:'+r['source_id']+':'+r['version'] for r in selected]
        return value,digest(value)

    def _path(self,p,conversation_id):
        return conversation_path(self.root,p.instance_id,p.project_id,p.repository_id,conversation_id)

    def _read(self,path,p,conversation_id,context,create=False):
        if create and not path.exists() and not path.is_symlink():
            return {'contract_version':self.contract,'principal_reference':p.reference,'conversation_id':conversation_id,
                    'scope':{k:getattr(p,k) for k in ['instance_id','project_id','repository_id']},
                    'dataset_generation':context['dataset_generation'],'maximum_turns':p.maximum_turns,'revision':0,'turns':[]}
        try:value=json.loads(_private_bytes(path))
        except (OSError,ValueError):raise RuntimeError('private transcript unavailable') from None
        if isinstance(value,dict) and value.get('principal_reference')!=p.reference:raise PermissionError('foreign conversation owner')
        fields={'contract_version','principal_reference','conversation_id','scope','dataset_generation','maximum_turns','revision','turns'}
        if (not isinstance(value,dict) or set(value)!=fields or value['contract_version']!=self.contract
                or value['principal_reference']!=p.reference or value['conversation_id']!=conversation_id
                or value['scope']!={k:getattr(p,k) for k in ['instance_id','project_id','repository_id']}
                or type(value['dataset_generation']) is not int or value['dataset_generation']!=context['dataset_generation']
                or type(value['maximum_turns']) is not int or not 1<=value['maximum_turns']<=8
                or type(value['revision']) is not int or value['revision']<1 or not isinstance(value['turns'],list)
                or not 1<=len(value['turns'])<=value['maximum_turns']):
            raise RuntimeError('private session binding unavailable')
        seen=set()
        for t in value['turns']:
            if not isinstance(t,dict) or set(t)!={'request','request_digest','session_id','invocation_id','context','provider','status','lifecycle','execution','outcome','admitted_at','grant_id','consumption'}:
                raise RuntimeError('private turn shape unavailable')
            try:r,h=self.parse_request(t['request'])
            except (ValueError,TypeError):raise RuntimeError('stored request unavailable') from None
            if (h!=t['request_digest'] or r['conversation_id']!=conversation_id or r['turn_id'] in seen
                    or any(r[k]!=value['scope'][k] for k in value['scope']) or t['consumption']!=1 or type(t['consumption']) is not int
                    or t['status'] not in ('REASONING','REVIEW','COMPLETE','FAILED','CANCEL_REQUESTED')
                    or t['execution'] not in ('MAY_HAVE_HAPPENED','NOT_STARTED','CONFIRMED')
                    or not isinstance(t['lifecycle'],list) or t['lifecycle'][:3]!=['CREATED','PREPARED','REASONING']):
                raise RuntimeError('stored session provenance unavailable')
            try:identifier(t['session_id']);identifier(t['invocation_id']);identifier(t['grant_id'])
            except (TypeError,ValueError):raise RuntimeError('stored identities invalid') from None
            expected_lifecycle=['CREATED','PREPARED','REASONING']+(['REVIEW','COMPLETE'] if t['status']=='COMPLETE' else ['REVIEW'] if t['status']=='REVIEW' else [])
            if t['lifecycle']!=expected_lifecycle:raise RuntimeError('stored lifecycle invalid')
            provider=t['provider']
            provider_fields={'provider_id','requested_model','requested_profile','requested_effort','policy_digest','generation_digest','configuration_revision','input_token_bound','context_token_bound','output_token_bound'}
            if not isinstance(provider,dict) or set(provider)!=provider_fields or any(type(provider[k]) is not int or provider[k]<1 for k in ['configuration_revision','input_token_bound','context_token_bound','output_token_bound']):raise RuntimeError('stored provider bounds invalid')
            self.context(p,r['selected_sources'])
            if digest(t['context'])!=r['context_revision']:raise RuntimeError('stored context digest invalid')
            if t['outcome'] is not None:
                o=t['outcome']
                if not isinstance(o,dict) or set(o)!={'execution','diagnostic','usage','usage_status','observed_model','observed_effort','output','result_digest','error_code'} or o['execution']!=t['execution']:
                    raise RuntimeError('stored result unavailable')
                if o['output'] is not None:
                    try:output=self.validate_result(o['output'],t,t['context']['evidence_references'])
                    except (ValueError,TypeError,KeyError):raise RuntimeError('stored advice invalid') from None
                    if digest(output)!=o['result_digest'] or t['execution']!='CONFIRMED' or o['error_code'] is not None:raise RuntimeError('result provenance unavailable')
                    usage=o['usage']
                    if not isinstance(usage,dict) or set(usage)!={'input_tokens','output_tokens'} or any(type(v) is not int or v<0 for v in usage.values()) or o['usage_status']!='OBSERVED':raise RuntimeError('accepted usage unavailable')
                    if usage['input_tokens']>provider['input_token_bound'] or usage['output_tokens']>provider['output_token_bound'] or sum(usage.values())>provider['context_token_bound']:raise RuntimeError('accepted usage outside bounds')
                elif t['status'] in ('COMPLETE','REVIEW'):raise RuntimeError('complete advice missing')
            elif t['status'] in ('COMPLETE','REVIEW'):raise RuntimeError('durable result missing')
            seen.add(r['turn_id'])
        return value

    def _save(self,path,value):
        value['revision']+=1
        raw=json.dumps(value,sort_keys=True,ensure_ascii=True).encode()
        if len(raw)>65536:raise AdvisoryConflict('TRANSCRIPT_CAPACITY_EXHAUSTED')
        _write_private(path,raw)

    @staticmethod
    def _history(value):
        return [{'turn_id':t['request']['turn_id'],'advisor_kind':t['request']['advisor_kind'],
                 'objective':t['request']['objective'],'session_id':t['session_id'],
                 'request_digest':t['request_digest'],'output':t['outcome']['output']}
                for t in value['turns'] if t['status']=='COMPLETE']

    def submit(self, authorization, document):
        r,h=self.parse_request(document);p=self.grant.authorize(authorization,r['conversation_id'])
        if any(r[k]!=getattr(p,k) for k in ['instance_id','project_id','repository_id']):raise PermissionError('foreign scope')
        path=self._path(p,r['conversation_id'])
        with conversation_lock(path):
            # Grant lease linearizes revoke and transport; conversation lock rejects overlap.
            with _locked(self.grant.path),_locked(AdvisoryContext(self.root,p.instance_id).path):
                p=self.grant.authorize(authorization,r['conversation_id']);context,context_revision=self.turn_context(p,r)
                value=self._read(path,p,r['conversation_id'],context,True)
                existing=next((t for t in value['turns'] if t['request']['turn_id']==r['turn_id']),None)
                if existing is not None:
                    if existing['request_digest']!=h:raise AdvisoryConflict('TURN_PAYLOAD_CONFLICT')
                    if existing['outcome'] is not None and existing['outcome']['execution']=='CONFIRMED':
                        with control_runtime(self.root) as runtime:self._release_confirmed_permit(runtime,existing)
                    if existing['status']=='REVIEW' and existing['outcome']['output'] is not None:
                        existing['status']='COMPLETE';existing['lifecycle'].append('COMPLETE');self._save(path,value)
                    return {'contract_version':self.contract,'recorded':False,'original_turn':existing,'current_revision':value['revision']}
                if r['expected_revision']!=value['revision'] or r['context_revision']!=context_revision:raise AdvisoryConflict('CONVERSATION_OR_CONTEXT_STALE')
                if any(t['status'] in ('REASONING','REVIEW','CANCEL_REQUESTED') or t['execution']=='MAY_HAVE_HAPPENED' for t in value['turns']):raise AdvisoryConflict('INVOCATION_UNRESOLVED')
                if len(value['turns'])>=min(value['maximum_turns'],p.maximum_turns):raise AdvisoryConflict('TURN_BUDGET_EXHAUSTED')
                if len(json.dumps(value,ensure_ascii=True).encode())+16000>65536:raise AdvisoryConflict('TRANSCRIPT_CAPACITY_EXHAUSTED')
                t={'request':r,'request_digest':h,'session_id':'advice-session-'+uuid4().hex,'invocation_id':'advice-invocation-'+uuid4().hex,
                   'context':context,'provider':None,'status':'REASONING','lifecycle':['CREATED','PREPARED','REASONING'],
                   'execution':'MAY_HAVE_HAPPENED','outcome':None,'admitted_at':datetime.now(UTC).isoformat(),'grant_id':p.grant_id,'consumption':1}
                with control_runtime(self.root) as runtime:
                    used,unresolved=self._root_budget(p,new_conversation=value['revision']==0)
                    if unresolved:raise AdvisoryConflict('INVOCATION_UNRESOLVED')
                    if used>=min(8,p.maximum_turns):raise AdvisoryConflict('TURN_BUDGET_EXHAUSTED')
                    provider=self.provider_type(runtime,self.provider_id);history=self._history(value)
                    policy,_,generation_digest=provider.prepare(t,history)
                    from .planner.codex_cli_session import _policy_digest
                    t['provider']={'provider_id':policy.provider_id,'requested_model':policy.model,'requested_profile':policy.profile,
                                   'requested_effort':'NOT_CONFIGURED','policy_digest':_policy_digest(policy),'generation_digest':generation_digest,
                                   'configuration_revision':policy.version,'input_token_bound':policy.input_token_bound,
                                   'context_token_bound':policy.context_token_bound,'output_token_bound':policy.output_token_bound}
                    value['turns'].append(t);self._save(path,value)
                    def authorize():
                        actual=self.grant.authorize(authorization,r['conversation_id']);_,current=self.turn_context(actual,r)
                        if current!=context_revision:raise PermissionError('context changed before provider')
                    def sink(outcome):
                        t['outcome']=outcome;t['execution']=outcome['execution']
                        t['status']='REVIEW' if outcome['output'] is not None else ('REASONING' if outcome['execution']=='MAY_HAVE_HAPPENED' else 'FAILED')
                        if t['status']=='REVIEW':t['lifecycle'].append('REVIEW')
                        self._save(path,value)
                        if t['status']=='REVIEW':authorize()
                    try:provider.invoke(t,history,authorize,sink)
                    except AdvisoryNotStarted:
                        t['execution']='NOT_STARTED';t['status']='FAILED';self._save(path,value)
                        raise
                    if t['status']=='REVIEW':t['status']='COMPLETE';t['lifecycle'].append('COMPLETE');self._save(path,value)
                self.grant.authorize(authorization,r['conversation_id'])
                return {'contract_version':self.contract,'recorded':True,'original_turn':t,'current_revision':value['revision']}

    def read(self, authorization, conversation_id, turn_id=None, cursor=0, limit=4):
        p=self.grant.authorize(authorization,conversation_id);context,_=self.context(p);path=self._path(p,conversation_id)
        if not path.exists() and not path.is_symlink():raise FileNotFoundError('unknown conversation')
        value=self._read(path,p,conversation_id,context)
        self.grant.authorize(authorization,conversation_id)
        if turn_id is not None:
            t=next((t for t in value['turns'] if t['request']['turn_id']==turn_id),None)
            if t is None:raise FileNotFoundError('unknown turn')
            return {'contract_version':self.contract,'original_turn':t,'current_revision':value['revision'],'read_only':True}
        if type(cursor) is not int or type(limit) is not int or cursor<0 or not 1<=limit<=4 or cursor>len(value['turns']):raise ValueError('invalid bounded cursor')
        selected=value['turns'][cursor:cursor+limit]
        return {'contract_version':self.contract,'conversation_id':conversation_id,'scope':value['scope'],'revision':value['revision'],
                'turns':selected,'next_cursor':None if cursor+len(selected)>=len(value['turns']) else cursor+len(selected),
                'consumed_turns':len(value['turns']),'maximum_turns':min(value['maximum_turns'],p.maximum_turns),
                'retention':'PRIVATE_RETAINED_NO_AUTOMATIC_DELETE','read_only':True}

    @staticmethod
    def _release_confirmed_permit(runtime,turn):
        from .provider_security import PlanningProviderSecurityService
        if turn['outcome'] is None or turn['outcome']['execution']!='CONFIRMED':return
        rows=runtime.database._connection.execute(
            'SELECT permit_id FROM planning_provider_generation_permits WHERE provider_id=? AND request_digest=?',
            (turn['provider']['provider_id'],turn['provider']['generation_digest'])).fetchall()
        service=PlanningProviderSecurityService(runtime.database,None,runtime.repository.operators)
        for row in rows:service._release_generation_permit(row[0])

    def _root_budget(self,p,*,new_conversation=False):
        paths=list((self.root/'advisory'/'transcripts').glob('*.json'))
        if len(paths)>64 or (new_conversation and len(paths)>=64):raise AdvisoryConflict('CONVERSATION_CAPACITY_EXHAUSTED')
        used=0;unresolved=False
        for path in paths:
            try:v=json.loads(_private_bytes(path))
            except (ValueError,OSError):raise RuntimeError('retained budget unavailable') from None
            if not isinstance(v,dict) or not isinstance(v.get('turns'),list) or not isinstance(v.get('principal_reference'),str):raise RuntimeError('retained budget invalid')
            if v['principal_reference']==p.reference:used+=len(v['turns'])
            for t in v['turns']:
                if not isinstance(t,dict) or t.get('execution') not in ('MAY_HAVE_HAPPENED','CONFIRMED','NOT_STARTED'):raise RuntimeError('retained invocation invalid')
                if t['execution']=='MAY_HAVE_HAPPENED':unresolved=True
        return used,unresolved

    def cancel_request(self,authorization,conversation_id,turn_id,body):
        if not isinstance(body,dict) or set(body)!={'contract_version','expected_revision','request_digest'} or body['contract_version']!=self.contract or type(body['expected_revision']) is not int:raise ValueError('invalid cancel intent')
        p=self.grant.authorize(authorization,conversation_id);context,_=self.context(p);path=self._path(p,conversation_id)
        with conversation_lock(path),_locked(self.grant.path):
            self.grant.authorize(authorization,conversation_id);value=self._read(path,p,conversation_id,context)
            t=next((t for t in value['turns'] if t['request']['turn_id']==turn_id),None)
            if t is None:raise FileNotFoundError('unknown turn')
            if value['revision']!=body['expected_revision'] or t['request_digest']!=body['request_digest'] or t['status'] in ('COMPLETE','REVIEW'):raise AdvisoryConflict('CANCEL_PRECONDITION_CHANGED')
            t['status']='CANCEL_REQUESTED';self._save(path,value)
            return {'contract_version':self.contract,'original_turn':t,'current_revision':value['revision'],'provider_stopped':False,'cancel_request_recorded':True}

    def capability(self,authorization,selections=None):
        p=self.grant.authorize(authorization);context,revision=self.context(p,selections)
        return {'contract_version':self.contract,'supported_modes':list(MODES),'unsupported':['UX','APPLY','ATTACHMENTS','EXPORT','STREAMING','PROVIDER_CANCEL'],
                'project_id':p.project_id,'repository_id':p.repository_id,'instance_id':p.instance_id,'conversation_ids':list(p.conversation_ids),
                'context':context,'context_revision':revision,'maximum_turns':p.maximum_turns,'available_sources':AdvisoryContext(self.root,p.instance_id).available(p),'max_concurrent_invocations_per_instance':1,
                'cancel_request_supported':True,'provider_stop_supported':False,'retained_principal_consumed_turns':self._root_budget(p)[0],'live_model_quality':'NOT_QUALIFIED','unknown_usage':'NOT_REPORTED_AND_NOT_ACCEPTED_AS_BOUND_PROOF','read_only':True}

    def handle(self,method,target,authorization,body):
        try:
            parsed=urlsplit(target);parts=parsed.path.split('/');query=parse_qs(parsed.query,keep_blank_values=True)
            if method=='GET' and parsed.path=='/v1/advisory/capability':
                if set(query)-{'source_id','source_version'} or len(query.get('source_id',[]))!=len(query.get('source_version',[])):raise ValueError('source preview invalid')
                selections=[{'source_id':key,'version':v} for key,v in zip(query.get('source_id',[]),query.get('source_version',[]))]
                return 200,self.capability(authorization,selections)
            if len(parts)<4 or parts[:3]!=['','v1','advisory']:raise PermissionError('advisory routes only')
            conversation_id=identifier(parts[3])
            if method=='POST' and len(parts)==5 and parts[4]=='turns' and not query:
                if not isinstance(body,dict) or body.get('conversation_id')!=conversation_id:raise ValueError('route/request mismatch')
                return 200,self.submit(authorization,body)
            if method=='GET' and len(parts)==4:
                if set(query)-{'cursor','limit'} or any(len(v)!=1 for v in query.values()):raise ValueError('invalid history query')
                return 200,self.read(authorization,conversation_id,cursor=int(query.get('cursor',['0'])[0]),limit=int(query.get('limit',['4'])[0]))
            if method=='POST' and len(parts)==7 and parts[4]=='turns' and parts[6]=='cancel' and not query:return 200,self.cancel_request(authorization,conversation_id,identifier(parts[5]),body)
            if method=='GET' and len(parts)==6 and parts[4]=='turns' and not query:return 200,self.read(authorization,conversation_id,identifier(parts[5]))
            return 404,{'contract_version':self.contract,'error':{'code':'ADVISORY_ROUTE_NOT_FOUND'}}
        except AdvisoryProviderUnavailable:status,code=503,'ADVISORY_PROVIDER_UNAVAILABLE'
        except PermissionError:status,code=403,'ADVISORY_SCOPE_DENIED'
        except AdvisoryConflict as e:status,code=409,e.code
        except AdvisoryUnsupported:status,code=400,'ADVISOR_UNSUPPORTED'
        except FileNotFoundError:status,code=404,'ADVISORY_NOT_FOUND'
        except (ValueError,TypeError,KeyError):status,code=400,'ADVISORY_REQUEST_INVALID'
        except (OSError,RuntimeError,sqlite3.Error):status,code=503,'ADVISORY_SOURCE_UNAVAILABLE'
        return status,{'contract_version':self.contract,'error':{'code':code}}
