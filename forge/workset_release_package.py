"""Closed finite selection and exact human-visible approved workset package."""
from datetime import UTC, datetime
from .advisory_contract import digest
from .approved_worklist import CONTRACT as WORKSET, identifier, timestamp
from .advisory_candidate_contract import hash_reference
from .workset_release_grant import CONTRACT
from .workset_release_subjects import approved_subject, repository_truth
from .governed_continuation import PROFILE_DEFINITION_REVISION, PROGRESSION_POLICY_REVISION


def selection(body):
    fields={'contract_version','subjects','expires_at','maximum_activations','progression_mode'}
    if not isinstance(body,dict) or set(body)!=fields or body['contract_version']!=CONTRACT:
        raise ValueError('closed approved workset selection required')
    if (not isinstance(body['subjects'],list) or not 1<=len(body['subjects'])<=16
            or type(body['maximum_activations']) is not int
            or not 1<=body['maximum_activations']<=len(body['subjects'])
            or body['progression_mode'] not in ('continuous','after_action')):
        raise ValueError('finite workset and explicit progression choice required')
    timestamp(body['expires_at']);seen=set()
    for s in body['subjects']:
        if not isinstance(s,dict) or set(s)!={'candidate_id','subject_revision'}:
            raise ValueError('exact approved subject selection required')
        identifier(s['candidate_id']);hash_reference(s['subject_revision'])
        if s['candidate_id'] in seen:raise ValueError('duplicate selected subject')
        seen.add(s['candidate_id'])
    return body


def prepare(root,grant,principal,body):
    request=selection(body);limits=grant.allowance(principal)
    if (not datetime.now(UTC)<timestamp(request['expires_at'])<=timestamp(principal.expires_at)
            or request['maximum_activations']>limits['maximum_activations']):
        raise ValueError('release expiry/activation ceiling exceeded')
    if any(s not in principal.subjects for s in request['subjects']):
        raise PermissionError('selection outside explicit release subject scope')
    scope={k:getattr(principal,k) for k in ('instance_id','project_id','repository_id')}
    subjects=[approved_subject(root,scope,**s,profile_id=principal.profile_id) for s in request['subjects']]
    truth=repository_truth(root,scope)
    members=[];included=[];gaps=[]
    for subject in subjects:
        dependencies=[d['candidate_id'] for d in subject['dependency_bindings']]
        for d in subject['dependency_bindings']:
            prior=next((s for s in subjects if s['candidate_id']==d['candidate_id']),None)
            if prior is None:gaps.append({'code':'PREDECESSOR_NOT_SELECTED','candidate_id':d['candidate_id']})
            elif prior['subject_revision']!=d['subject_revision']:gaps.append({'code':'DEPENDENCY_SUBJECT_CHANGED','candidate_id':d['candidate_id']})
            elif d['candidate_id'] not in included:gaps.append({'code':'DEPENDENCY_ORDER_CONFLICT','candidate_id':d['candidate_id']})
        members.append({'candidate_id':subject['candidate_id'],'subject_revision':subject['subject_revision'],
            'mission':subject['mission'],'planning':subject['planning'],'dependencies':dependencies,'truth':truth,
            'progression_policy':{'profile_id':principal.profile_id,'profile_revision':PROFILE_DEFINITION_REVISION,
                'policy_revision':PROGRESSION_POLICY_REVISION,'mode':request['progression_mode'],
                'required_decision_role':'platform_architect','higher_scope_obligations':subject['planning']['human_gates']}})
        included.append(subject['candidate_id'])
    semantic={**scope,'principal_reference':principal.reference,'selection':request,
        'members':members,'operator_binding':{k:getattr(principal,k) for k in
            ('installation_id','operator_id','operator_binding_version')},'candidate_decisions':
        [{k:s['candidate_decisions'][k]['canonical_decision_digest'] for k in ('business','architecture')} for s in subjects]}
    key=digest(semantic);definition={'contract_version':WORKSET,'workset_id':'released-'+key[7:47],
        'profile_id':principal.profile_id,'expires_at':request['expires_at'],
        'maximum_activations':request['maximum_activations'],'members':members}
    package={'contract_version':CONTRACT,'release_key':key,'scope':scope,
        'principal_reference':principal.reference,'operator_binding':semantic['operator_binding'],
        'selection':request,'definition':definition,'subjects':subjects,'gaps':gaps,
        'effect_boundary':'FUTURE_SELECTION_ONLY','ongoing_work_cancelled':False,
        'execution_resources':'NOT_OBSERVED','execution_ready':False,'additional_model_calls':0}
    return {'contract_version':CONTRACT,'package':package,'package_digest':digest(package),
        'release_supported':not gaps,'gaps':gaps,'read_only':True,'additional_model_calls':0}
