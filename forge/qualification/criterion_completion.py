"""Installed criterion-completion qualification with external boundary fixtures.

Run from a non-editable wheel using ``python -I -m
forge.qualification.criterion_completion --output-dir FRESH_DIRECTORY``.
The normal public runtime factory, provider parser, observer, evaluator, planner,
runner and persistent stores remain production code. No live provider or EP is
used. Approved criteria describe JSON properties, not application behavior.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from hashlib import sha256
from importlib.metadata import distribution, PackageNotFoundError
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import forge.runtime.dynamic_mission as composition
from forge.architecture import ArchitectureWorkspace
from forge.business import BusinessWorkspace
from forge.completion.repository_observer import RepositoryObservationUnavailable
from forge.governance_authority import ArchitecturePlanningEvidence, MissionPlanningEvidenceEnvelope
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_assessment import (
    ApprovedRepositoryEvidenceSource, CriterionAssessmentContract, CriterionEvidenceRequirement,
)
from forge.models.execution_host import (
    ExecutionDispatch, ExecutionEvidenceOutcome, ExecutionHostEvidence, ExecutionRepositoryEvidence,
)
from forge.models.mission_recommendation import RequiredDiscipline
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.planner.codex_cli_session import (
    CodexCliChatGPTSessionPlanningProvider, CodexCliSessionReadinessChecker,
)
from forge.provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderSecurityService, ProviderAuthenticationMode,
)
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from forge.runtime import RuntimeBootstrap
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.secure_store import MacOSKeychainSecureStoreAdapter


K1 = 'The export contract declares the report_data field.'
K2 = 'The published policy declares authorization_required=true.'
ARTIFACT_PATH = 'contracts/export.json'
SOURCE = ApprovedRepositoryEvidenceSource('synthetic-repository', 'synthetic-owner/synthetic-repository')
IDENTITY = NamedOperatorIdentity('synthetic-criterion-qualification', 501)
PROVIDER = 'synthetic-codex-transport'
SCENARIOS = ('partial', 'single', 'misleading', 'invalid', 'missing', 'no-progress', 'limit', 'regression')


def _digest(value):
    return 'sha256:' + sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def _write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def _append(path, value):
    _write(path, [*_read(path, []), value])


def _contracts():
    return (CriterionAssessmentContract(K1, (CriterionEvidenceRequirement('report-field',
        kind='repository_json', artifact_path=ARTIFACT_PATH, json_pointer='/report/fields',
        expected_json='["report_data"]'),)), CriterionAssessmentContract(K2,
        (CriterionEvidenceRequirement('authorization-policy', kind='repository_json', artifact_path=ARTIFACT_PATH,
         json_pointer='/policy/authorization_required', expected_json='true'),)))


class _CodexTransport:
    def __init__(self, root):
        self.root = root

    def __call__(self, command, **kwargs):
        if '--version' in command:
            return subprocess.CompletedProcess(command, 0, 'codex-cli 0.153.4\n', '')
        if command[-2:] == ['login', 'status']:
            return subprocess.CompletedProcess(command, 0, 'Logged in using ChatGPT\n', '')
        assert 'exec' in command, 'Unexpected external process request'
        incoming = json.loads(kwargs['input'])
        snapshot = incoming['snapshot']
        _append(self.root / 'provider-inputs.private.json', incoming)
        continuation = snapshot.get('continuation_context', {})
        prior = continuation.get('prior_actions', [])
        unmet = [item for item in snapshot['criteria'] if item['status'] == 'UNSATISFIED']
        assert unmet, 'The planner must not be invoked after all criteria are proven'
        action_id = 'synthetic-action-' + chr(ord('a') + len(prior))
        target = unmet[0]
        objective = 'Publish the approved JSON property: ' + target['criterion']
        references = [item['source_id'] for item in snapshot['evidence']]
        gap = None if not prior else {'classification': 'UNPROVEN_MISSION_CRITERION',
            'criterion_ids': [target['criterion_id']], 'triggering_evidence_refs': references,
            'planning_snapshot_digest': snapshot['digest'], 'causal_objective': objective,
            'mission_caused_by_action_ids': []}
        proposal = {'logical_action_id': action_id, 'scope': 'synthetic-contract', 'objective': objective,
            'dependencies': [], 'write_scopes': ['contracts'], 'expected_evidence': [target['criterion']],
            'validation_strategy': ['Verify the exact approved JSON pointer at the delivery revision.'],
            'priority': 1, 'postponed': False, 'human_gates': ['protected-delivery'],
            'risk_inputs': ['scope-drift'], 'source_evidence_refs': references, 'mission_gap': gap}
        Path(command[command.index('--output-last-message') + 1]).write_text(
            json.dumps({'result': {'kind': 'proposals', 'proposals': [proposal]}}))
        return subprocess.CompletedProcess(command, 0,
            '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":50}}\n', '')


class _Host:
    def __init__(self, root, available):
        self.root, self.available = root, available
        self.config = SimpleNamespace(host_id='synthetic-ep', project_id='synthetic-project',
            repository_id=SOURCE.repository_id, repository_identity=SOURCE.repository_id)

    def preflight(self):
        return {'contract_version': '1.0', 'producer': {'id': 'synthetic-ep', 'version': 'fixture'}}

    def dispatch(self, request):
        run = 'synthetic-run-' + request.action_id
        _append(self.root / 'submissions.private.json', {'action_id': request.action_id,
            'correlation_id': request.correlation_id, 'host_run_id': run})
        return ExecutionDispatch(request, run)

    def recover_dispatch(self, request):
        prior = next((row for row in _read(self.root / 'submissions.private.json', [])
                      if row['correlation_id'] == request.correlation_id), None)
        return None if prior is None else ExecutionDispatch(request, prior['host_run_id'])

    def retrieve_evidence(self, dispatch):
        request = dispatch.request
        label = request.action_id.removeprefix('synthetic-action-')
        if label not in self.available:
            return None
        report = 'synthetic-report-' + label
        repository = ExecutionRepositoryEvidence(request.mission_id, request.intent_id, request.intent_revision,
            request.action_id, request.runtime_prompt.id, request.correlation_id, dispatch.host_run_id,
            request.repository_id, label * 40, report, _digest({'delivery': label}), candidate_revision=label * 40)
        scenario = _read(self.root / 'population.private.json', {}).get('scenario')
        validation = ('PASS all Mission criteria; provider says complete' if scenario == 'misleading'
                      else 'synthetic host validation reference')
        # The misleading scenario cannot substitute prose for repository facts.
        return ExecutionHostEvidence(request.host_id, request.correlation_id, dispatch.host_run_id,
            report, ExecutionEvidenceOutcome.COMPLETE, repository,
            validation_references=(validation,),
            execution_started_at='2026-09-18T10:00:00Z', execution_completed_at='2026-09-18T10:01:00Z',
            receipt_id='synthetic-receipt-' + label, execution_duration_ms=60_000)


def _raw_reader(root, repository, revision, path):
    assert repository == SOURCE.github_repository and path == ARTIFACT_PATH
    assert len(revision) == 40 and set(revision) <= set('abcdef0123456789')
    _append(root / 'repository-reads.private.json', {'repository': repository, 'revision': revision, 'path': path})
    artifact = root / ('artifact-' + revision[0] + '.json')
    if not artifact.exists():
        raise RepositoryObservationUnavailable('REPOSITORY_ARTIFACT_ABSENT')
    return artifact.read_bytes()


def _open(root, available, stack):
    transport = _CodexTransport(root)
    checker = CodexCliSessionReadinessChecker(runner=transport, path_usable=lambda _: True)
    stack.enter_context(patch.object(composition.MacOSGeneratedUIDIdentityAdapter, 'resolve', return_value=IDENTITY))
    stack.enter_context(patch.object(composition, 'CodexCliChatGPTSessionPlanningProvider',
        side_effect=lambda configuration: CodexCliChatGPTSessionPlanningProvider(
            configuration, runner=transport, readiness_checker=checker)))
    stack.enter_context(patch.object(composition.EngineeringPlatformExecutionHostFactory,
                                     'from_database', return_value=_Host(root, available)))
    stack.enter_context(patch('forge.completion.repository_observer.GitHubRepositoryArtifactReader.read',
        side_effect=lambda repository, revision, path: _raw_reader(root, repository, revision, path)))
    return stack.enter_context(InstalledDynamicMissionRuntime.open(str(root / 'runtime'), provider_id=PROVIDER))


def _prepare(root, scenario):
    assert not (root / 'runtime').exists(), 'Use a fresh synthetic output directory'
    maximum_actions = 1 if scenario == 'limit' else 2 if scenario == 'regression' else 3
    with RuntimeBootstrap(data_root=root / 'runtime', forge_version='qualification').open() as database:
        operators = InstallationOperatorService(database, lambda: IDENTITY)
        context = operators.first_bind()
        PlanningProviderSecurityService(database, MacOSKeychainSecureStoreAdapter(), operators).configure(
            configuration_id='synthetic-config', provider_id=PROVIDER, operator_context=context,
            authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
            provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
            executable_path='/usr/bin/false', adapter_version='codex-cli-chatgpt-session-v1',
            timeout_seconds=10, input_token_bound=40000, context_token_bound=48000, output_token_bound=8000)
    with ExitStack() as stack:
        runtime = _open(root, (), stack)
        repository, context = runtime.repository, runtime.repository.operators.context()
        options = {'criterion_assessment_contracts': _contracts(), 'maximum_actions': maximum_actions,
                   'maximum_consecutive_no_progress_actions': 1, 'repository_evidence_source': SOURCE}
        planning = ArchitecturePlanningEvidence(('synthetic-contract',), ('contracts',), ('no behavior claim',),
            ('scope-drift',), ('protected-delivery',), ('synthetic-host',), 40000, 8000, '1', **options)
        BusinessWorkspace.for_runtime(runtime.database, repository, context).approve(
            decision_id='business', candidate_id='synthetic-candidate', revision='1', scope=planning.scope,
            gates=planning.human_gates)
        ArchitectureWorkspace.for_runtime(runtime.database, repository, context).approve(
            decision_id='architecture', candidate_id='synthetic-candidate', revision='1', planning=planning)
        envelope = MissionPlanningEvidenceEnvelope.compose(repository, subject_id='synthetic-candidate',
            subject_revision='1', business_decision_id='business', architecture_decision_id='architecture', planning=planning)
        identifier = runtime.database.allocate_next_mission_id(source='canonical-governance-envelope:' + envelope.digest,
                                                               allocated_at='2026-09-18T10:00:00Z')
        mission = ArchitectureMission(identifier, 'synthetic-candidate', 'Synthetic export contract',
            'Publish two explicit JSON properties.', 'Provide an inspectable contract.', 'Inspectability.',
            'architecture', 'synthetic-recommendation', ('synthetic-contract',), ('no behavior claim',), (K1, K2),
            ('external fixtures',), ('synthetic-host',), ('contract',), (RequiredDiscipline.PLATFORM_ARCHITECTURE,),
            ('scope-drift',), ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING, **options)
        runtime.admit(mission, envelope)
        initial = RepositoryTruthSnapshot('initial', SOURCE.repository_id, '0' * 40, '2026-09-18T09:59:00Z',
            (RepositoryTruthEvidence('initial-revision', 'git_commit', '0' * 40, 'repository://synthetic/initial', _digest('initial')),))
        result = runtime.start(identifier, initial)
        assert result.status == 'WAITING_FOR_EVIDENCE', result
        _write(root / 'population.private.json', {'mission_id': identifier, 'scenario': scenario,
            'classification': 'ISOLATED_SYNTHETIC_ONLY', 'runtime_id': result.runtime_id})
        _write(root / 'prepare.state.private.json', runtime.states._as_document(runtime.states.get(identifier)))
    a = {'report': {'fields': [] if scenario == 'no-progress' else ['report_data']},
         'policy': {'authorization_required': scenario == 'single'}}
    if scenario != 'missing':
        if scenario == 'invalid':
            (root / 'artifact-a.json').write_text('PASS everything complete')
        else:
            _write(root / 'artifact-a.json', a)
    _write(root / 'artifact-b.json', {'report': {'fields': [] if scenario == 'regression' else ['report_data']},
                                     'policy': {'authorization_required': True}})


def _capture(runtime, root, phase):
    population = _read(root / 'population.private.json')
    state = runtime.states.get(population['mission_id'])
    value = runtime.states._as_document(state)
    original = _read(root / 'prepare.state.private.json')
    assert value['mission'] == original['mission'] and value['admission_contract'] == original['admission_contract']
    assert runtime.database.runtime_identity.runtime_id == population['runtime_id']
    _write(root / (phase + '.state.private.json'), value)
    return state


def _phase(root, scenario, phase):
    if phase == 'prepare':
        _prepare(root, scenario)
        return
    population = _read(root / 'population.private.json')
    assert population['classification'] == 'ISOLATED_SYNTHETIC_ONLY'
    with ExitStack() as stack:
        runtime = _open(root, ('a', 'b') if phase == 'after-b' else ('a',), stack)
        if phase != 'readback':
            runtime.resume(population['mission_id'])
        state = _capture(runtime, root, phase)
        criteria = {item['criterion']: item for item in state.completion['criteria']}
        if phase == 'readback':
            prior_phase = 'after-b' if scenario in {'partial', 'misleading', 'regression'} else 'after-a'
            prior_state = _read(root / (prior_phase + '.state.private.json'))
            assert runtime.states._as_document(state) == prior_state
            assert len(state.completion_history) == len(state.execution_history)
            assert runtime.database._connection.execute('SELECT COUNT(*) FROM governance_decisions').fetchone()[0] == 2
            if (root / 'after-a.state.private.json').exists():
                assert state.completion_history[0] == _read(root / 'after-a.state.private.json')['completion']
        if phase == 'after-a' and scenario in {'partial', 'misleading', 'regression'}:
            assert state.status.value == 'WAITING_FOR_EVIDENCE', state.waiting_reason
            assert criteria[K1]['status'] == 'PROVEN' and criteria[K2]['status'] == 'UNSATISFIED'
            assert len(state.actions) == 2 and len(state.planning_history) == 2
            inputs = _read(root / 'provider-inputs.private.json')
            assert inputs[0]['snapshot']['approved_mission'] == inputs[1]['snapshot']['approved_mission']
            context = inputs[1]['snapshot']['continuation_context']
            assert context['repository_truth']['revision'] == 'a' * 40
            assert context['terminal_evidence'][0]['receipt_id'] == 'synthetic-receipt-a'
            assert context['prior_actions'][0]['id'] == 'synthetic-action-a'
            assert context['prior_actions'][0]['status'] == 'COMPLETE'
            unmet = next(item for item in context['criterion_assessments'] if item['criterion'] == K2)
            assert unmet['status'] == 'UNSATISFIED' and unmet['requirement_results'][0]['reason'] == 'JSON_ASSERTION_MISMATCH'
        if phase == 'replay-a':
            assert runtime.states._as_document(state) == _read(root / 'after-a.state.private.json')
            assert len(_read(root / 'submissions.private.json')) == 2
            assert len(_read(root / 'provider-inputs.private.json')) == 2
        if phase in {'after-b', 'readback'} and scenario in {'partial', 'misleading'} or scenario == 'single':
            assert state.status.value == 'COMPLETED', state.waiting_reason
            assert all(item['status'] == 'PROVEN' for item in criteria.values())
            expected = 1 if scenario == 'single' else 2
            assert len(state.actions) == len(state.planning_history) == len(state.execution_history) == expected
            assert len(_read(root / 'submissions.private.json')) == expected
            assert len(_read(root / 'provider-inputs.private.json')) == expected
            assert len(state.completion_history) == expected
            assert all(row['processing_phase'] == 'MATERIALIZED'
                       for row in runtime.database.durable_action_derivation_readback(state.mission_id))
            if expected == 2:
                first = _read(root / 'after-a.state.private.json')['completion']
                assert state.completion_history[0] == first
                assert all(obs['repository_revision'] == 'a' * 40 for item in first['criteria'] for obs in item['observations'])
                assert all(any(obs['repository_revision'] == 'b' * 40 for obs in item['observations'])
                           for item in state.completion['criteria'])
        if scenario in {'invalid', 'missing', 'no-progress', 'limit'} or scenario == 'regression' and phase in {'after-b', 'readback'}:
            assert state.status.value == 'BLOCKED', state.status.value
            assert not state.completion['all_required_criteria_proven']
            expected = 2 if scenario == 'regression' else 1
            assert len(_read(root / 'provider-inputs.private.json')) == expected
            assert len(_read(root / 'submissions.private.json')) == expected


def _summary(root, scenario):
    state = _read(root / 'readback.state.private.json')
    return {'scenario': scenario, 'status': state['status'], 'waiting_reason': state['waiting_reason'],
        'criteria': [{'criterion': 'SYNTHETIC-K1' if row['criterion'] == K1 else 'SYNTHETIC-K2',
                      'status': row['status'], 'reason': row['reason']} for row in state['completion']['criteria']],
        'actions': len(state['actions']), 'submissions': len(_read(root / 'submissions.private.json')),
        'planner_invocations': len(_read(root / 'provider-inputs.private.json')),
        'assessments': len(state.get('completion_history', [])), 'separate_process_reopen': True,
        'same_mission_and_approval': True, 'original_observations_preserved': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--scenario', choices=('all', *SCENARIOS), default='all')
    parser.add_argument('--phase', choices=('prepare', 'after-a', 'after-b', 'replay-a', 'readback'))
    parser.add_argument('--source-development', action='store_true', help='Explicitly label source-only development, never installed qualification')
    args = parser.parse_args()
    root = (args.output_dir or Path(tempfile.mkdtemp(prefix='forge-criterion-qualification-'))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.phase:
        _phase(root, args.scenario, args.phase)
        return 0
    try:
        installed = distribution('forge-autonomy')
        direct = json.loads(installed.read_text('direct_url.json') or '{}')
        metadata = {'version': installed.version, 'wheel_sha256': direct.get('archive_info', {}).get('hashes', {}).get('sha256')}
    except PackageNotFoundError:
        metadata, direct = {}, {}
    if not args.source_development:
        assert metadata and metadata['wheel_sha256'] and not direct.get('dir_info', {}).get('editable'), 'Use a non-editable installed wheel'
        assert Path(__file__).resolve().is_relative_to(Path(installed.locate_file('forge')).resolve()), 'Source checkout imports are not installed qualification'
    scenarios = SCENARIOS if args.scenario == 'all' else (args.scenario,)
    summaries = []
    for scenario in scenarios:
        case = root / scenario
        case.mkdir()
        phases = ['prepare', 'after-a']
        if scenario in {'partial', 'misleading', 'regression'}:
            phases += ['replay-a', 'after-b']
        phases += ['readback']
        for phase in phases:
            command = [sys.executable]
            if not args.source_development:
                command += ['-I']
            command += ['-m', 'forge.qualification.criterion_completion', '--scenario', scenario,
                        '--phase', phase, '--output-dir', str(case)]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            (case / (phase + '.raw.private.log')).write_text(result.stdout + result.stderr)
            if result.returncode:
                print(json.dumps({'scenario': scenario, 'phase': phase, 'exit_code': result.returncode,
                                  'detail': result.stderr.splitlines()[-1] if result.stderr else 'see private phase log'}))
                return result.returncode
        summaries.append(_summary(case, scenario))
    report = {'qualification': ('SOURCE_COMPOSITION_WITH_EXTERNAL_FIXTURES' if args.source_development
                               else 'INSTALLED_COMPOSITION_WITH_EXTERNAL_FIXTURES'),
              'artifact': metadata, 'scenarios': summaries,
              'limitations': ['JSON artifact properties only; no application behavior claim.',
                'Codex process, ExecutionHost and immutable repository transport are external fixtures.',
                'This is not provider-backed planning or live EP autonomy acceptance.']}
    _write(root / 'criterion-completion.public.json', report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
