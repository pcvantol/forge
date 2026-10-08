"""A bounded explicit proposal-to-Candidate bridge over canonical governance."""
from contextlib import contextmanager
from datetime import UTC,datetime
from pathlib import Path
import json,sqlite3,os
from urllib.parse import urlsplit,parse_qs
from .advisory_candidate_contract import CONTRACT,exact,fields,proposal_request,registration_request,candidate_objects,revision,hash_reference,registration_key,registration_receipt
from .advisory_contract import digest,AdvisoryConflict
from .advisory_service import AdvisoryService,conversation_lock
from .advisory_grant import conversation_path
from .advisory_context import AdvisoryContext
from .approved_worklist import identifier
from .workspace_review_grant import _private_bytes,_write_private,_locked
from .lifecycle import RecommendationLifecycleStore,LifecycleError
from .worklist_control import control_runtime

class AdvisoryCandidateService:
    def __init__(self,root,grant):self.root=Path(root);self.grant=grant
    def _path(self,p,proposal_id):return self.root/'advisory'/'candidate-proposals'/(digest([p.instance_id,p.project_id,p.repository_id,p.conversation_id,proposal_id])[7:]+'.json')
    def _source(self,token,p,turn_id):
        value=AdvisoryService(self.root,self.grant,'unused-for-read').read(token,p.conversation_id,turn_id)
        t=value['original_turn']
        if t['status']!='COMPLETE' or t['execution']!='CONFIRMED' or t['outcome']['output'] is None:raise AdvisoryConflict('ADVICE_NOT_COMPLETE')
        _,current=AdvisoryService(self.root,self.grant,'unused-for-read').context(p,t['request']['selected_sources'])
        if current!=t['request']['context_revision']:raise AdvisoryConflict('SOURCE_CONTEXT_CHANGED')
        return {'turn_id':turn_id,'session_id':t['session_id'],'invocation_id':t['invocation_id'],'request_digest':t['request_digest'],
                'result_digest':t['outcome']['result_digest'],'advisor_kind':t['request']['advisor_kind'],
                'context_revision':current,'conversation_revision':value['current_revision'],
                'selected_sources':t['request']['selected_sources'],'evidence_references':t['context']['evidence_references'],
                'advice_summary':t['outcome']['output']['summary']}
    @contextmanager
    def _lease(self,token,conversation_id,proposal_id):
        p=self.grant.authorize(token,conversation_id,proposal_id)
        path=conversation_path(self.root,p.instance_id,p.project_id,p.repository_id,p.conversation_id)
        with conversation_lock(path),_locked(self.grant.path),_locked(AdvisoryContext(self.root,p.instance_id).path):
            yield self.grant.authorize(token,conversation_id,proposal_id)
    def _load(self,token,p,proposal_id,create=False):
        path=self._path(p,proposal_id)
        if create and not path.exists() and not path.is_symlink():
            return {'contract_version':CONTRACT,'principal_reference':p.reference,'scope':{k:getattr(p,k) for k in ['instance_id','project_id','repository_id']},'conversation_id':p.conversation_id,'proposal_id':proposal_id,'maximum_registrations':p.maximum_registrations,'creation_grant_id':p.grant_id,'revisions':[]}
        try:v=json.loads(_private_bytes(path))
        except FileNotFoundError:raise
        except (OSError,ValueError):raise RuntimeError('private proposal unavailable') from None
        if isinstance(v,dict) and v.get('principal_reference')!=p.reference:raise PermissionError('foreign proposal owner')
        if (not isinstance(v,dict) or set(v)!=set('contract_version principal_reference scope conversation_id proposal_id maximum_registrations creation_grant_id revisions'.split()) or v['contract_version']!=CONTRACT or v['scope']!={k:getattr(p,k) for k in ['instance_id','project_id','repository_id']} or v['proposal_id']!=proposal_id or v['conversation_id']!=p.conversation_id or type(v['maximum_registrations']) is not int or not 1<=v['maximum_registrations']<=8 or not isinstance(v['revisions'],list) or not 1<=len(v['revisions'])<=8):raise RuntimeError('stored proposal binding invalid')
        creation=next((r for r in self.grant._records() if r['grant_id']==v['creation_grant_id']),None)
        if creation is None or creation['maximum_registrations']!=v['maximum_registrations'] or creation['principal_id']!=p.principal_id or creation['conversation_id']!=p.conversation_id or proposal_id not in creation['proposal_ids'] or any(creation[k]!=getattr(p,k) for k in ['instance_id','project_id','repository_id']):raise RuntimeError('original proposal allowance unavailable')
        for n,d in enumerate(v['revisions'],1):
            if not isinstance(d,dict) or set(d)!=set('contract_version principal_reference instance_id project_id repository_id conversation_id proposal_id proposal_revision source fields field_origins proposal_digest'.split()):raise RuntimeError('stored proposal shape invalid')
            if type(d['proposal_revision']) is not int or d['proposal_revision']!=n or d['contract_version']!=CONTRACT or d['principal_reference']!=p.reference or d['proposal_id']!=proposal_id or d['conversation_id']!=p.conversation_id or any(d[k]!=getattr(p,k) for k in ['instance_id','project_id','repository_id']):raise RuntimeError('stored proposal identity invalid')
            if d['field_origins']!={'fields':'EXPLICIT_USER','source.advice_summary':'VALIDATED_ADVICE'}:raise RuntimeError('stored field origins invalid')
            try:fields(d['fields']);actual=self._source(token,p,d['source']['turn_id'])
            except (ValueError,TypeError,KeyError):raise RuntimeError('stored proposal fields invalid') from None
            old={k:x for k,x in d['source'].items() if k!='conversation_revision'}
            if old!={k:x for k,x in actual.items() if k!='conversation_revision'} or type(d['source']['conversation_revision']) is not int or not 1<=d['source']['conversation_revision']<=actual['conversation_revision']:raise RuntimeError('stored source provenance invalid')
            if digest({k:x for k,x in d.items() if k!='proposal_digest'})!=d['proposal_digest']:raise RuntimeError('stored proposal digest invalid')
        return v
    def _save(self,p,proposal_id,value):
        path=self._path(p,proposal_id)
        if not path.exists() and len(list(path.parent.glob('*.json')))>=64:raise AdvisoryConflict('PROPOSAL_CAPACITY_EXHAUSTED')
        raw=json.dumps(value,sort_keys=True,ensure_ascii=True).encode()
        if len(raw)>65536:raise AdvisoryConflict('PROPOSAL_CAPACITY_EXHAUSTED')
        _write_private(path,raw)
    @staticmethod
    def _scope(p,r):
        if any(r[k]!=getattr(p,k) for k in ['instance_id','project_id','repository_id','conversation_id']):raise PermissionError('foreign proposal scope')
    @staticmethod
    def _key(p,d):return registration_key(p.reference,d)
    def _database_path(self,create=False):
        path=self.root/'governance'/'candidates.sqlite'
        if any(x.is_symlink() for x in [self.root,path.parent,path]) or path.resolve().parent.parent!=self.root.resolve():raise RuntimeError('canonical aggregate redirected')
        if create and not path.exists():
            path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600);os.close(fd)
        return path
    @contextmanager
    def _read_store(self):
        path=self._database_path()
        if not path.exists():yield None;return
        with RecommendationLifecycleStore.read_only(path) as store:yield store
    @staticmethod
    def _has_table(store,name):return store is not None and store._connection.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',name)).fetchone() is not None
    def _registered(self,store,p,d):
        if not self._has_table(store,'advisory_candidate_registrations'):return None
        value=store.candidate_registration(self._key(p,d),p.reference)
        if value is not None:
            if (set(value)!=set('contract_version operation_id principal_reference registration_key proposal_digest proposal_revision source candidate recommendation_id candidate_digest recommendation_digest registered_at status_at_registration rationale'.split()) or value['contract_version']!=CONTRACT or value['registration_key']!=self._key(p,d) or value['principal_reference']!=p.reference or value['proposal_digest']!=d['proposal_digest'] or value['proposal_revision']!=d['proposal_revision'] or value['source']!=d['source'] or value['status_at_registration']!='RECOMMENDED'):raise RuntimeError('registration provenance unavailable')
            rec,can=candidate_objects(d,self._key(p,d),value['registered_at'])
            if value['candidate']!=json.loads(json.dumps(can.to_dict())) or value['candidate_digest']!=digest(can.to_dict()) or value['recommendation_id']!=rec.id or value['recommendation_digest']!=digest(rec.to_dict()) or value['rationale']!=d['fields']['rationale']:raise RuntimeError('registration subject binding invalid')
            # Current Candidate may legitimately change; original Recommendation is immutable.
            original=store._connection.execute('SELECT document FROM recommendations WHERE recommendation_id=?',(rec.id,)).fetchone()
            if original is None or digest(json.loads(original[0]))!=value['recommendation_digest']:raise RuntimeError('canonical recommendation differs')
        return value
    def _readback(self,token,p,d,receipt,recorded=False):
        self.grant.authorize(token,p.conversation_id,d['proposal_id']);actual=self._source(token,p,d['source']['turn_id'])
        with self._read_store() as store:
            original=self._registered(store,p,d)
            if receipt!=original:raise RuntimeError('canonical receipt differs')
            can=store.get_candidate(receipt['candidate']['id']);rec=store.get_recommendation(receipt['recommendation_id'])
            current={'candidate':can.to_dict(),'candidate_digest':digest(can.to_dict()),'recommendation_status':rec.status.value,'conversation_revision':actual['conversation_revision'],'source_fresh':actual==d['source'],'mission_allocation':store.allocation_for_recommendation(rec.id) is not None}
        return {'contract_version':CONTRACT,'recorded':recorded,'original_receipt':receipt,'current':current}
    def capability(self,token):
        p=self.grant.authorize(token)
        return {'contract_version':CONTRACT,**{k:getattr(p,k) for k in ['instance_id','project_id','repository_id','conversation_id']},'proposal_ids':list(p.proposal_ids),'maximum_registrations':p.maximum_registrations,'registration_authority':'CANDIDATE_ONLY_NO_APPROVAL_OR_EXECUTION','additional_model_calls':0,'maximum_proposals_per_instance':64,'maximum_revisions_per_proposal':8,'read_only':True}
    def source(self,token,conversation_id,turn_id):
        identifier(turn_id);p=self.grant.authorize(token,conversation_id)
        return {'contract_version':CONTRACT,'source':self._source(token,p,turn_id),'read_only':True}
    def save(self,token,r):
        r=proposal_request(r)
        with self._lease(token,r['conversation_id'],r['proposal_id']) as p:
            self._scope(p,r);source=self._source(token,p,r['turn_id'])
            if source['conversation_revision']!=r['expected_conversation_revision'] or source['context_revision']!=r['context_revision']:raise AdvisoryConflict('SOURCE_STALE')
            v=self._load(token,p,r['proposal_id'],True)
            if len(v['revisions'])!=r['expected_revision']:raise AdvisoryConflict('PROPOSAL_STALE')
            if len(v['revisions'])>=8:raise AdvisoryConflict('PROPOSAL_CAPACITY_EXHAUSTED')
            d={'contract_version':CONTRACT,'principal_reference':p.reference,**{k:getattr(p,k) for k in ['instance_id','project_id','repository_id','conversation_id']},'proposal_id':r['proposal_id'],'proposal_revision':len(v['revisions'])+1,'source':source,'fields':r['fields'],'field_origins':{'fields':'EXPLICIT_USER','source.advice_summary':'VALIDATED_ADVICE'}}
            d['proposal_digest']=digest(d);candidate_objects(d,self._key(p,d),'preview-not-registered')
            v['revisions'].append(d);self._save(p,r['proposal_id'],v)
            return {'contract_version':CONTRACT,'proposal':d,'registered':False,'additional_model_calls':0}
    def preview(self,token,conversation_id,proposal_id,number=None):
        p=self.grant.authorize(token,conversation_id,proposal_id);v=self._load(token,p,proposal_id)
        if number is None:number=len(v['revisions'])
        if type(number) is not int or not 1<=number<=len(v['revisions']):raise FileNotFoundError('unknown proposal revision')
        d=v['revisions'][number-1];_,can=candidate_objects(d,self._key(p,d),'preview-not-registered')
        with self._read_store() as store:receipt=self._registered(store,p,d)
        return {'contract_version':CONTRACT,'proposal':d,'latest_revision':len(v['revisions']),'candidate_preview':can.to_dict(),'registration':self._readback(token,p,d,receipt) if receipt else None,'read_only':True}
    def register(self,token,r):
        r=registration_request(r)
        with self._lease(token,r['conversation_id'],r['proposal_id']) as p:
            self._scope(p,r);v=self._load(token,p,r['proposal_id'])
            n=r['proposal_revision']
            if n>len(v['revisions']):raise AdvisoryConflict('PROPOSAL_STALE')
            d=v['revisions'][n-1]
            if d['proposal_digest']!=r['proposal_digest']:raise AdvisoryConflict('PROPOSAL_STALE')
            key=self._key(p,d)
            with self._read_store() as store:
                old=store.candidate_registration_intent(r['operation_id'],p.reference) if self._has_table(store,'advisory_candidate_intents') else None
                receipt=self._registered(store,p,d)
            if old is not None and old['request']!=r:raise AdvisoryConflict('OPERATION_PAYLOAD_CONFLICT')
            if receipt is not None:
                if old is None:
                    actual=self._source(token,p,d['source']['turn_id'])
                    if n!=len(v['revisions']) or actual!=d['source'] or r['expected_conversation_revision']!=actual['conversation_revision'] or r['context_revision']!=actual['context_revision']:raise AdvisoryConflict('SOURCE_OR_PROPOSAL_STALE')
                    with control_runtime(self.root),RecommendationLifecycleStore(self._database_path()) as store:
                        self.grant.authorize(token,p.conversation_id,d['proposal_id'])
                        store.begin_candidate_registration(r['operation_id'],p.reference,key,{'request':r,'proposal':d,'registered_at':receipt['registered_at']},min(p.maximum_registrations,v['maximum_registrations']))
                return self._readback(token,p,d,receipt)
            actual=self._source(token,p,d['source']['turn_id'])
            if n!=len(v['revisions']) or actual!=d['source'] or r['expected_conversation_revision']!=actual['conversation_revision'] or r['context_revision']!=actual['context_revision']:raise AdvisoryConflict('SOURCE_OR_PROPOSAL_STALE')
            with control_runtime(self.root),RecommendationLifecycleStore(self._database_path(True)) as store:
                p=self.grant.authorize(token,p.conversation_id,d['proposal_id']);actual=self._source(token,p,d['source']['turn_id'])
                if actual!=d['source']:raise AdvisoryConflict('SOURCE_STALE')
                intent=old or {'request':r,'proposal':d,'registered_at':datetime.now(UTC).isoformat()}
                if intent['proposal']!=d:raise RuntimeError('intent proposal differs')
                store.begin_candidate_registration(r['operation_id'],p.reference,key,intent,min(p.maximum_registrations,v['maximum_registrations']))
                p=self.grant.authorize(token,p.conversation_id,d['proposal_id']);self._source(token,p,d['source']['turn_id'])
                rec,can=candidate_objects(d,key,intent['registered_at'])
                receipt=registration_receipt(p.reference,r['operation_id'],key,d,intent['registered_at'])
                receipt,recorded=store.finish_candidate_registration(r['operation_id'],p.reference,key,rec,can,receipt)
            return self._readback(token,p,d,receipt,recorded)
    def operation(self,token,conversation_id,proposal_id,operation_id):
        identifier(operation_id);p=self.grant.authorize(token,conversation_id,proposal_id)
        with self._read_store() as store:op=store.candidate_registration_intent(operation_id,p.reference) if self._has_table(store,'advisory_candidate_intents') else None
        if op is None:raise FileNotFoundError('unknown operation')
        r=registration_request(op['request'])
        if r['conversation_id']!=conversation_id or r['proposal_id']!=proposal_id:raise PermissionError('foreign operation')
        v=self._load(token,p,proposal_id);d=v['revisions'][r['proposal_revision']-1]
        if op['proposal']!=d or r['proposal_digest']!=d['proposal_digest']:raise RuntimeError('operation provenance differs')
        with self._read_store() as store:receipt=self._registered(store,p,d)
        return self._readback(token,p,d,receipt) if receipt else {'contract_version':CONTRACT,'state':'PENDING','operation_id':operation_id,'read_only':True}
    def handle(self,method,target,token,body=None):
        try:
            if self.grant.authenticate(token) is None:return 401,{'contract_version':CONTRACT,'error':{'code':'CANDIDATE_AUTHENTICATION_REQUIRED'}}
            parsed=urlsplit(target);a=parsed.path.split('/');q=parse_qs(parsed.query,keep_blank_values=True)
            if method=='GET' and parsed.path=='/v1/advisory-candidates/capability' and not q:return 200,self.capability(token)
            if len(a)>=4 and a[:3]==['','v1','advisory-candidates']:
                conv=identifier(a[3])
                if method=='GET' and len(a)==6 and a[4]=='source' and not q:return 200,self.source(token,conv,a[5])
                if method=='POST' and len(a)==5 and a[4]=='proposals' and not q:
                    if body['conversation_id']!=conv:raise PermissionError('route scope differs')
                    return 200,self.save(token,body)
                if len(a)>=6 and a[4]=='proposals':
                    prop=identifier(a[5])
                    if method=='GET' and len(a)==6 and set(q)<={'revision'} and len(q.get('revision',[]))<=1:
                        return 200,self.preview(token,conv,prop,int(q['revision'][0]) if q else None)
                    if method=='POST' and len(a)==7 and a[6]=='registrations' and not q:
                        if body['conversation_id']!=conv or body['proposal_id']!=prop:raise PermissionError('route scope differs')
                        return 200,self.register(token,body)
                    if method=='GET' and len(a)==8 and a[6]=='registrations' and not q:return 200,self.operation(token,conv,prop,a[7])
            raise PermissionError('Candidate grant does not authorize route')
        except AdvisoryConflict as e:status=409;code=e.code
        except PermissionError:status=403;code='CANDIDATE_SCOPE_DENIED'
        except FileNotFoundError:status=404;code='CANDIDATE_SUBJECT_NOT_FOUND'
        except LifecycleError:status=409;code='CANDIDATE_LIFECYCLE_CONFLICT'
        except (ValueError,TypeError,KeyError,IndexError):status=400;code='CANDIDATE_REQUEST_INVALID'
        except (RuntimeError,OSError,sqlite3.Error):status=503;code='CANDIDATE_SOURCE_UNAVAILABLE'
        return status,{'contract_version':CONTRACT,'error':{'code':code}}
