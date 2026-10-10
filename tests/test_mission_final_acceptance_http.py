"""Actual chat/intake/release/EP completion and scoped HTTP/CLI end acceptance."""
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
from jsonschema import Draft202012Validator

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "forge/api/mission-final-acceptance-v1.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)

from test_workset_release_chain import chain
from test_mission_concept_readiness import driver
from forge.advisory_grant import project_scope
from forge.candidate_decision_grant import signer
from forge.governed_continuation import _mission_subject_revision
from forge.mission_final_acceptance_contract import CONTRACT
from forge.mission_final_acceptance_grant import MissionFinalAcceptanceGrant
from forge.mission_final_acceptance_service import BASE
from forge.server_runtime import existing_instance


def provision(root, runtime):
    instance = existing_instance(root / 'runtime')
    scope = project_scope(root / 'runtime', instance.instance_id)
    grant = MissionFinalAcceptanceGrant(root / 'runtime', instance.instance_id)
    actor = signer(root / 'runtime', instance.instance_id, 'solo', ('READ',))['operator_id']
    data = chain.utils.fixture._read(root / 'release-case.private.json')
    subjects = [{'mission_id': mission_id, 'subject_revision': _mission_subject_revision(runtime.states.get(mission_id))}
                for mission_id in data['mission_ids']]
    common = dict(principal_id=actor, project_id=scope['project_id'], repository_id=scope['repository_id'],
                  profile_id='solo', missions=subjects, maximum_acceptances=2,
                  expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    accept = grant.issue(**common, permissions=['READ', 'ACCEPT'], token_path=root / 'accept.private')
    grant.issue(**common, permissions=['READ'], token_path=root / 'accept-read.private')
    return grant, accept


def command(detail, operation_id):
    package = detail['package']
    return {'contract_version': CONTRACT, 'operation_id': operation_id,
            **{key: package[key] for key in ('instance_id', 'project_id', 'repository_id', 'mission_id')},
            'package_digest': detail['package_digest'], 'reason': 'Accepteer het naïeve ontwerpresultaat met bewezen vóórwaarden en criteria.',
            'confirm': True}


class MissionFinalAcceptanceHTTPTests(unittest.TestCase):
    def test_real_http_accept_a_then_cli_accept_b_preserve_existing_runtime_chain(self):
        ready, _ = driver.cases()
        receipts = []
        ep_requests = []
        original_counter = chain.utils._count_ep_http_requests
        def capture_counter(server):
            observed = original_counter(server)
            ep_requests.append(observed)
            return observed
        with patch.object(chain.utils, '_count_ep_http_requests', capture_counter), TemporaryDirectory() as temporary:
            root = Path(temporary) / 'final-acceptance-a-b'
            def phase(root, scenario, name, endpoint):
                if not name.startswith('accept-'):
                    return chain.phase(root, scenario, name, endpoint)
                index = int(name[-1]) - 1
                with ExitStack() as stack:
                    runtime = chain.utils._open(root, stack, effect_scenario=scenario)
                    if index == 0:
                        provision(root, runtime)
                    data = chain.utils.fixture._read(root / 'release-case.private.json')
                    mission_id = data['mission_ids'][index]
                    before_decisions = runtime.database._connection.execute('SELECT count(*) FROM governance_decisions').fetchone()[0]
                    before_provider = len(chain.utils.fixture._read(root / 'provider-inputs.private.json', []))
                    before_chat = len((root / 'provider-requests.private.jsonl').read_text().splitlines())
                    before_ep = len(ep_requests[0])
                    with ready.qual.http(root) as port:
                        token = root / 'accept.private'
                        for old in ('release.private', 'admin.private', 'owner.private'):
                            if (root / old).exists():
                                self.assertEqual(403, ready.call(port, root / old, 'GET', BASE + '/capability')[0])
                        status, capability = ready.call(port, token, 'GET', BASE + '/capability')
                        self.assertEqual(200, status, capability)
                        VALIDATOR.validate(capability)
                        self.assertTrue(capability['acceptance_supported'])
                        status, detail = ready.call(port, token, 'GET', BASE + '/' + mission_id)
                        self.assertEqual(200, status, detail)
                        VALIDATOR.validate(detail)
                        self.assertTrue(detail['acceptance_supported'], detail)
                        self.assertTrue(detail['package']['result']['completion_proven'])
                        self.assertTrue(detail['package']['result']['objective'])
                        self.assertTrue(detail['package']['result']['summary'])
                        self.assertTrue(detail['package']['result']['criteria_results'][0]['evidence_references'])
                        self.assertEqual('business_owner', detail['package']['required_role'])
                        request = command(detail, 'accept-result-' + str(index + 1))
                        VALIDATOR.validate(request)
                        self.assertEqual(403, ready.call(port, root / 'accept-read.private', 'POST',
                            BASE + '/' + mission_id + '/accept', request)[0])
                        self.assertEqual(before_decisions, runtime.database._connection.execute('SELECT count(*) FROM governance_decisions').fetchone()[0])
                        if index == 0:
                            status, accepted = ready.call(port, token, 'POST', BASE + '/' + mission_id + '/accept', request)
                            self.assertEqual(200, status, accepted)
                            status, replay = ready.call(port, token, 'POST', BASE + '/' + mission_id + '/accept', request)
                            self.assertEqual(200, status, replay)
                            self.assertEqual(accepted['original_receipt'], replay['original_receipt'])
                        else:
                            from forge.mission_final_acceptance_cli import main
                            package_file = root / 'shown-final-package.private.json'
                            with patch('sys.stdout', new_callable=StringIO) as output:
                                code = main(['--data-root', str(root / 'runtime'), '--token-file', str(token),
                                    'show', '--mission-id', mission_id, '--output', str(package_file)])
                            self.assertEqual(0, code, output.getvalue())
                            with patch('sys.stdout', new_callable=StringIO) as output:
                                code = main(['--data-root', str(root / 'runtime'), '--token-file', str(token),
                                    'accept', '--shown-package', str(package_file), '--operation-id', request['operation_id'],
                                    '--reason', request['reason'], '--confirm'])
                            self.assertEqual(0, code, output.getvalue())
                            accepted = json.loads(output.getvalue())
                        VALIDATOR.validate(accepted)
                        self.assertEqual('COMPLETE', accepted['state'])
                        self.assertEqual('COMPLETED', accepted['original_receipt']['lifecycle'])
                        self.assertTrue(accepted['original_receipt']['dispatcher_released'])
                        self.assertEqual(mission_id, accepted['mission_id'])
                        self.assertEqual(200, ready.call(port, root / 'accept-read.private', 'GET',
                            BASE + '/' + mission_id + '/operations/' + request['operation_id'])[0])
                        receipts.append(accepted['original_receipt'])
                    self.assertEqual(before_decisions + 1, runtime.database._connection.execute('SELECT count(*) FROM governance_decisions').fetchone()[0])
                    self.assertEqual(before_provider, len(chain.utils.fixture._read(root / 'provider-inputs.private.json', [])))
                    self.assertEqual(before_chat, len((root / 'provider-requests.private.jsonl').read_text().splitlines()))
                    self.assertEqual(before_ep, len(ep_requests[0]))
                return chain.phase(root, scenario, 'read', endpoint)
            result = chain.flow(root, phase_runner=phase)
            self.assertEqual(['COMPLETED', 'COMPLETED'], [s['status'] for s in result[-1]['states']])
            self.assertEqual(2, result[-1]['allocations'])
            self.assertEqual(2, result[-1]['workset']['consumed_activations'])
            self.assertEqual(2, len(receipts))
