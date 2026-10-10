"""Noneditable installed scoped Mission-result acceptance and actual guard control."""
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
from importlib.metadata import distribution
from pathlib import Path
import argparse
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

SOURCE = Path(__file__).resolve().parents[2]


def run(args):
    import forge
    from forge._version import canonical_version
    wheel = Path(args.wheel).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if len(args.source_revision) != 40 or any(c not in '0123456789abcdef' for c in args.source_revision):
        raise ValueError('exact source revision required')
    actual_source = subprocess.run(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
        check=True, capture_output=True, text=True).stdout.strip()
    if actual_source != args.source_revision:
        raise ValueError('qualifier checkout does not match exact source revision')
    installed = Path(forge.__file__).resolve()
    if installed.is_relative_to(SOURCE / 'forge'):
        raise ValueError('qualification requires a noneditable installed product')
    direct = distribution('forge-autonomy').read_text('direct_url.json')
    if direct and json.loads(direct).get('dir_info', {}).get('editable'):
        raise ValueError('editable product cannot qualify')
    artifact = {'filename': wheel.name, 'sha256': sha256(wheel.read_bytes()).hexdigest(),
                'version': canonical_version()}
    receipt = {'qualification': 'INSTALLED_SCOPED_MISSION_FINAL_ACCEPTANCE_V1',
        'source_revision': args.source_revision, 'artifact': artifact, 'result': 'FAIL',
        'noneditable_product': True, 'product_files': {}, 'tests': 0, 'failures': [],
        'actual_guard_control': None, 'owned_scratch_removed': False,
        'boundary': 'real product governance/intake/runtime/HTTP/CLI/durable state; only external model/EP/OS boundaries fixtured; no live release or user installation'}
    with zipfile.ZipFile(wheel) as archive:
        payload = [name for name in archive.namelist() if name.startswith('forge/') and not name.endswith('/')]
        if not payload:
            raise ValueError('wheel lacks the product payload')
        for name in payload:
            if (installed.parent.parent / name).read_bytes() != archive.read(name):
                raise ValueError('installed product differs from exact wheel payload')
        receipt['wheel_payload_files_verified'] = len(payload)
    for name in ('governed_continuation.py', 'runtime/dynamic_mission.py', 'server_runtime.py',
                 'state/mission_state.py', 'worklist_conditions.py',
                 'api/mission-final-acceptance-v1.json', 'api/server-openapi-v1.json', 'api/server-postman-v1.json',
                 'mission_final_acceptance_contract.py', 'mission_final_acceptance_grant.py',
                 'mission_final_acceptance_package.py', 'mission_final_acceptance_journal.py',
                 'mission_final_acceptance_service.py', 'mission_final_acceptance_cli.py'):
        path = installed.parent / name
        if path.read_bytes() != (SOURCE / 'forge' / name).read_bytes():
            raise ValueError('installed production source does not match selected qualifier source')
        receipt['product_files'][name] = sha256(path.read_bytes()).hexdigest()
    try:
        with tempfile.TemporaryDirectory(prefix='forge-scoped-final-acceptance-') as temporary:
            scratch = Path(temporary)
            old_temp = tempfile.tempdir
            tempfile.tempdir = str(scratch)
            old_environment = os.environ.get('TMPDIR')
            os.environ['TMPDIR'] = str(scratch) + os.sep
            try:
                sys.path.insert(0, str(SOURCE / 'tests'))
                suite = unittest.TestSuite()
                modules = ['test_mission_final_acceptance_contract', 'test_mission_final_acceptance_grant',
                           'test_mission_final_acceptance_http', 'test_mission_final_acceptance_denials',
                           'test_mission_final_acceptance_process', 'test_mission_final_acceptance_dependencies',
                           'test_mission_final_acceptance_cli']
                with (output / 'installed-cases.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
                    for name in modules:
                        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name)))
                    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
                receipt['tests'] = result.testsRun
                receipt['failures'] = [{'test': str(test), 'traceback': details[-2000:]}
                                       for test, details in result.failures + result.errors]
                if not result.wasSuccessful() or result.skipped:
                    raise AssertionError('required installed final-acceptance cases failed or skipped')
                control = subprocess.run([sys.executable, '-I', str(SOURCE / 'scripts/qualification/control_mission_final_acceptance_guard.py')],
                    capture_output=True, text=True, timeout=30)
                (output / 'actual-guard-removal.log').write_text(control.stdout + control.stderr)
                detected = (control.returncode == 1 and 'FAILED (failures=1)' in control.stderr
                            and "self.assertEqual(before['a'], after['a'])" in control.stderr)
                receipt['actual_guard_control'] = {'exit': control.returncode, 'detected': detected,
                    'actual_production_guard_removed': True, 'failure_stage': 'unauthorized-terminal-state-change'}
                if not detected:
                    raise AssertionError('actual final-acceptance guard removal was not detected')
            finally:
                tempfile.tempdir = old_temp
                if old_environment is None:
                    os.environ.pop('TMPDIR', None)
                else:
                    os.environ['TMPDIR'] = old_environment
        receipt['owned_scratch_removed'] = not scratch.exists()
        receipt['result'] = 'SCOPED_MISSION_FINAL_ACCEPTANCE_PASS'
    except (AssertionError, OSError, ValueError, RuntimeError) as error:
        receipt['error_type'] = type(error).__name__
    receipt['logs'] = {path.name: sha256(path.read_bytes()).hexdigest()
                       for path in output.glob('*.log')}
    (output / 'installed-mission-final-acceptance.public.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return 0 if receipt['result'] == 'SCOPED_MISSION_FINAL_ACCEPTANCE_PASS' else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel', required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output-dir', required=True)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
