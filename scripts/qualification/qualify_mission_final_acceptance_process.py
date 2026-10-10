"""Fresh-process acceptance/read driver with genuine effect-boundary interruption."""
from contextlib import ExitStack, contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import argparse
import json
import os
import sys
import time

SOURCE = Path(__file__).resolve().parents[2]
if '--source-development' in sys.argv:
    sys.path.insert(0, str(SOURCE))


def publish_boundary(root, stage):
    from forge.workspace_review_grant import _write_private
    _write_private(root / 'accept-boundary.ready.private',
        json.dumps({'pid': os.getpid(), 'stage': stage}).encode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-development', action='store_true')
    parser.add_argument('--root', required=True)
    parser.add_argument('--action', choices=('accept', 'read'), required=True)
    parser.add_argument('--stage', choices=('normal', 'before-canonical', 'after-canonical',
        'after-terminal', 'after-dispatcher', 'lost-response'), default='normal')
    args = parser.parse_args()
    root = Path(args.root)
    spec = spec_from_file_location('final_acceptance_existing_chain', SOURCE / 'scripts/qualification/qualify_workset_release_chain.py')
    chain = module_from_spec(spec)
    spec.loader.exec_module(chain)
    from forge.mission_final_acceptance_service import MissionFinalAcceptanceService
    from forge.mission_final_acceptance_grant import MissionFinalAcceptanceGrant
    from forge.server_runtime import existing_instance
    from forge.workspace_review_grant import _private_bytes
    import forge.mission_final_acceptance_service as product
    from unittest.mock import patch
    from contextlib import closing
    import sqlite3

    original_lock = product._locked
    instance = existing_instance(root / 'runtime')
    grant = MissionFinalAcceptanceGrant(instance.data_root, instance.instance_id)
    service = MissionFinalAcceptanceService(instance.data_root, grant)
    token = 'Bearer ' + _private_bytes(root / ('accept.private' if args.action == 'accept' else 'accept-read.private')).decode().strip()
    request = json.loads((root / 'accept-command.private.json').read_text())
    paused = False

    def pause():
        nonlocal paused
        if paused:
            return
        paused = True
        publish_boundary(root, args.stage)
        # Parent kills this owned process or explicitly releases the boundary.
        deadline = time.monotonic() + 20
        while not (root / 'accept-boundary.continue.private').exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('owned acceptance boundary not released')
            time.sleep(.02)

    @contextmanager
    def actual_lock(path):
        if path.resolve() == grant.path.resolve() and not paused:
            with closing(sqlite3.connect((root / 'runtime/forge.db').as_uri() + '?mode=ro', uri=True)) as read:
                canonical = read.execute("SELECT count(*) FROM governance_decisions WHERE json_extract(document,'$.decision')='accept'").fetchone()[0]
                state = json.loads(read.execute('SELECT document FROM mission_state WHERE mission_id=?', (request['mission_id'],)).fetchone()[0])
                dispatcher = read.execute('SELECT status,active_mission_id FROM dispatcher_state WHERE singleton=1').fetchone()
            stage = args.stage
            observed = ((stage == 'before-canonical' and canonical == 0)
                or (stage == 'after-canonical' and canonical == 1 and state['status'] == 'AWAITING_APPROVAL')
                or (stage == 'after-terminal' and canonical == 1 and state['status'] == 'COMPLETED'
                    and dispatcher[0] == 'ACTIVE' and dispatcher[1] == request['mission_id'])
                or (stage == 'after-dispatcher' and canonical == 1 and state['status'] == 'COMPLETED'
                    and not (dispatcher[0] == 'ACTIVE' and dispatcher[1] == request['mission_id'])))
            if observed:
                pause()
        with original_lock(path):
            yield

    with ExitStack() as stack:
        chain.utils._open(root, stack, effect_scenario='effect-read-only')
        stack.enter_context(patch.object(product, '_locked', actual_lock))
        if args.action == 'read':
            output = service.operation(token, request['mission_id'], request['operation_id'])
        else:
            output = service.execute(token, request)
        if args.stage == 'lost-response':
            os._exit(23)
        print(json.dumps({'pid': os.getpid(), 'output': output}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, PermissionError, OSError):
        print(json.dumps({'error': 'SCOPED_ACCEPTANCE_PROCESS_REFUSED', 'pid': os.getpid()}))
        raise SystemExit(1)
