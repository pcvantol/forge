"""Exact, governed finite selectors over canonical Candidate Intake.

This store adds release/selection facts, never a second allocator or planner.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from .governance import GovernanceRole, resolve_governance_profile
from .governance_authority import GovernanceCapability, GovernanceDecision, ArchitecturePlanningEvidence
from .governed_candidate_intake import GovernedCandidateIntake
from .models.architecture_mission import ArchitectureMission
from .models.criterion_observation import canonical_digest
from .governance_authority import _digest as governance_digest
from .lifecycle import RecommendationLifecycleStore
from .runtime.service import RuntimeServiceLock

CONTRACT = 'forge-approved-worklist/v1'
READ_CONTRACT = 'forge-workspace-worklist/v1'
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z')


def identifier(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('invalid worklist identity')
    from .operations_read_api import _redact
    if _redact(value)!=value:raise ValueError('unsafe worklist identity')
    return value


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError('timestamp must be a string')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp requires timezone')
    return result.astimezone(UTC)


class ApprovedWorklistService:
    """Single-runtime governed workset definition and release service."""
    def __init__(self, runtime, lifecycle: RecommendationLifecycleStore):
        source=Path(lifecycle._connection.execute('PRAGMA database_list').fetchone()[2]).resolve()
        if source!=(Path(runtime.data_root)/'governance'/'candidates.sqlite').resolve():
            raise ValueError('worklist requires the canonical instance Candidate aggregate')
        self.runtime, self.lifecycle = runtime, lifecycle
        self.db = runtime.database._connection
        self.instance_id = runtime.repository.operators.installation_id()

    def _get(self, workset_id: str) -> dict[str, Any]:
        row = self.db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',
                              (identifier(workset_id),)).fetchone()
        if row is None:
            raise ValueError('unknown workset')
        value = json.loads(row[0])
        if value['definition_digest'] != canonical_digest(value['definition']) or value['authority_digest'] != canonical_digest((value['definition_digest'],value['installation_id'],value['runtime_generation'])):
            raise ValueError('workset definition integrity failed')
        return value

    def _save(self, value: dict[str, Any], expected: int) -> dict[str, Any]:
        value['revision'] = expected + 1
        with self.db:
            result = self.db.execute('UPDATE approved_worksets SET revision=?,document=? WHERE workset_id=? AND revision=?',
                (value['revision'], json.dumps(value, sort_keys=True), value['definition']['workset_id'], expected))
            if result.rowcount != 1:
                raise ValueError('stale workset revision')
        return value

    def propose(self, definition: dict[str, Any]) -> dict[str, Any]:
        required = {'contract_version','workset_id','profile_id','expires_at','maximum_activations','members'}
        if set(definition) != required or definition['contract_version'] != CONTRACT:
            raise ValueError('invalid workset definition shape')
        key = identifier(definition['workset_id'])
        profile = resolve_governance_profile(definition['profile_id'])
        if timestamp(definition['expires_at']) <= datetime.now(UTC):
            raise ValueError('workset is expired')
        members = definition['members']
        if (not isinstance(members,list) or not 1 <= len(members) <= 64
                or type(definition['maximum_activations']) is not int
                or not 1 <= definition['maximum_activations'] <= len(members)):
            raise ValueError('workset must have finite bounded membership/allowance')
        ids = []
        for member in members:
            if not isinstance(member,dict) or set(member) != {'candidate_id','subject_revision','mission','planning','dependencies','truth','progression_policy'}:
                raise ValueError('invalid workset member shape')
            candidate = self.lifecycle.get_candidate(identifier(member['candidate_id']))
            ids.append(candidate.id)
            if member['subject_revision'] != canonical_digest(candidate.to_dict()):
                raise ValueError('stale Candidate revision')
            if not isinstance(member['mission'].get('title'),str):raise ValueError('invalid Mission title')
            bridge = GovernedCandidateIntake(self.lifecycle, self.runtime, profile)
            bridge._validate_preview(candidate, ArchitectureMission.from_dict(member['mission']),
                ArchitecturePlanningEvidence.from_dict(member['planning']), member['subject_revision'])
            if not isinstance(member['dependencies'],list) or len(set(member['dependencies'])) != len(member['dependencies']):
                raise ValueError('invalid dependency set')
            # Exact order is a selector. Hard predecessors must already occur in it.
            if any(dep not in ids[:-1] for dep in member['dependencies']):
                raise ValueError('unresolved, cyclic or out-of-order dependency')
        if len(set(ids)) != len(ids):
            raise ValueError('duplicate Candidate membership')
        generation=self.db.execute('SELECT dataset_generation FROM operational_reset_state WHERE singleton=1').fetchone()[0]
        value = {'runtime_generation':generation,'authority_digest':canonical_digest((canonical_digest(definition),self.instance_id,generation)), 'definition':definition,'definition_digest':canonical_digest(definition),
                 'installation_id':self.instance_id,'revision':1,'decisions':{},'release':'DISARMED',
                 'held':False,'revoked':False,'consumed_activations':0,'claims':{}}
        with RuntimeServiceLock(self.runtime.database.path).acquire(), self.db:
            current = self.db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',(key,)).fetchone()
            if current:
                old=self._get(key)
                if old['definition_digest'] != value['definition_digest']:
                    raise ValueError('workset identity is immutable; amendment requires new exact decisions')
                return old
            self.db.execute('INSERT INTO approved_worksets VALUES (?,?,?)',(key,1,json.dumps(value,sort_keys=True)))
        return value

    def decide(self, workset_id: str, *, expected_revision: int, role: str, actor: str) -> dict[str,Any]:
        roles={'business':(GovernanceRole.BUSINESS_OWNER,GovernanceCapability.BUSINESS_APPROVAL),
               'architecture':(GovernanceRole.PLATFORM_ARCHITECT,GovernanceCapability.ARCHITECTURE_APPROVAL)}
        if role not in roles: raise ValueError('invalid workset decision role')
        with RuntimeServiceLock(self.runtime.database.path).acquire():
            value=self._get(workset_id)
            if type(expected_revision) is not int or expected_revision != value['revision']:
                raise ValueError('stale workset revision')
            profile=resolve_governance_profile(value['definition']['profile_id']); required,capability=roles[role]
            if actor not in profile.role_assignments.get(required,()):
                raise PermissionError('current owning workset role is required')
            decision_id=f"workset:{workset_id}:{role}:{value['definition_digest'][7:]}"
            repository=self.runtime.repository
            if role in value['decisions']: return value
            repository.record(GovernanceDecision(decision_id,workset_id,value['authority_digest'],capability,
                'approved',tuple(m['candidate_id'] for m in value['definition']['members']),
                ('EXACT_COMMITTED_ORDER','FINITE_ACTIVATION_ALLOWANCE'),evidence={'actor':actor}),repository.operators.context())
            value['decisions'][role]=decision_id
            return self._save(value,expected_revision)

    def control(self, workset_id: str, *, expected_revision: int, operation: str) -> dict[str,Any]:
        if operation not in {'arm','disarm','hold','unhold','revoke'}:
            raise ValueError('unsupported workset control')
        with RuntimeServiceLock(self.runtime.database.path).acquire():
            value=self._get(workset_id)
            if type(expected_revision) is not int or expected_revision != value['revision']:
                raise ValueError('stale workset revision')
            # All mutating controls require the currently bound operator, never a read token.
            context=self.runtime.repository.operators.context()
            if not self.runtime.repository.operators.authorize(context):
                raise PermissionError('current installed operator required')
            if operation=='arm':
                if value['runtime_generation']!=self.db.execute('SELECT dataset_generation FROM operational_reset_state WHERE singleton=1').fetchone()[0]:raise ValueError('workset runtime generation changed')
                if value['revoked'] or timestamp(value['definition']['expires_at']) <= datetime.now(UTC):
                    raise ValueError('workset release authority is not current')
                if set(value['decisions']) != {'business','architecture'}:
                    raise ValueError('two exact workset decisions required')
                for role,decision_id in value['decisions'].items():
                    d=self.runtime.repository.decision(decision_id)
                    if d['subject_revision'] != value['authority_digest'] or d['installation_id'] != self.instance_id:
                        raise ValueError('workset decision lineage mismatch')
                for member in value['definition']['members']:
                    GovernedCandidateIntake(self.lifecycle,self.runtime,resolve_governance_profile(value['definition']['profile_id'])).approved_envelope(
                        member['candidate_id'],ArchitectureMission.from_dict(member['mission']),
                        ArchitecturePlanningEvidence.from_dict(member['planning']))
                for row in self.db.execute('SELECT document FROM approved_worksets WHERE workset_id!=?',(workset_id,)):
                    other=json.loads(row[0])
                    if other['release']=='AUTO_WHEN_ELIGIBLE' and not other['revoked']:
                        raise ValueError('another selected workset is armed')
                value['release']='AUTO_WHEN_ELIGIBLE'
            elif operation=='disarm': value['release']='DISARMED'
            elif operation=='revoke': value['revoked']=True;value['release']='DISARMED'
            else:value['held']=operation=='hold'
            return self._save(value,expected_revision)



def projection(data_root: Path, instance_id: str, workset_id: str, principal_id: str) -> dict[str,Any]:
    from .operations_read_api import _redact
    from .operations_read_api import InstalledOperationsReadService
    with InstalledOperationsReadService(data_root)._runtime_snapshot() as (db,metadata):
        db.row_factory=sqlite3.Row
        if metadata['runtime_id']!=instance_id:raise PermissionError('foreign runtime instance')
        row=db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',(identifier(workset_id),)).fetchone()
        if row is None:raise PermissionError('workset outside available scope')
        value=json.loads(row[0]);definition=value['definition']
        if canonical_digest(definition)!=value['definition_digest'] or value['authority_digest']!=canonical_digest((value['definition_digest'],value['installation_id'],value['runtime_generation'])):raise ValueError('workset integrity failed')
        if value['installation_id']!=metadata['installation_id']:raise ValueError('foreign workset installation')
        source=data_root/'governance'/'candidates.sqlite'
        if source.is_symlink() or not source.is_file():raise ValueError('Candidate read source unavailable')
        db.execute('ATTACH DATABASE ? AS candidates',(source.resolve().as_uri()+'?mode=ro',))
        for role,decision_id in value['decisions'].items():
            found=db.execute('SELECT document,digest FROM governance_decisions WHERE decision_id=?',(decision_id,)).fetchone()
            if found is None:raise ValueError('workset approval missing')
            decision=json.loads(found[0])
            if (governance_digest(decision)!=found[1] or decision['subject_id']!=workset_id
                    or decision['subject_revision']!=value['authority_digest']
                    or decision['installation_id']!=value['installation_id']
                    or decision['capability']!= {'business':'BUSINESS_APPROVAL','architecture':'ARCHITECTURE_APPROVAL'}.get(role)):
                raise ValueError('workset approval mismatch')
        items=[]
        for order,member in enumerate(definition['members']):
            claim=value['claims'].get(member['candidate_id']);state=None
            if claim is None:
                allocation=db.execute('SELECT document FROM candidates.allocations WHERE candidate_id=?',(member['candidate_id'],)).fetchone()
                if allocation:
                    allocated=json.loads(allocation[0])
                    if allocated.get('installation_id')!=value['installation_id']:raise ValueError('foreign allocation')
                    claim={'mission_id':allocated['mission_id']}

            if claim and claim.get('mission_id'):
                found=db.execute('SELECT document FROM mission_state WHERE mission_id=?',(claim['mission_id'],)).fetchone()
                if found:state=json.loads(found[0])
            lifecycle=state['status'] if state else 'PENDING_INTAKE'
            reasons=[]
            current=db.execute('SELECT document FROM candidates.candidates WHERE candidate_id=?',(member['candidate_id'],)).fetchone()
            candidate_approved=False
            if current is None:reasons.append('SUBJECT_UNAVAILABLE')
            elif canonical_digest(json.loads(current[0]))!=member['subject_revision']:reasons.append('SUBJECT_STALE')
            else:
                candidate_approved=True
                for role,cap in (('business','BUSINESS_APPROVAL'),('architecture','ARCHITECTURE_APPROVAL')):
                    key=GovernedCandidateIntake._decision_id(role,member['candidate_id'],member['subject_revision'])
                    approval=db.execute('SELECT document,digest FROM governance_decisions WHERE decision_id=?',(key,)).fetchone()
                    if approval is None:candidate_approved=False;continue
                    decision=json.loads(approval[0])
                    if governance_digest(decision)!=approval[1]:raise ValueError('approval integrity failed')
                    if (decision['subject_id']!=member['candidate_id'] or decision['subject_revision']!=member['subject_revision']
                            or decision['installation_id']!=value['installation_id'] or decision['capability']!=cap
                            or decision['decision']!='approved'):candidate_approved=False
            if not candidate_approved:reasons.append('SUBJECT_UNAPPROVED')
            if value['runtime_generation']!=db.execute('SELECT dataset_generation FROM operational_reset_state WHERE singleton=1').fetchone()[0]:reasons.append('RUNTIME_GENERATION_CHANGED')
            if value['revoked']:reasons.append('RELEASE_REVOKED')
            if timestamp(definition['expires_at'])<=datetime.now(UTC):reasons.append('RELEASE_EXPIRED')
            if value['held']:reasons.append('WORKSET_HELD')
            if value['release']!='AUTO_WHEN_ELIGIBLE':reasons.append('NOT_RELEASED')
            if set(value['decisions'])!={'business','architecture'}:reasons.append('WORKSET_UNAPPROVED')
            reasons.append('ACTIVATION_NOT_YET_QUALIFIED')
            items.append({'candidate_id':member['candidate_id'],'subject_revision':member['subject_revision'],
                'committed_order':order,'title':_redact(member['mission']['title'])[:160],
                'mission_id':claim.get('mission_id') if claim else None,
                'mission_state_revision':state['revision'] if state else None,
                'approved':candidate_approved,
                'released':value['release']=='AUTO_WHEN_ELIGIBLE' and not value['revoked'],
                'eligibility':'BLOCKED' if len(reasons)>1 else 'UNKNOWN','blocking_reasons':reasons,
                'active':bool(state and lifecycle in {'ACTIVE','READY','WAITING_FOR_EXECUTION','WAITING_FOR_EVIDENCE'}),
                'execution_state':lifecycle,'engineering_result': 'PROVEN' if state and (state.get('completion') or {}).get('all_required_criteria_proven') is True else 'UNKNOWN',
                'review_state':'WAITING' if lifecycle=='AWAITING_APPROVAL' else 'NONE',
                'final_acceptance':'WAITING' if lifecycle=='AWAITING_FINAL_ACCEPTANCE' else 'UNKNOWN',
                'completed':lifecycle=='COMPLETED','effect_mode':(member['mission'].get('effect_policy') or {}).get('mode','UNKNOWN'),
                'dependencies':list(member['dependencies']),
                'detail_reference':{'kind':'MISSION_REVIEW','mission_id':claim['mission_id']} if claim and claim.get('mission_id') else None})
        revision=canonical_digest({'workset_revision':value['revision'],'items':items})
        return {'contract_version':READ_CONTRACT,'instance_id':instance_id,
            'scope':{'kind':'EXPLICIT_WORKSET','principal_id':principal_id,'workset_id':workset_id,'project_id':None},
            'membership_revision':value['definition_digest'],'selector_revision':value['definition_digest'],
            'workset_revision':value['revision'],'snapshot_revision':revision,'observed_at':datetime.now(UTC).isoformat(),
            'freshness':'CURRENT_READBACK','completeness':'COMPLETE_WITHIN_SCOPE','activation_support':'NOT_YET_QUALIFIED',
            'items':items,'read_only':True}
