"""Private-token HTTP-equivalent Candidate commands; no admin fallback."""
import argparse,json
from pathlib import Path
from .advisory_candidate_contract import CONTRACT
from .advisory_candidate_grant import AdvisoryCandidateGrant
from .advisory_candidate_service import AdvisoryCandidateService
from .workspace_review_grant import _private_bytes

def main(argv=None):
    p=argparse.ArgumentParser(prog='forge-advisory-candidate');p.add_argument('--data-root',required=True);p.add_argument('--token-file',required=True);c=p.add_subparsers(dest='action',required=True);c.add_parser('capability')
    source=c.add_parser('source');source.add_argument('--conversation-id',required=True);source.add_argument('--turn-id',required=True)
    preview=c.add_parser('preview');preview.add_argument('--conversation-id',required=True);preview.add_argument('--proposal-id',required=True);preview.add_argument('--revision',type=int)
    op=c.add_parser('operation');op.add_argument('--conversation-id',required=True);op.add_argument('--proposal-id',required=True);op.add_argument('--operation-id',required=True)
    for name in ['save','register']:s=c.add_parser(name);s.add_argument('--request-file',required=True)
    a=p.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        i=existing_instance(a.data_root);g=AdvisoryCandidateGrant(i.data_root,i.instance_id);t=Path(a.token_file)
        if t.is_symlink() or t.stat().st_mode&0o077 or t.stat().st_size>256:raise ValueError('private token file required')
        token='Bearer '+t.read_text().strip();service=AdvisoryCandidateService(i.data_root,g);method='GET';body=None
        if a.action=='capability':target='/v1/advisory-candidates/capability'
        elif a.action=='source':target='/v1/advisory-candidates/'+a.conversation_id+'/source/'+a.turn_id
        elif a.action=='preview':target='/v1/advisory-candidates/'+a.conversation_id+'/proposals/'+a.proposal_id+('' if a.revision is None else '?revision='+str(a.revision))
        elif a.action=='operation':target='/v1/advisory-candidates/'+a.conversation_id+'/proposals/'+a.proposal_id+'/registrations/'+a.operation_id
        else:
            body=json.loads(_private_bytes(Path(a.request_file)));method='POST';target='/v1/advisory-candidates/'+body['conversation_id']+'/proposals'+('' if a.action=='save' else '/'+body['proposal_id']+'/registrations')
        status,out=service.handle(method,target,token,body);print(json.dumps(out,sort_keys=True));return 0 if status==200 else 1
    except (OSError,ValueError,KeyError,RuntimeError):print(json.dumps({'contract_version':CONTRACT,'error':{'code':'CANDIDATE_CLI_UNAVAILABLE'}}));return 1

if __name__=='__main__':raise SystemExit(main())
