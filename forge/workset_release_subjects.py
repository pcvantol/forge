"""Read existing approved chat-first subjects; never allocate or decide them."""
from datetime import UTC, datetime
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from .advisory_contract import digest
from .advisory_context import AdvisoryContext
from .approved_worklist import candidate_source, identifier
from .candidate_decision_service import CandidateDecisionService
from .governance import resolve_governance_profile
from .governance_authority import ArchitecturePlanningEvidence
from .governed_candidate_intake import GovernedCandidateIntake
from .lifecycle import RecommendationLifecycleStore
from .mission_concept_contract import CONTRACT
from .mission_concept_registration import registration_receipt
from .models.architecture_mission import ArchitectureMission
from .models.criterion_observation import canonical_digest
from .repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from .runtime.dynamic_mission import InstalledDynamicMissionRuntime


def approved_subject(root, scope, candidate_id, subject_revision, profile_id='solo'):
    """Verify immutable registration, both real decisions and existing admission."""
    identifier(candidate_id)
    with RecommendationLifecycleStore.read_only(candidate_source(Path(root))) as store, \
            InstalledDynamicMissionRuntime.open_for_governance_read(str(root)) as runtime:
        receipt, proposal = store.registered_candidate_source(candidate_id)
        if (proposal.get('contract_version') != CONTRACT
                or any(proposal.get(k) != scope[k] for k in ('instance_id','project_id','repository_id'))):
            raise PermissionError('subject outside approved chat-first project')
        expected = registration_receipt(proposal['principal_reference'],receipt['operation_id'],
            receipt['registration_key'],proposal,receipt['registered_at'])
        if digest(receipt) != digest(expected):
            raise ValueError('approved subject registration integrity changed')
        package = proposal['package']
        candidate = store.get_candidate(candidate_id)
        if (canonical_digest(candidate.to_dict()) != subject_revision
                or package['subject_revision'] != subject_revision
                or canonical_digest(package['candidate']) != canonical_digest(candidate.to_dict())):
            raise ValueError('approved subject revision changed')
        preview = ArchitectureMission.from_dict(package['mission_preview'])
        planning = ArchitecturePlanningEvidence.from_dict(package['planning'])
        bridge = GovernedCandidateIntake(store,runtime,resolve_governance_profile(profile_id))
        envelope = bridge.approved_envelope(candidate_id,preview,planning)
        if envelope.subject_revision != subject_revision:
            raise ValueError('approved subject envelope changed')
        decisions = {}
        for kind in ('business','architecture'):
            decision_id = bridge._decision_id(kind,candidate_id,subject_revision)
            decisions[kind] = CandidateDecisionService.checked_receipt(store,runtime,decision_id)
            if decisions[kind] is None:
                raise ValueError('canonical Candidate decision receipt missing')
        allocation = store.allocation_for_recommendation(candidate.recommendation_id)
        if allocation is None:
            raise ValueError('existing chat-first Mission admission required')
        state = runtime.states.get(allocation.mission_id)
        if ((state.admission_contract or {}).get('subject_revision') != subject_revision
                or canonical_digest(dict(state.mission)) != canonical_digest(replace(preview,id=allocation.mission_id).to_dict())):
            raise ValueError('existing Mission admission differs from approved definition')
        return {'candidate_id':candidate_id,'subject_revision':subject_revision,
            'mission_id':allocation.mission_id,
            'definition':package['definition'],'mission':package['mission_preview'],
            'planning':package['planning'],'dependency_bindings':package['dependency_bindings'],
            'candidate_decisions':decisions,'source':package['source']}


def repository_truth(root, scope):
    """Use genuine owner-published immutable context; no transport call or defaults."""
    context=AdvisoryContext(root,scope['instance_id'])
    sources=[r for r in context._read(True) if r['scope']==scope and r['state']=='ACTIVE']
    if not sources or len({(s['repository'],s['revision']) for s in sources})!=1:
        raise ValueError('one current owner-published repository revision required')
    from .approved_worklist import timestamp
    observations=[timestamp(s['observed_at']) for s in sources if 'observed_at' in s]
    if not observations:
        raise ValueError('current owner-published observation receipt required')
    source = sources[0]
    return RepositoryTruthSnapshot('published-context-'+source['source_id'],scope['repository_id'],
        source['revision'],max(observations).isoformat(),tuple(
            RepositoryTruthEvidence(s['source_id'],'repository_document',s['revision'],
                'https://github.com/'+s['repository']+'/blob/'+s['revision']+'/'+s['path'],
                s['content_digest']) for s in sources)).to_dict()
