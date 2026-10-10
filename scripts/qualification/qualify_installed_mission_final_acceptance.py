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
import signal
import sys
import tempfile
import unittest
import time
import zipfile

SOURCE = Path(__file__).resolve().parents[2]


def stop_owned_worker(process):
    """A terminated leader does not imply that its owned process group ended."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def validate_worker_receipt(value, *, source_revision, product_version, modules, expected):
    fields = {'source_revision', 'product_version', 'modules', 'noneditable_product',
        'expected_tests', 'tests', 'failures', 'skipped', 'owned_scratch_removed', 'result'}
    if (type(value) is not dict or set(value) != fields
            or value['source_revision'] != source_revision or value['product_version'] != product_version
            or type(value['modules']) is not list or value['modules'] != modules
            or value['noneditable_product'] is not True or value['owned_scratch_removed'] is not True
            or type(value['expected_tests']) is not int or type(value['tests']) is not int
            or type(expected) is not int or not 1 <= expected <= 64
            or value['expected_tests'] != expected or value['tests'] != expected
            or type(value['failures']) is not list or value['failures'] != []
            or type(value['skipped']) is not list or value['skipped'] != []
            or value['result'] != 'SCOPED_FINAL_ACCEPTANCE_WORKER_PASS'):
        raise AssertionError('required isolated installed worker receipt malformed or incomplete')


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
            from forge.runtime.bootstrap import RuntimeBootstrap
            from forge.runtime.database import RUNTIME_SCHEMA_VERSION
            with RuntimeBootstrap(scratch / 'schema-proof', forge_version=canonical_version()).open() as database:
                receipt['runtime_readback'] = {'schema_version': database.metadata['schema_version'],
                    'product_version': database.metadata['forge_version']}
                if (receipt['runtime_readback']['schema_version'] != str(RUNTIME_SCHEMA_VERSION)
                        or receipt['runtime_readback']['product_version'] != artifact['version']):
                    raise AssertionError('installed runtime schema/product readback mismatch')
            old_temp = tempfile.tempdir
            tempfile.tempdir = str(scratch)
            old_environment = os.environ.get('TMPDIR')
            os.environ['TMPDIR'] = str(scratch) + os.sep
            try:
                sys.path.insert(0, str(SOURCE / 'tests'))
                groups = [
                    ['test_mission_final_acceptance_contract', 'test_mission_final_acceptance_grant',
                     'test_mission_final_acceptance_http', 'test_mission_final_acceptance_denials'],
                    ['test_mission_final_acceptance_process', 'test_mission_final_acceptance_dependencies',
                     'test_mission_final_acceptance_cli', 'test_mission_final_acceptance_worker_cleanup'],
                ]
                workers = []
                streams = []
                receipt['worker_receipts'] = []
                deadline = time.monotonic() + 390
                try:
                    for index, modules in enumerate(groups):
                        owned = scratch / ('worker-' + str(index))
                        owned.mkdir(mode=0o700)
                        prefix = output / ('installed-worker-' + str(index))
                        log = prefix.with_suffix('.controller.log').open('w')
                        streams.append(log)
                        expected = sum(unittest.defaultTestLoader.loadTestsFromModule(
                            importlib.import_module(name)).countTestCases() for name in modules)
                        command = [sys.executable, '-I', str(SOURCE / 'scripts/qualification/qualify_mission_final_acceptance_worker.py'),
                            '--source-revision', args.source_revision, '--product-version', artifact['version'],
                            '--scratch-root', str(owned), '--output-prefix', str(prefix)]
                        for name in modules:
                            command.extend(['--module', name])
                        workers.append((subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True), prefix, expected, modules))
                    for process, prefix, expected, modules in workers:
                        exit_code = process.wait(timeout=max(.1, deadline - time.monotonic()))
                        raw = prefix.with_suffix('.public.json').read_bytes()
                        completed = json.loads(raw)
                        if exit_code != 0:
                            raise AssertionError('required isolated installed worker process failed')
                        validate_worker_receipt(completed, source_revision=args.source_revision,
                            product_version=artifact['version'], modules=modules, expected=expected)
                        receipt['worker_receipts'].append({'sha256': sha256(raw).hexdigest(), 'receipt': completed})
                        receipt['tests'] += completed['tests']
                        receipt['failures'].extend(completed['failures'])
                finally:
                    for process, _, _, _ in workers:
                        stop_owned_worker(process)
                    for stream in streams:
                        stream.close()
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
    except (AssertionError, OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
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
