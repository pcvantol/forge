"""Actual exited-leader cleanup and strict qualification-proof boundary regressions."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
import copy
import json
import os
import signal
import subprocess
import sys
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location('actual_installed_acceptance_qualifier',
    SOURCE / 'scripts/qualification/qualify_installed_mission_final_acceptance.py')
qualifier = module_from_spec(SPEC)
SPEC.loader.exec_module(qualifier)


def process_state(pid):
    return subprocess.run(['ps', '-p', str(pid), '-o', 'stat='],
        capture_output=True, text=True, check=False).stdout.strip()


class MissionFinalAcceptanceWorkerCleanupTests(unittest.TestCase):
    def test_exited_worker_leader_cannot_leave_its_actual_owned_child_running(self):
        code = "import subprocess,sys; child=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(30)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); print(child.pid,flush=True); sys.exit(1)"
        worker = subprocess.Popen([sys.executable, '-I', '-c', code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            out, err = worker.communicate(timeout=10)
            self.assertEqual(1, worker.returncode, err)
            child = int(out.strip())
            before = process_state(child)
            self.assertTrue(before and not before.startswith('Z'), before)
            qualifier.stop_owned_worker(worker)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                state = process_state(child)
                if not state or state.startswith('Z'):
                    break
                time.sleep(.02)
            self.assertTrue(not state or state.startswith('Z'), 'owned child survived leader-exit cleanup: ' + state)
        finally:
            try:
                os.killpg(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            worker.wait(timeout=10)

    def test_closed_typed_worker_receipt_denies_truthy_false_counts_skips_and_missing_proof(self):
        expected = dict(source_revision='a' * 40, product_version='2.13.0',
            modules=['test_mission_final_acceptance_contract'], expected=4)
        valid = {'source_revision': expected['source_revision'], 'product_version': '2.13.0',
            'modules': expected['modules'], 'expected_tests': 4, 'tests': 4,
            'noneditable_product': True, 'owned_scratch_removed': True,
            'failures': [], 'skipped': [], 'result': 'SCOPED_FINAL_ACCEPTANCE_WORKER_PASS'}
        qualifier.validate_worker_receipt(valid, **expected)
        mutations = [('noneditable_product', v) for v in ('false', 1, [], False, None)]
        mutations += [('owned_scratch_removed', v) for v in ('false', 1, [], False, None)]
        mutations += [('expected_tests', True), ('tests', 4.0), ('tests', 3),
            ('source_revision', 'b' * 40), ('product_version', '2.12.2'),
            ('modules', []), ('failures', ['failure']), ('skipped', ['skip']),
            ('failures', {}), ('skipped', {}), ('result', 'FAIL')]
        for key, value in mutations:
            with self.subTest(field=key, value=value):
                broken = copy.deepcopy(valid)
                broken[key] = value
                with self.assertRaises(AssertionError):
                    qualifier.validate_worker_receipt(broken, **expected)
        for key in valid:
            broken = copy.deepcopy(valid)
            broken.pop(key)
            with self.assertRaises(AssertionError):
                qualifier.validate_worker_receipt(broken, **expected)
        with self.assertRaises(AssertionError):
            qualifier.validate_worker_receipt({**valid, 'unexpected': True}, **expected)
