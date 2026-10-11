"""Real A→C→B through the existing approved workset/runtime/EP simulator."""
from contextlib import ExitStack, redirect_stdout
from importlib.util import spec_from_file_location, module_from_spec
from io import StringIO
from pathlib import Path
import json
import sys

SOURCE = Path(__file__).resolve().parents[2]
if '--source-development' in sys.argv:
    sys.path.insert(0, str(SOURCE))
spec = spec_from_file_location('existing_release_chain', SOURCE / 'scripts/qualification/qualify_workset_release_chain.py')
chain = module_from_spec(spec); spec.loader.exec_module(chain)
utils = chain.utils


def flow(root, *, ceiling=3, revoke_order=False, observe=None):
    sys.path.insert(0, str(SOURCE / 'tests'))
    from test_workset_order_http import provision, command
    from test_mission_concept_readiness import driver
    from forge.workset_order_cli import main as order_cli
    from forge.workset_order_service import BASE
    scenario = 'effect-read-only'
    simulator = utils.EpSimulatorState(project_id=utils.PROJECT, repository_id=utils.fixture.SOURCE.repository_id,
        repository_identity=utils.fixture.SOURCE.github_repository, consumer_id=utils.CONSUMER,
        instance_id=utils.INSTANCE, bearer_token=utils.TOKEN,
        scenario=utils.EpSimulatorScenario(name=scenario, effect_declaration_supported=True))
    server = utils.EpSimulatorServer(simulator)
    ep_requests = utils._count_ep_http_requests(server)
    ready, _ = driver.cases(); records = []
    def phase(name):
        record = chain.phase(root, scenario, name, server.base_url, include_order=True)
        records.append(record)
        if observe is not None:
            observe(name, record)
        return record
    with server:
        target, baseline, manifest = chain.chat_setup(root, server.base_url, scenario,
            order_population=True, maximum_activations=ceiling)
        initial = phase('tick')
        assert initial['allocations'] == 4 and initial['workset']['consumed_activations'] == 1
        with ExitStack() as stack:
            runtime = utils._open(root, stack, effect_scenario=scenario)
            grant, grant_record = provision(root, initial['workset'])
            key = initial['workset']['definition']['workset_id']
            arguments = ['--data-root', str(root / 'runtime'), '--token-file', str(root / 'order.private')]
            preview = root / 'order-preview.private.json'
            with redirect_stdout(StringIO()) as output:
                code = order_cli(arguments + ['preview', '--positions', '2', '1', '--output', str(preview)])
            assert code == 0, output.getvalue()
            shown = json.loads(preview.read_text())
            original = initial['workset']; old_ids = [m['candidate_id'] for m in original['definition']['members']]
            assert shown['package']['proposed_order'] == [old_ids[0], old_ids[2], old_ids[1]]
            before = (len(ep_requests), (root / 'provider-requests.private.jsonl').read_bytes())
            with ready.qual.http(root) as port:
                status, receipt = ready.call(port, root / 'order.private', 'POST', BASE + '/' + key + '/confirm', command(shown))
                assert status == 200, receipt
                assert (len(ep_requests), (root / 'provider-requests.private.jsonl').read_bytes()) == before
            if observe is not None:
                observe('order-confirmed', initial)
            if revoke_order:
                grant.revoke(grant_record['grant_id'])
        for started, index in enumerate((1, 3, 2), 1):
            current = initial if started == 1 else phase('tick')
            assert current['allocations'] == 4 and current['workset']['consumed_activations'] == started
            assert len(simulator.submission_ids()) == started
            submission = simulator.submission_ids()[-1]; payload = simulator.submitted_payload(submission)
            assert payload['mission_id'] == current['states'][index - 1]['mission_id']
            snapshot = utils._effect_target_snapshot(target); source_manifest = {name: snapshot[name] for name in manifest}
            revision, _ = utils._execute_effect_fixture(root, target, baseline, payload)
            simulator.complete(submission, delivery_revision=revision)
            readback, artifact = simulator.terminal_documents(submission)
            readback, result, terminal = utils.qualified_effect_result(payload, readback, artifact, source_manifest=source_manifest)
            simulator.seed_terminal(submission, readback, terminal); simulator.seed_effect_result(submission, result)
            pending = phase('tick'); assert pending['states'][index - 1]['status'] == 'AWAITING_APPROVAL'
            phase('tick'); assert len(simulator.submission_ids()) == started
            accepted = phase('accept-' + str(index)); assert accepted['states'][index - 1]['status'] == 'COMPLETED'
            if revoke_order or started == ceiling < 3:
                blocked = phase('tick')
                assert len(simulator.submission_ids()) == started
                assert blocked['workset']['consumed_activations'] == started
                expected = 'ORDER_AUTHORITY_NOT_CURRENT' if revoke_order else 'ACTIVATION_LIMIT_EXHAUSTED'
                assert expected in blocked['read']['items'][started]['blocking_reasons'], blocked['read']
                assert blocked['states'][1]['status'] == 'APPROVED_PLANNABLE'
                return records
        idle = phase('tick')
        assert idle['read']['continuation']['state'] == 'IDLE'
        assert idle['allocations'] == 4 and idle['workset']['consumed_activations'] == 3
        assert len(idle['workset']['claims']) == 3 and len(simulator.submission_ids()) == 3
        assert len(idle['workset']['order_amendments']) == 1
        # Four admitted subjects × two approvals, two original workset decisions,
        # two order decisions, three existing progression-policy assignments and
        # three actual final acceptances. Every canonical identity occurs once.
        assert initial['governance_decisions'] == 11
        assert idle['governance_decisions'] == 18, [(r['phase'], r['governance_decisions']) for r in records]
        data = utils.fixture._read(root / 'release-case.private.json')
        with ExitStack() as stack:
            runtime = utils._open(root, stack, effect_scenario=scenario)
            assert runtime.states.get(data['unreleased_mission_id']).status.value == 'APPROVED_PLANNABLE'
        return records
