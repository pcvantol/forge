"""Real provider adapter with only the external model process replaced."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.request import Request, urlopen
from test_advisory_http import qual
import test_mission_concept_contract as concept_tests
from forge.advisory_contract import digest
from forge.advisory_service import AdvisoryService
from forge.mission_concept_provider import MissionConceptProvider
from forge.server_runtime import existing_instance
from forge.worklist_control import control_runtime
from forge.mission_concept_service import MissionConceptService
from forge.mission_concept_contract import CONTRACT
from jsonschema import Draft202012Validator


class MissionConceptProviderTests(unittest.TestCase):
    def test_real_transport_new_schema_and_current_policy(self):
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             'forge/api/mission-concepts-v1.json').read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / 'concept'
            grant = qual.configure(root)
            executable = root / 'external-provider'
            raw = executable.read_text()
            raw = raw.replace("assert v['contract_version']=='forge-advisory-conversation/v1'",
                              "assert v['contract_version']=='forge-chat-first-mission/v1'")
            raw = raw.replace("assert schema['properties']['applied']=={'const':False}",
                              "assert schema['properties']['definition']['additionalProperties'] is False")
            start = raw.index("response={'contract_version'")
            end = raw.index("if fault=='inject'", start)
            definition = concept_tests.MissionConceptContractTests().output()['definition']
            # This advice-only grant has no owner component authority: preserve
            # a meaningful unresolved content proposal, never invent path bounds.
            definition['components']=[]
            definition['questions']=['Which configured project component should contain the portal?']
            raw = raw[:start] + ('response={"contract_version":v["contract_version"],'
                  '"request_digest":v["request_digest"],"definition":' + repr(definition) + '}\n') + raw[end:]
            executable.write_text(raw)
            with qual.http(root) as port:
                token = 'Bearer ' + (root / 'alice.private').read_text().strip()
                principal = grant.authorize(token, 'conversation-alice')
                context, _ = AdvisoryService(root / 'runtime', grant, qual.utils.fixture.PROVIDER).context(principal)
                context['concept_dependency_references'] = []
                request = {'instance_id': existing_instance(root / 'runtime').instance_id,
                           'project_id': principal.project_id, 'repository_id': principal.repository_id,
                           'advisor_kind': 'BUSINESS', 'objective': 'Build a client portal for invoices.',
                           'selected_sources': []}
                admitted = {'request': request, 'request_digest': digest(request),
                            'context': context, 'session_id': 'concept-session',
                            'invocation_id': 'concept-invocation'}
                def authorize():
                    grant.authorize(token, 'conversation-alice')
                with control_runtime(root / 'runtime') as runtime:
                    from forge.planner.codex_cli_session import _policy_digest
                    provider = MissionConceptProvider(runtime, qual.utils.fixture.PROVIDER)
                    policy, _, generation_digest = provider.prepare(admitted, [])
                    admitted['provider'] = {'policy_digest': _policy_digest(policy),
                                            'generation_digest': generation_digest}
                    outcomes = []
                    result = provider.invoke(admitted, [], authorize, outcomes.append)
                    self.assertEqual(result['execution'], 'CONFIRMED')
                    self.assertEqual(result['output']['definition'], definition)
                    self.assertEqual(len(outcomes), 1)
                    self.assertIsNone(result['error_code'])
                self.assertEqual(len((root / 'provider-requests.private.jsonl').read_text().splitlines()), 1)
                service = MissionConceptService(root / 'runtime', grant, qual.utils.fixture.PROVIDER)
                _, context_revision = service.context(principal)
                turn = {**request, 'contract_version': CONTRACT,
                        'turn_id': 'explicit-concept-turn',
                        'conversation_id': 'conversation-alice', 'expected_revision': 0,
                        'context_revision': context_revision}
                first = service.submit(token, turn)
                validator.validate(turn)
                validator.validate(first)
                self.assertEqual(first['original_turn']['status'], 'COMPLETE')
                self.assertEqual(first['original_turn']['outcome']['output']['definition'], definition)
                restarted = MissionConceptService(root / 'runtime', grant, qual.utils.fixture.PROVIDER)
                replay = restarted.submit(token, turn)
                validator.validate(replay)
                self.assertFalse(replay['recorded'])
                self.assertEqual(replay['original_turn'], first['original_turn'])
                self.assertEqual(restarted.read(token, 'conversation-alice')['consumed_turns'], 1)
                self.assertEqual(len((root / 'provider-requests.private.jsonl').read_text().splitlines()), 2)
                from urllib.error import HTTPError
                for query in ('cursor=-1', 'limit=0', 'cursor=0&cursor=1', 'foreign_filter=all'):
                    with self.subTest(query=query), self.assertRaises(HTTPError) as denied:
                        urlopen(Request('http://127.0.0.1:' + str(port) +
                            '/v1/mission-concepts/catalog?' + query,
                            headers={'Authorization': token}))
                    self.assertEqual(denied.exception.code, 400)
                    denied.exception.close()
                catalog = restarted.catalog(token)
                validator.validate(catalog)
                self.assertEqual(len(catalog['items']), 1)
                self.assertEqual(catalog['items'][0]['state'], 'CONCEPT')
                self.assertFalse(catalog['items'][0]['approval_supported'])
                self.assertEqual(catalog['items'][0]['definition'], definition)
                bob = 'Bearer ' + (root / 'bob.private').read_text().strip()
                self.assertEqual(restarted.catalog(bob)['items'], [])
                from forge.advisory_contract import AdvisoryConflict
                with self.assertRaises(AdvisoryConflict):
                    restarted.catalog(token, expected_snapshot='sha256:' + 'b' * 64)
                with urlopen(Request('http://127.0.0.1:' + str(port) +
                                     '/v1/mission-concepts/conversation-alice/turns',
                                     data=json.dumps(turn).encode(), method='POST',
                                     headers={'Authorization': token,
                                              'Content-Type': 'application/json'})) as response:
                    http_replay = json.load(response)
                self.assertFalse(http_replay['recorded'])
                self.assertEqual(http_replay['original_turn'], first['original_turn'])
                validator.validate(http_replay)
                self.assertEqual(len((root / 'provider-requests.private.jsonl').read_text().splitlines()), 2)
                with urlopen(Request('http://127.0.0.1:' + str(port) +
                                     '/v1/mission-concepts/capability',
                                     headers={'Authorization': token})) as response:
                    capability = json.load(response)
                self.assertEqual(capability['contract_version'], CONTRACT)
                validator.validate(capability)
                self.assertFalse(capability['approval_supported'])
                self.assertEqual(capability['retained_principal_consumed_turns'], 1)
                with urlopen(Request('http://127.0.0.1:' + str(port) +
                                     '/v1/mission-concepts/conversation-alice',
                                     headers={'Authorization': token})) as response:
                    history = json.load(response)
                self.assertEqual(history['turns'][0]['outcome']['output']['definition'], definition)
                validator.validate(history)
                self.assertEqual(len((root / 'provider-requests.private.jsonl').read_text().splitlines()), 2)
