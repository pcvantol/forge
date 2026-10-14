import unittest
from copy import deepcopy
from forge.concept_advisory_contract import CONTRACT, FIELDS, request, result, digest


def example():
    source = {'concept_id': 'concept-one', 'revision': 1,
              'fields': {key: None for key in FIELDS}}
    source['fields']['purpose'] = 'Help volunteers coordinate local deliveries.'
    return {'contract_version': CONTRACT, 'instance_id': 'instance-one',
            'dossier_id': 'dossier-one', 'conversation_id': 'conversation-one',
            'operation_id': 'operation-one', 'turn_id': 'turn-one',
            'expected_revision': 0, 'briefing': source, 'briefing_digest': digest(source),
            'advisor_kind': 'BUSINESS', 'language': 'nl', 'message': 'Welke doelgroep eerst?',
            'transfer_policy_digest': digest({'profile': 'explicit-synthetic'})}


class ConceptContractTest(unittest.TestCase):
    def test_closed_source_unknowns_and_exact_language_preservation(self):
        for language in ['en', 'nl', 'de', 'fr', 'es']:
            value = example(); value['language'] = language
            actual, bound = request(value)
            self.assertEqual(actual, value); self.assertEqual(bound, digest(value))
            self.assertIsNone(actual['briefing']['fields']['users'])
        for mutation in ['extra', 'digest', 'revision', 'field', 'language', 'secret']:
            value = example()
            if mutation == 'extra': value['actor'] = 'owner'
            if mutation == 'digest': value['briefing_digest'] = digest({})
            if mutation == 'revision': value['expected_revision'] = True
            if mutation == 'field': value['briefing']['fields']['repository_path'] = '/tmp'
            if mutation == 'language': value['language'] = 'it'
            if mutation == 'secret': value['message'] = 'Bearer abcdefghijklmnop'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): request(value)

    def test_exact_change_binding_and_no_invented_source_or_effect(self):
        r, h = request(example()); ref = 'briefing:'+r['briefing_digest']
        admitted = {'request': r, 'request_digest': h, 'context': {'evidence_references': [ref]}}
        value = {'contract_version': CONTRACT, 'request_digest': h,
                 'briefing_digest': r['briefing_digest'], 'advisor_kind': 'BUSINESS', 'language': 'nl',
                 'answer': 'Begin met de lokale vrijwilligers; dit is een voorstel.',
                 'questions': ['Wie neemt de levering in ontvangst?'],
                 'assumptions': ['De doelgroep is nog niet bevestigd.'],
                 'changes': [{'field': 'users', 'before': None, 'proposed': 'Lokale vrijwilligers',
                              'reason': 'Een beperkte eerste doelgroep maakt feedback mogelijk.', 'references': [ref]}],
                 'applied': False}
        self.assertEqual(result(value, admitted), value)
        for mutation in ['before', 'reference', 'field', 'applied', 'extra']:
            bad = deepcopy(value)
            if mutation == 'before': bad['changes'][0]['before'] = 'invented'
            if mutation == 'reference': bad['changes'][0]['references'] = ['live-repo:invented']
            if mutation == 'field': bad['changes'][0]['field'] = 'shell'
            if mutation == 'applied': bad['applied'] = True
            if mutation == 'extra': bad['tool_calls'] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): result(bad, admitted)

    def test_lost_intent_retransmission_cannot_start_after_original_deadline(self):
        from importlib.util import spec_from_file_location,module_from_spec
        from pathlib import Path
        from unittest.mock import patch,MagicMock
        spec=spec_from_file_location('concept_http_deadline',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_installed_concept_advisory_http.py')
        module=module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module.time,'monotonic',return_value=11),patch.object(module.socket,'create_connection') as connect:
            with self.assertRaises(TimeoutError):module.resend_lost_original(1,b'header',b'body',10)
            connect.assert_not_called()
        client=MagicMock()
        with patch.object(module.time,'monotonic',side_effect=[9.0,10.1]),patch.object(module.socket,'create_connection') as connect:
            connect.return_value.__enter__.return_value=client
            with self.assertRaises(TimeoutError):module.resend_lost_original(1,b'header',b'body',10)
            client.sendall.assert_not_called()
        with patch.object(module.time,'monotonic',side_effect=[9.0,9.4]),patch.object(module.socket,'create_connection') as connect:
            connect.return_value.__enter__.return_value=client
            module.resend_lost_original(1,b'header',b'body',10)
            self.assertEqual(connect.call_args.kwargs['timeout'],1.0)
            self.assertAlmostEqual(client.settimeout.call_args.args[0],0.6)

    def test_original_private_capture_before_cleanup_and_primary_failure_retention(self):
        from importlib.util import spec_from_file_location,module_from_spec
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        spec=spec_from_file_location('concept_private_capture',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_installed_concept_advisory_http.py')
        module=module_from_spec(spec);spec.loader.exec_module(module)
        with TemporaryDirectory() as tmp:
            output=Path(tmp).resolve()
            with module.owned_scratch(output) as (_,root):
                root.mkdir();(root/'provider-requests.private.jsonl').write_bytes(b'synthetic original request\n')
            self.assertFalse(root.exists());self.assertEqual((output/'provider-requests.private.jsonl').read_bytes(),b'synthetic original request\n')
            original=RuntimeError('primary-probe')
            with patch.object(module.BINDING.CAPTURE,'retain',side_effect=OSError('secondary private capture failure')):
                with self.assertRaises(RuntimeError) as caught:
                    with module.owned_scratch(output) as (_,root):
                        root.mkdir();(root/'provider-requests.private.jsonl').write_bytes(b'synthetic\n');raise original
            self.assertIs(caught.exception,original);self.assertFalse(root.exists());self.assertTrue(original.__notes__)

    def test_known_initialization_backoff_only_one_healthy_original_retry(self):
        from importlib.util import spec_from_file_location,module_from_spec
        from pathlib import Path
        from unittest.mock import patch
        spec=spec_from_file_location('concept_original_busy',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_installed_concept_advisory_http.py')
        module=module_from_spec(spec);spec.loader.exec_module(module)
        busy=(503,{'error':{'code':'CONCEPT_RUNTIME_INITIALIZING'}})
        missing=(404,{'error':{'code':'CONCEPT_TURN_NOT_FOUND'}})
        for original in (missing,(200,{'original_turn':{'status':'UNCERTAIN'}}),(503,{'error':{'code':'CONCEPT_STORAGE_OR_PROVIDER_UNAVAILABLE'}})):
            with self.subTest(original=original),patch.object(module,'call',side_effect=[busy,original,busy]) as call,patch.object(module.time,'sleep') as wait:
                actual=module.submit_original(1,'token',example())
                if original==missing:
                    self.assertEqual(actual,busy);self.assertEqual(call.call_count,3);wait.assert_called_once_with(1)
                    self.assertEqual(call.call_args_list[0],call.call_args_list[2])
                else:
                    self.assertEqual(call.call_count,2);wait.assert_not_called()
