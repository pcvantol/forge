"""Explicit local owner setup and private parity for the Genesis HTTP core."""
import argparse
import json
import sqlite3
from pathlib import Path
from .genesis_bootstrap_contract import CONTRACT
from .genesis_bootstrap_grant import GenesisBootstrapGrant
from .genesis_bootstrap_service import GenesisBootstrapService
from .concept_advisory_cli import publish_cli
from .workspace_review_grant import _private_bytes
from .project_bootstrap.schema import load_json


def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-genesis-bootstrap')
    parser.add_argument('--data-root',required=True)
    sub=parser.add_subparsers(dest='action',required=True); sub.add_parser('init')
    issue=sub.add_parser('issue')
    for key in ('principal-id','proposal-principal-id','audience','expires-at','token-file'):
        issue.add_argument('--'+key,required=True)
    for key in ('dossier-id','source-plan-id','permission'):
        issue.add_argument('--'+key,action='append',required=True)
    issue.add_argument('--exact-plans-file')
    revoke=sub.add_parser('revoke'); revoke.add_argument('--grant-id',required=True)
    for action in ('capability','plan','decide','read','intent','decision','decision-intent'):
        item=sub.add_parser(action); item.add_argument('--token-file',required=True); item.add_argument('--audience',required=True)
        if action in ('plan','decide'):
            item.add_argument('--request-file',required=True)
        elif action!='capability':
            item.add_argument('--dossier-id',required=True); item.add_argument('--reference',required=True)
    args=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(args.data_root); grant=GenesisBootstrapGrant(instance.data_root,instance.instance_id)
        if args.action=='init':
            grant.initialize(); document={'contract_version':CONTRACT,'state':'PRIVATE_GENESIS_BOOTSTRAP_INITIALIZED'}
        elif args.action=='issue':
            plans=load_json(_private_bytes(Path(args.exact_plans_file))) if args.exact_plans_file else []
            document=grant.issue(principal_id=args.principal_id,audience=args.audience,proposal_principal_id=args.proposal_principal_id,dossier_ids=args.dossier_id,source_plan_ids=args.source_plan_id,permissions=args.permission,exact_plans=plans,expires_at=args.expires_at,token_path=args.token_file)
        elif args.action=='revoke':
            document=grant.revoke(args.grant_id)
        else:
            token=_private_bytes(Path(args.token_file))
            if len(token)>256:
                raise ValueError('finite token required')
            auth='Bearer '+token.decode().strip(); service=GenesisBootstrapService(grant); base='/v1/genesis-bootstrap'
            if args.action=='capability':
                status,document=service.handle('GET',base+'/capability',auth,args.audience)
            elif args.action in ('plan','decide'):
                status,document=service.handle('POST',base+('/plans' if args.action=='plan' else '/decisions'),auth,args.audience,load_json(_private_bytes(Path(args.request_file))))
            else:
                leaves={'read':'plans','intent':'intents','decision':'decisions','decision-intent':'decision-intents'}
                status,document=service.handle('GET',base+'/'+leaves[args.action]+'/'+args.reference+'?dossier_id='+args.dossier_id,auth,args.audience)
            if status!=200:
                print(json.dumps(document,sort_keys=True)); return 1
            try:
                publish_cli(grant,auth,args.audience,document)
            except (OSError,ValueError,RuntimeError,PermissionError,sqlite3.Error):
                return 1
            return 0
        print(json.dumps(document,sort_keys=True)); return 0
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,PermissionError,sqlite3.Error):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'GENESIS_CLI_UNAVAILABLE'}})); return 1


if __name__=='__main__':
    raise SystemExit(main())
