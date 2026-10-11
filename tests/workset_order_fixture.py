"""Existing synthetic external adapters with real bounded canonical worksets."""
from contextlib import contextmanager, ExitStack
from pathlib import Path
import json

from test_workset_release_chain import chain
from test_mission_concept_readiness import driver
from test_workset_order_http import provision, command
from forge.workset_order_contract import CONTRACT
from forge.workset_order_service import BASE


@contextmanager
def order_case(root, *, c_depends_on_b=False, active_a=True, maximum_activations=3):
    utils = chain.utils; root = Path(root)
    simulator = utils.EpSimulatorState(project_id=utils.PROJECT, repository_id=utils.fixture.SOURCE.repository_id,
        repository_identity=utils.fixture.SOURCE.github_repository, consumer_id=utils.CONSUMER,
        instance_id=utils.INSTANCE, bearer_token=utils.TOKEN,
        scenario=utils.EpSimulatorScenario(name='effect-read-only', effect_declaration_supported=True))
    server = utils.EpSimulatorServer(simulator); requests = utils._count_ep_http_requests(server)
    ready, _ = driver.cases()
    with server:
        target, baseline, manifest = chain.chat_setup(root, server.base_url, 'effect-read-only', order_population=True,
                         c_depends_on_b=c_depends_on_b, maximum_activations=maximum_activations)
        initial = chain.phase(root, 'effect-read-only', 'tick' if active_a else 'read', server.base_url, include_order=True)
        with ExitStack() as stack:
            runtime = utils._open(root, stack, effect_scenario='effect-read-only')
            grant, record = provision(root, initial['workset'])
            key = initial['workset']['definition']['workset_id']
            order = [m['candidate_id'] for m in initial['workset']['definition']['members']]
            with ready.qual.http(root) as port:
                yield {'root': root, 'runtime': runtime, 'grant': grant, 'grant_record': record,
                    'key': key, 'order': order, 'proposed': [order[0], order[2], order[1]],
                    'initial': initial, 'port': port, 'ready': ready, 'endpoint': server.base_url,
                    'target': target, 'baseline': baseline, 'manifest': manifest,
                    'simulator': simulator, 'ep_requests': requests}


def call(case, method, suffix='', body=None, token='order.private'):
    return case['ready'].call(case['port'], case['root'] / token, method, BASE + '/' + case['key'] + suffix, body)


def shown(case):
    status, output = call(case, 'POST', '/preview', {'contract_version': CONTRACT, 'proposed_order': case['proposed']})
    assert status == 200, output
    return output


def counts(case):
    db = case['runtime'].database._connection
    return {'worksets': db.execute('SELECT document FROM approved_worksets ORDER BY workset_id').fetchall(),
        'states': db.execute('SELECT document FROM mission_state ORDER BY mission_id').fetchall(),
        'decisions': db.execute('SELECT document,digest FROM governance_decisions ORDER BY decision_id').fetchall(),
        'allocations': db.execute('SELECT * FROM mission_id_allocations').fetchall(),
        'ep_requests': len(case['ep_requests']),
        'provider_requests': (case['root'] / 'provider-requests.private.jsonl').read_bytes()}
