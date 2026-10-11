"""Real crash, duplicate/replacement intent, concurrency and read-only recovery."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import signal
import socket
import subprocess
import sys
import time
import unittest

from workset_order_fixture import order_case, counts, shown, command
from forge.workspace_review_grant import _write_private

DRIVER = Path(__file__).resolve().parents[1] / 'scripts/qualification/qualify_workset_order_process.py'


def child(root, action, stage='normal', *, token='order.private', operation=None):
    import forge
    source = Path(__file__).resolve().parents[1]
    development = ['--source-development'] if Path(forge.__file__).resolve().is_relative_to(source / 'forge') else []
    result = [sys.executable, '-I', str(DRIVER), *development, '--root', str(root),
              '--action', action, '--stage', stage, '--token-file', token]
    return result + (['--operation-id', operation] if operation else [])


def wait_boundary(process, root, stage):
    marker = root / 'order-boundary.ready.private'
    deadline = time.monotonic() + 15
    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(.02)
    if not marker.exists():
        out, err = process.communicate(timeout=2)
        raise AssertionError('actual order boundary not observed: ' + out + err)
    packet = json.loads(marker.read_text())
    assert packet == {'pid': process.pid, 'stage': stage}


def cleanup(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=5)


class WorksetOrderProcessTests(unittest.TestCase):
    def test_real_http_lost_body_recovers_original_receipt_without_new_effect(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'lost-http-body') as case:
            from workset_order_fixture import call
            from forge.workset_order_service import BASE
            request = command(shown(case)); raw = json.dumps(request).encode()
            token = (case['root'] / 'order.private').read_text().strip()
            path = BASE + '/' + case['key'] + '/confirm'
            with socket.create_connection(('127.0.0.1', case['port']), timeout=15) as connection:
                header = ('POST ' + path + ' HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer ' + token +
                          '\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(raw)) +
                          '\r\nConnection: close\r\n\r\n').encode()
                connection.sendall(header + raw); received = b''
                while b'\r\n\r\n' not in received:
                    piece = connection.recv(1); self.assertTrue(piece); received += piece
                self.assertIn(b'200', received.splitlines()[0])
                # Close before consuming any response body; the receipt is lost.
            status, read = call(case, 'GET', '/operations/' + request['operation_id'])
            self.assertEqual(status, 200, read)
            self.assertEqual(read['state'], 'APPLIED')
            before = counts(case)
            status, replay = call(case, 'POST', '/confirm', request)
            self.assertEqual(status, 200, replay)
            self.assertEqual(replay['original_receipt'], read['original_receipt'])
            self.assertEqual(counts(case), before)

    def test_real_runtime_b_claim_and_order_confirmation_have_one_fixed_prefix(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'claim-race') as case:
            from test_workset_release_chain import chain
            root = case['root']; simulator = case['simulator']; utils = chain.utils
            submission = simulator.submission_ids()[0]; payload = simulator.submitted_payload(submission)
            target = case['target']
            snapshot = utils._effect_target_snapshot(target)
            revision, _ = utils._execute_effect_fixture(root, target, case['baseline'], payload)
            simulator.complete(submission, delivery_revision=revision)
            readback, artifact = simulator.terminal_documents(submission)
            readback, result, terminal = utils.qualified_effect_result(payload, readback, artifact,
                source_manifest={name: snapshot[name] for name in case['manifest']})
            simulator.seed_terminal(submission, readback, terminal); simulator.seed_effect_result(submission, result)
            pending = chain.phase(root, 'effect-read-only', 'tick', case['endpoint'], include_order=True)
            self.assertEqual(pending['states'][0]['status'], 'AWAITING_APPROVAL', pending['states'][0])
            chain.phase(root, 'effect-read-only', 'accept-1', case['endpoint'], include_order=True)
            request = command(shown(case)); _write_private(root / 'order-command.private.json', json.dumps(request).encode())
            process = subprocess.Popen(child(root, 'tick', 'after-runtime-claim') + ['--endpoint', case['endpoint']],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                wait_boundary(process, root, 'after-runtime-claim')
                contender = subprocess.run(child(root, 'confirm'), capture_output=True, text=True, timeout=15)
                self.assertEqual(contender.returncode, 1, contender.stdout + contender.stderr)
                _write_private(root / 'order-boundary.continue.private', b'continue')
                out, err = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, out + err)
                result = json.loads(out)['output']
                self.assertEqual(result['workset']['consumed_activations'], 2)
                self.assertNotIn('order_amendments', result['workset'])
                self.assertEqual(len(simulator.submission_ids()), 2)
                before = counts(case)
                stale = subprocess.run(child(root, 'confirm'), capture_output=True, text=True, timeout=15)
                self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
                self.assertEqual(counts(case), before)
                from workset_order_fixture import call
                from forge.workset_order_contract import CONTRACT
                status, output = call(case, 'POST', '/preview', {'contract_version': CONTRACT,
                                                              'proposed_order': case['proposed']})
                self.assertEqual(status, 409, 'actual claimed B cannot be moved by a fresh preview')
                self.assertEqual(counts(case), before)
            finally:
                cleanup(process)

    def test_actual_crash_at_each_order_effect_and_response_loss_restore_same_intent(self):
        for stage in ('before-intent', 'after-intent', 'after-business', 'after-architecture', 'after-apply', 'lost-response'):
            with self.subTest(stage=stage), TemporaryDirectory() as tmp, order_case(Path(tmp) / stage) as case:
                root = case['root']; request = command(shown(case))
                _write_private(root / 'order-command.private.json', json.dumps(request).encode())
                process = subprocess.Popen(child(root, 'confirm', stage), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    if stage == 'lost-response':
                        out, err = process.communicate(timeout=20)
                        self.assertEqual(process.returncode, 23, out + err)
                    else:
                        wait_boundary(process, root, stage)
                        os.kill(process.pid, signal.SIGKILL)
                        process.communicate(timeout=5)
                finally:
                    cleanup(process)
                partial = counts(case)
                read = subprocess.run(child(root, 'read'), capture_output=True, text=True, timeout=15)
                self.assertEqual(read.returncode, 1 if stage == 'before-intent' else 0, read.stdout + read.stderr)
                self.assertEqual(counts(case), partial, 'GET must never finish any pending stage')
                restored = subprocess.run(child(root, 'confirm'), capture_output=True, text=True, timeout=20)
                self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
                receipt = json.loads(restored.stdout)['output']['original_receipt']
                self.assertEqual(receipt['order_revision'], 1)
                final = counts(case)
                replay = subprocess.run(child(root, 'confirm'), capture_output=True, text=True, timeout=15)
                self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
                self.assertEqual(json.loads(replay.stdout)['output']['original_receipt'], receipt)
                self.assertEqual(counts(case), final)

    def test_actual_partial_revocation_new_key_replacement_grant_and_reads_cannot_complete(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'revoked') as case:
            root = case['root']; request = command(shown(case))
            _write_private(root / 'order-command.private.json', json.dumps(request).encode())
            process = subprocess.Popen(child(root, 'confirm', 'after-business'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                wait_boundary(process, root, 'after-business')
                os.kill(process.pid, signal.SIGKILL); process.communicate(timeout=5)
            finally:
                cleanup(process)
            case['grant'].revoke(case['grant_record']['grant_id'])
            record = case['grant_record']; fields = {k: record[k] for k in
                ('principal_id', 'project_id', 'repository_id', 'worksets', 'maximum_amendments', 'expires_at')}
            case['grant'].issue(**fields, permissions=['READ', 'REORDER'], token_path=root / 'replacement.private')
            before = counts(case)
            read = subprocess.run(child(root, 'read', token='replacement.private'), capture_output=True, text=True, timeout=15)
            self.assertEqual(read.returncode, 0, read.stdout + read.stderr)
            self.assertEqual(json.loads(read.stdout)['output']['state'], 'PENDING')
            for token, operation in (('order.private', None), ('replacement.private', None), ('replacement.private', 'new-key')):
                result = subprocess.run(child(root, 'confirm', token=token, operation=operation), capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(counts(case), before)
            from forge.approved_worklist import ApprovedWorklistService, candidate_source
            from forge.lifecycle import RecommendationLifecycleStore
            with RecommendationLifecycleStore(candidate_source(root / 'runtime')) as lifecycle:
                service = ApprovedWorklistService(case['runtime'], lifecycle)
                original = service._get(case['key'])
                with self.assertRaisesRegex(ValueError, 'cannot move to another'):
                    service.propose({**original['definition'], 'workset_id': 'replacement-workset'})
            self.assertEqual(counts(case), before)

    def test_real_contender_is_prompt_conflict_with_one_order_revision(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'concurrent') as case:
            root = case['root']; request = command(shown(case))
            _write_private(root / 'order-command.private.json', json.dumps(request).encode())
            process = subprocess.Popen(child(root, 'confirm', 'after-intent'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                wait_boundary(process, root, 'after-intent'); started = time.monotonic()
                contender = subprocess.run(child(root, 'confirm', operation='contender'), capture_output=True, text=True, timeout=15)
                self.assertEqual(contender.returncode, 1, contender.stdout + contender.stderr)
                self.assertLess(time.monotonic() - started, 5)
                _write_private(root / 'order-boundary.continue.private', b'continue')
                out, err = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, out + err)
                self.assertEqual(json.loads(out)['output']['original_receipt']['order_revision'], 1)
            finally:
                cleanup(process)
