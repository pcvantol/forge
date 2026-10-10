"""Exact noneditable wheel qualification of project-free installation detach."""
import argparse
from importlib.util import spec_from_file_location, module_from_spec
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]
spec = spec_from_file_location('detach_installed_utils', SOURCE/'scripts/qualification/qualify_installed_http_successor.py')
utils = module_from_spec(spec); spec.loader.exec_module(utils)


def run(args):
    artifact = utils._installed_wheel(args.wheel, source_revision=args.source_revision, verify_source=True)
    output = args.output_dir.resolve()
    if not args.child:
        if output.exists(): raise ValueError('qualification output must be fresh')
        output.mkdir()
        command = [sys.executable, '-I', str(Path(__file__).resolve()), '--wheel', str(args.wheel.resolve()),
                   '--source-revision', args.source_revision, '--output-dir', str(output), '--child']
        if args.failure_control: command.append('--failure-control')
        result = subprocess.run(command, cwd=output, env=utils._child_env(output/'isolated'), capture_output=True, text=True, timeout=120)
        (output/'child.private.log').write_text(result.stdout+result.stderr)
        receipt = json.loads((output/'installed-installation-detach.public.json').read_text())
        assert receipt['artifact'] == artifact and receipt['source_revision'] == args.source_revision
        print(json.dumps({'result':receipt['result'], 'case_count':receipt['case_count'], 'failure_control_detected':receipt['failure_control_detected']}))
        return result.returncode
    receipt = dict(qualification='INSTALLED_INSTALLATION_PEER_DETACH_V1', artifact=artifact,
                   source_revision=args.source_revision, result='FAIL', case_count=0,
                   failure_control_detected=False, expected_failure_control=args.failure_control,
                   limitations=['External portable OS identity fixture; native identity has separate source tests.',
                                'Real isolated CLI/HTTP/storage/restart receipts; no live instance or installer orchestration.'],
                   cleanup={'owned_runtime_home_credentials_scratch_removed':False})
    try:
        sys.path.insert(0, str(SOURCE/'tests'))
        module = __import__('test_installation_peer_detach')
        stream = StringIO()
        if args.failure_control:
            # Disable the actual positive transition. The ordinary positive test
            # must detect the missing effect; a forced exception is not evidence.
            from forge.installation_pairing import InstallationPairingService
            with patch.object(InstallationPairingService, 'detach', return_value={}):
                suite = unittest.TestSuite([module.InstallationDetachTests('test_atomic_receipt_restart_exact_retry_and_read_only_status')])
                result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
            receipt['failure_control_detected'] = not result.wasSuccessful()
        else:
            suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
            if result.wasSuccessful() and result.testsRun >= 11: receipt['result'] = 'INSTALLATION_DETACH_PASS'
        receipt['case_count'] = result.testsRun
        (output/'tests.private.log').write_text(stream.getvalue())
    finally:
        for name in ('home','scratch','config'):
            path = output/'isolated'/name
            if path.exists(): shutil.rmtree(path)
        receipt['cleanup']['owned_runtime_home_credentials_scratch_removed'] = True
        (output/'installed-installation-detach.public.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return 0 if receipt['result'] == 'INSTALLATION_DETACH_PASS' else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--wheel',type=Path,required=True); p.add_argument('--source-revision',required=True)
    p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--child',action='store_true')
    p.add_argument('--failure-control',action='store_true')
    raise SystemExit(run(p.parse_args()))
