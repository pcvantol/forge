"""Canonical scheduler composition for one released, finite approved workset."""
from datetime import UTC,datetime
import json
from pathlib import Path
from .approved_worklist import ApprovedWorklistService,candidate_source,projection
from .lifecycle import RecommendationLifecycleStore
from .governance import resolve_governance_profile
from .governance_authority import ArchitecturePlanningEvidence
from .governed_candidate_intake import GovernedCandidateIntake
from .models.architecture_mission import ArchitectureMission
from .models.criterion_observation import canonical_digest
from .repository_truth import RepositoryTruthEvidence,RepositoryTruthSnapshot
from .runtime.service import RuntimeServiceLock
from .runtime.dynamic_mission import _quiescent_failed_attempt
from .governed_continuation import _resolved_policy,PROFILE_DEFINITION_REVISION,PROGRESSION_POLICY_REVISION


def _now():return datetime.now(UTC).isoformat()


def truth_snapshot(document):
    value=dict(document)
    value['evidence']=tuple(RepositoryTruthEvidence(**item) for item in value['evidence'])
    return RepositoryTruthSnapshot(**value)


def validate_activation_inputs(value,member):
    try:
        truth=truth_snapshot(member['truth'])
        preview=ArchitectureMission.from_dict(member['mission'])
        policy=member['progression_policy']
        required={'profile_id','profile_revision','policy_revision','mode','required_decision_role','higher_scope_obligations'}
        if (preview.effect_policy is None or set(policy)!=required
                or policy['profile_id']!=value['definition']['profile_id']
                or policy['profile_revision']!=PROFILE_DEFINITION_REVISION
                or policy['policy_revision']!=PROGRESSION_POLICY_REVISION
                or policy['higher_scope_obligations']!=member['planning']['human_gates']
                or truth.repository_id!=preview.repository_evidence_source.repository_id):
            raise ValueError('unsupported workset activation inputs')
        _resolved_policy(policy['profile_id'],policy['mode'],policy['required_decision_role'])
        return truth
    except (KeyError,TypeError,AttributeError) as error:
        raise ValueError('malformed workset activation inputs') from error


class ApprovedWorklistActivation:
    """Reuse canonical intake, policy and dynamic runtime under their single lease."""
    def __init__(self,service):
        self.service=service;self.runtime=service.runtime

    def _current(self,key,candidate_id):
        value=self.service._get(key)
        operator=self.runtime.repository.operators
        if not operator.authorize(operator.context()):raise PermissionError('current operator required')
        read=projection(Path(self.runtime.data_root),self.runtime.database.runtime_identity.runtime_id,key,'forge-scheduler')
        item=next((item for item in read['items'] if not item['completed']),None)
        if item is None or item['candidate_id']!=candidate_id:raise ValueError('committed selector changed')
        reasons=set(item['blocking_reasons'])-{'ACTIVATION_NOT_YET_QUALIFIED'}
        claim=value['claims'].get(candidate_id)
        if claim and claim.get('mission_id') is None:reasons.discard('MISSION_STATE_UNAVAILABLE')
        if reasons:raise ValueError('workset activation blocked')
        member=value['definition']['members'][item['committed_order']]
        validate_activation_inputs(value,member)
        bridge=GovernedCandidateIntake(self.service.lifecycle,self.runtime,resolve_governance_profile(value['definition']['profile_id']))
        preview=ArchitectureMission.from_dict(member['mission'])
        planning=ArchitecturePlanningEvidence.from_dict(member['planning'])
        envelope=bridge.approved_envelope(candidate_id,preview,planning)
        if envelope.subject_revision!=member['subject_revision']:raise ValueError('activation subject changed')
        return value,member,bridge,preview,planning

    def tick(self):
        with RuntimeServiceLock(self.runtime.database.path).acquire(reuse_current=True):
            records=[json.loads(row[0]) for row in self.service.db.execute('SELECT document FROM approved_worksets')]
            selected=[value for value in records if value['release']=='AUTO_WHEN_ELIGIBLE' and not value['revoked']]
            if not selected:return None
            if len(selected)!=1:raise ValueError('ambiguous armed workset')
            key=selected[0]['definition']['workset_id']
            read=projection(Path(self.runtime.data_root),self.runtime.database.runtime_identity.runtime_id,key,'forge-scheduler')
            head=next((item for item in read['items'] if not item['completed']),None)
            if head is None:return None
            candidate_id=head['candidate_id']
            try:value,member,bridge,preview,planning=self._current(key,candidate_id)
            except (ValueError,PermissionError):return None
            candidate=self.service.lifecycle.get_candidate(candidate_id)
            allocation=self.service.lifecycle.allocation_for_recommendation(candidate.recommendation_id)
            claim=value['claims'].get(candidate_id)
            own_id=(claim or {}).get('mission_id') or (allocation.mission_id if allocation else None)
            if any(state.mission_id!=own_id and not _quiescent_failed_attempt(state) for state in self.runtime.states.resumable()):return None
            if own_id:
                existing=self.service.db.execute('SELECT document FROM mission_state WHERE mission_id=?',(own_id,)).fetchone()
                if existing and json.loads(existing[0])['status']!='APPROVED_PLANNABLE':return None
            operation_id=canonical_digest((value['authority_digest'],candidate_id,member['subject_revision']))
            if claim is None:
                if value['consumed_activations']>=value['definition']['maximum_activations']:return None
                value['claims'][candidate_id]={'operation_id':operation_id,'subject_revision':member['subject_revision'],
                    'claimed_at':_now(),'mission_id':None,'eligibility_revision':read['snapshot_revision'],
                    'release_revision':value['revision'],'expires_at':value['definition']['expires_at'],
                    'runtime_generation':value['runtime_generation'],'predecessor_evidence':
                    [ref for item in read['items'][:head['committed_order']] for ref in item['evidence_references']]}
                value['consumed_activations']+=1
                value=self.service._save(value,value['revision'])
            elif claim['operation_id']!=operation_id or claim['subject_revision']!=member['subject_revision']:
                raise ValueError('claim lineage conflict')
            self._current(key,candidate_id)
            state=bridge.admit(candidate_id,preview,planning,occurred_at=_now())
            value=self.service._get(key)
            if value['claims'][candidate_id]['mission_id'] not in (None,state.mission_id):raise ValueError('claim allocation conflict')
            if value['claims'][candidate_id]['mission_id'] is None:
                value['claims'][candidate_id]['mission_id']=state.mission_id
                self.service._save(value,value['revision'])
            policy=dict(member['progression_policy'])
            policy['assignment_id']='workset-policy:'+operation_id[7:]
            if (state.execution_policy or {}).get('assignment_contract'):
                self.runtime._progression_policy(state)
                if any(state.execution_policy.get(k)!=v for k,v in policy.items()):raise ValueError('claim policy conflict')
            else:
                policy['expected_state_revision']=state.revision
                self.runtime.assign_progression_policy(state.mission_id,policy)
            from .mission_cli import _verified_initial_truth
            requested=validate_activation_inputs(value,member)
            # A predecessor's proven same-repository delivery may advance source
            # Truth without changing the approved next Candidate or its scope.
            if head['committed_order']:
                previous=read['items'][head['committed_order']-1]
                prior=self.runtime.states.get(previous['mission_id'])
                prior_mission=ArchitectureMission.from_dict(dict(prior.mission))
                source=preview.repository_evidence_source
                if prior_mission.repository_evidence_source!=source:
                    raise ValueError('predecessor repository scope differs')
                fact=prior.repository_truth
                requested=RepositoryTruthSnapshot(fact['source_id'],source.repository_id,fact['revision'],_now(),
                    (RepositoryTruthEvidence(fact['source_id'],'canonical_completed_repository_truth',fact['revision'],fact['locator'],fact['content_digest']),))
            truth=_verified_initial_truth(self.runtime,state.mission_id,requested)
            def current():
                self._current(key,candidate_id)
                validate_activation_inputs(self.service._get(key),member)
            current()
            return self.runtime.start(state.mission_id,truth,activation_check=current)


def activate_selected(runtime):
    rows=runtime.database._connection.execute('SELECT document FROM approved_worksets').fetchall()
    if not any(json.loads(row[0])['release']=='AUTO_WHEN_ELIGIBLE' and not json.loads(row[0])['revoked'] for row in rows):return None
    with RecommendationLifecycleStore(candidate_source(Path(runtime.data_root))) as lifecycle:
        return ApprovedWorklistActivation(ApprovedWorklistService(runtime,lifecycle)).tick()
