"""Two explicit canonical approvals with durable cross-store recovery, never intake."""
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import json, sqlite3
from urllib.parse import urlsplit, unquote
from .candidate_decision_contract import CONTRACT, decision_request, architecture_inputs
from .candidate_decision_grant import DecisionPrincipal
from .advisory_contract import digest, AdvisoryConflict
from .advisory_candidate_contract import registration_receipt
from .advisory_candidate_grant import CandidatePrincipal
from .advisory_candidate_service import AdvisoryCandidateService
from .advisory_context import AdvisoryContext
from .approved_worklist import candidate_source, identifier
from .governance import resolve_governance_profile
from .governed_candidate_intake import GovernedCandidateIntake
from .lifecycle import RecommendationLifecycleStore, LifecycleError
from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
from .runtime.service import RuntimeServiceLock, RuntimeServiceBusy
from .workspace_review_grant import _locked
from .worklist_control import control_runtime
from .models.criterion_observation import canonical_digest

class CandidateSourceReadScope:
    """Adapt only the exact registered source for an admitted Candidate grant.

    This cannot generate advice or act on a caller-selected conversation. The
    retained original principal is provenance; current authority is the new grant.
    """
    def __init__(self, grant, token, candidate_id, proposal, permission):
        self.grant,self.token,self.candidate_id,self.proposal,self.permission=grant,token,candidate_id,proposal,permission
    def authorize(self,token,conversation_id=None,proposal_id=None):
        self.grant.authorize(token,self.candidate_id,self.permission)
        d=self.proposal
        if token!=self.token or conversation_id is not None and conversation_id!=d['conversation_id'] or proposal_id is not None and proposal_id!=d['proposal_id']:
            raise PermissionError('foreign registered source')
        principal=d['principal_reference'].removeprefix(d['instance_id']+':')
        return CandidatePrincipal(principal,d['instance_id'],d['project_id'],d['repository_id'],d['conversation_id'],(d['proposal_id'],),'registered-source-read',1)

def decision_receipt(intent, decision, evidence):
    r=intent['request']
    gates=r['human_gates'] if r['kind']=='BUSINESS' else r['planning']['human_gates']
    if (decision['decision_id']!=intent['decision_id'] or decision['subject_id']!=r['candidate_id']
            or decision['subject_revision']!=r['subject_revision'] or decision['capability']!=r['kind']+'_APPROVAL'
            or decision['decision']!='approved' or decision['operator_id']!=intent['operator_id']
            or decision['installation_id']!=intent['installation_id'] or sorted(decision['gates'])!=sorted(gates)
            or sorted(decision['scope'])!=sorted(intent['candidate']['scope'])
            or canonical_digest(intent['candidate'])!=r['subject_revision']
            or evidence.recommendation_id!=intent['candidate']['recommendation_id']
            or evidence.kind!=r['kind'].lower()+'_decision' or evidence.actor!='primary_operator'
            or evidence.rationale!=r['rationale'] or evidence.occurred_at!=intent['admitted_at']
            or not {r['candidate_id'],r['subject_revision'],intent['decision_id']}.issubset(evidence.references)):
        raise RuntimeError('canonical decision/lifecycle differs from durable intent')
    if r['kind']=='ARCHITECTURE' and decision['evidence'].get('planning_digest')!=digest(r['planning']):
        raise RuntimeError('canonical Architecture planning differs')
    return {'contract_version':CONTRACT,'operation_id':r['operation_id'],'principal_reference':intent['principal_reference'],'decision_id':intent['decision_id'],'kind':r['kind'],'subject_revision':r['subject_revision'],'candidate_id':r['candidate_id'],'request_digest':intent['request_digest'],'profile_id':intent['profile_id'],'operator_id':intent['operator_id'],'operator_binding_version':intent['operator_binding_version'],'installation_id':intent['installation_id'],'source_digest':intent['source_digest'],'rationale':r['rationale'],'admitted_at':intent['admitted_at'],'canonical_decision':decision,'canonical_decision_digest':digest(decision),'lifecycle_evidence':evidence.to_dict(),'lifecycle_evidence_digest':evidence.content_digest}

class CandidateDecisionService:
    def __init__(self,root,grant):
        self.root=Path(root);self.grant=grant
    @contextmanager
    def read_store(self):
        with RecommendationLifecycleStore.read_only(candidate_source(self.root)) as store:
            yield store
    @staticmethod
    def has_table(store,name):
        return store._connection.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',name)).fetchone() is not None
    def admitted_candidate(self,candidate_id,scope,subject_revision=None):
        identifier(candidate_id)
        with self.read_store() as store:
            receipt,proposal=store.registered_candidate_source(candidate_id)
            if any(proposal[k]!=scope[k] for k in ('instance_id','project_id','repository_id')):
                raise PermissionError('foreign registered Candidate project')
            expected=registration_receipt(proposal['principal_reference'],receipt['operation_id'],receipt['registration_key'],proposal,receipt['registered_at'])
            if digest(receipt)!=digest(expected):
                raise RuntimeError('registered Candidate provenance differs')
            candidate=store.get_candidate(candidate_id)
            original=store._connection.execute('SELECT document FROM recommendations WHERE recommendation_id=?',(candidate.recommendation_id,)).fetchone()
            if original is None or digest(json.loads(original[0]))!=receipt['recommendation_digest']:
                raise RuntimeError('registered recommendation provenance differs')
            if subject_revision is not None and (canonical_digest(candidate.to_dict())!=subject_revision or digest(candidate.to_dict())!=receipt['candidate_digest']):
                raise AdvisoryConflict('CANDIDATE_SUBJECT_CHANGED')
            return candidate,store.get_recommendation(candidate.recommendation_id),proposal,receipt
    def source(self,token,p,candidate_id,proposal,permission):
        scope=CandidateSourceReadScope(self.grant,token,candidate_id,proposal,permission)
        reader=AdvisoryCandidateService(self.root,scope)
        original=scope.authorize(token,proposal['conversation_id'])
        return reader._source(token,original,proposal['source']['turn_id'])
    def authority(self,token,candidate_id,permission,revision=None):
        p=self.grant.authorize(token,candidate_id,permission)
        bound=next(c for c in p.candidates if c['candidate_id']==candidate_id)
        if revision is not None and revision!=bound['subject_revision']:
            raise PermissionError('Candidate revision outside grant')
        candidate,rec,proposal,registration=self.admitted_candidate(candidate_id,{k:getattr(p,k) for k in ('instance_id','project_id','repository_id')},revision)
        source=self.source(token,p,candidate_id,proposal,permission)
        return p,candidate,rec,proposal,registration,source
    def capability(self,token):
        p=self.grant.authorize(token)
        return {'contract_version':CONTRACT,'scope':{k:getattr(p,k) for k in ('instance_id','project_id','repository_id')},'principal_id':p.principal_id,'profile_id':p.profile_id,'permissions':list(p.permissions),'candidates':list(p.candidates),'supported_population':'REGISTERED_R39_EXACT_SOURCE_CANDIDATES','signer_binding':'EXACT_CURRENT_G001_PRIMARY_OPERATOR','mission_intake':False,'read_only':True}
    @staticmethod
    def checked_receipt(store,runtime,key):
        receipt=store.decision_operation_receipt(key) if CandidateDecisionService.has_table(store,'candidate_decision_receipts') else None
        if receipt is not None:
            original=store.decision_operation_intent(receipt['principal_reference'],receipt['operation_id'])
            decision=runtime.repository.decision(key)
            evidence=store.decision_evidence(receipt['lifecycle_evidence']['id'])
            if receipt!=json.loads(json.dumps(decision_receipt(original,decision,evidence))):
                raise RuntimeError('decision receipt no longer joins canonical evidence')
        return receipt
    def detail(self,token,candidate_id):
        p,candidate,rec,proposal,registration,source=self.authority(token,candidate_id,'READ')
        with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime,self.read_store() as store:
            bridge=GovernedCandidateIntake(store,runtime,resolve_governance_profile(p.profile_id))
            revision,business_id,architecture_id=bridge.decision_ids(candidate_id)
            decisions={}
            for kind,key in (('BUSINESS',business_id),('ARCHITECTURE',architecture_id)):
                try:
                    decision=runtime.repository.decision(key)
                except ValueError as error:
                    if str(error)!='unknown canonical governance decision':
                        raise
                    decision=None
                history=next((e for e in store.history(rec.id) if e.kind==kind.lower()+'_decision'),None)
                receipt=self.checked_receipt(store,runtime,key)
                decisions[kind]={'decision_id':key,'canonical_decision':decision,'decision_digest':digest(decision) if decision else None,'lifecycle_evidence':history.to_dict() if history else None,'publication_complete':receipt is not None,'applicable':receipt is not None and decision is not None and history is not None and revision==receipt['subject_revision']}
            bound=next(c for c in p.candidates if c['candidate_id']==candidate_id)
            exact=revision==bound['subject_revision'] and digest(candidate.to_dict())==registration['candidate_digest']
            fresh=source==proposal['source'];allowed=[]
            for kind,status in (('BUSINESS','RECOMMENDED'),('ARCHITECTURE','BUSINESS_APPROVED')):
                if exact and fresh and rec.status.value==status and kind in p.permissions:
                    try:
                        self.grant.authorize(token,candidate_id,kind)
                        if kind=='BUSINESS' or decisions['BUSINESS']['applicable']:
                            allowed.append(kind)
                    except PermissionError:
                        pass
            missing=[]
            if not exact:missing.append('CANDIDATE_SUBJECT_CHANGED')
            if not fresh:missing.append('SOURCE_CHANGED')
            if not decisions['BUSINESS']['applicable']:missing.append('BUSINESS_DECISION_PUBLICATION_REQUIRED')
            if not decisions['ARCHITECTURE']['applicable']:missing.append('EXPLICIT_ARCHITECTURE_PREVIEW_AND_PLANNING_REQUIRED')
            current={'candidate':candidate.to_dict() if exact else None,'candidate_id':candidate_id,'subject_revision':revision,'subject_within_grant':exact,'recommendation_id':rec.id,'recommendation_status':rec.status.value,'source_fresh':fresh,'source_digest':digest(proposal['source']),'decisions':decisions,'allowed_operations':allowed,'missing_conditions':missing,'mission_allocation':store.allocation_for_recommendation(rec.id) is not None}
            projection={'id':'MISSION-PREVIEW','schema_version':'1.0','status':'approved_for_engineering','candidate_id':candidate.id,'title':candidate.title,'summary':candidate.objective,'business_objective':rec.business_summary,'business_value':rec.business_value,'architecture_review_reference':architecture_id,'mission_recommendation_reference':rec.id,'scope':list(candidate.scope),'acceptance_criteria':list(candidate.acceptance_criteria),'engineering_constraints':list(candidate.architecture_constraints),'dependencies':list(candidate.dependencies),'effect_policy':candidate.effect_policy.to_dict()} if exact else None
            preparation={'candidate_id':candidate_id,'subject_revision':revision,'source_registration_subject_revision':registration['candidate_digest'],'architecture_review_reference':architecture_id,'mission_preview_id':'MISSION-PREVIEW','expected_mission_fields':projection,'required_user_inputs':['human_gates','rationale','complete_mission_preview','complete_planning_evidence'],'planning_generated':False,'approval_granted':False}
            self.grant.authorize(token,candidate_id)
            return {'contract_version':CONTRACT,'current':current,'preparation':preparation,'read_only':True}
    def operation(self,token,candidate_id,operation_id):
        p,*_=self.authority(token,candidate_id,'READ');identifier(operation_id)
        with self.read_store() as store:
            intent=store.decision_operation_intent(p.reference,operation_id) if self.has_table(store,'candidate_decision_intents') else None
            if intent is None:
                raise FileNotFoundError('unknown scoped decision operation')
            if intent['request']['candidate_id']!=candidate_id:
                raise PermissionError('foreign operation Candidate')
            self.grant.authorize(token,candidate_id,intent['request']['kind'])
            receipt=store.decision_operation_receipt(intent['decision_id'])
            if receipt is not None:
                with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
                    self.checked_receipt(store,runtime,intent['decision_id'])
        return {'contract_version':CONTRACT,'state':'COMPLETE' if receipt else 'PENDING','original_receipt':receipt,'current':self.detail(token,candidate_id)['current'],'read_only':True}
    def decide(self,token,candidate_id,body):
        request=decision_request(body)
        if request['candidate_id']!=candidate_id:
            raise PermissionError('foreign command Candidate')
        p,*_=self.authority(token,candidate_id,request['kind'],request['subject_revision'])
        if any(request[k]!=getattr(p,k) for k in ('instance_id','project_id','repository_id')):
            raise PermissionError('foreign decision scope')
        with RuntimeServiceLock(self.root/'forge.db').acquire(),_locked(self.grant.path),_locked(AdvisoryContext(self.root,p.instance_id).path):
            p,candidate,rec,proposal,registration,source=self.authority(token,candidate_id,request['kind'],request['subject_revision'])
            if source!=proposal['source']:
                raise AdvisoryConflict('CANDIDATE_SOURCE_STALE')
            with control_runtime(self.root) as runtime,RecommendationLifecycleStore(candidate_source(self.root)) as store:
                bridge=GovernedCandidateIntake(store,runtime,resolve_governance_profile(p.profile_id))
                revision,business_id,architecture_id=bridge.decision_ids(candidate_id)
                key=business_id if request['kind']=='BUSINESS' else architecture_id
                old=store.decision_operation_intent(p.reference,request['operation_id'])
                if old is not None and old['request']!=request:
                    raise AdvisoryConflict('DECISION_OPERATION_PAYLOAD_CONFLICT')
                if request['kind']=='ARCHITECTURE':
                    business=runtime.repository.decision(business_id)
                    if request['business_decision_id']!=business_id or request['business_decision_digest']!=digest(business):
                        raise AdvisoryConflict('BUSINESS_DECISION_CHANGED')
                    preview,planning=architecture_inputs(request['mission_preview'],request['planning'])
                    bridge._validate_preview(candidate,preview,planning,revision)
                    bridge._require_lifecycle_decision(candidate.recommendation_id,'business_decision',candidate_id,revision,business_id)
                    if (self.checked_receipt(store,runtime,business_id) is None
                            or preview.architecture_review_reference!=architecture_id
                            or business['capability']!='BUSINESS_APPROVAL'
                            or business['installation_id']!=p.installation_id
                            or sorted(business['scope'])!=sorted(candidate.scope)
                            or sorted(business['gates'])!=sorted(planning.human_gates)):
                        raise AdvisoryConflict('BUSINESS_OR_PLANNING_NOT_APPLICABLE')
                intent=old or {'request':request,'request_digest':digest(request),'candidate':candidate.to_dict(),'decision_id':key,'principal_reference':p.reference,'profile_id':p.profile_id,'operator_id':p.operator_id,'operator_binding_version':p.operator_binding_version,'installation_id':p.installation_id,'source_digest':digest(proposal['source']),'admitted_at':datetime.now(UTC).isoformat()}
                intent=store.begin_decision_operation(p.reference,request['operation_id'],key,intent,p.maximum_decisions)
                existing=store.decision_operation_receipt(key)
                if existing is None:
                    def guard():
                        current,*values=self.authority(token,candidate_id,request['kind'],request['subject_revision'])
                        if any(getattr(current,k)!=intent[k] for k in ('profile_id','operator_id','operator_binding_version','installation_id')) or digest(values[-1])!=intent['source_digest']:
                            raise PermissionError('decision actor/source changed before effect')
                    # Runtime canonical evidence commits first. Lifecycle approval and
                    # receipt publish together, so a torn operation cannot satisfy intake.
                    with store.atomic():
                        if request['kind']=='BUSINESS':
                            bridge.approve_business(candidate_id,actor='primary_operator',occurred_at=intent['admitted_at'],rationale=request['rationale'],human_gates=tuple(request['human_gates']),effect_guard=guard)
                        else:
                            bridge.approve_architecture(candidate_id,preview,planning,actor='primary_operator',occurred_at=intent['admitted_at'],rationale=request['rationale'],effect_guard=guard)
                            bridge.approved_envelope(candidate_id,preview,planning)
                        guard()
                        decision=runtime.repository.decision(key)
                        if decision['operator_id']!=p.operator_id or decision['installation_id']!=p.installation_id:
                            raise PermissionError('canonical signer differs from authenticated decider')
                        evidence=next(e for e in store.history(candidate.recommendation_id) if e.kind==request['kind'].lower()+'_decision')
                        store.finish_decision_operation(p.reference,request['operation_id'],key,decision_receipt(intent,decision,evidence))
        result=self.operation(token,candidate_id,request['operation_id']); result['recorded']=existing is None;result['read_only']=False
        return result
    def handle(self,method,target,token,body=None):
        try:
            path=urlsplit(target).path;parts=[unquote(v) for v in path.split('/')]
            if method=='GET' and path=='/v1/candidate-decisions/capability':
                return 200,self.capability(token)
            if len(parts)<4 or parts[:3]!=['','v1','candidate-decisions']:
                raise PermissionError('outside decision namespace')
            candidate=identifier(parts[3])
            if method=='GET' and len(parts)==4:
                return 200,self.detail(token,candidate)
            if method=='POST' and len(parts)==5 and parts[4] in ('business','architecture'):
                if not isinstance(body,dict) or body.get('kind')!=parts[4].upper():
                    raise ValueError('separate typed decision route required')
                return 200,self.decide(token,candidate,body)
            if method=='GET' and len(parts)==6 and parts[4]=='operations':
                return 200,self.operation(token,candidate,parts[5])
            raise PermissionError('outside decision scope')
        except PermissionError:
            status,code=403,'DECISION_SCOPE_DENIED'
        except FileNotFoundError:
            status,code=404,'DECISION_OPERATION_NOT_FOUND'
        except AdvisoryConflict as error:
            status,code=409,error.code
        except RuntimeServiceBusy:
            status,code=409,'DECISION_BUSY_RETRY_SAME_OPERATION'
        except (LifecycleError,ValueError,TypeError,KeyError):
            status,code=409,'DECISION_INPUT_OR_STATE_INVALID'
        except (OSError,RuntimeError,sqlite3.Error):
            status,code=503,'DECISION_UNAVAILABLE'
        return status,{'contract_version':CONTRACT,'error':{'code':code}}
