"""Noneditable installed scoped workset retained activity read and actual guard control."""
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


from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location('installed_owning_worker_guards', SOURCE / 'scripts/qualification/qualify_installed_mission_final_acceptance.py')
shared = module_from_spec(spec); spec.loader.exec_module(shared)
stop_owned_worker = shared.stop_owned_worker
validate_worker_receipt = shared.validate_worker_receipt


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
    clean = subprocess.run(['git', '-C', str(SOURCE), 'diff', '--quiet', 'HEAD'], check=False)
    untracked = subprocess.run(['git', '-C', str(SOURCE), 'ls-files', '--others', '--exclude-standard',
                                '--', 'forge', 'tests', 'scripts/qualification'],
                               check=True, capture_output=True, text=True).stdout.strip()
    if clean.returncode != 0 or untracked:
        raise ValueError('installed qualification requires the complete committed source candidate')
    installed = Path(forge.__file__).resolve()
    if installed.is_relative_to(SOURCE / 'forge'):
        raise ValueError('qualification requires a noneditable installed product')
    direct = distribution('forge-autonomy').read_text('direct_url.json')
    if direct and json.loads(direct).get('dir_info', {}).get('editable'):
        raise ValueError('editable product cannot qualify')
    artifact = {'filename': wheel.name, 'sha256': sha256(wheel.read_bytes()).hexdigest(),
                'version': canonical_version()}
    receipt = {'qualification': 'INSTALLED_SCOPED_WORKSET_ACTIVITY_V1',
        'source_revision': args.source_revision, 'artifact': artifact, 'result': 'FAIL',
        'noneditable_product': True, 'product_files': {}, 'tests': 0, 'failures': [],
        'actual_guard_control': None, 'owned_scratch_removed': False,
        'boundary': 'real product governance/intake/runtime/HTTP/CLI/durable state; only external model/EP/OS boundaries fixtured; no live release or user installation'}
    scripts = {entry.name: entry.value for entry in distribution('forge-autonomy').entry_points}
    expected = {'forge-workset-activity': 'forge.workset_activity_cli:main',
                'forge-workset-activity-grant': 'forge.workset_activity_grant:main'}
    if any(scripts.get(name) != value for name, value in expected.items()):
        raise ValueError('supported installed activity console scripts unavailable')
    receipt['console_scripts'] = expected
    with zipfile.ZipFile(wheel) as archive:
        payload = [name for name in archive.namelist() if name.startswith('forge/') and not name.endswith('/')]
        if not payload:
            raise ValueError('wheel lacks the product payload')
        for name in payload:
            if (installed.parent.parent / name).read_bytes() != archive.read(name):
                raise ValueError('installed product differs from exact wheel payload')
        receipt['wheel_payload_files_verified'] = len(payload)
    for name in ('server_runtime.py', 'workset_activity_cursor.py', 'workset_activity_projection.py',
                 'workset_activity_grant.py', 'workset_activity_service.py', 'workset_activity_cli.py',
                 'api/workset-activity-v1.json', 'api/server-openapi-v1.json', 'api/server-postman-v1.json'):
        path = installed.parent / name
        if path.read_bytes() != (SOURCE / 'forge' / name).read_bytes():
            raise ValueError('installed production source does not match selected qualifier source')
        receipt['product_files'][name] = sha256(path.read_bytes()).hexdigest()
    try:
        with tempfile.TemporaryDirectory(prefix='forge-scoped-workset-activity-') as temporary:
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
                    ['test_workset_activity_cursor', 'test_workset_activity_bounds', 'test_mission_final_acceptance_worker_cleanup'],
                    ['test_workset_activity_http', 'test_workset_activity_edges'],
                    ['test_workset_activity_process', 'test_workset_activity_retained', 'test_workset_activity_chain'],
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
                            '--scratch-root', str(owned), '--output-prefix', str(prefix), '--case-family', 'workset-activity']
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
                            product_version=artifact['version'], modules=modules, expected=expected, result_label='SCOPED_WORKSET_ACTIVITY_WORKER_PASS')
                        receipt['worker_receipts'].append({'sha256': sha256(raw).hexdigest(), 'receipt': completed})
                        receipt['tests'] += completed['tests']
                        receipt['failures'].extend(completed['failures'])
                finally:
                    for process, _, _, _ in workers:
                        stop_owned_worker(process)
                    for stream in streams:
                        stream.close()
                control = subprocess.run([sys.executable, '-I', str(SOURCE / 'scripts/qualification/control_workset_activity_snapshot.py')],
                    capture_output=True, text=True, timeout=30)
                (output / 'actual-guard-removal.log').write_text(control.stdout + control.stderr)
                detected = (control.returncode == 1 and 'FAILED (failures=1)' in control.stderr
                            and 'snapshot drift was accepted' in control.stderr)
                receipt['actual_guard_control'] = {'exit': control.returncode, 'detected': detected,
                    'actual_production_guard_removed': True, 'failure_stage': 'mixed-read-snapshot-accepted'}
                if not detected:
                    raise AssertionError('actual workset-activity snapshot guard removal was not detected')
            finally:
                tempfile.tempdir = old_temp
                if old_environment is None:
                    os.environ.pop('TMPDIR', None)
                else:
                    os.environ['TMPDIR'] = old_environment
        receipt['owned_scratch_removed'] = not scratch.exists()
        receipt['result'] = 'SCOPED_WORKSET_ACTIVITY_PASS'
    except (AssertionError, OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        receipt['error_type'] = type(error).__name__
    receipt['logs'] = {path.name: sha256(path.read_bytes()).hexdigest()
                       for path in output.glob('*.log')}
    (output / 'installed-workset-activity.public.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return 0 if receipt['result'] == 'SCOPED_WORKSET_ACTIVITY_PASS' else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel', required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output-dir', required=True)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
