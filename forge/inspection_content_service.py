"""Append-only exact R55 content decisions, durable intent and current readback."""
from datetime import UTC, datetime
import secrets
import sqlite3
from urllib.parse import urlsplit, parse_qs
from .approved_worklist import identifier
from .project_bootstrap.schema import canonical
from .project_bootstrap.service import digest
from .ep_inspection_service import InspectionAdoptionService
from .ep_inspection_peer import PeerError
from .inspection_content_contract import CONTRACT, PROFILE_ID, PROFILE, BASE, LIMITS, ROLES, ContentConflict, decision_request, subject


class InspectionContentService:
    def __init__(self, grant):
        self.grant = grant

    def checked_source(self, authorization, audience, *, deadline=None):
        with self.grant.boundary(deadline):
            p = self.grant.authorize(authorization,audience=audience)
            source_p = self.grant.source_principal(p)
            bound, points, blockers = self.local_subject(p,source_p)
        InspectionAdoptionService(self.grant.source)._peer(source_p,deadline=deadline)
        with self.grant.boundary(deadline):
            if self.grant.authorize(authorization,audience=audience) != p or self.local_subject(p,self.grant.source_principal(p)) != (bound,points,blockers):
                raise PermissionError('late source authority or snapshot changed')
        return p, bound, points, blockers

    def local_subject(self, p, source_p):
        values = subject(self.grant.original(source_p,p.dossier_id,p.plan_id))
        if values[0]['subject_digest'] != p.subject_digest:
            raise ContentConflict('INSPECTION_CONTENT_SUBJECT_CHANGED')
        return values

    @staticmethod
    def key(p, operation):
        return 'inspection-content-'+digest(canonical([p.instance_id,p.dossier_id,operation]))[:32]

    def history(self, store, plan):
        groups = {}
        for key, r in store['records'].items():
            keys = {'decision_id','request','request_digest','principal_id','audience','human_binding','grant_id','occurred_at','revision','integrity'}
            if not isinstance(r,dict) or set(r) != keys:
                raise ValueError('closed retained content record required')
            request, h = decision_request(r['request'])
            expected = 'inspection-content-'+digest(canonical([request['instance_id'],request['dossier_id'],request['operation_id']]))[:32]
            if h != r['request_digest'] or key != r['decision_id'] or key != expected or not secrets.compare_digest(r['integrity'],self.grant.integrity({k:v for k,v in r.items() if k != 'integrity'})):
                raise ValueError('retained decision integrity failed')
            intent = store['dossiers'].get(key)
            if intent is None or intent['request_digest'] != h or intent['grant_id'] != r['grant_id']:
                raise ValueError('retained original intent lost')
            groups.setdefault(request['plan_id'],[]).append(r)
        for rows in groups.values():
            rows.sort(key=lambda r:r['revision'])
            for n,r in enumerate(rows):
                if r['revision'] != n+1 or r['request']['expected_decision_revision'] != n or r['request']['previous_decision_id'] != (rows[n-1]['decision_id'] if n else None) or r['request']['subject_digest'] != rows[0]['request']['subject_digest']:
                    raise ValueError('append-only subject lineage invalid')
        return groups.get(plan,[])

    def view(self, p, bound, points, blockers, store, operation=None):
        history = self.history(store,p.plan_id)
        roles = {}
        for role in ROLES:
            latest = next((r for r in reversed(history) if r['request']['role'] == role),None)
            roles[role] = {'decision_id':latest['decision_id'] if latest else None,
                           'decision':latest['request']['decision'] if latest else None,
                           'currently_applicable':latest is not None and self.grant.applicable(latest)}
        current = [v['decision'] for v in roles.values() if v['currently_applicable']]
        state = 'CHANGES_REQUESTED' if 'REQUEST_CHANGES' in current else 'CONTENT_APPROVED_ONLY' if len(current) == len(ROLES) and all(x == 'APPROVE_CONTENT' for x in current) and not blockers else 'DECISION_NEEDED'
        original = store['records'].get(self.key(p,operation)) if operation else None
        intent = store['dossiers'].get(self.key(p,operation)) if operation else None
        if operation and intent is not None and (intent['plan_id'] != p.plan_id or intent['audience'] != p.audience or intent['request']['subject_digest'] != p.subject_digest):
            raise PermissionError('foreign original decision intent')
        if operation and intent is None:

            raise FileNotFoundError('original content intent unavailable')
        return {'contract_version':CONTRACT,'profile_id':PROFILE_ID,'instance_id':p.instance_id,'principal_id':p.principal_id,
                'audience':p.audience,'dossier_id':p.dossier_id,'plan_id':p.plan_id,'subject':bound,
                'review':points,'review_digest':digest(canonical(points)),'blockers':blockers,'role_status':roles,
                'state':state,'decision_revision':len(history),'history':history,'intent_id':operation,
                'intent_state':('COMMITTED' if original else 'PENDING') if intent else None,
                'original_decision':original,'effects_authorized':False,'execution_readiness':'NOT_ASSESSED',
                'original_proposal_state':'PROPOSED_NOT_APPROVED'}

    def capability(self, p):
        return {'contract_version':CONTRACT,'profile':PROFILE,'limits':LIMITS,'instance_id':p.instance_id,
                'principal_id':p.principal_id,'audience':p.audience,'dossier_id':p.dossier_id,'permissions':list(p.permissions),
                'roles':list(p.roles),'scoped_plan_id':p.plan_id,'subject_digest':p.subject_digest,'apply':False}

    def read(self, authorization, audience, *, dossier, plan=None, operation=None, decision=None):
        p,bound,points,blockers = self.checked_source(authorization,audience)
        with self.grant.boundary():
            current = self.grant.authorize(authorization,audience=audience,dossier_id=dossier,plan_id=plan)
            if current != p or self.local_subject(p,self.grant.source_principal(p)) != (bound,points,blockers):
                raise PermissionError('late read authority changed')
            store = self.grant._store()
            if decision is not None:
                self.history(store,p.plan_id)
                original = store['records'].get(decision)
                if original is None:
                    raise FileNotFoundError('original decision unavailable')
                if original['request']['plan_id'] != p.plan_id or original['request']['dossier_id'] != p.dossier_id or original['audience'] != p.audience:
                    raise PermissionError('foreign original decision')
                operation = original['request']['operation_id']
            return self.view(p,bound,points,blockers,store,operation)

    def submit(self, authorization, audience, document):
        request,h = decision_request(document)
        with self.grant.boundary():
            p = self.grant.authorize(authorization,audience=audience,dossier_id=request['dossier_id'],plan_id=request['plan_id'],permission='DECIDE',role=request['role'])
            if request['instance_id'] != p.instance_id or request['subject_digest'] != p.subject_digest:
                raise ContentConflict('INSPECTION_CONTENT_SUBJECT_CHANGED')
            bound,points,blockers = self.local_subject(p,self.grant.source_principal(p))
            if request['acknowledged_review_digest'] != digest(canonical(points)):
                raise ContentConflict('INSPECTION_CONTENT_REVIEW_UNACKNOWLEDGED')
            if request['decision'] == 'APPROVE_CONTENT' and blockers:
                raise ContentConflict('INSPECTION_CONTENT_BLOCKED')
            store = self.grant._store()
            history = self.history(store,p.plan_id)
            key = self.key(p,request['operation_id'])
            intent = {'request_digest':h,'grant_id':p.grant_id,'principal_id':p.principal_id,'human_binding':p.human_binding,
                      'audience':p.audience,'plan_id':p.plan_id,'request':request}
            prior = store['dossiers'].get(key)
            if prior is not None:
                if prior != intent:
                    raise ContentConflict('INSPECTION_CONTENT_OPERATION_CONFLICT')
            else:
                self.cas(request,history)
                if len(store['dossiers']) >= LIMITS['global_records']:
                    raise ContentConflict('INSPECTION_CONTENT_CAPACITY')
                store['dossiers'][key] = intent
                self.save(store)  # Original intent durably precedes all decision effects.
        checked_p,new_bound,new_points,new_blockers = self.checked_source(authorization,audience)
        with self.grant.boundary():
            current = self.grant.authorize(authorization,audience=audience,dossier_id=p.dossier_id,plan_id=p.plan_id,permission='DECIDE',role=request['role'])
            if current != p or checked_p != p or (bound,points,blockers) != (new_bound,new_points,new_blockers) or self.local_subject(p,self.grant.source_principal(p)) != (bound,points,blockers):
                raise PermissionError('late decision authority changed')
            store = self.grant._store()
            if store['dossiers'].get(key) != intent:
                raise RuntimeError('durable original decision intent unavailable')
            history = self.history(store,p.plan_id)
            original = store['records'].get(key)
            if original is None:
                self.cas(request,history)
                row = {'decision_id':key,'request':request,'request_digest':h,'principal_id':p.principal_id,
                       'audience':p.audience,'human_binding':p.human_binding,'grant_id':p.grant_id,
                       'occurred_at':datetime.now(UTC).isoformat(),'revision':len(history)+1}
                row['integrity'] = self.grant.integrity(row)
                store['records'][key] = row
                self.save(store)
            return self.view(p,bound,points,blockers,store,request['operation_id'])

    @staticmethod
    def cas(request, history):
        if request['expected_decision_revision'] != len(history) or request['previous_decision_id'] != (history[-1]['decision_id'] if history else None):
            raise ContentConflict('INSPECTION_CONTENT_DECISION_STALE')
        if len(history) >= LIMITS['records_per_proposal']:
            raise ContentConflict('INSPECTION_CONTENT_CAPACITY')

    def save(self, store):
        if len(canonical(store)) > LIMITS['store_bytes']:
            raise ContentConflict('INSPECTION_CONTENT_STORAGE_CAPACITY')
        self.grant.save_store(store)

    def handle(self, method, target, authorization, audience, body=None):
        try:
            if not isinstance(audience,str):
                raise PermissionError('explicit audience required')
            p = self.grant.authorize(authorization,audience=audience)
            parsed = urlsplit(target)
            query = parse_qs(parsed.query,strict_parsing=True)
            if parsed.fragment or '%' in target or '\\' in target or '//' in parsed.path or any(len(v) != 1 for v in query.values()):
                raise ValueError('closed inspection-content route required')
            if method == 'GET' and parsed.path == BASE+'/capability' and not query and body is None:
                p,_,_,_ = self.checked_source(authorization,audience)
                self.history(self.grant._store(),None)
                return 200,self.capability(p)
            if method == 'POST' and parsed.path == BASE+'/decisions' and not query:
                return 200,self.submit(authorization,audience,body)
            for leaf,argument in [('proposals','plan'),('intents','operation'),('decisions','decision')]:
                prefix = BASE+'/'+leaf+'/'
                if method == 'GET' and parsed.path.startswith(prefix) and set(query) == {'dossier_id'} and body is None:
                    reference = identifier(parsed.path[len(prefix):])
                    return 200,self.read(authorization,audience,dossier=identifier(query['dossier_id'][0]),**{argument:reference})
            return 404,{'contract_version':CONTRACT,'error':{'code':'INSPECTION_CONTENT_ROUTE_UNSUPPORTED'}}
        except PermissionError:
            status,code = 403,'INSPECTION_CONTENT_SCOPE_DENIED'
        except ContentConflict as error:
            status,code = 409,error.code
        except PeerError as error:
            status,code = error.status,error.code
        except FileNotFoundError:
            status,code = 404,'INSPECTION_CONTENT_NOT_FOUND'
        except (OSError,RuntimeError,sqlite3.Error):
            status,code = 503,'INSPECTION_CONTENT_UNAVAILABLE'
        except (ValueError,KeyError,TypeError):
            status,code = 400,'INSPECTION_CONTENT_INVALID_OR_CORRUPT'
        return status,{'contract_version':CONTRACT,'error':{'code':code}}
