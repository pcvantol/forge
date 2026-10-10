"""Genuine separate OS-process crashes, response loss and same-intent recovery."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import signal
import subprocess
import sys
import time
import unittest

from mission_final_acceptance_fixture import pending_a, state_counts
from forge.mission_final_acceptance_journal import FinalAcceptanceJournal
from forge.workspace_review_grant import _write_private
from forge.mission_final_acceptance_service import BASE

DRIVER = Path(__file__).resolve().parents[1] / 'scripts/qualification/qualify_mission_final_acceptance_process.py'


def child(root, action, stage='normal'):
    import forge
    source = Path(__file__).resolve().parents[1]
    development = ['--source-development'] if Path(forge.__file__).resolve().is_relative_to(source / 'forge') else []
    return [sys.executable, '-I', str(DRIVER), *development,
            '--root', str(root), '--action', action, '--stage', stage]


class MissionFinalAcceptanceProcessTests(unittest.TestCase):
    def test_real_process_crash_at_each_effect_boundary_and_lost_response_resume_original(self):
        for stage in ('before-canonical', 'after-canonical', 'after-terminal', 'after-dispatcher', 'lost-response'):
            with self.subTest(stage=stage), TemporaryDirectory() as temporary, pending_a(Path(temporary) / stage) as case:
                root = case['root']
                _write_private(root / 'accept-command.private.json', json.dumps(case['request']).encode())
                before = state_counts(case)
                process = subprocess.Popen(child(root, 'accept', stage), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    if stage == 'lost-response':
                        out, err = process.communicate(timeout=20)
                        self.assertEqual(23, process.returncode, out + err)
                    else:
                        deadline = time.monotonic() + 15
                        marker = root / 'accept-boundary.ready.private'
                        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                            time.sleep(.02)
                        if not marker.exists():
                            out, err = process.communicate(timeout=2)
                            self.fail('actual effect boundary not observed: ' + out + err)
                        observed = json.loads(marker.read_text())
                        self.assertEqual(process.pid, observed['pid'])
                        self.assertEqual(stage, observed['stage'])
                        os.kill(process.pid, signal.SIGKILL)
                        process.communicate(timeout=5)
                        self.assertEqual(-signal.SIGKILL, process.returncode)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)
                partial = state_counts(case)
                read = subprocess.run(child(root, 'read'), capture_output=True, text=True, timeout=15)
                if stage == 'before-canonical':
                    # The original intent may or may not yet be retained, but
                    # no read may create it or complete anything.
                    self.assertIn(read.returncode, (0, 1), read.stdout + read.stderr)
                else:
                    self.assertEqual(0, read.returncode, read.stdout + read.stderr)
                    output = json.loads(read.stdout)['output']
                    self.assertEqual('COMPLETE' if stage == 'lost-response' else 'PENDING', output['state'])
                self.assertEqual(partial, state_counts(case))
                recovered = subprocess.run(child(root, 'accept'), capture_output=True, text=True, timeout=15)
                self.assertEqual(0, recovered.returncode, recovered.stdout + recovered.stderr)
                output = json.loads(recovered.stdout)
                self.assertNotEqual(process.pid, output['pid'])
                receipt = output['output']['original_receipt']
                self.assertEqual(case['request']['operation_id'], receipt['original_operation_id'])
                self.assertEqual('COMPLETE', output['output']['state'])
                final = state_counts(case)
                self.assertEqual(before['governance'] + 1, final['governance'])
                self.assertEqual(before['allocations'], final['allocations'])
                self.assertEqual(before['b'], final['b'])
                self.assertEqual(before['ep_requests'], final['ep_requests'])
                self.assertEqual(before['provider_requests'], final['provider_requests'])
                self.assertEqual(before['planner_inputs'], final['planner_inputs'])
                replay = subprocess.run(child(root, 'accept'), capture_output=True, text=True, timeout=15)
                self.assertEqual(0, replay.returncode, replay.stdout + replay.stderr)
                self.assertEqual(receipt, json.loads(replay.stdout)['output']['original_receipt'])
                self.assertEqual(final, state_counts(case))

    def test_process_revoke_after_canonical_denies_recovery_and_new_keys_without_write_reads(self):
        with TemporaryDirectory() as temporary, pending_a(Path(temporary) / 'cold-revoked') as case:
            root = case['root']
            _write_private(root / 'accept-command.private.json', json.dumps(case['request']).encode())
            before = state_counts(case)
            process = subprocess.Popen(child(root, 'accept', 'after-canonical'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                marker = root / 'accept-boundary.ready.private'
                deadline = time.monotonic() + 15
                while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(marker.exists())
                self.assertEqual(process.pid, json.loads(marker.read_text())['pid'])
                process.kill()
                process.communicate(timeout=5)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
            case['grant'].revoke(case['grant_record']['grant_id'])
            partial = state_counts(case)
            self.assertEqual(before['governance'] + 1, partial['governance'])
            self.assertEqual(before['a'], partial['a'])
            self.assertEqual(before['b'], partial['b'])
            for action in ('read', 'accept'):
                result = subprocess.run(child(root, action), capture_output=True, text=True, timeout=15)
                self.assertEqual(0 if action == 'read' else 1, result.returncode, result.stdout + result.stderr)
                self.assertEqual(partial, state_counts(case))

    def test_real_concurrent_acceptance_is_one_canonical_decision_and_prompt_conflict(self):
        with TemporaryDirectory() as temporary, pending_a(Path(temporary) / 'concurrent') as case:
            root = case['root']
            _write_private(root / 'accept-command.private.json', json.dumps(case['request']).encode())
            first = subprocess.Popen(child(root, 'accept', 'after-canonical'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                marker = root / 'accept-boundary.ready.private'
                deadline = time.monotonic() + 15
                while not marker.exists() and first.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(marker.exists())
                partial = state_counts(case)
                start = time.monotonic()
                status, rejected = case['ready'].call(case['port'], root / 'accept.private', 'POST',
                    BASE + '/' + case['mission_id'] + '/accept',
                    {**case['request'], 'operation_id': 'second-concurrent-operation'})
                self.assertEqual(409, status, rejected)
                self.assertLess(time.monotonic() - start, 2)
                self.assertEqual(partial, state_counts(case))
                (root / 'accept-boundary.continue.private').write_text('continue original')
                out, err = first.communicate(timeout=15)
                self.assertEqual(0, first.returncode, out + err)
                accepted = json.loads(out)['output']
                final = state_counts(case)
                self.assertEqual(partial['governance'], final['governance'])
                self.assertEqual('COMPLETE', accepted['state'])
                self.assertEqual(partial['b'], final['b'])
                replay = subprocess.run(child(root, 'accept'), capture_output=True, text=True, timeout=15)
                self.assertEqual(0, replay.returncode, replay.stdout + replay.stderr)
                self.assertEqual(accepted['original_receipt'], json.loads(replay.stdout)['output']['original_receipt'])
                self.assertEqual(final, state_counts(case))
            finally:
                if first.poll() is None:
                    first.kill()
                    first.communicate(timeout=5)
