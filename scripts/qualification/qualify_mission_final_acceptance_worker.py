"""One isolated installed qualification process; no source or shared runtime writes."""
from contextlib import redirect_stdout, redirect_stderr
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

SOURCE = Path(__file__).resolve().parents[2]
MODULES = ('test_mission_final_acceptance_contract', 'test_mission_final_acceptance_grant',
    'test_mission_final_acceptance_http', 'test_mission_final_acceptance_denials',
    'test_mission_final_acceptance_process', 'test_mission_final_acceptance_dependencies',
    'test_mission_final_acceptance_cli', 'test_mission_final_acceptance_worker_cleanup')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', action='append', choices=MODULES, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--product-version', required=True)
    parser.add_argument('--scratch-root', required=True)
    parser.add_argument('--output-prefix', required=True)
    args = parser.parse_args()
    import forge
    from forge._version import canonical_version
    if Path(forge.__file__).resolve().is_relative_to(SOURCE / 'forge'):
        raise ValueError('worker requires installed product')
    direct = distribution('forge-autonomy').read_text('direct_url.json')
    if direct and json.loads(direct).get('dir_info', {}).get('editable'):
        raise ValueError('worker cannot use editable product')
    source = subprocess.run(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
        check=True, capture_output=True, text=True).stdout.strip()
    if source != args.source_revision or canonical_version() != args.product_version:
        raise ValueError('worker source/product binding mismatch')
    prefix = Path(args.output_prefix)
    receipt = {'source_revision': source, 'product_version': canonical_version(),
        'modules': args.module, 'noneditable_product': True, 'expected_tests': 0,
        'tests': 0, 'failures': [], 'skipped': [], 'owned_scratch_removed': False,
        'result': 'FAIL'}
    with tempfile.TemporaryDirectory(prefix='installed-cases-', dir=args.scratch_root) as temporary:
        old_temp, old_environment = tempfile.tempdir, os.environ.get('TMPDIR')
        tempfile.tempdir = temporary
        os.environ['TMPDIR'] = temporary + os.sep
        try:
            sys.path.insert(0, str(SOURCE / 'tests'))
            suite = unittest.TestSuite()
            with prefix.with_suffix('.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
                for name in args.module:
                    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name)))
                receipt['expected_tests'] = suite.countTestCases()
                result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            receipt['tests'] = result.testsRun
            receipt['failures'] = [{'test': str(test), 'traceback': details[-2000:]}
                for test, details in result.failures + result.errors]
            receipt['skipped'] = [{'test': str(test), 'reason': reason} for test, reason in result.skipped]
            if result.wasSuccessful() and not result.skipped and result.testsRun == receipt['expected_tests']:
                receipt['result'] = 'SCOPED_FINAL_ACCEPTANCE_WORKER_PASS'
        finally:
            tempfile.tempdir = old_temp
            if old_environment is None:
                os.environ.pop('TMPDIR', None)
            else:
                os.environ['TMPDIR'] = old_environment
    receipt['owned_scratch_removed'] = not Path(temporary).exists()
    prefix.with_suffix('.public.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return 0 if receipt['result'] == 'SCOPED_FINAL_ACCEPTANCE_WORKER_PASS' and receipt['owned_scratch_removed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
