"""Explicit user-authored Candidate fields and immutable advice provenance."""
from .advisory_contract import digest,text,AdvisoryConflict
from .approved_worklist import identifier
from .models.mission_effect import MissionEffectPolicy
from .lifecycle import MissionCandidate,MissionRecommendation

CONTRACT='forge-advisory-candidate/v1'

def revision(value):
    if type(value) is not int or value<0:raise ValueError('invalid revision')
    return value

def hash_reference(value):
    if not isinstance(value,str) or len(value)!=71 or not value.startswith('sha256:') or any(c not in '0123456789abcdef' for c in value[7:]):raise ValueError('invalid digest')
    return value

def exact(value,fields):
    if not isinstance(value,dict) or set(value)!=set(fields.split()) or value.get('contract_version')!=CONTRACT:raise ValueError('closed Candidate contract required')
    return value

def fields(value):
    names='title objective business_value engineering_value architectural_value rationale confidence scope exclusions acceptance_criteria architecture_constraints dependencies effect_policy'
    if not isinstance(value,dict) or set(value)!=set(names.split()):raise ValueError('explicit structured fields required')
    for k in ['title','objective','business_value','engineering_value','architectural_value','rationale']:text(value[k],1000 if k!='title' else 256)
    if type(value['confidence']) is not int or not 0<=value['confidence']<=100:raise ValueError('explicit confidence required')
    for k in ['scope','exclusions','acceptance_criteria','architecture_constraints','dependencies']:
        a=value[k]
        if not isinstance(a,list) or len(a)>8 or len(a)!=len(set(a)):raise ValueError('bounded unique fields required')
        for v in a:text(v,1000)
    if not value['scope'] or not value['acceptance_criteria'] or any(len(v.strip())<20 for v in value['acceptance_criteria']):raise ValueError('substantive scope and criteria required')
    policy=MissionEffectPolicy.from_dict(value['effect_policy'])
    if policy.mode in {'DOCUMENTATION_ONLY','ARCHITECTURE_DESIGN_ONLY'} and any(v.endswith('/') for v in policy.write_paths):raise ValueError('document proposals require exact document paths')
    return value

def proposal_request(value):
    exact(value,'contract_version instance_id project_id repository_id conversation_id proposal_id turn_id expected_revision expected_conversation_revision context_revision fields')
    for k in ['instance_id','project_id','repository_id','conversation_id','proposal_id','turn_id']:identifier(value[k])
    revision(value['expected_revision']);revision(value['expected_conversation_revision']);hash_reference(value['context_revision']);fields(value['fields'])
    return value

def registration_request(value):
    exact(value,'contract_version operation_id instance_id project_id repository_id conversation_id proposal_id proposal_revision proposal_digest expected_conversation_revision context_revision confirm')
    for k in ['operation_id','instance_id','project_id','repository_id','conversation_id','proposal_id']:identifier(value[k])
    if revision(value['proposal_revision'])<1:raise ValueError('proposal revision required')
    revision(value['expected_conversation_revision']);hash_reference(value['proposal_digest']);hash_reference(value['context_revision'])
    if value['confirm'] is not True:raise ValueError('explicit confirmation required')
    return value

def candidate_objects(proposal,key,occurred_at):
    """Only declared user fields populate the existing governance models."""
    if proposal.get('contract_version') == 'forge-chat-first-mission/v1':
        from .mission_concept_registration import candidate_objects as generated_objects
        return generated_objects(proposal,key,occurred_at)
    f=fields(proposal['fields']);source=proposal['source'];rec_id='advice-recommendation-'+key[7:39];can_id='advice-candidate-'+key[7:39]
    rec=MissionRecommendation(id=rec_id,title=f['title'],mission_origin=source['advisor_kind'].lower(),
        business_summary=f['objective'],engineering_summary=f['objective'],business_value=f['business_value'],
        engineering_value=f['engineering_value'],architectural_value=f['architectural_value'],
        repository_evidence=tuple(source['evidence_references']),decision_evidence_reference=source['result_digest'],
        dependencies=tuple(f['dependencies']),alternatives=(),confidence=f['confidence'],recommendation_timestamp=occurred_at,
        known_constraints=tuple(f['exclusions']),evidence_references=(source['request_digest'],source['context_revision']))
    candidate=MissionCandidate(id=can_id,recommendation_id=rec.id,title=f['title'],objective=f['objective'],
        scope=tuple(f['scope']),acceptance_criteria=tuple(f['acceptance_criteria']),
        architecture_constraints=tuple(f['architecture_constraints'])+tuple('EXCLUDED: '+v for v in f['exclusions']),
        dependencies=tuple(f['dependencies']),effect_policy=MissionEffectPolicy.from_dict(f['effect_policy']))
    return rec,candidate

def registration_key(principal,proposal):
    return digest([principal,proposal['project_id'],proposal['repository_id'],proposal['conversation_id'],proposal['proposal_id'],proposal['proposal_revision']])

def registration_receipt(principal,operation_id,key,proposal,occurred_at):
    if proposal.get('contract_version') == 'forge-chat-first-mission/v1':
        from .mission_concept_registration import registration_receipt as generated_receipt
        return generated_receipt(principal,operation_id,key,proposal,occurred_at)
    from .approved_worklist import timestamp
    timestamp(occurred_at)
    if proposal['principal_reference']!=principal or registration_key(principal,proposal)!=key:raise ValueError('registration correlation differs')
    rec,can=candidate_objects(proposal,key,occurred_at)
    return {'contract_version':CONTRACT,'operation_id':identifier(operation_id),'principal_reference':principal,'registration_key':key,'proposal_digest':proposal['proposal_digest'],'proposal_revision':proposal['proposal_revision'],'source':proposal['source'],'candidate':can.to_dict(),'recommendation_id':rec.id,'candidate_digest':digest(can.to_dict()),'recommendation_digest':digest(rec.to_dict()),'registered_at':occurred_at,'status_at_registration':'RECOMMENDED','rationale':proposal['fields']['rationale']}
