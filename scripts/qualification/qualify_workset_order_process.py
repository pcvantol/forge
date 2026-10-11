"""Owned cold process with genuine observed order-effect interruption boundaries."""
from contextlib import ExitStack, contextmanager, closing
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import argparse
import json
import os
import sqlite3
import sys
import time
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]
if '--source-development' in sys.argv:
    sys.path.insert(0, str(SOURCE))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-development', action='store_true')
    parser.add_argument('--root', required=True)
    parser.add_argument('--action', choices=['confirm', 'read', 'tick', 'activity', 'activity-cli'], required=True)
    parser.add_argument('--endpoint')
    parser.add_argument('--activity-path')
    parser.add_argument('--cursor-file')
    parser.add_argument('--stage', default='normal', choices=['normal', 'before-intent', 'after-intent',
        'after-business', 'after-architecture', 'after-apply', 'lost-response', 'after-runtime-claim'])
    parser.add_argument('--token-file', default='order.private')
    parser.add_argument('--operation-id')
    args = parser.parse_args(); root = Path(args.root)
    spec = spec_from_file_location('order_existing_external_fixture', SOURCE / 'scripts/qualification/qualify_workset_release_chain.py')
    chain = module_from_spec(spec); spec.loader.exec_module(chain)
    from forge.server_runtime import existing_instance
    from forge.workspace_review_grant import _private_bytes, _write_private
    from forge.workset_order_grant import WorksetOrderGrant
    from forge.workset_order_service import WorksetOrderService
    import forge.workset_order_service as product
    instance = existing_instance(root / 'runtime')
    grant = WorksetOrderGrant(instance.data_root, instance.instance_id)
    service = WorksetOrderService(instance.data_root, grant)
    token = 'Bearer ' + _private_bytes(root / args.token_file).decode().strip()
    if args.action in ('activity', 'activity-cli'):
        from forge.workset_activity_service import WorksetActivityService
        from forge.workset_activity_cli import main as activity_cli
        with patch.object(chain.utils.composition.MacOSGeneratedUIDIdentityAdapter, 'resolve', return_value=chain.utils.fixture.IDENTITY):
            if args.action == 'activity-cli':
                command = ['--data-root', instance.data_root, '--token-file', str(root / args.token_file), 'pages']
                if args.cursor_file:
                    command += ['--cursor-file', args.cursor_file]
                return activity_cli(command)
            status, output = WorksetActivityService(instance.data_root, grant).handle('GET', args.activity_path, token)
            print(json.dumps({'pid': os.getpid(), 'status': status, 'output': output}))
            return 0 if status == 200 else 1
    request = json.loads(_private_bytes(root / 'order-command.private.json'))
    if args.action == 'tick':
        if not args.endpoint:
            raise ValueError('explicit own simulator endpoint required')
        output = chain.phase(root, 'effect-read-only', 'pause-next-claim' if args.stage == 'after-runtime-claim'
                             else 'tick', args.endpoint, include_order=True)
        print(json.dumps({'pid': os.getpid(), 'output': output}))
        return 0
    if args.operation_id:
        request['operation_id'] = args.operation_id
    paused = False

    def pause_if_observed():
        nonlocal paused
        if paused or args.stage in ('normal', 'lost-response'):
            return
        with closing(sqlite3.connect((root / 'runtime/forge.db').as_uri() + '?mode=ro', uri=True)) as db:
            document = json.loads(db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',
                                            (request['workset_id'],)).fetchone()[0])
            intent = document.get('order_intents', {}).get(request['operation_id'])
            count = db.execute("SELECT count(*) FROM governance_decisions WHERE subject_id=?",
                               ('workset-order:' + request['workset_id'],)).fetchone()[0]
        hit = ((args.stage == 'before-intent' and intent is None)
            or (args.stage == 'after-intent' and intent is not None and count == 0)
            or (args.stage == 'after-business' and count == 1)
            or (args.stage == 'after-architecture' and count == 2 and intent is not None and intent['state'] == 'PENDING')
            or (args.stage == 'after-apply' and intent is not None and intent['state'] == 'APPLIED'))
        if not hit:
            return
        paused = True
        _write_private(root / 'order-boundary.ready.private', json.dumps({'pid': os.getpid(), 'stage': args.stage}).encode())
        deadline = time.monotonic() + 20
        while not (root / 'order-boundary.continue.private').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('own observed order boundary was not released')
            time.sleep(.02)

    original_lock = product._locked
    @contextmanager
    def observed_lock(path):
        if path.resolve() == grant.path.resolve():
            pause_if_observed()
        with original_lock(path):
            yield

    def identity():
        pause_if_observed()
        return chain.utils.fixture.IDENTITY

    with ExitStack() as stack:
        chain.utils._open(root, stack, effect_scenario='effect-read-only')
        stack.enter_context(patch.object(product, '_locked', observed_lock))
        stack.enter_context(patch.object(chain.utils.composition.MacOSGeneratedUIDIdentityAdapter, 'resolve', side_effect=identity))
        output = service.operation(token, request['workset_id'], request['operation_id']) if args.action == 'read' else service.execute(token, request)
        if args.stage == 'lost-response':
            os._exit(23)
        print(json.dumps({'pid': os.getpid(), 'output': output}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, PermissionError, OSError, KeyError, TypeError):
        print(json.dumps({'error': 'SCOPED_ORDER_PROCESS_REFUSED', 'pid': os.getpid()}))
        raise SystemExit(1)
