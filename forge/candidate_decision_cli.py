"""Private Candidate decision CLI, sharing the exact HTTP application service."""
import argparse,json
from pathlib import Path
from .candidate_decision_contract import CONTRACT
from .candidate_decision_grant import CandidateDecisionGrant
from .candidate_decision_service import CandidateDecisionService
from .workspace_review_grant import _private_bytes

def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-candidate-decision');parser.add_argument('--data-root',required=True);parser.add_argument('--token-file',required=True)
    sub=parser.add_subparsers(dest='action',required=True);sub.add_parser('capability')
    detail=sub.add_parser('prepare');detail.add_argument('--candidate-id',required=True)
    operation=sub.add_parser('operation');operation.add_argument('--candidate-id',required=True);operation.add_argument('--operation-id',required=True)
    for name in ('business','architecture'):
        sub.add_parser(name).add_argument('--request-file',required=True)
    a=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        i=existing_instance(a.data_root);g=CandidateDecisionGrant(i.data_root,i.instance_id);p=Path(a.token_file)
        if p.is_symlink() or p.stat().st_mode&0o077 or p.stat().st_size>256:
            raise ValueError('private decision token required')
        service=CandidateDecisionService(i.data_root,g);token='Bearer '+p.read_text().strip();method='GET';body=None
        if a.action=='capability':
            target='/v1/candidate-decisions/capability'
        elif a.action=='prepare':
            target='/v1/candidate-decisions/'+a.candidate_id
        elif a.action=='operation':
            target='/v1/candidate-decisions/'+a.candidate_id+'/operations/'+a.operation_id
        else:
            method='POST';body=json.loads(_private_bytes(Path(a.request_file)));target='/v1/candidate-decisions/'+body['candidate_id']+'/'+a.action
        status,out=service.handle(method,target,token,body);print(json.dumps(out,sort_keys=True));return 0 if status==200 else 1
    except (OSError,ValueError,RuntimeError,PermissionError,KeyError):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'DECISION_CLI_UNAVAILABLE'}}));return 1

if __name__=='__main__':
    raise SystemExit(main())
