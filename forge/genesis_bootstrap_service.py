"""Private append-only Genesis plans and separate finite human effect decisions."""
from datetime import UTC, datetime, timedelta
from dataclasses import asdict
import secrets
import sqlite3
from urllib.parse import urlsplit, parse_qs
from .approved_worklist import identifier, timestamp
from .project_bootstrap.schema import canonical
from .project_bootstrap.service import digest
from .project_proposal_grant import ProjectProposalGrant, operator_binding
from .project_proposal_service import ProjectProposalService
from .proposal_content_grant import ProposalContentGrant
from .proposal_content_service import ProposalContentService
from .candidate_decision_grant import signer
from .genesis_bootstrap_contract import CONTRACT, PROFILE, EFFECT_PURPOSE, BootstrapConflict, plan_request, plan_document, effect_request


class GenesisBootstrapService:
    def __init__(self, grant):
        self.grant = grant

    @staticmethod
    def key(p, dossier, operation, kind):
        return 'bootstrap-'+kind+'-'+digest(canonical([p.instance_id,p.principal_id,p.audience,dossier,operation]))[:32]

    def store(self):
        try:
            store=self.grant._store()
            for key,row in store['records'].items():
                if not isinstance(row,dict) or set(row)!={'kind','request','request_digest','document','integrity'} or row['kind'] not in ('PLAN','EFFECT_DECISION') or not secrets.compare_digest(row['integrity'],self.grant.integrity({k:v for k,v in row.items() if k!='integrity'})):
                    raise ValueError('original Genesis record integrity invalid')
                request,h=(plan_request if row['kind']=='PLAN' else effect_request)(row['request'])
                doc=row['document']; identity='plan_id' if row['kind']=='PLAN' else 'decision_id'
                prefix='plan' if row['kind']=='PLAN' else 'decision'
                expected='bootstrap-'+prefix+'-'+digest(canonical([request['instance_id'],doc['principal_id'],doc['audience'],request['dossier_id'],request['operation_id']]))[:32]
                if h!=row['request_digest'] or key!=doc[identity] or key!=expected:
                    raise ValueError('original Genesis identity invalid')
                if row['kind']=='PLAN' and doc['plan_digest']!=digest(canonical({k:v for k,v in doc.items() if k!='plan_digest'})):
                    raise ValueError('original plan digest invalid')
            self.lineages(store)
            return store
        except (OSError,ValueError,KeyError,TypeError) as error:
            raise RuntimeError('initialized Genesis storage unavailable') from error

    @staticmethod
    def lineages(store):
        groups={}
        for row in store['records'].values():
            request=row['request']; doc=row['document']; kind=row['kind']
            group=(kind,request['source_plan_id'] if kind=='PLAN' else request['plan_id'])
            groups.setdefault(group,[]).append(row)
        for (kind,_),rows in groups.items():
            field='plan' if kind=='PLAN' else 'decision'
            rows.sort(key=lambda r:r['document'][field+'_revision'])
            for index,row in enumerate(rows):
                if row['document'][field+'_revision']!=index+1 or row['request']['expected_'+field+'_revision']!=index or row['request']['previous_'+field+'_id']!=(rows[index-1]['document'][field+'_id'] if index else None):
                    raise ValueError('append-only Genesis lineage invalid')
        return groups

    def source(self,p,dossier,source_id):
        if source_id not in p.source_plan_ids:
            raise PermissionError('source outside finite Genesis scope')
        try:
            original_grant=ProjectProposalGrant(self.grant.root,self.grant.instance_id)
            record=ProjectProposalService(original_grant)._record(original_grant._store(),source_id)
            content_grant=ProposalContentGrant(self.grant.root,self.grant.instance_id)
            content_service=ProposalContentService(content_grant)
            subject,points=content_service.subject(p,dossier,source_id)
            history=content_service.history(content_grant._store(),source_id)
            content=content_service.response(p,dossier,source_id,subject,points,history)
            return record,content,content_grant
        except PermissionError:
            raise
        except (OSError,ValueError,KeyError,TypeError,RuntimeError) as error:
            raise RuntimeError('owning original proposal/content storage unavailable') from error

    def content_current(self, content, grant):
        latest={r['request']['role']:r for r in content['history']}
        if content['state']!='CONTENT_APPROVED':
            return False
        grants={r['grant_id']:r for r in grant._records()}
        for role in ('BUSINESS','ARCHITECTURE'):
            decision=latest[role]; row=grants.get(decision['grant_id'])
            if row is None or row['state']!='ACTIVE' or timestamp(row['expires_at'])<=datetime.now(UTC) or row['operator_binding']!=operator_binding(grant.root,grant.instance_id):
                return False
            if role not in row['roles'] or 'DECIDE' not in row['permissions'] or row['principal_id']!=decision['principal_id'] or row['human_binding']!=decision['human_binding'] or row['audience']!=decision['audience'] or row['proposal_principal_id']!=content['subject']['proposal_principal_id'] or decision['request']['dossier_id'] not in row['dossier_ids']:
                return False
            try:
                if signer(grant.root,grant.instance_id,'solo',('READ',role),row['principal_id'])!=decision['human_binding']:
                    return False
            except PermissionError:
                return False
        return True

    def scope(self,p,plan):
        if (plan['instance_id'],plan['audience'],plan['source_subject']['proposal_principal_id'])!=(p.instance_id,p.audience,p.proposal_principal_id) or plan['dossier_id'] not in p.dossier_ids or plan['source_subject']['plan_id'] not in p.source_plan_ids:
            raise PermissionError('foreign Genesis plan')

    def view(self,p,store,plan_id,original=None):
        row=store['records'].get(plan_id)
        if row is None or row['kind']!='PLAN':
            raise FileNotFoundError('original plan unavailable')
        plan=row['document']; self.scope(p,plan)
        record,content,content_grant=self.source(p,plan['dossier_id'],plan['source_subject']['plan_id'])
        groups=self.lineages(store)
        lineage=groups[('PLAN',plan['source_subject']['plan_id'])]
        decisions=[r['document'] for r in groups.get(('EFFECT_DECISION',plan_id),[])]
        reasons=[]
        if lineage[-1]['document']['plan_id']!=plan_id:
            reasons.append('PLAN_SUPERSEDED')
        if timestamp(plan['expires_at'])<=datetime.now(UTC):
            reasons.append('PLAN_EXPIRED')
        if content['subject']!=plan['source_subject'] or digest(canonical(content['history']))!=plan['content_history_digest']:
            reasons.append('SOURCE_CONTENT_CHANGED')
        if not self.content_current(content,content_grant):
            reasons.append('CURRENT_CONTENT_AUTHORITY_REQUIRED')
        if plan['blocking_open_points']:
            reasons.append('REQUIRED_OPEN_POINTS_UNANSWERED')
        eligible=not reasons
        applicable=False
        if decisions:
            last=decisions[-1]
            own_grants={r['grant_id']:r for r in self.grant._records()}
            grant=own_grants.get(last['grant_id'])
            if grant is not None:
                try:
                    self.grant.current(grant)
                    applicable=eligible and last['decision']=='APPROVE_EFFECT' and 'DECIDE_EFFECT' in grant['permissions'] and {'plan_id':plan_id,'plan_digest':plan['plan_digest']} in grant['exact_plans']
                except PermissionError:
                    pass
        if original is not None and original not in decisions:
            raise PermissionError('foreign original effect decision')
        return {'contract_version':CONTRACT,'instance_id':p.instance_id,'principal_id':p.principal_id,'audience':p.audience,'dossier_id':plan['dossier_id'],
                'plan':plan,'effect_decision_revision':len(decisions),'effect_history':decisions,'original_decision':original,
                'effect_decision_eligible':eligible,'inapplicability_reasons':reasons,'effect_decision_currently_applicable':applicable,
                'state':'EP_ADMISSION_REQUIRED','execution_authorized':False,'target_write':'NOT_PERFORMED','ep_credential':'NOT_ISSUED'}

    @staticmethod
    def capability(p):
        return {'contract_version':CONTRACT,'instance_id':p.instance_id,'principal_id':p.principal_id,'audience':p.audience,
                'dossier_ids':list(p.dossier_ids),'source_plan_ids':list(p.source_plan_ids),'permissions':list(p.permissions),
                'profile_id':PROFILE,'purpose':EFFECT_PURPOSE,'target_write':False,'ep_admission':False,'execution_authorized':False}

    def save(self,store,key,kind,request,h,document):
        if len(store['records'])>=64:
            raise BootstrapConflict('GENESIS_STORAGE_CAPACITY')
        row={'kind':kind,'request':request,'request_digest':h,'document':document}
        row['integrity']=self.grant.integrity(row)
        store['records'][key]=row
        if len(canonical(store))>16*1024*1024:
            raise BootstrapConflict('GENESIS_STORAGE_CAPACITY')
        self.grant.save_store(store)

    def prepare(self,authorization,audience,document):
        request,h=plan_request(document)
        with self.grant.boundary():
            p=self.grant.authorize(authorization,audience=audience,dossier_id=request['dossier_id'],permission='PREPARE',source_plan_id=request['source_plan_id'])
            if request['instance_id']!=p.instance_id:
                raise PermissionError('foreign Genesis instance')
            store=self.store(); key=self.key(p,request['dossier_id'],request['operation_id'],'plan')
            prior=store['records'].get(key)
            if prior is not None:
                if prior['request_digest']!=h:
                    raise BootstrapConflict('GENESIS_OPERATION_CONFLICT')
                return self.view(p,store,key)
            record,content,_=self.source(p,request['dossier_id'],request['source_plan_id'])
        # Pure frozen-byte verification outside all authority/storage fences.
        plan=plan_document(record,content,request,asdict(p))
        with self.grant.boundary():
            p=self.grant.authorize(authorization,audience=audience,dossier_id=request['dossier_id'],permission='PREPARE',source_plan_id=request['source_plan_id'])
            store=self.store(); prior=store['records'].get(key)
            if prior is not None:
                if prior['request_digest']!=h:
                    raise BootstrapConflict('GENESIS_OPERATION_CONFLICT')
                return self.view(p,store,key)
            current_record,current,_=self.source(p,request['dossier_id'],request['source_plan_id'])
            if current_record!=record or current!=content:
                raise BootstrapConflict('GENESIS_SOURCE_CHANGED')
            lineage=self.lineages(store).get(('PLAN',request['source_plan_id']),[])
            if request['expected_plan_revision']!=len(lineage) or request['previous_plan_id']!=(lineage[-1]['document']['plan_id'] if lineage else None):
                raise BootstrapConflict('GENESIS_PLAN_STALE')
            if not datetime.now(UTC)<timestamp(plan['expires_at'])<=datetime.now(UTC)+timedelta(days=30):
                raise BootstrapConflict('GENESIS_PLAN_EXPIRY')
            self.save(store,key,'PLAN',request,h,plan)
            return self.view(p,store,key)

    def decide(self,authorization,audience,document):
        request,h=effect_request(document)
        with self.grant.boundary():
            p=self.grant.authorize(authorization,audience=audience,dossier_id=request['dossier_id'],permission='DECIDE_EFFECT')
            if request['instance_id']!=p.instance_id:
                raise PermissionError('foreign Genesis instance')
            store=self.store(); view=self.view(p,store,request['plan_id']); plan=view['plan']
            self.grant.authorize(authorization,audience=audience,dossier_id=request['dossier_id'],permission='DECIDE_EFFECT',source_plan_id=plan['source_subject']['plan_id'],plan=plan)
            if request['dossier_id']!=plan['dossier_id'] or request['plan_digest']!=plan['plan_digest']:
                raise BootstrapConflict('GENESIS_EXACT_PLAN_REQUIRED')
            key=self.key(p,request['dossier_id'],request['operation_id'],'decision'); prior=store['records'].get(key)
            if prior is not None:
                if prior['request_digest']!=h:
                    raise BootstrapConflict('GENESIS_OPERATION_CONFLICT')
                return self.view(p,store,plan['plan_id'],prior['document'])
            history=view['effect_history']
            if request['expected_decision_revision']!=len(history) or request['previous_decision_id']!=(history[-1]['decision_id'] if history else None):
                raise BootstrapConflict('GENESIS_EFFECT_STALE')
            if request['decision']=='APPROVE_EFFECT' and not view['effect_decision_eligible']:
                raise BootstrapConflict('GENESIS_EFFECT_INAPPLICABLE')
            decision={'decision_id':key,'decision_revision':len(history)+1,'principal_id':p.principal_id,'audience':p.audience,
                      'grant_id':p.grant_id,'human_binding':p.human_binding,'occurred_at':datetime.now(UTC).isoformat(),**request}
            self.save(store,key,'EFFECT_DECISION',request,h,decision)
            return self.view(p,store,plan['plan_id'],decision)

    def read(self,authorization,audience,dossier,reference,leaf):
        with self.grant.boundary():
            p=self.grant.authorize(authorization,audience=audience,dossier_id=dossier)
            store=self.store(); original=None
            key=self.key(p,dossier,reference,'plan' if leaf=='intents' else 'decision') if leaf in ('intents','decision-intents') else reference
            row=store['records'].get(key)
            if row is None:
                raise FileNotFoundError('original Genesis intent unavailable')
            if leaf in ('decisions','decision-intents'):
                if row['kind']!='EFFECT_DECISION':
                    raise FileNotFoundError('original effect decision unavailable')
                original=row['document']; key=original['plan_id']
            view=self.view(p,store,key,original)
            if view['dossier_id']!=dossier:
                raise PermissionError('foreign Genesis dossier')
            return view

    def handle(self,method,target,authorization,audience,body=None):
        try:
            if not isinstance(audience,str):
                raise PermissionError('explicit Bootstrap audience required')
            self.grant.authorize(authorization,audience=audience)
            parsed=urlsplit(target); query=parse_qs(parsed.query,strict_parsing=True)
            if parsed.fragment or '%' in target or '\\' in target or '//' in parsed.path or any(len(v)!=1 for v in query.values()):
                raise ValueError('closed Genesis route required')
            base='/v1/genesis-bootstrap'
            if method=='GET' and parsed.path==base+'/capability' and not query and body is None:
                with self.grant.boundary():
                    p=self.grant.authorize(authorization,audience=audience); self.store()
                    return 200,self.capability(p)
            if method=='POST' and not query:
                if parsed.path==base+'/plans':
                    return 200,self.prepare(authorization,audience,body)
                if parsed.path==base+'/decisions':
                    return 200,self.decide(authorization,audience,body)
            for leaf in ('plans','intents','decisions','decision-intents'):
                prefix=base+'/'+leaf+'/'
                if method=='GET' and parsed.path.startswith(prefix) and set(query)=={'dossier_id'} and body is None:
                    return 200,self.read(authorization,audience,identifier(query['dossier_id'][0]),identifier(parsed.path[len(prefix):]),leaf)
            return 404,{'contract_version':CONTRACT,'error':{'code':'GENESIS_ROUTE_UNSUPPORTED'}}
        except PermissionError:
            status,code=403,'GENESIS_SCOPE_DENIED'
        except BootstrapConflict as error:
            status,code=409,error.code
        except FileNotFoundError:
            status,code=404,'GENESIS_NOT_FOUND'
        except (OSError,RuntimeError,sqlite3.Error):
            status,code=503,'GENESIS_STORAGE_UNAVAILABLE'
        except (ValueError,KeyError,TypeError):
            status,code=400,'GENESIS_INVALID_OR_CORRUPT'
        return status,{'contract_version':CONTRACT,'error':{'code':code}}
