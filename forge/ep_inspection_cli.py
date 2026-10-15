"""Private local owner pairing/setup and HTTP-service-core parity; no offline export."""
import argparse
import json
import sqlite3
from pathlib import Path
from .server_runtime import existing_instance
from .ep_inspection_grant import InspectionAdoptionGrant
from .ep_inspection_service import InspectionAdoptionService
from .ep_inspection_contract import CONTRACT
from .project_bootstrap.schema import load_json
from .workspace_review_grant import _private_bytes
from .concept_advisory_cli import publish_cli


def main(argv=None):
    parser = argparse.ArgumentParser(prog='forge-inspection-adoption')
    parser.add_argument('--data-root', required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('init')
    bind = sub.add_parser('bind')
    bind.add_argument('--config-file', required=True)
    bind.add_argument('--ep-token-file', required=True)
    issue = sub.add_parser('issue')
    for key in ('principal-id','audience','pairing-id','expires-at','token-file'):
        issue.add_argument('--'+key, required=True)
    for key in ('dossier-id','permission'):
        issue.add_argument('--'+key, action='append', required=True)
    issue.add_argument('--maximum-records', type=int, required=True)
    revoke = sub.add_parser('revoke')
    revoke.add_argument('--grant-id', required=True)
    unpair = sub.add_parser('revoke-pairing')
    unpair.add_argument('--pairing-id', required=True)
    for action in ('capability','prepare','read','intent'):
        command = sub.add_parser(action)
        command.add_argument('--token-file', required=True)
        command.add_argument('--audience', required=True)
        if action == 'prepare':
            command.add_argument('--request-file', required=True)
        elif action in ('read','intent'):
            command.add_argument('--dossier-id', required=True)
            command.add_argument('--plan-id' if action == 'read' else '--operation-id', required=True)
    args = parser.parse_args(argv)
    try:
        instance = existing_instance(args.data_root)
        grant = InspectionAdoptionGrant(instance.data_root,instance.instance_id)
        if args.action == 'init':
            grant.initialize()
            document = {'contract_version':CONTRACT,'state':'PRIVATE_INSPECTION_ADOPTION_INITIALIZED'}
        elif args.action == 'bind':
            document = grant.bind(load_json(_private_bytes(Path(args.config_file))),args.ep_token_file)
        elif args.action == 'issue':
            document = grant.issue(principal_id=args.principal_id,audience=args.audience,dossier_ids=args.dossier_id,
                                   permissions=args.permission,pairing_id=args.pairing_id,maximum_records=args.maximum_records,
                                   expires_at=args.expires_at,token_path=args.token_file)
        elif args.action == 'revoke':
            document = grant.revoke(args.grant_id)
        elif args.action == 'revoke-pairing':
            document = grant.revoke_pair(args.pairing_id)
        else:
            token = _private_bytes(Path(args.token_file)).decode().strip()
            if not 1 <= len(token) <= 256:
                raise ValueError('finite private bearer required')
            auth = 'Bearer '+token
            base = '/v1/inspection-adoptions'
            service = InspectionAdoptionService(grant)
            if args.action == 'capability':
                status, document = service.handle('GET',base+'/capability',auth,args.audience)
            elif args.action == 'prepare':
                status, document = service.handle('POST',base+'/plans',auth,args.audience,load_json(_private_bytes(Path(args.request_file))))
            else:
                target = base+('/plans/'+args.plan_id if args.action == 'read' else '/intents/'+args.operation_id)+'?dossier_id='+args.dossier_id
                status, document = service.handle('GET',target,auth,args.audience)
            if status not in (200,202):
                print(json.dumps(document,sort_keys=True))
                return 1
            try:
                publish_cli(grant,auth,args.audience,document)
            except (OSError,ValueError,RuntimeError,PermissionError,sqlite3.Error):
                return 1
            return 0
        print(json.dumps(document,sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,PermissionError,sqlite3.Error):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'INSPECTION_ADOPTION_CLI_UNAVAILABLE'}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
