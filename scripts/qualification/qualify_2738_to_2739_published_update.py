"""Disposable exact published Forge 2.7.38 -> 2.7.39 controller matrix."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser()
for name in ('old-wheel', 'target-wheel', 'receipt', 'controller'):
    parser.add_argument('--' + name, type=Path, required=True)
for name in ('old-sha256', 'target-sha256', 'receipt-sha256', 'controller-sha256',
             'target-source', 'controller-source'):
    parser.add_argument('--' + name, required=True)
args = parser.parse_args()
if sys.version_info[:2] != (3, 14):
    raise RuntimeError('published controller matrix requires Python 3.14')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

for file, expected in ((args.old_wheel, args.old_sha256),
                       (args.target_wheel, args.target_sha256),
                       (args.receipt, args.receipt_sha256),
                       (args.controller, args.controller_sha256)):
    if not file.is_file() or digest(file) != expected:
        raise RuntimeError('exact published input mismatch: ' + file.name)
if args.old_wheel.name != 'forge_autonomy-2.7.38-py3-none-any.whl' \
        or args.target_wheel.name != 'forge_autonomy-2.7.39-py3-none-any.whl':
    raise RuntimeError('unexpected published version filename')
if not all(len(x) == 40 and all(c in '0123456789abcdef' for c in x)
           for x in (args.target_source, args.controller_source)):
    raise RuntimeError('source revision must be exact')
spec = importlib.util.spec_from_file_location('r29_exact_controller', args.controller)
if spec is None or spec.loader is None:
    raise RuntimeError('controller cannot be imported')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONSAFEPATH='1')
def run(command, cwd):
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError('disposable command failed: stdout=' + completed.stdout[-1000:]
                           + ' stderr=' + completed.stderr[-800:])
    return completed.stdout

def tree_digest(root):
    rows = []
    for item in sorted(root.rglob('*')):
        if item.is_symlink():
            raise RuntimeError('disposable data tree contains a symlink')
        rows.append((item.relative_to(root).as_posix(),
                     digest(item) if item.is_file() else 'DIRECTORY'))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()

with tempfile.TemporaryDirectory(prefix='r29-published-update-') as temporary:
    root = Path(temporary).resolve()
    results = {}
    for label, paired in (('paired', True), ('unpaired', False)):
        cell = root / label
        cell.mkdir()
        venv = cell / 'baseline-venv'
        run([sys.executable, '-I', '-m', 'venv', str(venv)], cell)
        run([str(venv / 'bin/python'), '-I', '-m', 'pip', 'install', '--isolated',
             '--no-index', '--no-deps', str(args.old_wheel)], cell)
        data_root = cell / 'forge-instance'
        run([str(venv / 'bin/forge'), '--data-root', str(data_root), 'server', 'init'], cell)
        if paired:
            run([str(venv / 'bin/forge'), '--data-root', str(data_root),
                 'execution-host', 'configure', '--binding-id', 'ep-synthetic',
                 '--endpoint', 'http://127.0.0.1:18767', '--expected-instance-id', 'ep-synthetic',
                 '--consumer-id', 'forge-synthetic', '--host-id', 'local-synthetic',
                 '--project-id', 'project-synthetic', '--repository-id', 'repo-synthetic',
                 '--repository-identity', 'repository-synthetic',
                 '--credential-reference', 'keychain://forge.ep/consumer',
                 '--operator-id', 'operator-synthetic', '--allow-loopback-http'], cell)
            historical = module.database_snapshot(data_root / 'forge.db')
            identity = [
                '--instances-root', str(cell),
                '--instance-id', historical['metadata']['runtime_id'],
                '--runtime-id', historical['metadata']['runtime_id'],
                '--installation-id', historical['metadata']['installation_id'],
                '--installed-version', '2.7.38',
                '--installed-source', '0a3d6e35b01da93bb5a674ae7795558655c16c7d',
                '--installed-artifact-digest', 'sha256:' + args.old_sha256,
            ]
            preserve = json.loads(run([str(venv / 'bin/forge'), '--data-root', str(data_root),
                'server', 'preserve', '--operation-id', 'r29-historical-preserve', *identity], cell))
            if preserve.get('lifecycle_state') != 'UNINSTALLED_DATA_PRESERVED':
                raise RuntimeError('2.7.38 PRESERVE failed')
            restore = json.loads(run([str(venv / 'bin/forge'), '--data-root', str(data_root),
                'server', 'restore', '--operation-id', 'r29-historical-restore',
                '--preserve-operation-id', 'r29-historical-preserve', *identity], cell))
            if restore.get('lifecycle_state') != 'RESTORE_VALIDATED':
                raise RuntimeError('2.7.38 RESTORE failed')
            historical_receipt = (cell / '.forge-server-runtime-lifecycle'
                / hashlib.sha256(historical['metadata']['runtime_id'].encode()).hexdigest()
                / 'instance-lifecycle-v1' / 'operations' / 'r29-historical-preserve' / 'receipt.json')
            historical_receipt_digest = digest(historical_receipt) if historical_receipt.is_file() else None
        sibling = cell / 'sibling'
        run([str(venv / 'bin/forge'), '--data-root', str(sibling), 'server', 'init'], cell)
        sibling_before = tree_digest(sibling)
        before = module.database_snapshot(data_root / 'forge.db')
        if bool(before['peer']) != paired or before['user_version'] != 39:
            raise RuntimeError('baseline state was not selected exactly')
        runtime_root = cell / 'runtime'
        runtime_root.mkdir()
        fields = {
            'operation_id': 'r29-published-update-' + label,
            'version': '2.7.39', 'product_source': args.target_source,
            'wheel': str(args.target_wheel), 'wheel_sha256': 'sha256:' + args.target_sha256,
            'qualification_receipt': str(args.receipt),
            'qualification_receipt_sha256': 'sha256:' + args.receipt_sha256,
            'controller_source': args.controller_source,
            'controller_sha256': 'sha256:' + args.controller_sha256,
            'data_root': str(data_root), 'runtime_root': str(runtime_root),
            'runtime_id': before['metadata']['runtime_id'],
            'installation_id': before['metadata']['installation_id'],
            'peer_configuration_digest': before['peer_state_digest'],
            'resolver': str(venv / 'bin/forge'),
            'resolver_sha256': module.file_digest(venv / 'bin/forge'),
            'existing_interpreter': str(venv / 'bin/python'),
            'existing_version': '2.7.38', 'base_python': sys.executable,
            'installed_source': '0a3d6e35b01da93bb5a674ae7795558655c16c7d',
            'installed_artifact_digest': 'sha256:' + args.old_sha256,
        }
        command = [sys.executable, '-I', str(args.controller)] + [
            value for key, raw in fields.items()
            for value in ('--' + key.replace('_', '-'), raw)
        ]
        assessment = json.loads(run(command + ['--assess-only'], cell))
        if assessment.get('state') != 'UPDATE_AVAILABLE':
            raise RuntimeError('published update assessment denied')
        command += ['--assessment-digest', assessment['assessment_digest']]
        terminal = json.loads(run(command, cell))
        if terminal.get('state') != 'COMPLETE':
            raise RuntimeError('published update did not complete')
        replay = json.loads(run(command, cell))
        after = module.database_snapshot(data_root / 'forge.db')
        if replay != terminal or after['user_version'] != 40 \
                or after['metadata']['forge_version'] != '2.7.39' \
                or after['metadata']['runtime_id'] != before['metadata']['runtime_id'] \
                or after['metadata']['installation_id'] != before['metadata']['installation_id'] \
                or after['peer'] != before['peer'] \
                or after['peer_state_digest'] != before['peer_state_digest'] \
                or tree_digest(sibling) != sibling_before:
            raise RuntimeError('published update replay or preservation failed')
        if paired and (historical_receipt_digest is None
                       or digest(historical_receipt) != historical_receipt_digest):
            raise RuntimeError('historical 2.7.38 preserve receipt was changed')
        with sqlite3.connect(f'file:{data_root / "forge.db"}?mode=ro', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' \
                    or db.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('updated database integrity failed')
        results[label] = {'assessment': 'PASS', 'complete': 'PASS',
                          'terminal_replay': 'PASS', 'schema_39_to_40': 'PASS',
                          'identity_peer_and_sibling_preserved': 'PASS'}
        if paired:
            results[label]['historical_2738_preserve_restore_receipt'] = 'PASS'
    print(json.dumps({'controller_source': args.controller_source,
                      'controller_sha256': args.controller_sha256,
                      'target_source': args.target_source,
                      'target_wheel_sha256': args.target_sha256,
                      'release_receipt_sha256': args.receipt_sha256,
                      'cells': results}, sort_keys=True))
