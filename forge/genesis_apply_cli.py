"""Owner private setup and CLI parity over the same Genesis coordinator."""
import argparse
import json
from pathlib import Path
import sqlite3
from .genesis_apply_contract import CONTRACT
from .genesis_apply_grant import GenesisApplyGrant
from .genesis_apply_pairing import GenesisApplyPairings
from .genesis_apply_service import GenesisApplyService, BASE
from .concept_advisory_cli import publish_cli
from .workspace_review_grant import _private_bytes
from .project_bootstrap.schema import load_json


def main(argv=None):
    parser = argparse.ArgumentParser(prog='forge-genesis-apply')
    parser.add_argument('--data-root', required=True)
    sub = parser.add_subparsers(dest='action', required=True); sub.add_parser('init')
    issue = sub.add_parser('issue')
    for key in ('principal-id', 'proposal-principal-id', 'audience', 'expires-at', 'token-file'):
        issue.add_argument('--'+key, required=True)
    for key in ('dossier-id', 'source-plan-id', 'permission'):
        issue.add_argument('--'+key, action='append', required=True)
    issue.add_argument('--exact-plans-file')
    revoke = sub.add_parser('revoke'); revoke.add_argument('--grant-id', required=True)
    bind = sub.add_parser('bind-peer'); bind.add_argument('--config-file', required=True); bind.add_argument('--credential-file', required=True)
    revoke_peer = sub.add_parser('revoke-peer'); revoke_peer.add_argument('--pairing-id', required=True)
    for action in ('request', 'read', 'resume'):
        item = sub.add_parser(action); item.add_argument('--token-file', required=True); item.add_argument('--audience', required=True)
        if action != 'read': item.add_argument('--request-file', required=True)
        if action != 'request': item.add_argument('--operation-id', required=True)
        if action == 'read': item.add_argument('--dossier-id', required=True)
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root); grant = GenesisApplyGrant(instance.data_root, instance.instance_id)
        if args.action == 'init':
            grant.initialize(); document = {'contract_version':CONTRACT, 'state':'PRIVATE_GENESIS_APPLY_INITIALIZED'}
        elif args.action == 'issue':
            plans = load_json(_private_bytes(Path(args.exact_plans_file))) if args.exact_plans_file else []
            document = grant.issue(principal_id=args.principal_id, audience=args.audience, proposal_principal_id=args.proposal_principal_id,
                dossier_ids=args.dossier_id, source_plan_ids=args.source_plan_id, permissions=args.permission, exact_plans=plans,
                expires_at=args.expires_at, token_path=args.token_file)
        elif args.action == 'revoke': document = grant.revoke(args.grant_id)
        elif args.action == 'bind-peer':
            document = GenesisApplyPairings(grant).bind(load_json(_private_bytes(Path(args.config_file))), args.credential_file)
        elif args.action == 'revoke-peer': document = GenesisApplyPairings(grant).revoke(args.pairing_id)
        else:
            token = _private_bytes(Path(args.token_file))
            if len(token) > 256: raise ValueError('finite private bearer required')
            auth = 'Bearer '+token.decode('ascii').strip(); service = GenesisApplyService(grant)
            if args.action == 'read': status, document = service.handle('GET', BASE+'/operations/'+args.operation_id+'?dossier_id='+args.dossier_id, auth, args.audience)
            else:
                path = BASE+'/operations'+('/'+args.operation_id+'/resume' if args.action == 'resume' else '')
                status, document = service.handle('POST', path, auth, args.audience, load_json(_private_bytes(Path(args.request_file))))
            if status != 200:
                print(json.dumps(document, sort_keys=True)); return 1
            try: publish_cli(grant, auth, args.audience, document, chunk_bytes=65536)
            except (OSError, ValueError, TypeError, KeyError, RuntimeError, PermissionError, sqlite3.Error): return 1
            return 0
        print(json.dumps(document, sort_keys=True)); return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, PermissionError, sqlite3.Error):
        print(json.dumps({'contract_version':CONTRACT, 'error':{'code':'GENESIS_APPLY_CLI_UNAVAILABLE'}})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
