"""Read the actual Mission result; derive the exact Business confirmation basis."""
from __future__ import annotations

from collections.abc import Mapping

from .advisory_contract import digest
from .completion import MissionCompletionEvaluator
from .governed_continuation import GovernedContinuationService, _digest
from .mission_final_acceptance_contract import CONTRACT
from .models.architecture_mission import ArchitectureMission
from .models.mission_completion import MissionCompletionEvidence
from .operations_read_api import _redact
from .state import MissionExecutionStatus


def proven_result(state):
    """Reuse the same criterion evaluator required by the terminal transition."""
    completion = state.completion
    evidence = state.execution_evidence
    if (not isinstance(completion, Mapping) or completion.get('schema_version') != '2.0'
            or not isinstance(evidence, Mapping) or evidence.get('outcome') != 'complete'
            or not state.actions or any(a.get('status') != 'COMPLETE' for a in state.actions)):
        raise ValueError('Mission result is not proven complete')
    proposed = completion.get('evidence')
    evidence_contract = None if proposed is None else MissionCompletionEvidence.from_dict(proposed)
    checked = MissionCompletionEvaluator().evaluate(ArchitectureMission.from_dict(state.mission),
        state.repository_truth, state.execution_history, evidence_contract)
    if not checked.all_required_criteria_proven or checked.to_dict() != completion:
        raise ValueError('Mission result criteria/evidence no longer match')
    required = ('host_id', 'receipt_id', 'host_run_id', 'correlation_id', 'report_id',
                'execution_started_at', 'execution_completed_at', 'execution_duration_ms')
    lineage = evidence.get('repository_evidence')
    if (any(not evidence.get(key) for key in required) or not isinstance(lineage, Mapping)
            or any(not lineage.get(key) for key in ('mission_id', 'intent_id', 'intent_revision',
                'action_id', 'runtime_prompt_id', 'correlation_id', 'host_run_id', 'report_id'))
            or lineage['mission_id'] != state.mission_id
            or any(evidence[key] != lineage[key] for key in ('correlation_id', 'host_run_id', 'report_id'))):
        raise ValueError('Mission terminal lineage is incomplete or inconsistent')
    return checked


def source_basis(state):
    return {'scope_digest': digest(sorted(state.mission.get('scope', ()))),
            'mission_definition_digest': digest(state.mission),
            'admission_digest': digest(state.admission_contract),
            'policy_digest': _digest(state.execution_policy),
            'completion_digest': _digest(state.completion),
            'terminal_evidence_digest': _digest(state.execution_evidence)}


def result_summary(state):
    def bounded(value, limit=1000):
        safe = _redact(value)
        return safe[:limit] if isinstance(safe, str) else ''
    criteria = state.mission.get('acceptance_criteria', [])
    try:
        proven_result(state)
        proven = True
    except (ValueError, TypeError, KeyError):
        proven = False
    return {'mission_id': state.mission_id, 'title': bounded(state.mission.get('title'), 256),
            'objective': bounded(state.mission.get('business_objective')),
            'summary': bounded(state.mission.get('summary')),
            'criteria': [bounded(c) for c in criteria[:64] if isinstance(c, str)],
            'criteria_results': [{
                'criterion_id': bounded(item.get('criterion_id'), 128),
                'criterion': bounded(item.get('criterion')),
                'status': item.get('status') if item.get('status') in ('PROVEN', 'UNSATISFIED') else 'UNKNOWN',
                'reason': bounded(item.get('reason')),
                'evidence_references': [{
                    'receipt_id': bounded(ref.get('receipt_id'), 128),
                    'action_id': bounded(ref.get('action_id'), 128),
                    'report_id': bounded(ref.get('report_id'), 128),
                    'repository_evidence_digest': bounded(ref.get('repository_evidence_digest'), 128),
                } for ref in item.get('execution_evidence', [])[:8] if isinstance(ref, Mapping)],
            } for item in (state.completion or {}).get('criteria', [])[:64] if isinstance(item, Mapping)],
            'completion_proven': proven,
            'completion_digest': _digest(state.completion),
            'terminal_evidence_digest': _digest(state.execution_evidence)}


def prepare_package(runtime, principal, mission_id):
    state = runtime.states.get(mission_id)
    if state.status is not MissionExecutionStatus.AWAITING_APPROVAL:
        raise ValueError('Mission is not awaiting Business final acceptance')
    proven_result(state)
    service = GovernedContinuationService(runtime.database, runtime.repository, runtime.states, runtime.clock)
    requirement = service.validate_final_acceptance(state, state.pause_reason or {}, project_id=principal.project_id)
    return {'contract_version': CONTRACT, 'instance_id': principal.instance_id,
            'project_id': principal.project_id, 'repository_id': principal.repository_id,
            'mission_id': mission_id, 'principal_reference': principal.reference,
            'mission_state_revision': state.revision, 'requirement': requirement,
            'source_basis': source_basis(state), 'result': result_summary(state),
            'required_role': 'business_owner', 'required_capability': 'BUSINESS_APPROVAL',
            'decision': 'accept', 'execution_started': False}
