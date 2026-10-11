"""Show, preview numbered remaining work, explicitly confirm and recover."""
import argparse
import json
from pathlib import Path

from .advisory_contract import digest
from .workset_order_contract import CONTRACT
from .workset_order_grant import WorksetOrderGrant
from .workset_order_service import BASE, WorksetOrderService
from .workset_release_journal import private_packet
from .workspace_review_grant import _private_bytes, _write_private


def main(argv=None):
    parser = argparse.ArgumentParser(prog='forge-workset-order')
    parser.add_argument('--data-root', required=True)
    parser.add_argument('--token-file', required=True)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('capability')
    for name in ('show', 'preview', 'operation'):
        command = commands.add_parser(name)
        command.add_argument('--workset-id')
        if name == 'preview':
            command.add_argument('--positions', nargs='+', type=int, required=True,
                                 help='New order of the numbered remaining members, e.g. 2 1')
            command.add_argument('--output', required=True)
        if name == 'operation':
            command.add_argument('--operation-id', required=True)
    confirm = commands.add_parser('confirm')
    confirm.add_argument('--shown-package', required=True)
    confirm.add_argument('--operation-id', required=True)
    confirm.add_argument('--reason', required=True)
    confirm.add_argument('--confirm', action='store_true')
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root)
        grant = WorksetOrderGrant(instance.data_root, instance.instance_id)
        token = 'Bearer ' + _private_bytes(Path(args.token_file)).decode().strip()
        service = WorksetOrderService(instance.data_root, grant)
        body = None; method = 'GET'
        if args.action == 'capability':
            path = BASE + '/capability'
        elif args.action == 'confirm':
            shown = json.loads(private_packet(Path(args.shown_package)))
            package = shown['package']
            if shown['contract_version'] != CONTRACT or digest(package) != shown['package_digest']:
                raise ValueError('exact shown order package required')
            body = {'contract_version': CONTRACT, 'operation_id': args.operation_id,
                **{k: package[k] for k in ('instance_id', 'project_id', 'repository_id', 'workset_id')},
                'package': package, 'package_digest': shown['package_digest'],
                'reason': args.reason, 'confirm': args.confirm}
            method = 'POST'; path = BASE + '/' + package['workset_id'] + '/confirm'
        else:
            p = grant.authorize(token)
            key = args.workset_id
            if key is None:
                if len(p.worksets) != 1:
                    raise ValueError('choose one of the current explicitly scoped worksets')
                key = p.worksets[0]['workset_id']
            path = BASE + '/' + key
            if args.action == 'operation':
                path += '/operations/' + args.operation_id
            if args.action == 'preview':
                current = service.current(token, key)
                fixed = current['fixed_prefix']; order = current['current_order']; remaining = order[fixed:]
                if sorted(args.positions) != list(range(1, len(remaining) + 1)):
                    raise ValueError('positions must permute the displayed remaining members exactly')
                body = {'contract_version': CONTRACT,
                        'proposed_order': order[:fixed] + [remaining[i - 1] for i in args.positions]}
                method = 'POST'; path += '/preview'
        status, result = service.handle(method, path, token, body)
        if args.action == 'preview' and status == 200:
            _write_private(Path(args.output), json.dumps(result, sort_keys=True, ensure_ascii=False).encode())
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0 if status == 200 else 1
    except (OSError, ValueError, RuntimeError, PermissionError, KeyError, TypeError):
        print(json.dumps({'contract_version': CONTRACT, 'error': {'code': 'ORDER_CLI_UNAVAILABLE'}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
