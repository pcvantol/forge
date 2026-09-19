"""Source-pinned EP v1.4 fixture over real loopback HTTP and the normal adapter.

The payload shape is the EP producer contract at 13691e4502c239e03558a9c79538ae9b7387938f
(submission_service.write_terminal_evidence / producer_readback); the fixture is
synthetic and does not claim host execution. Private qualification additionally
exercises the owning EP serializer and authenticated production HTTP handler.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest
from urllib.parse import unquote

from forge.completion import MissionCompletionEvaluator
from forge.models.execution_host import ExecutionDispatch
from forge.models.mission_completion import CanonicalExecutionEvidenceReference
from forge.scheduler.ep_http_adapter import EngineeringPlatformHttpExecutionHost
from tests import test_ep_http_adapter as existing
from tests.test_substantive_mission_completion import contract_evidence, mission, truth


class CriterionEpHttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = existing.EngineeringPlatformHttpExecutionHostTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.artifact = json.loads(self.fixture.artifact)
        self.readback = self.fixture.readback
        self.paths = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.paths.append(unquote(self.path))
                # This credential is only the existing synthetic fixture value.
                if self.headers.get('Authorization') != 'Bearer ' + owner.fixture.config.bearer_token:
                    self.send_error(401)
                    return
                route = unquote(self.path)
                if route == '/v1/producer-compatibility':
                    raw = json.dumps(owner.fixture.compatible).encode()
                elif route == '/v1/projects/forge/submissions/submission-fixture':
                    raw = json.dumps(owner.readback).encode()
                elif route == '/v1/projects/forge/artifacts/terminal-evidence:run-fixture':
                    raw = owner.raw
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)
        self.fixture.config = replace(self.fixture.config,
            base_url=f'http://127.0.0.1:{self.server.server_port}', allow_loopback_http=True)
        self.fixture._seed_binding()
        self.host = EngineeringPlatformHttpExecutionHost(self.fixture.config, self.fixture.database)
        self._publish()

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _publish(self):
        self.raw = json.dumps(self.artifact, sort_keys=True, separators=(',', ':')).encode() + b'\n'
        self.readback['evidence']['terminal_artifact']['digest'] = 'sha256:' + sha256(self.raw).hexdigest()

    def _retrieve(self):
        return self.host.retrieve_evidence(ExecutionDispatch(self.fixture.request, 'run-fixture'))

    def _assert_no_criterion_proof(self, evidence):
        approved = replace(mission(), id='mission-fixture')
        repository = evidence.repository_evidence
        reference = CanonicalExecutionEvidenceReference(evidence.receipt_id, repository.action_id,
            evidence.report_id, repository.repository_revision, repository.content_digest,
            candidate_revision=repository.candidate_revision)
        realized = asdict(evidence)
        realized['outcome'] = evidence.outcome.value
        result = MissionCompletionEvaluator().evaluate(approved, truth(reference).to_dict(), (realized,),
            contract_evidence(approved, (reference,), ()))
        self.assertFalse(result.all_required_criteria_proven)
        self.assertTrue(all(item.status.value == 'UNSATISFIED' for item in result.criteria))
        self.assertTrue(all(not item.observations for item in result.criteria))

    def test_delivery_candidate_and_digest_survive_exact_http_readback(self):
        self.artifact['references']['validation'] = [{'command': 'python3 -m unittest', 'result': 'PASS'}]
        self._publish()
        evidence = self._retrieve()
        self.assertEqual(evidence.repository_evidence.repository_revision, '1' * 40)
        self.assertEqual(evidence.repository_evidence.candidate_revision, 'c' * 40)
        self.assertEqual(evidence.repository_evidence.content_digest, 'sha256:' + sha256(self.raw).hexdigest())
        self.assertEqual(evidence.validation_references, ('python3 -m unittest',))
        self.assertEqual(self.paths, ['/v1/producer-compatibility',
            '/v1/projects/forge/submissions/submission-fixture',
            '/v1/projects/forge/artifacts/terminal-evidence:run-fixture'])
        self._assert_no_criterion_proof(evidence)

    def test_misleading_provider_pass_and_malformed_entries_never_become_control_authority(self):
        self.artifact['references']['validation'] = [
            {'command': 'ALL CRITERIA SATISFIED', 'result': 'PASS'},
            {'command': 13, 'result': 'PASS'}, 'PASS', {'result': 'PASS'},
        ]
        self._publish()
        evidence = self._retrieve()
        self.assertEqual(evidence.validation_references, ('ALL CRITERIA SATISFIED',))
        self.assertNotIn('control_results', asdict(evidence))
        self._assert_no_criterion_proof(evidence)

    def test_validation_collection_wrong_type_fails_closed(self):
        self.artifact['references']['validation'] = {'command': 'PASS', 'result': 'PASS'}
        self._publish()
        with self.assertRaisesRegex(ValueError, 'validation references'):
            self._retrieve()

    def test_implementation_candidate_remains_distinct_from_later_assurance_candidate(self):
        self.artifact['repository']['candidate'] = 'd' * 40
        self._publish()
        evidence = self._retrieve()
        self.assertEqual(evidence.repository_evidence.candidate_revision, 'd' * 40)
        self.assertEqual(self.artifact['assurance']['profile']['candidate_sha'], 'c' * 40)

    def test_delivery_mismatch_fails_even_with_valid_artifact_digest(self):
        self.artifact['delivery']['revision'] = 'd' * 40
        self._publish()
        with self.assertRaises(ValueError):
            self._retrieve()

    def test_changed_artifact_bytes_fail_before_any_criterion_interpretation(self):
        self.raw += b' '
        with self.assertRaisesRegex(ValueError, 'DIGEST_MISMATCH'):
            self._retrieve()


if __name__ == '__main__':
    unittest.main()
