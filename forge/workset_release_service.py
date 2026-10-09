"""Exact finite release/disarm through existing governed workset services."""
from datetime import UTC, datetime
from pathlib import Path
import json, sqlite3
from .advisory_contract import digest
from .approved_worklist import ApprovedWorklistService, candidate_source, identifier, projection
from .advisory_candidate_contract import hash_reference
from .lifecycle import RecommendationLifecycleStore
from .operations_read_api import InstalledOperationsReadService
from .runtime.service import RuntimeServiceLock, RuntimeServiceBusy
from .workspace_review_grant import _locked
from .worklist_control import control_runtime
from .workset_release_grant import CONTRACT, validate_activation_authority
from .workset_release_journal import ReleaseJournal
from .workset_release_package import prepare, selection

BASE='/v1/approved-workset-releases'


def original_intent_authority(root,intent,reference):
    from .models.criterion_observation import canonical_digest
    package=intent['package']
    validate_activation_authority(root,{'definition':package['definition'],
        'definition_digest':canonical_digest(package['definition']),
        'release_capability':{'grant_id':intent['grant_id'],'principal_reference':reference,
            'package_digest':intent['package_digest'],'subjects':package['selection']['subjects']}})



class WorksetReleaseService:
    def __init__(self,root,grant):self.root=Path(root);self.grant=grant

    def capability(self,token):
        p=self.grant.authorize(token)
        supported={}
        for permission in ('RELEASE','DISARM'):
            try:self.grant.authorize(token,permission);supported[permission]=True
            except PermissionError:supported[permission]=False
        return {'contract_version':CONTRACT,'scope':{k:getattr(p,k) for k in
            ('instance_id','project_id','repository_id')},'principal_id':p.principal_id,
            'permissions':list(p.permissions),'subjects':list(p.subjects),
            'limits':self.grant.allowance(p),'expires_at':p.expires_at,
            'release_supported':supported['RELEASE'],'disarm_supported':supported['DISARM'],
            'read_only':True,'additional_model_calls':0}

    def prepare(self,token,body):
        p=self.grant.authorize(token)
        result=prepare(self.root,self.grant,p,body)
        try:self.grant.authorize(token,'RELEASE')
        except PermissionError:result['gaps'].append({'code':'RELEASE_AUTHORITY_UNAVAILABLE','candidate_id':None})
        package=result['package'];key=package['definition']['workset_id']
        with InstalledOperationsReadService(self.root)._runtime_snapshot() as (db,_):
            for row in db.execute('SELECT document FROM approved_worksets'):
                v=json.loads(row[0])
                if v['release']=='AUTO_WHEN_ELIGIBLE' and not v['revoked'] and v['definition']['workset_id']!=key:
                    result['gaps'].append({'code':'ANOTHER_WORKSET_ARMED','candidate_id':None})
                for s in package['subjects']:
                    if v['claims'].get(s['candidate_id']) and v['definition']['workset_id']!=key:
                        result['gaps'].append({'code':'SUBJECT_ALREADY_CLAIMED','candidate_id':s['candidate_id']})
        result['release_supported']=not result['gaps']
        result['package_digest']=digest(result['package'])
        self.grant.authorize(token)
        return result

    def operation(self,token,operation_id):
        identifier(operation_id);p=self.grant.authorize(token)
        j=ReleaseJournal(self.root,p.reference);d=j.read();o=d['operations'].get(operation_id)
        if o is None:raise FileNotFoundError('unknown scoped release operation')
        intent=d['intents'][o['release_key']];package=intent['package']
        if any(s not in p.subjects for s in package['selection']['subjects']):
            raise PermissionError('release operation outside current subject scope')
        key=package['definition']['workset_id'];value=None
        with InstalledOperationsReadService(self.root)._runtime_snapshot() as (db,_):
            row=db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',(key,)).fetchone()
            if row:value=json.loads(row[0])
        original=(value or {}).get('release_commands',{}).get(o['request']['canonical_operation_id'])
        if value:
            from .models.criterion_observation import canonical_digest
            if value['definition_digest']!=canonical_digest(package['definition']):
                raise RuntimeError('release workset definition changed')
        if original is not None:
            required={'operation_id','intent','package_digest','principal_reference','definition_digest',
                'workset_id','candidate_mission_ids','workset_decisions','effect_boundary',
                'ongoing_work_cancelled','applied_revision','original_release','observed_at'}
            if (not isinstance(original,dict) or set(original)!=required
                    or original['operation_id']!=o['request']['canonical_operation_id']
                    or original['intent']!=o['request']['intent']
                    or original['package_digest']!=intent['package_digest']
                    or original['principal_reference']!=p.reference
                    or original['definition_digest']!=value['definition_digest']
                    or original['workset_id']!=key
                    or original['candidate_mission_ids']!=[s['mission_id'] for s in package['subjects']]
                    or original['workset_decisions']!=value['decisions']
                    or original['effect_boundary']!='FUTURE_SELECTION_ONLY'
                    or original['ongoing_work_cancelled'] is not False
                    or type(original['applied_revision']) is not int
                    or not 1<original['applied_revision']<=value['revision']
                    or original['original_release']!=('AUTO_WHEN_ELIGIBLE' if original['intent']=='release' else 'DISARMED')):
                raise RuntimeError('original release receipt integrity failed')
            from .approved_worklist import timestamp
            timestamp(original['observed_at'])
        current=projection(self.root,p.instance_id,key,p.principal_id) if value else None
        self.grant.authorize(token)
        return {'contract_version':CONTRACT,'operation_id':operation_id,
            'state':'COMPLETE' if original else 'PENDING','original_receipt':original,
            'original_request':{k:v for k,v in o['request'].items() if k!='canonical_operation_id'},
            'frozen_package':package,'package_digest':intent['package_digest'],
            'workset_id':key,'current':current,'read_only':True,
            'execution_resources':'NOT_OBSERVED','execution_ready':False,'additional_model_calls':0}

    def execute(self,token,body):
        fields={'contract_version','operation_id','intent','selection','package_digest','confirm','expected_revision'}
        if (not isinstance(body,dict) or set(body)!=fields or body['contract_version']!=CONTRACT
                or body['confirm'] is not True or body['intent'] not in ('release','disarm')):
            raise ValueError('exact explicit release/disarm confirmation required')
        identifier(body['operation_id']);hash_reference(body['package_digest']);selection(body['selection'])
        if body['intent']=='release' and body['expected_revision'] is not None:
            raise ValueError('release targets the immutable prepared package')
        if body['intent']=='disarm' and (type(body['expected_revision']) is not int or body['expected_revision']<1):
            raise ValueError('disarm requires exact current workset revision')
        permission='RELEASE' if body['intent']=='release' else 'DISARM'
        p=self.grant.authorize(token,permission);j=ReleaseJournal(self.root,p.reference)
        # Locks cover only bounded local effects, never provider/EP waits.
        with RuntimeServiceLock(self.root/'forge.db').acquire(),_locked(self.grant.path),_locked(j.path):
            p=self.grant.authorize(token,permission);d=j.read()
            prior=d['operations'].get(body['operation_id'])
            if prior:
                if prior['request']!={**body,'canonical_operation_id':prior['request']['canonical_operation_id']}:
                    raise ValueError('release operation payload conflict')
                key=prior['release_key'];intent=d['intents'][key]
            else:
                if len(d['operations'])>=128:raise ValueError('release operation capacity exhausted')
                # A later disarm must bind the originally confirmed immutable
                # package even if current runtime status/context has advanced.
                existing=next((i for i in d['intents'].values() if i['package_digest']==body['package_digest']),None)
                if existing:
                    if body['selection']!=existing['package']['selection']:
                        raise ValueError('release selection changed')
                    intent=existing;key=intent['package']['release_key']
                    if body['intent']=='release':original_intent_authority(self.root,intent,p.reference)
                else:
                    if body['intent']=='disarm':raise ValueError('no original release to disarm')
                    prepared=self.prepare(token,body['selection'])
                    if not prepared['release_supported'] or prepared['package_digest']!=body['package_digest']:
                        raise ValueError('release package changed or blocked')
                    package=prepared['package'];key=package['release_key']
                    limits=self.grant.allowance(p)
                    if (len(d['intents'])>=limits['maximum_releases']
                            or sum(i['package']['definition']['maximum_activations'] for i in d['intents'].values())+
                            package['definition']['maximum_activations']>limits['maximum_activations']):
                        raise ValueError('retained release/activation allowance exhausted')
                    intent={'package':package,'package_digest':body['package_digest'],'grant_id':p.grant_id,
                        'operation_id':body['operation_id'],'created_at':datetime.now(UTC).isoformat()}
                    d['intents'][key]=intent
                alias=next((v for v in d['operations'].values() if v['release_key']==key
                    and {k:v['request'][k] for k in body if k!='operation_id'}==
                        {k:body[k] for k in body if k!='operation_id'}),None)
                canonical=alias['request']['canonical_operation_id'] if alias else body['operation_id']
                request={**body,'canonical_operation_id':canonical}
                d['operations'][body['operation_id']]={'request':request,'request_digest':digest(request),'release_key':key}
                j.save(d)  # Durable exact intent before the first canonical effect.
            package=intent['package'];workset_id=package['definition']['workset_id']
            canonical=d['operations'][body['operation_id']]['request']['canonical_operation_id']
            with control_runtime(self.root) as runtime,RecommendationLifecycleStore(candidate_source(self.root)) as store:
                service=ApprovedWorklistService(runtime,store)
                def guard():
                    current=self.grant.authorize(token,permission)
                    if (current.reference!=p.reference or any(s not in current.subjects for s in package['selection']['subjects'])):
                        raise PermissionError('release principal/subject drift')
                    from .workset_release_subjects import approved_subject
                    for s in package['selection']['subjects']:
                        approved_subject(self.root,package['scope'],**s)
                    if body['intent']=='release':
                        original_intent_authority(self.root,intent,p.reference)
                        existing=service.db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',(workset_id,)).fetchone()
                        if existing and json.loads(existing[0])['held']:
                            raise ValueError('original workset is held')
                        if existing and any(c['intent']=='disarm' for c in json.loads(existing[0]).get('release_commands',{}).values()):
                            raise PermissionError('future release withdrawn before completion')
                        fresh=prepare(self.root,self.grant,current,package['selection'])
                        if fresh['package_digest']!=intent['package_digest']:
                            raise ValueError('frozen release subject/source/planning drift')
                row=service.db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',(workset_id,)).fetchone()
                value=service._get(workset_id) if row else None
                original=(value or {}).get('release_commands',{}).get(canonical)
                if original is None:
                    guard()
                    if body['intent']=='release':
                        value=service.propose(package['definition'],effect_guard=guard,reuse_current=True)
                        authority={'grant_id':intent['grant_id'],'principal_reference':p.reference,
                            'package_digest':intent['package_digest'],'subjects':package['selection']['subjects']}
                        if value.get('release_capability') not in (None,authority):raise ValueError('original release capability changed')
                        if value.get('release_capability') is None:
                            value['release_capability']=authority;guard();value=service._save(value,value['revision'])
                        for role in ('business','architecture'):
                            value=service.decide(workset_id,expected_revision=value['revision'],role=role,
                                actor='primary_operator',effect_guard=guard,reuse_current=True)
                        expected=value['revision'];operation='arm'
                    else:
                        if value is None:raise ValueError('original workset unavailable')
                        expected=body['expected_revision'];operation='disarm'
                    guard()
                    value=service._control_locked(workset_id,expected_revision=expected,operation=operation,
                        release_operation={'operation_id':canonical,'intent':body['intent'],
                            'package_digest':intent['package_digest'],'principal_reference':p.reference,
                            'definition_digest':value['definition_digest'],'workset_id':workset_id,
                            'candidate_mission_ids':[s['mission_id'] for s in package['subjects']],
                            'workset_decisions':dict(value['decisions']),'effect_boundary':'FUTURE_SELECTION_ONLY',
                            'ongoing_work_cancelled':False},effect_guard=guard)
        return self.operation(token,body['operation_id'])

    def handle(self,method,path,token,body=None):
        try:
            self.grant.authorize(token)
            if method=='GET' and path==BASE+'/capability':return 200,self.capability(token)
            if method=='POST' and path==BASE+'/prepare':return 200,self.prepare(token,body)
            if method=='POST' and path==BASE+'/commands':return 200,self.execute(token,body)
            prefix=BASE+'/operations/'
            if method=='GET' and path.startswith(prefix) and '/' not in path[len(prefix):]:
                return 200,self.operation(token,path[len(prefix):])
            return 403,{'contract_version':CONTRACT,'error':{'code':'RELEASE_SCOPE_DENIED'}}
        except PermissionError:return 403,{'contract_version':CONTRACT,'error':{'code':'RELEASE_SCOPE_DENIED'}}
        except FileNotFoundError:return 404,{'contract_version':CONTRACT,'error':{'code':'RELEASE_OPERATION_NOT_FOUND'}}
        except RuntimeServiceBusy:return 503,{'contract_version':CONTRACT,'error':{'code':'RELEASE_BUSY'}}
        except (ValueError,KeyError,TypeError) as error:
            codes={'current owner-published observation receipt required':'RELEASE_SOURCE_OBSERVATION_REQUIRED',
                'one current owner-published repository revision required':'RELEASE_REPOSITORY_CONTEXT_REQUIRED',
                'retained release/activation allowance exhausted':'RELEASE_ALLOWANCE_EXHAUSTED',
                'original workset is held':'RELEASE_WORKSET_HELD'}
            return 409,{'contract_version':CONTRACT,'error':{'code':codes.get(str(error),'RELEASE_CONFLICT')}}
        except (OSError,RuntimeError,sqlite3.Error):return 503,{'contract_version':CONTRACT,'error':{'code':'RELEASE_UNAVAILABLE'}}
