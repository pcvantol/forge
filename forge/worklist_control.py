"""Scoped durable hold intents over the existing workset and runtime mutation lease."""
from contextlib import contextmanager
from datetime import UTC, datetime
import json
import sqlite3
from .approved_worklist import ApprovedWorklistService, candidate_source, identifier, projection, timestamp
from .models.criterion_observation import canonical_digest
from .operations_read_api import InstalledOperationsReadService
from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
from .runtime.service import RuntimeServiceLock, RuntimeServiceBusy
from .lifecycle import RecommendationLifecycleStore
from .workspace_review_grant import _locked
from .workspace_worklist_control_grant import current_operator

REQUEST='forge-worklist-control-request/v1'
RECEIPT='forge-worklist-control-receipt/v1'
READBACK='forge-worklist-control-readback/v1'
ERROR='forge-worklist-control-error/v1'

class ControlConflict(ValueError):
    pass

@contextmanager
def control_runtime(root):
    """Canonical mutating governance composition, with no provider/host adapters."""
    from .runtime.bootstrap import RuntimeBootstrap
    from .governance_authority import CanonicalGovernanceRepository
    from .runtime.dynamic_mission import MacOSGeneratedUIDIdentityAdapter
    from ._version import canonical_version
    database=RuntimeBootstrap(data_root=root,forge_version=canonical_version()).open()
    try:
        repository=CanonicalGovernanceRepository.for_runtime(database,MacOSGeneratedUIDIdentityAdapter().resolve,data_root=root)
        yield InstalledDynamicMissionRuntime(database,repository,data_root=str(root),provider=None,host=None)
    finally:database.close()

def canonical_request(body):
    fields={'contract_version','operation_id','intent','instance_id','workset_id','definition_revision',
            'expected_revision','hold_operation_id','expected_hold_revision','reason_code'}
    if not isinstance(body,dict) or set(body)!=fields or body['contract_version']!=REQUEST:
        raise ValueError('invalid command shape')
    for key in ('operation_id','instance_id','workset_id'):identifier(body[key])
    digest=body['definition_revision']
    if not isinstance(digest,str) or not digest.startswith('sha256:') or len(digest)!=71 or any(c not in '0123456789abcdef' for c in digest[7:]):
        raise ValueError('invalid definition revision')
    if type(body['expected_revision']) is not int or body['expected_revision']<1:
        raise ValueError('invalid expected revision')
    if (not isinstance(body['intent'],str) or not isinstance(body['reason_code'],str)
            or body['intent'] not in {'hold','unhold'} or body['reason_code'] not in {'USER_REQUEST','TEMPORARY_WAIT'}):
        raise ValueError('unsupported intent or reason')
    if body['intent']=='hold':
        if body['hold_operation_id'] is not None or body['expected_hold_revision'] is not None:
            raise ValueError('hold must not target another hold')
    else:
        identifier(body['hold_operation_id'])
        if type(body['expected_hold_revision']) is not int or body['expected_hold_revision']<1:
            raise ValueError('unhold requires exact hold revision')
    return json.loads(json.dumps(body,sort_keys=True))

def control_state(value, principal, admitted_mission_ids=None):
    hold=value.get('operator_hold')
    if (type(value['held']) is not bool or type(value['revision']) is not int or value['revision']<1
            or type(value.get('control_revision',0)) is not int or value.get('control_revision',0)<0
            or not isinstance(value['claims'],dict)):
        raise RuntimeError('invalid current control state')
    if hold is not None and (not isinstance(hold,dict)
            or set(hold)!={'principal_reference','operation_id','reason_code','control_revision'}
            or not isinstance(hold['principal_reference'],str) or not hold['principal_reference']
            or len(hold['principal_reference'])>400 or not value['held']
            or type(hold['control_revision']) is not int or hold['control_revision']<1
            or hold['control_revision']!=value.get('control_revision',0)
            or not isinstance(hold['reason_code'],str)
            or hold['reason_code'] not in {'USER_REQUEST','TEMPORARY_WAIT','OWNER_REQUEST'}):
        raise RuntimeError('invalid hold provenance')
    if hold is not None:
        try:identifier(hold['operation_id'])
        except ValueError as error:raise RuntimeError('invalid current hold identity') from error
    return {'instance_id':principal.instance_id,'workset_id':value['definition']['workset_id'],
            'definition_revision':value['definition_digest'],'workset_revision':value['revision'],
            'control_revision':value.get('control_revision',0),'held':value['held'],
            'hold':({'operation_id':hold['operation_id'],'control_revision':hold['control_revision'],
                     'reason_code':hold['reason_code'],'owned_by_principal':hold['principal_reference']==principal.reference}
                    if hold else None),
            'hold_provenance':'RECORDED' if hold else 'LEGACY_UNKNOWN' if value['held'] else 'NONE',
            'admitted_mission_ids':sorted(admitted_mission_ids if admitted_mission_ids is not None else
                (c['mission_id'] for c in value['claims'].values() if c.get('mission_id'))),
            'boundary':'FUTURE_ADMISSION_ONLY','ongoing_work_cancelled':False,
            'observed_at':datetime.now(UTC).isoformat()}

def finish_operation(value, operation):
    """Effect and original receipt are committed atomically in the same workset row."""
    principal=operation['principal']
    request=operation['request']
    state=control_state({**value,'revision':value['revision']+1},principal,operation['admitted_mission_ids'])
    receipt={'contract_version':RECEIPT,'operation_id':request['operation_id'],
             'principal_id':principal.principal_id,'grant_id':principal.grant_id,
             'request':request,'request_digest':canonical_digest(request),'outcome':'APPLIED',
             'effect':state,'only_target_hold_removed':request['hold_operation_id'] if request['intent']=='unhold' else None}
    stored=value['control_operations'][request['operation_id']]
    stored['state']='APPLIED';stored['admission_bindings']=operation['admission_bindings']
    stored['receipt']=receipt;stored['receipt_digest']=canonical_digest(receipt)

def _validated_receipt(value, stored, request, principal, canonical_bindings):
    receipt=stored['receipt'];effect=receipt['effect']
    repeated=canonical_request(receipt['request'])
    if canonical_digest(repeated)!=stored['request_digest']:raise RuntimeError('receipt repeated request bytes failed')
    fields={'contract_version','operation_id','principal_id','grant_id','request','request_digest','outcome','effect','only_target_hold_removed'}
    effect_fields={'instance_id','workset_id','definition_revision','workset_revision','control_revision','held','hold',
                   'hold_provenance','admitted_mission_ids','boundary','ongoing_work_cancelled','observed_at'}
    if (not isinstance(receipt,dict) or set(receipt)!=fields or receipt['contract_version']!=RECEIPT
            or receipt['outcome']!='APPLIED' or not isinstance(effect,dict) or set(effect)!=effect_fields
            or receipt['request']!=request or receipt['request_digest']!=stored['request_digest']
            or receipt['operation_id']!=request['operation_id'] or receipt['grant_id']!=principal.grant_id
            or receipt['principal_id']!=principal.principal_id or effect['instance_id']!=principal.instance_id
            or effect['workset_id']!=request['workset_id'] or effect['definition_revision']!=request['definition_revision']):
        raise RuntimeError('receipt shape or authority binding failed')
    if (type(effect['workset_revision']) is not int or effect['workset_revision']!=stored['intent_revision']+1
            or type(effect['control_revision']) is not int or effect['control_revision']!=stored['control_revision_before']+1
            or effect['held'] is not (request['intent']=='hold') or effect['boundary']!='FUTURE_ADMISSION_ONLY'
            or effect['ongoing_work_cancelled'] is not False):
        raise RuntimeError('receipt original effect or revision failed')
    expected_hold=({'operation_id':request['operation_id'],'control_revision':effect['control_revision'],
                    'reason_code':request['reason_code'],'owned_by_principal':True} if request['intent']=='hold' else None)
    if (effect['hold']!=expected_hold or (expected_hold is not None
            and (type(effect['hold'].get('owned_by_principal')) is not bool
                 or type(effect['hold'].get('control_revision')) is not int))
            or effect['hold_provenance']!=('RECORDED' if expected_hold else 'NONE')
            or receipt['only_target_hold_removed']!=request['hold_operation_id']):
        raise RuntimeError('receipt hold provenance failed')
    if not isinstance(effect['observed_at'],str) or len(effect['observed_at'])>64:raise RuntimeError('invalid effect observation')
    timestamp(effect['observed_at'])
    references=stored['admission_bindings'];members={m['candidate_id']:m for m in value['definition']['members']}
    if not isinstance(references,list) or len(references)>len(members):raise RuntimeError('invalid original admission bindings')
    ids=[];seen=set()
    for ref in references:
        if (not isinstance(ref,dict) or set(ref)!={'kind','candidate_id','subject_revision','mission_id','installation_id','envelope_digest'}
                or ref['kind']!='CANONICAL_CANDIDATE_INTAKE' or ref['candidate_id'] not in members
                or ref['candidate_id'] in seen or ref['subject_revision']!=members[ref['candidate_id']]['subject_revision']
                or ref['installation_id']!=value['installation_id']
                or ref not in canonical_bindings):raise RuntimeError('unproven original canonical admission binding')
        identifier(ref['mission_id']);canonical_request({**request,'definition_revision':ref['envelope_digest']})
        ids.append(ref['mission_id']);seen.add(ref['candidate_id'])
    if (not isinstance(effect['admitted_mission_ids'],list) or effect['admitted_mission_ids']!=sorted(ids)
            or len(set(ids))!=len(ids)):raise RuntimeError('receipt original admission set failed')


def _operation(value, operation_id, principal, canonical_bindings=()):
    stored=value.get('control_operations',{}).get(operation_id)
    if stored is None:return None
    if stored['principal_reference']!=principal.reference:
        raise PermissionError('command belongs to another grant principal')
    try:
        request=canonical_request(stored['request'])
        required={'request','request_digest','principal_reference','state','intent_revision','control_revision_before','hold_before'}
        if stored['state']=='APPLIED':required|={'receipt','receipt_digest','admission_bindings'}
        if (set(stored)!=required or stored['state'] not in {'PENDING','APPLIED'}
                or stored['request_digest']!=canonical_digest(request) or request['operation_id']!=operation_id
                or request['instance_id']!=principal.instance_id or request['workset_id']!=value['definition']['workset_id']
                or request['definition_revision']!=value['definition_digest']
                or type(stored['intent_revision']) is not int or stored['intent_revision']!=request['expected_revision']+1
                or type(stored['control_revision_before']) is not int or stored['control_revision_before']<0):
            raise RuntimeError('intent integrity or original revision failed')
        before=stored['hold_before']
        if request['intent']=='hold':
            if before is not None:raise RuntimeError('hold intent has another prior hold')
        elif (not isinstance(before,dict) or set(before)!={'principal_reference','operation_id','reason_code','control_revision'}
                or before['principal_reference']!=principal.reference or before['operation_id']!=request['hold_operation_id']
                or type(before['control_revision']) is not int or before['control_revision']!=request['expected_hold_revision']
                or before['control_revision']!=stored['control_revision_before']
                or before['reason_code'] not in {'USER_REQUEST','TEMPORARY_WAIT'}):
            raise RuntimeError('unhold intent original target failed')
        if stored['state']=='APPLIED':
            if stored['receipt_digest']!=canonical_digest(stored['receipt']):raise RuntimeError('receipt integrity failed')
            _validated_receipt(value,stored,request,principal,canonical_bindings)
    except (ValueError,KeyError,TypeError,AttributeError) as error:
        raise RuntimeError('invalid persisted command proof') from error
    return stored

def _validate_effect(value, request, principal, expected):
    control_state(value,principal)
    if value['definition_digest']!=request['definition_revision'] or value['revision']!=expected:
        raise ControlConflict('stale workset revision')
    hold=value.get('operator_hold')
    if request['intent']=='hold':
        if value['held']:raise ControlConflict('another hold already exists')
    elif (not value['held'] or not hold or hold['principal_reference']!=principal.reference
          or hold['operation_id']!=request['hold_operation_id']
          or hold['control_revision']!=request['expected_hold_revision']):
        raise ControlConflict('target hold provenance changed')

class WorklistControlService:
    def __init__(self, root, grant, provider_id):
        self.root,self.grant,self.provider_id=root,grant,provider_id

    def _authorize(self, authorization, key):
        principal=self.grant.authenticate(authorization)
        if principal is None:raise PermissionError('control grant is unavailable')
        if key not in principal.workset_ids:raise PermissionError('foreign workset')
        current_operator(self.root,principal.instance_id)
        return principal

    def read(self, authorization, key, operation_id=None):
        identifier(key)
        if operation_id is not None:identifier(operation_id)
        with _locked(self.grant.path):
            principal=self._authorize(authorization,key)
            # Canonical projection validates instance/installation and definition integrity.
            snapshot=projection(self.root,principal.instance_id,key,principal.principal_id)
            with InstalledOperationsReadService(self.root)._runtime_snapshot() as (db,metadata):
                row=db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',(key,)).fetchone()
                value=json.loads(row[0])
            if value['revision']!=snapshot['workset_revision']:
                raise RuntimeError('readback changed during observation')
            stored=_operation(value,operation_id,principal,[i['allocation_binding'] for i in snapshot['items'] if i['allocation_binding']]) if operation_id else None
            return {'contract_version':READBACK,'principal_id':principal.principal_id,'read_only':True,
                    'operation':({'state':stored['state'],'original_receipt':stored.get('receipt'),
                                  'operation_id':operation_id,'execution_known':stored['state']=='APPLIED'} if stored else None),
                    'current':control_state(value,principal,[i['mission_id'] for i in snapshot['items'] if i['allocation_binding']]),'worklist':snapshot}

    def execute(self, authorization, key, body):
        request=canonical_request(body)
        # Deny scope and live authority before composing any mutating database.
        # Keep the grant lease through commit; canonical runtime leases are nonblocking.
        with _locked(self.grant.path):
            principal=self._authorize(authorization,key)
            if request['instance_id']!=principal.instance_id or request['workset_id']!=key:
                raise PermissionError('command instance or workset mismatch')
            with control_runtime(self.root) as runtime,RuntimeServiceLock(runtime.database.path).acquire(reuse_current=True):
                principal=self._authorize(authorization,key)
                with RecommendationLifecycleStore(candidate_source(self.root)) as lifecycle:
                    service=ApprovedWorklistService(runtime,lifecycle);value=service._get(key)
                    if value['runtime_generation']!=runtime.database._connection.execute('SELECT dataset_generation FROM operational_reset_state WHERE singleton=1').fetchone()[0]:
                        raise ControlConflict('workset generation changed')
                    current_snapshot=projection(self.root,principal.instance_id,key,principal.principal_id)
                    stored=_operation(value,request['operation_id'],principal,[i['allocation_binding'] for i in current_snapshot['items'] if i['allocation_binding']])
                    if stored is not None:
                        if stored['request']!=request:raise ControlConflict('operation payload conflict')
                        if stored['state']=='APPLIED':return stored['receipt'],False
                        expected=stored['intent_revision']
                    else:
                        _validate_effect(value,request,principal,request['expected_revision'])
                        if len(value.get('control_operations',{}))>=64:raise ControlConflict('command history capacity exhausted')
                        stored={'request':request,'request_digest':canonical_digest(request),
                                'principal_reference':principal.reference,'state':'PENDING',
                                'intent_revision':value['revision']+1,'control_revision_before':value.get('control_revision',0),
                                'hold_before':value.get('operator_hold')}
                        value.setdefault('control_operations',{})[request['operation_id']]=stored
                        value=service._save(value,value['revision']);expected=value['revision']
                    # Recheck all live authority and exact provenance immediately before effect.
                    principal=self._authorize(authorization,key)
                    value=service._get(key);_validate_effect(value,request,principal,expected)
                    provenance={'principal_reference':principal.reference,'operation_id':request['operation_id'],
                                'reason_code':request['reason_code']}
                    snapshot=projection(self.root,principal.instance_id,key,principal.principal_id)
                    value=service._control_locked(key,expected_revision=expected,operation=request['intent'],
                        hold_provenance=provenance,command_operation={'principal':principal,'request':request,
                            'admitted_mission_ids':[i['mission_id'] for i in snapshot['items'] if i['allocation_binding']],
                            'admission_bindings':[i['allocation_binding'] for i in snapshot['items'] if i['allocation_binding']]})
                    return value['control_operations'][request['operation_id']]['receipt'],True

    def handle(self, method, path, authorization, body):
        parts=path.split('/')
        if (len(parts) not in {4,5,6} or parts[:3]!=['','v1','workset-controls']
                or (len(parts)>4 and parts[4]!='commands')):
            return 403,{'contract_version':ERROR,'error':{'code':'CONTROL_SCOPE_DENIED'}}
        key=parts[3]
        try:
            if method=='GET' and len(parts) in {4,6}:
                value=self.read(authorization,key,parts[5] if len(parts)==6 else None)
                return (404 if len(parts)==6 and value['operation'] is None else 200),value
            if method=='POST' and len(parts)==5:
                receipt,recorded=self.execute(authorization,key,body)
                return 200,{'contract_version':READBACK,'original_receipt':receipt,'recorded':recorded,
                            'current_readback':self.read(authorization,key,receipt['operation_id'])}
            return 403,{'contract_version':ERROR,'error':{'code':'CONTROL_SCOPE_DENIED'}}
        except PermissionError:return 403,{'contract_version':ERROR,'error':{'code':'CONTROL_AUTHORITY_DENIED'}}
        except (ControlConflict,RuntimeServiceBusy):return 409,{'contract_version':ERROR,'error':{'code':'CONTROL_CONFLICT'}}
        except ValueError:return 400,{'contract_version':ERROR,'error':{'code':'CONTROL_REQUEST_INVALID'}}
        except (OSError,RuntimeError,sqlite3.Error,KeyError,TypeError,AttributeError):
            return 503,{'contract_version':ERROR,'error':{'code':'CONTROL_SOURCE_UNAVAILABLE'}}
