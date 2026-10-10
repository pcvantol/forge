"""Actual admitted A/B, released selector and EP-completed A, not seeded success."""
from contextlib import ExitStack, contextmanager
from pathlib import Path

from test_workset_release_chain import chain
from test_mission_concept_readiness import driver
from test_mission_final_acceptance_http import provision, command
from forge.mission_final_acceptance_service import BASE


@contextmanager
def pending_a(root, *, maximum_activations=2, approve_unreleased_c=False):
    utils = chain.utils
    scenario = 'effect-read-only'
    simulator = utils.EpSimulatorState(project_id=utils.PROJECT,
        repository_id=utils.fixture.SOURCE.repository_id, repository_identity=utils.fixture.SOURCE.github_repository,
        consumer_id=utils.CONSUMER, instance_id=utils.INSTANCE, bearer_token=utils.TOKEN,
        scenario=utils.EpSimulatorScenario(name=scenario, effect_declaration_supported=True))
    server = utils.EpSimulatorServer(simulator)
    requests = utils._count_ep_http_requests(server)
    ready, _ = driver.cases()
    with server:
        target, baseline, manifest = chain.chat_setup(root, server.base_url, scenario,
                                                     maximum_activations=maximum_activations, approve_unreleased_c=approve_unreleased_c)
        initial = chain.phase(root, scenario, 'tick', server.base_url)
        assert initial['allocations'] == (3 if approve_unreleased_c else 2) and initial['provider_invocations'] == 1
        assert len(simulator.submission_ids()) == 1
        submission = simulator.submission_ids()[0]
        payload = simulator.submitted_payload(submission)
        snapshot = utils._effect_target_snapshot(target)
        source_manifest = {name: snapshot[name] for name in manifest}
        revision, _ = utils._execute_effect_fixture(root, target, baseline, payload)
        simulator.complete(submission, delivery_revision=revision)
        readback, artifact = simulator.terminal_documents(submission)
        readback, result, terminal = utils.qualified_effect_result(payload, readback, artifact,
                                                                source_manifest=source_manifest)
        simulator.seed_terminal(submission, readback, terminal)
        simulator.seed_effect_result(submission, result)
        pending = chain.phase(root, scenario, 'tick', server.base_url)
        assert pending['states'][0]['status'] == 'AWAITING_APPROVAL'
        waiting = chain.phase(root, scenario, 'tick', server.base_url)
        assert waiting['states'][1]['status'] == 'APPROVED_PLANNABLE' and len(simulator.submission_ids()) == 1
        with ExitStack() as stack:
            runtime = utils._open(root, stack, effect_scenario=scenario)
            grant, record = provision(root, runtime)
            data = utils.fixture._read(root / 'release-case.private.json')
            with ready.qual.http(root) as port:
                mission = data['mission_ids'][0]
                status, detail = ready.call(port, root / 'accept.private', 'GET', BASE + '/' + mission)
                assert status == 200 and detail['acceptance_supported'], detail
                yield {'root': root, 'port': port, 'runtime': runtime, 'grant': grant, 'grant_record': record,
                       'mission_id': mission, 'mission_b': data['mission_ids'][1], 'request': command(detail, 'accept-a'),
                       'shown': detail, 'simulator': simulator, 'ep_requests': requests,
                       'endpoint': server.base_url, 'scenario': scenario, 'ready': ready, 'data': data}


def state_counts(case):
    runtime = case['runtime']
    return {'governance': runtime.database._connection.execute('SELECT count(*) FROM governance_decisions').fetchone()[0],
            'allocations': runtime.database._connection.execute('SELECT count(*) FROM mission_id_allocations').fetchone()[0],
            'a': runtime.states.get(case['mission_id']).to_dict() if hasattr(runtime.states.get(case['mission_id']), 'to_dict')
                else runtime.database.get_document('mission_state', case['mission_id']),
            'b': runtime.database.get_document('mission_state', case['mission_b']),
            'dispatcher': dict(runtime.database._connection.execute('SELECT * FROM dispatcher_state').fetchone()),
            'submissions': len(case['simulator'].submission_ids()),
            'ep_requests': len(case['ep_requests']),
            'provider_requests': (case['root'] / 'provider-requests.private.jsonl').read_bytes(),
            'planner_inputs': (case['root'] / 'provider-inputs.private.json').read_bytes()}
