"""Human read/confirm/recover CLI using the same bounded service as HTTP."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .advisory_contract import digest
from .mission_final_acceptance_contract import CONTRACT
from .mission_final_acceptance_grant import MissionFinalAcceptanceGrant
from .mission_final_acceptance_service import BASE, MissionFinalAcceptanceService
from .workset_release_journal import private_packet
from .workspace_review_grant import _private_bytes, _write_private


def main(argv=None):
    parser = argparse.ArgumentParser(prog='forge-mission-final-acceptance')
    parser.add_argument('--data-root', required=True)
    parser.add_argument('--token-file', required=True)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('capability')
    show = commands.add_parser('show')
    show.add_argument('--mission-id', required=True)
    show.add_argument('--output')
    accept = commands.add_parser('accept')
    accept.add_argument('--shown-package', required=True)
    accept.add_argument('--operation-id', required=True)
    accept.add_argument('--reason', required=True)
    accept.add_argument('--confirm', action='store_true')
    operation = commands.add_parser('operation')
    operation.add_argument('--mission-id', required=True)
    operation.add_argument('--operation-id', required=True)
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root)
        grant = MissionFinalAcceptanceGrant(instance.data_root, instance.instance_id)
        token = 'Bearer ' + _private_bytes(Path(args.token_file)).decode().strip()
        service = MissionFinalAcceptanceService(instance.data_root, grant)
        body = None
        method = 'GET'
        if args.action == 'capability':
            path = BASE + '/capability'
        elif args.action == 'show':
            path = BASE + '/' + args.mission_id
        elif args.action == 'operation':
            path = BASE + '/' + args.mission_id + '/operations/' + args.operation_id
        else:
            shown = json.loads(private_packet(Path(args.shown_package)))
            package = shown.get('package')
            if (shown.get('contract_version') != CONTRACT or not isinstance(package, dict)
                    or shown.get('package_digest') != digest(package)):
                raise ValueError('exact server-derived shown package required')
            body = {'contract_version': CONTRACT, 'operation_id': args.operation_id,
                **{key: package[key] for key in ('instance_id', 'project_id', 'repository_id', 'mission_id')},
                'package_digest': shown['package_digest'], 'reason': args.reason, 'confirm': args.confirm}
            method = 'POST'
            path = BASE + '/' + package['mission_id'] + '/accept'
        status, result = service.handle(method, path, token, body)
        if args.action == 'show' and args.output and status == 200:
            _write_private(Path(args.output), json.dumps(result, sort_keys=True, ensure_ascii=False).encode())
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0 if status == 200 else 1
    except (OSError, ValueError, RuntimeError, PermissionError, KeyError, TypeError):
        print(json.dumps({'contract_version': CONTRACT, 'error': {'code': 'FINAL_ACCEPTANCE_CLI_UNAVAILABLE'}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
