"""Supported scoped history CLI; exporting is the only caller-requested write."""
import argparse
import json
from pathlib import Path

from .workset_activity_cursor import CONTRACT
from .workset_activity_service import BASE, WorksetActivityService
from .workset_order_grant import WorksetOrderGrant
from .workset_release_journal import private_packet
from .workspace_review_grant import _private_bytes, _write_private


def main(argv=None):
    parser = argparse.ArgumentParser(prog='forge-workset-activity')
    parser.add_argument('--data-root', required=True)
    parser.add_argument('--token-file', required=True)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('capability')
    for name in ('pages', 'event'):
        command = commands.add_parser(name); command.add_argument('--workset-id')
        if name == 'pages':
            command.add_argument('--cursor-file'); command.add_argument('--output')
        else:
            command.add_argument('--event-id', required=True)
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root)
        grant = WorksetOrderGrant(instance.data_root, instance.instance_id)
        token = 'Bearer ' + _private_bytes(Path(args.token_file)).decode().strip()
        path = BASE
        if args.action != 'capability':
            p = grant.authorize(token, permission='READ')
            selected = args.workset_id
            if selected is None:
                if len(p.worksets) != 1:
                    raise ValueError('choose exactly one explicitly scoped workset')
                selected = p.worksets[0]['workset_id']
            path += '/' + selected + ('/events/' + args.event_id if args.action == 'event' else '/pages')
            if args.action == 'pages' and args.cursor_file:
                value = json.loads(private_packet(Path(args.cursor_file)))
                if value['contract_version'] != CONTRACT:
                    raise ValueError('activity cursor contract')
                path += '/' + value['cursor']
        status, result = WorksetActivityService(instance.data_root, grant).handle('GET', path, token)
        if args.action == 'pages' and args.output and status == 200:
            destination = Path(args.output)
            protected = [Path(args.token_file).resolve()]
            if args.cursor_file:
                protected.append(Path(args.cursor_file).resolve())
            if destination.resolve().is_relative_to(Path(instance.data_root).resolve()) or destination.resolve() in protected:
                raise ValueError('export must not replace authority or runtime data')
            _write_private(destination, json.dumps(result, ensure_ascii=True, sort_keys=True).encode())
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if status == 200 else 1
    except (OSError, ValueError, RuntimeError, PermissionError, KeyError, TypeError):
        print(json.dumps({'contract_version': CONTRACT, 'error': {'code': 'ACTIVITY_CLI_UNAVAILABLE'}})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
