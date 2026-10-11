"""Explicit owner setup reuses finite scoped READ; reads never provision a key."""
import argparse
import json
import secrets
from pathlib import Path

from .advisory_grant import project_scope
from .workset_order_grant import WorksetOrderGrant, authority_binding
from .workspace_review_grant import _locked, _private_bytes, _write_private


def key_path(root):
    return Path(root) / 'credentials' / 'workset-activity' / 'cursor-key.private'


def cursor_key(root):
    raw = _private_bytes(key_path(root))
    if len(raw) != 64 or any(c not in b'0123456789abcdef' for c in raw):
        raise ValueError('activity cursor key unavailable')
    return bytes.fromhex(raw.decode())


def provision_key(root, instance_id):
    """Only explicit supported setup has an effect; no data/credential migration."""
    authority_binding(root, instance_id, ('READ',), None)
    path = key_path(root)
    with _locked(path):
        if path.exists() or path.is_symlink():
            return cursor_key(root)
        _write_private(path, secrets.token_hex(32).encode())
        return cursor_key(root)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='forge-workset-activity-grant')
    parser.add_argument('--data-root', required=True)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('identity')
    revoke = commands.add_parser('revoke'); revoke.add_argument('--grant-id', required=True)
    issue = commands.add_parser('issue')
    issue.add_argument('--principal-id')
    issue.add_argument('--workset-id', action='append', required=True)
    issue.add_argument('--expires-at', required=True)
    issue.add_argument('--token-file', required=True)
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root)
        root = Path(instance.data_root); grant = WorksetOrderGrant(root, instance.instance_id)
        if args.action == 'identity':
            result = {**project_scope(root, instance.instance_id),
                      **authority_binding(root, instance.instance_id, ('READ',), None), 'permissions': ['READ'],
                      'history_supported': key_path(root).is_file()}
        elif args.action == 'revoke':
            result = grant.revoke(args.grant_id)
        else:
            from .workset_order_grant import scoped_workset
            scope = project_scope(root, instance.instance_id)
            subjects = [{'workset_id': k, 'definition_digest': scoped_workset(root, scope, k)['definition_digest']}
                        for k in args.workset_id]
            provision_key(root, instance.instance_id)
            actor = args.principal_id or authority_binding(root, instance.instance_id, ('READ',), None)['operator_id']
            result = grant.issue(principal_id=actor, project_id=scope['project_id'],
                repository_id=scope['repository_id'], permissions=['READ'], worksets=subjects,
                maximum_amendments=1, expires_at=args.expires_at, token_path=args.token_file)
        print(json.dumps(result, sort_keys=True)); return 0
    except (OSError, ValueError, RuntimeError, PermissionError, KeyError, TypeError):
        print(json.dumps({'error': {'code': 'ACTIVITY_SETUP_UNAVAILABLE'}})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
