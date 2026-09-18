"""Installed-composition negative regression: partial Action cannot close Mission.

Only external identity, Codex subprocess transport and ExecutionHost construction
are fixtures. The public installed factory, real provider parser/admission,
durable planner, completion producer/evaluator, runner and stores remain intact.
Run with an isolated interpreter containing the non-editable baseline wheel.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from hashlib import sha256
from importlib.metadata import distribution, version
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import forge.runtime.dynamic_mission as dynamic_module
from forge.architecture import ArchitectureWorkspace
from forge.business import BusinessWorkspace
from forge.governance_authority import ArchitecturePlanningEvidence, MissionPlanningEvidenceEnvelope
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.execution_host import (
    ExecutionDispatch, ExecutionEvidenceOutcome, ExecutionHostEvidence, ExecutionRepositoryEvidence,
)
from forge.models.mission_recommendation import RequiredDiscipline
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.planner.codex_cli_session import (
    CodexCliChatGPTSessionPlanningProvider as RealCodexProvider,
    CodexCliSessionReadinessChecker,
)
from forge.provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderSecurityService, ProviderAuthenticationMode,
)
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from forge.runtime import RuntimeBootstrap
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.secure_store import MacOSKeychainSecureStoreAdapter


IDENTITY = NamedOperatorIdentity('synthetic-criterion-regression-operator', 501)
PROVIDER_ID = 'synthetic-codex-boundary'
K1 = 'K1: export endpoint returns the approved report data'
K2 = 'K2: access control rejects an unauthorized export request'
CONTROL_K1 = 'python -m unittest synthetic_export.test_report_data'
CONTROL_K2 = 'python -m unittest synthetic_export.test_access_control'
SCOPE = 'synthetic-export'


def digest(value):
    return 'sha256:' + sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def append(path, value):
    path.write_text(json.dumps([*read(path, []), value], indent=2) + '\n')


def artifact_provenance(wheel, publication_receipt):
    """Verify exact local wheel bytes against installed and published metadata."""
    direct = json.loads(distribution('forge-autonomy').read_text('direct_url.json') or '{}')
    installed_hash = direct.get('archive_info', {}).get('hashes', {}).get('sha256')
    result = {'distribution': 'forge-autonomy', 'version': version('forge-autonomy'),
              'non_editable': not bool(direct.get('dir_info', {}).get('editable')),
              'installed_wheel_sha256': installed_hash,
              'local_wheel_bytes_verified': False, 'retained_publication_receipt_verified': False}
    assert result['non_editable'], 'Use a non-editable wheel installation'
    if wheel is not None:
        actual = sha256(wheel.read_bytes()).hexdigest()
        assert installed_hash == actual, 'Local wheel differs from installed artifact metadata'
        result.update({'wheel_filename': wheel.name, 'wheel_sha256': actual,
                       'local_wheel_bytes_verified': True})
    if publication_receipt is not None:
        assert wheel is not None, 'Publication receipt verification also requires --wheel'
        receipt = read(publication_receipt, {})
        expected = 'sha256:' + result['wheel_sha256']
        assert receipt.get('artifacts', {}).get('wheel') == expected, 'Release wheel digest differs'
        published = receipt.get('publication_receipt', {})
        assert published.get('readback') == 'PASS', 'Retained publication readback was not successful'
        assert published.get('observed_artifact_digests', {}).get(wheel.name) == expected
        if 'version' in receipt:
            assert receipt['version'] == result['version'], 'Release version differs from installation'
        result.update({'retained_publication_receipt_verified': True,
                       'publication_receipt_sha256': sha256(publication_receipt.read_bytes()).hexdigest(),
                       'publication_registry': published.get('registry'),
                       'publication_readback': published['readback'],
                       'release_source_revision': receipt.get('source_revision'),
                       'release_operation_id': receipt.get('operation_id'),
                       'release_state': receipt.get('state')})
    return result


def public_summary(report, artifact):
    """Publish an allow-listed summary with explicit synthetic identity aliases."""
    criterion_aliases = {K1: 'SYNTHETIC-K1', K2: 'SYNTHETIC-K2'}
    evaluations = []
    for item in report['criterion_evaluations']:
        evaluations.append({'criterion': criterion_aliases[item['criterion']],
            'status': item['status'], 'reason': item['reason'],
            'execution_evidence': [{'receipt': 'SYNTHETIC-RECEIPT-A', 'action': 'SYNTHETIC-A',
                                   'report': 'SYNTHETIC-REPORT-A', 'observed_revision': 'SYNTHETIC-RA'}
                                  for _ in item['execution_evidence']],
            'assessed_truth': 'SYNTHETIC-TRUTH-RA'})
    return {'qualification': report['qualification'], 'artifact_provenance': artifact,
            'loaded_product_module': 'installed-wheel:forge/runtime/dynamic_mission.py',
            'separate_process_store_reopen': report['separate_process_store_reopen'],
            'population': {'classification': 'ISOLATED_SYNTHETIC_ONLY',
                           'mission': 'SYNTHETIC-MISSION', 'runtime': 'SYNTHETIC-RUNTIME'},
            'canonical_terminal_evidence': {'action': 'SYNTHETIC-A', 'correlation': 'SYNTHETIC-CORRELATION-A',
                'receipt': 'SYNTHETIC-RECEIPT-A', 'report': 'SYNTHETIC-REPORT-A',
                'outcome': report['canonical_terminal_evidence']['outcome'],
                'observed_controls': ['SYNTHETIC-K1-CONTROL'],
                'unexecuted_controls': ['SYNTHETIC-K2-CONTROL']},
            'criterion_evaluations': evaluations, 'runner_result': report['runner_result'],
            'runner_decisions': report['runner_decisions'],
            'planner_invocations': report['planner_invocations'],
            'successor_planner_invocations': report['successor_planner_invocations'],
            'logical_submissions': len(report['logical_submissions']),
            'desired_behavior_assertions': report['desired_behavior_assertions'],
            'actual_defect': report['actual_defect'],
            'limitations': ['External identity, Codex subprocess answers and typed ExecutionHost evidence are fixtures.',
                           'No real provider generation, EP HTTP qualification or live autonomy acceptance.',
                           'Publication provenance is verified from retained release evidence, not a fresh registry query.']}


class CodexTransport:
    """Deterministic subprocess answer; the real provider parses this JSON."""
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
        append(self.root / 'provider-inputs.json', incoming)
        successor = any(item['kind'] == 'execution_evidence' for item in snapshot['evidence'])
        action_id = 'synthetic-action-b' if successor else 'synthetic-action-a'
        objective = ('Implement the missing access control for export.' if successor
                     else 'Implement report export data only; access control remains outstanding.')
        source_refs = [item['source_id'] for item in snapshot['evidence']]
        gap = None
        if successor:
            criterion = next(item for item in snapshot['criteria'] if item['criterion'] == K2)
            gap = {'classification': 'UNPROVEN_MISSION_CRITERION',
                   'criterion_ids': [criterion['criterion_id']],
                   'triggering_evidence_refs': source_refs,
                   'planning_snapshot_digest': snapshot['digest'],
                   'causal_objective': objective, 'mission_caused_by_action_ids': []}
        proposal = {'logical_action_id': action_id, 'scope': SCOPE, 'objective': objective,
                    'dependencies': [], 'write_scopes': ['synthetic_export'],
                    'expected_evidence': [CONTROL_K2 if successor else CONTROL_K1],
                    'validation_strategy': [CONTROL_K2 if successor else CONTROL_K1],
                    'priority': 1, 'postponed': False, 'human_gates': ['protected-delivery'],
                    'risk_inputs': ['scope-drift'], 'source_evidence_refs': source_refs,
                    'mission_gap': gap}
        output = Path(command[command.index('--output-last-message') + 1])
        output.write_text(json.dumps({'result': {'kind': 'proposals', 'proposals': [proposal]}}))
        return subprocess.CompletedProcess(command, 0, '{"type":"turn.completed"}\n', '')


class ExternalHost:
    """Canonical typed terminal receipt at the external ExecutionHost seam.

    The fixture explicitly supplies only K1 validation; K2 is neither executed
    nor claimed. This is external-fixture qualification, not live EP evidence.
    """
    def __init__(self, root, terminal):
        self.root, self.terminal = root, terminal
        self.config = SimpleNamespace(host_id='synthetic-ep', project_id='synthetic-project',
                                      repository_id='synthetic-repository',
                                      repository_identity='synthetic-repository')

    def preflight(self):
        return {'contract_version': '1.0', 'producer': {'id': 'synthetic-ep', 'version': 'fixture'}}

    def dispatch(self, request):
        run_id = 'synthetic-run-' + request.action_id
        append(self.root / 'host-submissions.json', {'action_id': request.action_id,
               'correlation_id': request.correlation_id, 'host_run_id': run_id})
        return ExecutionDispatch(request, run_id)

    def recover_dispatch(self, request):
        row = next((item for item in read(self.root / 'host-submissions.json', [])
                    if item['correlation_id'] == request.correlation_id), None)
        return None if row is None else ExecutionDispatch(request, row['host_run_id'])

    def retrieve_evidence(self, dispatch):
        request = dispatch.request
        if not self.terminal or request.action_id != 'synthetic-action-a':
            return None
        observed = {'fixture_contract': 'partial-export-delivery-v1',
                    'action_id': request.action_id, 'delivery_revision': 'b' * 40,
                    'observed_controls': [{'criterion': K1, 'command': CONTROL_K1, 'outcome': 'PASS'}],
                    'unimplemented_criteria': [K2], 'unexecuted_controls': [CONTROL_K2]}
        self.root.joinpath('external-host-observations.json').write_text(json.dumps(observed, indent=2) + '\n')
        repository = ExecutionRepositoryEvidence(
            request.mission_id, request.intent_id, request.intent_revision, request.action_id,
            request.runtime_prompt.id, request.correlation_id, dispatch.host_run_id,
            request.repository_id, 'b' * 40, 'synthetic-report-a', digest(observed),
        )
        return ExecutionHostEvidence(
            request.host_id, request.correlation_id, dispatch.host_run_id, 'synthetic-report-a',
            ExecutionEvidenceOutcome.COMPLETE, repository, validation_references=(CONTROL_K1,),
            execution_started_at='2026-09-18T10:00:00Z',
            execution_completed_at='2026-09-18T10:01:00Z',
            receipt_id='synthetic-receipt-a', execution_duration_ms=60_000,
        )


def open_runtime(root, terminal, stack):
    transport, host = CodexTransport(root), ExternalHost(root, terminal)
    checker = CodexCliSessionReadinessChecker(runner=transport, path_usable=lambda _: True)
    stack.enter_context(patch.object(dynamic_module.MacOSGeneratedUIDIdentityAdapter,
                                    'resolve', return_value=IDENTITY))
    stack.enter_context(patch.object(dynamic_module, 'CodexCliChatGPTSessionPlanningProvider',
                                    side_effect=lambda configuration: RealCodexProvider(
                                        configuration, runner=transport, readiness_checker=checker)))
    stack.enter_context(patch.object(dynamic_module.EngineeringPlatformExecutionHostFactory,
                                    'from_database', return_value=host))
    return stack.enter_context(InstalledDynamicMissionRuntime.open(str(root), provider_id=PROVIDER_ID))


def prepare(root):
    assert not (root / 'instance').exists(), 'Refusing to overwrite an existing runtime'
    with RuntimeBootstrap(data_root=root, forge_version=version('forge-autonomy')).open() as database:
        operators = InstallationOperatorService(database, lambda: IDENTITY)
        context = operators.first_bind()
        security = PlanningProviderSecurityService(database, MacOSKeychainSecureStoreAdapter(), operators)
        security.configure(configuration_id='synthetic-config', provider_id=PROVIDER_ID,
            operator_context=context, authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
            provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
            executable_path='/usr/bin/false', adapter_version='codex-cli-chatgpt-session-v1',
            timeout_seconds=10, input_token_bound=16000, context_token_bound=20000, output_token_bound=4000)
    with ExitStack() as stack:
        runtime = open_runtime(root, False, stack)
        repository, context = runtime.repository, runtime.repository.operators.context()
        planning = ArchitecturePlanningEvidence((SCOPE,), ('synthetic_export',),
                    ('no work outside synthetic export',), ('scope-drift',), ('protected-delivery',),
                    ('synthetic-host',), 16000, 4000, '1')
        BusinessWorkspace.for_runtime(runtime.database, repository, context).approve(
            decision_id='synthetic-business-approval', candidate_id='synthetic-export-candidate',
            revision='1', scope=planning.scope, gates=planning.human_gates)
        ArchitectureWorkspace.for_runtime(runtime.database, repository, context).approve(
            decision_id='synthetic-architecture-approval', candidate_id='synthetic-export-candidate',
            revision='1', planning=planning)
        envelope = MissionPlanningEvidenceEnvelope.compose(repository, subject_id='synthetic-export-candidate',
            subject_revision='1', business_decision_id='synthetic-business-approval',
            architecture_decision_id='synthetic-architecture-approval', planning=planning)
        mission_id = runtime.database.allocate_next_mission_id(
            source='canonical-governance-envelope:' + envelope.digest, allocated_at='2026-09-18T10:00:00Z')
        mission = ArchitectureMission(mission_id, 'synthetic-export-candidate', 'Synthetic protected export',
            'Deliver report data and access control.', 'Provide a usable protected export.',
            'Synthetic qualification only.', 'synthetic-architecture-approval', 'synthetic-recommendation',
            (SCOPE,), ('no work outside synthetic export',), (K1, K2), ('external boundaries are fixtures',),
            ('synthetic-host',), ('synthetic-export',), (RequiredDiscipline.PLATFORM_ARCHITECTURE,),
            ('scope-drift',), ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING)
        runtime.admit(mission, envelope)
        initial = RepositoryTruthSnapshot('synthetic-initial-truth', 'synthetic-repository', 'a' * 40,
            '2026-09-18T09:59:00Z', (RepositoryTruthEvidence('synthetic-initial-revision', 'git_commit',
                'a' * 40, 'repository://synthetic-repository/' + 'a' * 40, digest('synthetic-initial')),))
        result = runtime.start(mission_id, initial)
        assert result.status == 'WAITING_FOR_EVIDENCE', result
        root.joinpath('population.json').write_text(json.dumps({'mission_id': mission_id,
            'classification': 'ISOLATED_SYNTHETIC_ONLY', 'runtime_id': result.runtime_id}, indent=2) + '\n')
        print(json.dumps({'phase': 'prepare', 'status': result.status, 'actions': result.action_ids}))


def terminal(root):
    population = read(root / 'population.json', {})
    assert population.get('classification') == 'ISOLATED_SYNTHETIC_ONLY', 'Not a synthetic fixture runtime'
    with ExitStack() as stack:
        runtime = open_runtime(root, True, stack)
        result = runtime.resume(population['mission_id'])
        state = runtime.states.get(population['mission_id'])
        criteria = {item['criterion']: item for item in state.completion['criteria']}
        planner_inputs = read(root / 'provider-inputs.json', [])
        report = {'qualification': 'INSTALLED_COMPOSITION_WITH_EXTERNAL_TRANSPORT_FIXTURES',
            'distribution': version('forge-autonomy'), 'non_editable': not bool(
                json.loads(distribution('forge-autonomy').read_text('direct_url.json') or '{}').get('dir_info', {}).get('editable')),
            'loaded_dynamic_runtime': dynamic_module.__file__,
            'separate_process_store_reopen': True, 'population': population,
            'external_observed_controls': [CONTROL_K1], 'external_unexecuted_controls': [CONTROL_K2],
            'canonical_terminal_evidence': state.execution_evidence,
            'criterion_evaluations': list(criteria.values()), 'runner_result': result.status,
            'runner_decisions': [entry['reason'] for entry in state.state_history],
            'planner_invocations': len(planner_inputs),
            'successor_planner_invocations': sum(any(item['kind'] == 'execution_evidence'
                for item in incoming['snapshot']['evidence']) for incoming in planner_inputs),
            'logical_submissions': read(root / 'host-submissions.json', []),
            'expected': {'K2': 'UNSATISFIED', 'mission_complete': False, 'successor_planner_invoked': True},
            'actual_defect': {'K2_proven_without_K2_observation': criteria[K2]['status'] == 'PROVEN',
                'mission_completed': result.status == 'COMPLETED',
                'successor_planning_absent': len(planner_inputs) == 1}}
        report['desired_behavior_assertions'] = {
            'mission_not_completed_after_partial_action': result.status != 'COMPLETED',
            'K2_not_proven_without_observed_support': criteria[K2]['status'] != 'PROVEN',
            'actual_successor_planner_invocation': report['successor_planner_invocations'] > 0}
        root.joinpath('root-cause-evidence.json').write_text(json.dumps(report, indent=2) + '\n')
        summary = public_summary(report, read(root / 'artifact-provenance.public.json', {}))
        root.joinpath('root-cause-summary.public.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2), flush=True)
        failures = [name for name, passed in report['desired_behavior_assertions'].items() if not passed]
        assert not failures, 'Partial-action Mission regression failed: ' + ', '.join(failures)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('all', 'prepare', 'terminal'), default='all')
    parser.add_argument('--output-dir', type=Path, help='Fresh fixture/output directory; defaults to a new temporary directory')
    parser.add_argument('--wheel', type=Path, help='Optional exact installed wheel bytes for provenance verification')
    parser.add_argument('--publication-receipt', type=Path, help='Optional retained Forge release receipt to verify')
    args = parser.parse_args()
    root = (args.output_dir or Path(tempfile.mkdtemp(prefix='forge-criterion-regression-'))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.phase == 'prepare':
        prepare(root)
    elif args.phase == 'terminal':
        terminal(root)
    else:
        assert not (root / 'instance').exists(), 'Use a fresh output directory, never a product data root'
        provenance = artifact_provenance(args.wheel, args.publication_receipt)
        root.joinpath('artifact-provenance.public.json').write_text(json.dumps(provenance, indent=2) + '\n')
        statuses = {}
        for phase in ('prepare', 'terminal'):
            completed = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()),
                                        '--phase', phase, '--output-dir', str(root)],
                                       check=False, capture_output=True, text=True)
            root.joinpath(phase + '.raw.log').write_text(completed.stdout + completed.stderr)
            statuses[phase] = completed.returncode
            root.joinpath('subprocess-exit-codes.json').write_text(json.dumps(statuses, indent=2) + '\n')
            summary = read(root / 'root-cause-summary.public.json', None)
            if summary is not None:
                summary['subprocess_exit_codes'] = statuses
                root.joinpath('root-cause-summary.public.json').write_text(json.dumps(summary, indent=2) + '\n')
                print(json.dumps(summary, indent=2), flush=True)
            if completed.returncode:
                print(json.dumps({'phase': phase, 'regression_exit_code': completed.returncode,
                                  'public_summary': 'root-cause-summary.public.json',
                                  'private_raw_log': phase + '.raw.log'}), flush=True)
                return completed.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
