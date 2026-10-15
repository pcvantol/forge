"""Append-only decisions about frozen R52 document proposals, not effects."""
from datetime import UTC, datetime
import json
import sqlite3
import secrets
from urllib.parse import urlsplit, parse_qs
from .approved_worklist import identifier
from .project_bootstrap.schema import canonical
from .project_bootstrap.service import digest
from .project_proposal_grant import ProjectProposalGrant
from .project_proposal_service import ProjectProposalService
from .proposal_content_contract import CONTRACT, PROFILE, PROFILE_ID, ROLES, LIMITS, ContentConflict, decision_request

class ProposalContentService:
    def __init__(self, grant):self.grant=grant

    def subject(self, principal, dossier, plan):
        source=ProjectProposalGrant(self.grant.root,self.grant.instance_id)
        try:record=ProjectProposalService(source)._record(source._store(),plan)
        except (OSError,ValueError,KeyError,TypeError) as error:raise RuntimeError('original proposal storage unavailable') from error
        if record is None:raise FileNotFoundError('proposal not found')
        if (record['instance_id'],record['principal_id'],record['audience'],record['dossier_id']) != (principal.instance_id,principal.proposal_principal_id,principal.audience,dossier):raise PermissionError('foreign proposal subject')
        value=record['input']
        if record['proposal_kind']!='pb-render/1.0' or any(value.get(k)!=v for k,v in [('baseline','portable-docs/1.0.0'),('role','authority'),('mode','GENESIS'),('host_profile','LOCAL_POSIX'),('stack_profile','NO_PRODUCT_CODE'),('security_profile','DOCUMENT_ONLY')]):
            raise ContentConflict('CONTENT_PROFILE_UNSUPPORTED')
        artifacts={a['path']:a for a in record['result']['artifacts']}
        manifest=json.loads(artifacts['engineering/bootstrap-manifest.json']['content'])
        if manifest['baseline']!=PROFILE['baseline'] or manifest['contract_version']!=PROFILE['proposal_kind'] or manifest['input_digest']!=record['result']['input_digest'] or manifest['manifest_digest']!=digest(canonical({k:v for k,v in manifest.items() if k!='manifest_digest'})):
            raise ValueError('original manifest binding invalid')
        entries=manifest['artifacts']
        if len(entries)!=len(artifacts)-1 or len({a['relative_path'] for a in entries})!=len(entries):raise ValueError('manifest inventory invalid')
        for a in entries:
            actual=artifacts[a['relative_path']]
            if a['expected_after_digest']!=actual['sha256'] or a['input_digest']!=manifest['input_digest'] or a['file_mode']!='0644' or a['bytes']!=len(actual['content'].encode()):raise ValueError('manifest artifact mismatch')
        subject={'plan_id':plan,'proposal_principal_id':record['principal_id'],'proposal_kind':record['proposal_kind'],
                 'input_digest':record['result']['input_digest'],'result_digest':record['result']['result_digest'],'record_digest':record['record_digest'],
                 'manifest_digest':manifest['manifest_digest'],'baseline':value['baseline'],'profile_id':PROFILE_ID,
                 'source_references':value['source_references'],'concept_revision':None}
        return subject,value['product']['open_questions']

    def store(self):
        try:return self.grant._store()
        except (OSError,ValueError,KeyError,TypeError) as error:raise RuntimeError('initialized decision storage unavailable') from error

    @staticmethod
    def operation_key(p, dossier, operation):return 'content-'+digest(canonical([p.instance_id,p.principal_id,p.audience,dossier,operation]))[:32]

    def history(self, store, plan):
        groups={}
        for key,r in store['records'].items():
            if not isinstance(r,dict) or set(r)!={'decision_id','request','request_digest','principal_id','audience','human_binding','grant_id','occurred_at','revision','integrity'}:raise ValueError('retained content record invalid')
            request,h=decision_request(r['request'])
            if h!=r['request_digest'] or r['decision_id']!=key or not secrets.compare_digest(r['integrity'],self.grant.integrity({k:v for k,v in r.items() if k!='integrity'})):raise ValueError('retained content integrity invalid')
            binding=[request['instance_id'],r['principal_id'],r['audience'],request['dossier_id'],request['operation_id']]
            if key!='content-'+digest(canonical(binding))[:32] or r['revision']!=request['expected_decision_revision']+1:raise ValueError('retained decision identity invalid')
            groups.setdefault(request['plan_id'],[]).append(r)
        for items in groups.values():
            items.sort(key=lambda x:x['revision'])
            for n,r in enumerate(items):
                if r['revision']!=n+1 or r['request']['previous_decision_id']!=(items[n-1]['decision_id'] if n else None) or r['request']['subject']!=items[0]['request']['subject']:raise ValueError('append-only decision lineage invalid')
        return groups.get(plan,[])

    def response(self,p,dossier,plan,subject,points,history,original=None):
        latest={r['request']['role']:r for r in history}
        state='CHANGES_REQUESTED' if any(r['request']['decision']=='REQUEST_CHANGES' for r in latest.values()) else ('CONTENT_APPROVED' if all(k in latest and latest[k]['request']['decision']=='APPROVE_CONTENT' for k in ROLES) else 'DECISION_NEEDED')
        return {'contract_version':CONTRACT,'instance_id':p.instance_id,'principal_id':p.principal_id,'audience':p.audience,'dossier_id':dossier,'plan_id':plan,
                'subject':subject,'decision_revision':len(history),'state':state,'required_roles':list(ROLES),'open_points':points,
                'history':history,'original_decision':original,'meaning':'CONTENT_BASELINE_ONLY','effects_authorized':False,'execution_readiness':'NOT_ASSESSED',
                'concept_revision_qualification':'NOT_STRUCTURALLY_PROVIDED_BY_R52','original_proposal_state':'PROPOSED_NOT_APPROVED'}

    def read(self,authorization,audience,dossier,*,plan=None,operation=None):
        with self.grant.boundary():
            p=self.grant.authorize(authorization,audience=audience,dossier_id=dossier);store=self.store();original=None
            if operation is not None:
                original=store['records'].get(self.operation_key(p,dossier,operation))
                if original is None:raise FileNotFoundError('original decision unavailable')
                plan=original['request']['plan_id']
            subject,points=self.subject(p,dossier,plan);history=self.history(store,plan)
            return self.response(p,dossier,plan,subject,points,history,original)

    def submit(self,authorization,audience,document):
        r,h=decision_request(document)
        with self.grant.boundary():
            p=self.grant.authorize(authorization,audience=audience,dossier_id=r['dossier_id'],permission='DECIDE',role=r['role'])
            if r['instance_id']!=p.instance_id:raise PermissionError('foreign instance')
            subject,points=self.subject(p,r['dossier_id'],r['plan_id'])
            if r['subject']!=subject:raise ContentConflict('CONTENT_SUBJECT_CHANGED')
            if any(x not in points for x in r['acknowledged_open_points']) or (r['decision']=='APPROVE_CONTENT' and r['acknowledged_open_points']!=points):raise ContentConflict('CONTENT_OPEN_POINTS_UNACKNOWLEDGED')
            store=self.store();history=self.history(store,r['plan_id']);key=self.operation_key(p,r['dossier_id'],r['operation_id']);prior=store['records'].get(key)
            if prior is not None:
                if prior['request_digest']!=h:raise ContentConflict('CONTENT_OPERATION_CONFLICT')
                return self.response(p,r['dossier_id'],r['plan_id'],subject,points,history,prior)
            if r['expected_decision_revision']!=len(history) or r['previous_decision_id']!=(history[-1]['decision_id'] if history else None):raise ContentConflict('CONTENT_DECISION_STALE')
            if len(history)>=LIMITS['records_per_proposal'] or len(store['records'])>=LIMITS['global_records']:raise ContentConflict('CONTENT_DECISION_CAPACITY')
            record={'decision_id':key,'request':r,'request_digest':h,'principal_id':p.principal_id,'audience':p.audience,
                    'human_binding':p.human_binding,'grant_id':p.grant_id,'occurred_at':datetime.now(UTC).isoformat(),'revision':len(history)+1}
            record['integrity']=self.grant.integrity(record);store['records'][key]=record
            if len(canonical(store))>LIMITS['store_bytes']:raise ContentConflict('CONTENT_STORAGE_CAPACITY')
            # Current role/source/CAS still hold under the same short grant+SQL boundary.
            self.grant.authorize(authorization,audience=audience,dossier_id=r['dossier_id'],permission='DECIDE',role=r['role'])
            self.grant.save_store(store)
            return self.response(p,r['dossier_id'],r['plan_id'],subject,points,[*history,record],record)

    def handle(self,method,target,authorization,audience,body=None):
        try:
            if not isinstance(audience,str):raise PermissionError('explicit audience required')
            p=self.grant.authorize(authorization,audience=audience)
            parsed=urlsplit(target);query=parse_qs(parsed.query,strict_parsing=True)
            if parsed.fragment or '%' in target or '\\' in target or '//' in parsed.path or any(len(v)!=1 for v in query.values()):raise ValueError('closed content route required')
            base='/v1/project-proposal-decisions'
            if method=='GET' and parsed.path==base+'/capability' and not query and body is None:
                with self.grant.boundary():
                    p=self.grant.authorize(authorization,audience=audience);self.history(self.store(),None)
                    return 200,{'contract_version':CONTRACT,'instance_id':p.instance_id,'principal_id':p.principal_id,'audience':p.audience,'dossier_ids':list(p.dossier_ids),
                                'permissions':list(p.permissions),'roles':list(p.roles),'profile':PROFILE,'limits':LIMITS,'generation':False,'apply':False}
            if method=='POST' and parsed.path==base+'/decisions' and not query:return 200,self.submit(authorization,audience,body)
            for leaf,argument in [('proposals','plan'),('intents','operation')]:
                prefix=base+'/'+leaf+'/'
                if method=='GET' and parsed.path.startswith(prefix) and set(query)=={'dossier_id'} and body is None:
                    reference=identifier(parsed.path[len(prefix):]);dossier=identifier(query['dossier_id'][0])
                    return 200,self.read(authorization,audience,dossier,**{argument:reference})
            return 404,{'contract_version':CONTRACT,'error':{'code':'CONTENT_ROUTE_UNSUPPORTED'}}
        except PermissionError:status,code=403,'CONTENT_SCOPE_DENIED'
        except ContentConflict as e:status,code=409,e.code
        except FileNotFoundError:status,code=404,'CONTENT_NOT_FOUND'
        except (OSError,RuntimeError,sqlite3.Error):status,code=503,'CONTENT_STORAGE_UNAVAILABLE'
        except (ValueError,KeyError,TypeError):status,code=400,'CONTENT_INVALID_OR_CORRUPT'
        return status,{'contract_version':CONTRACT,'error':{'code':code}}
