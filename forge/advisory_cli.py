"""Capability-authenticated CLI parity through the same advisory application service."""
import argparse
import json
from pathlib import Path
from .advisory_contract import CONTRACT
from .advisory_grant import AdvisoryGrant
from .advisory_service import AdvisoryService
from .workspace_review_grant import _private_bytes

def main(argv=None):
    p=argparse.ArgumentParser(prog='forge-advisory');p.add_argument('--data-root',required=True)
    p.add_argument('--token-file',required=True);p.add_argument('--provider-id',default='codex-chatgpt-session')
    c=p.add_subparsers(dest='action',required=True);c.add_parser('capability')
    read=c.add_parser('history');read.add_argument('--conversation-id',required=True);read.add_argument('--cursor',type=int,default=0)
    turn=c.add_parser('turn');turn.add_argument('--conversation-id',required=True);turn.add_argument('--turn-id',required=True)
    send=c.add_parser('submit');send.add_argument('--request-file',required=True)
    a=p.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance=existing_instance(a.data_root);g=AdvisoryGrant(instance.data_root,instance.instance_id)
        token=Path(a.token_file)
        if token.is_symlink() or token.stat().st_mode & 0o077 or token.stat().st_size>256:raise ValueError('private token file required')
        authorization='Bearer '+token.read_text().strip();service=AdvisoryService(instance.data_root,g,a.provider_id)
        method='GET';body=None
        if a.action=='capability':target='/v1/advisory/capability'
        elif a.action=='history':target='/v1/advisory/'+a.conversation_id+'?cursor='+str(a.cursor)
        elif a.action=='turn':target='/v1/advisory/'+a.conversation_id+'/turns/'+a.turn_id
        else:
            body=json.loads(_private_bytes(Path(a.request_file)));method='POST';target='/v1/advisory/'+body['conversation_id']+'/turns'
        status,document=service.handle(method,target,authorization,body)
        print(json.dumps(document,sort_keys=True));return 0 if status==200 else 1
    except (OSError,ValueError,KeyError,RuntimeError):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'ADVISORY_CLI_UNAVAILABLE'}}));return 1

if __name__=='__main__':raise SystemExit(main())
