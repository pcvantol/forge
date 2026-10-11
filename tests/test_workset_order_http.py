"""Actual approved A/B/C/D, real A claim and scoped HTTP order amendment."""
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
import json
import unittest
from jsonschema import Draft202012Validator

from test_workset_release_chain import chain
from test_mission_concept_readiness import driver
from forge.advisory_grant import project_scope
from forge.candidate_decision_grant import signer
from forge.workset_order_contract import CONTRACT
from forge.workset_order_grant import WorksetOrderGrant
from forge.workset_order_service import BASE

VALIDATOR = Draft202012Validator(json.loads((Path(__file__).resolve().parents[1] /
                                          'forge/api/workset-order-v1.json').read_text()))


def provision(root, workset):
    from forge.server_runtime import existing_instance
    instance = existing_instance(root / 'runtime')
    scope = project_scope(root / 'runtime', instance.instance_id)
    grant = WorksetOrderGrant(root / 'runtime', instance.instance_id)
    actor = signer(root / 'runtime', instance.instance_id, 'solo', ('READ',))['operator_id']
    record = grant.issue(principal_id=actor, project_id=scope['project_id'], repository_id=scope['repository_id'],
        permissions=['READ', 'REORDER'], worksets=[{'workset_id': workset['definition']['workset_id'],
                                                 'definition_digest': workset['definition_digest']}],
        maximum_amendments=2, expires_at=(datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        token_path=root / 'order.private')
    return grant, record


def command(shown, operation_id='reorder-a-c-b'):
    package = shown['package']
    return {'contract_version': CONTRACT, 'operation_id': operation_id,
        **{k: package[k] for k in ('instance_id', 'project_id', 'repository_id', 'workset_id')},
        'package_digest': shown['package_digest'], 'package': package,
        'reason': 'Na de lopende missie eerst C; B behoudt dezelfde vóórwaarden.', 'confirm': True}


class WorksetOrderHTTPTests(unittest.TestCase):
    def test_real_http_preview_confirm_and_same_intent_preserve_original_release_and_claim(self):
        utils = chain.utils
        simulator = utils.EpSimulatorState(project_id=utils.PROJECT, repository_id=utils.fixture.SOURCE.repository_id,
            repository_identity=utils.fixture.SOURCE.github_repository, consumer_id=utils.CONSUMER,
            instance_id=utils.INSTANCE, bearer_token=utils.TOKEN,
            scenario=utils.EpSimulatorScenario(name='effect-read-only', effect_declaration_supported=True))
        server = utils.EpSimulatorServer(simulator)
        ready, _ = driver.cases()
        with TemporaryDirectory() as tmp, server:
            root = Path(tmp) / 'order'
            chain.chat_setup(root, server.base_url, 'effect-read-only', order_population=True, maximum_activations=3)
            initial = chain.phase(root, 'effect-read-only', 'tick', server.base_url, include_order=True)
            self.assertEqual(initial['allocations'], 4)
            self.assertEqual(initial['workset']['consumed_activations'], 1)
            self.assertEqual(len(simulator.submission_ids()), 1)
            with ExitStack() as stack:
                runtime = utils._open(root, stack, effect_scenario='effect-read-only')
                grant, record = provision(root, initial['workset'])
                key = initial['workset']['definition']['workset_id']
                order = [m['candidate_id'] for m in initial['workset']['definition']['members']]
                proposed = [order[0], order[2], order[1]]
                original = json.loads(json.dumps(initial['workset']))
                before = runtime.database._connection.execute('SELECT count(*) FROM governance_decisions').fetchone()[0]
                with ready.qual.http(root) as port:
                    status, shown = ready.call(port, root / 'order.private', 'POST', BASE + '/' + key + '/preview',
                        {'contract_version': CONTRACT, 'proposed_order': proposed})
                    self.assertEqual(status, 200, shown)
                    self.assertTrue(shown['reorder_supported'], shown)
                    VALIDATOR.validate(shown)
                    self.assertEqual(shown['package']['fixed_prefix'], 1)
                    read_workset = lambda: json.loads(runtime.database._connection.execute(
                        'SELECT document FROM approved_worksets WHERE workset_id=?', (key,)).fetchone()[0])
                    self.assertEqual(read_workset(), original)
                    body = command(shown)
                    status, applied = ready.call(port, root / 'order.private', 'POST', BASE + '/' + key + '/confirm', body)
                    self.assertEqual(status, 200, applied)
                    VALIDATOR.validate(applied)
                    self.assertEqual(applied['state'], 'APPLIED')
                    self.assertEqual(applied['current']['current_order'], proposed)
                    self.assertEqual(applied['current']['order_revision'], 1)
                    status, replay = ready.call(port, root / 'order.private', 'POST', BASE + '/' + key + '/confirm', body)
                    self.assertEqual(status, 200, replay)
                    self.assertEqual(replay['original_receipt'], applied['original_receipt'])
                    changed = read_workset()
                    for field in ('definition', 'definition_digest', 'authority_digest', 'decisions', 'release_commands',
                                  'release_capability', 'claims', 'consumed_activations', 'release', 'held', 'revoked'):
                        self.assertEqual(changed.get(field), original.get(field), field)
                    self.assertEqual(runtime.database._connection.execute('SELECT count(*) FROM governance_decisions').fetchone()[0], before + 2)
                    self.assertEqual(len(simulator.submission_ids()), 1)
                    status, old = ready.call(port, root / 'release.private', 'GET', '/v1/approved-workset-releases/operations/release-a-b')
                    self.assertEqual(status, 409, old)
                    self.assertEqual(old['error']['code'], 'WORKSET_ORDER_V2_REQUIRED')
                    grant.revoke(record['grant_id'])
                    from forge.approved_worklist import projection
                    read = projection(root / 'runtime', runtime.database.runtime_identity.runtime_id, key, 'own-read', include_order=True)
                    self.assertEqual(read['effective_order'], proposed)
                    self.assertIn('ORDER_AUTHORITY_NOT_CURRENT', read['items'][1]['blocking_reasons'])
