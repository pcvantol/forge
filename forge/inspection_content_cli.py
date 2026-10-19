"""Owner setup and finite content-decision CLI over the same HTTP service core."""
import argparse
import json
import sqlite3
from pathlib import Path
from .inspection_content_contract import CONTRACT
from .inspection_content_grant import InspectionContentGrant
from .inspection_content_service import InspectionContentService
from .concept_advisory_cli import publish_cli
from .workspace_review_grant import _private_bytes
from .project_bootstrap.schema import load_json

def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-inspection-adoption-decisions');parser.add_argument('--data-root',required=True)
    sub=parser.add_subparsers(dest='action',required=True);sub.add_parser('init')
    issue=sub.add_parser('issue')
    for key in ('principal-id','plan-id','dossier-id','source-token-file','audience','expires-at','token-file'):issue.add_argument('--'+key,required=True)
    for key in ('permission',):issue.add_argument('--'+key,action='append',required=True)
    issue.add_argument('--role',action='append',default=[])
    revoke=sub.add_parser('revoke');revoke.add_argument('--grant-id',required=True)
    for action in ('capability','read','intent','decision','decide'):
        item=sub.add_parser(action);item.add_argument('--token-file',required=True);item.add_argument('--audience',required=True)
        if action in ('read','intent','decision'):item.add_argument('--dossier-id',required=True);item.add_argument('--plan-id' if action=='read' else '--decision-id' if action=='decision' else '--operation-id',required=True)
        if action=='decide':item.add_argument('--request-file',required=True)
    args=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(args.data_root);grant=InspectionContentGrant(instance.data_root,instance.instance_id)
        if args.action=='init':grant.initialize();document={'contract_version':CONTRACT,'state':'PRIVATE_CONTENT_DECISIONS_INITIALIZED'}
        elif args.action=='issue':document=grant.issue(principal_id=args.principal_id,audience=args.audience,plan_id=args.plan_id,dossier_id=args.dossier_id,source_token_file=args.source_token_file,permissions=args.permission,roles=args.role,expires_at=args.expires_at,token_path=args.token_file)
        elif args.action=='revoke':document=grant.revoke(args.grant_id)
        else:
            token=_private_bytes(Path(args.token_file))
            if len(token)>256:raise ValueError('finite token required')
            auth='Bearer '+token.decode().strip();service=InspectionContentService(grant);base='/v1/inspection-adoption-decisions'
            if args.action=='capability':status,document=service.handle('GET',base+'/capability',auth,args.audience)
            elif args.action=='decide':status,document=service.handle('POST',base+'/decisions',auth,args.audience,load_json(_private_bytes(Path(args.request_file))))
            else:status,document=service.handle('GET',base+('/proposals/'+args.plan_id if args.action=='read' else '/decisions/'+args.decision_id if args.action=='decision' else '/intents/'+args.operation_id)+'?dossier_id='+args.dossier_id,auth,args.audience)
            if status!=200:print(json.dumps(document,sort_keys=True));return 1
            try:publish_cli(grant,auth,args.audience,document)
            except (OSError,ValueError,RuntimeError,PermissionError,sqlite3.Error):return 1
            return 0
        print(json.dumps(document,sort_keys=True));return 0
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,PermissionError,sqlite3.Error):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'CONTENT_CLI_UNAVAILABLE'}}));return 1

if __name__=='__main__':raise SystemExit(main())
