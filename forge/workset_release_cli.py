"""Human selection CLI using the same scoped application service as HTTP."""
import argparse,json
from pathlib import Path
from .workspace_review_grant import _private_bytes, _write_private
from .workset_release_grant import CONTRACT, WorksetReleaseGrant
from .workset_release_service import BASE,WorksetReleaseService
from .workset_release_journal import private_packet


def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-workset-release')
    parser.add_argument('--data-root',required=True);parser.add_argument('--token-file',required=True)
    sub=parser.add_subparsers(dest='action',required=True);sub.add_parser('capability')
    prep=sub.add_parser('prepare');prep.add_argument('--mission-id',action='append',required=True)
    prep.add_argument('--expires-at',required=True);prep.add_argument('--maximum-activations',type=int,required=True)
    prep.add_argument('--progression-mode',choices=('continuous','after_action'),required=True)
    prep.add_argument('--output',required=True)
    release=sub.add_parser('release');release.add_argument('--prepared-file',required=True)
    release.add_argument('--operation-id',required=True);release.add_argument('--confirm',action='store_true')
    disarm=sub.add_parser('disarm');disarm.add_argument('--original-operation-id',required=True)
    disarm.add_argument('--operation-id',required=True);disarm.add_argument('--confirm',action='store_true')
    sub.add_parser('operation').add_argument('--operation-id',required=True)
    args=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        from .workset_release_subjects import approved_subject
        instance=existing_instance(args.data_root);grant=WorksetReleaseGrant(instance.data_root,instance.instance_id)
        token='Bearer '+_private_bytes(Path(args.token_file)).decode().strip()
        service=WorksetReleaseService(instance.data_root,grant);method='GET';body=None
        if args.action=='capability':path=BASE+'/capability'
        elif args.action=='operation':path=BASE+'/operations/'+args.operation_id
        elif args.action=='prepare':
            p=grant.authorize(token);scope={k:getattr(p,k) for k in ('instance_id','project_id','repository_id')}
            subjects=[approved_subject(instance.data_root,scope,**s) for s in p.subjects]
            selected=[]
            for mission_id in args.mission_id:
                matches=[s for s in subjects if s['mission_id']==mission_id]
                if len(matches)!=1:raise PermissionError('Mission outside explicit release scope')
                selected.append({k:matches[0][k] for k in ('candidate_id','subject_revision')})
            method='POST';path=BASE+'/prepare';body={'contract_version':CONTRACT,'subjects':selected,
                'expires_at':args.expires_at,'maximum_activations':args.maximum_activations,
                'progression_mode':args.progression_mode}
        else:
            if args.action=='release':
                prepared=json.loads(private_packet(Path(args.prepared_file)))
                package=prepared['package'];package_digest=prepared['package_digest'];expected=None
            else:
                original=service.operation(token,args.original_operation_id)
                package=original['frozen_package'];package_digest=original['package_digest']
                if original['current'] is None:raise ValueError('original workset not yet present')
                expected=original['current']['workset_revision']
                try:prior=service.operation(token,args.operation_id)
                except FileNotFoundError:prior=None
                if prior is not None:
                    request=prior['original_request']
                    if request['intent']!='disarm' or request['package_digest']!=package_digest:
                        raise ValueError('disarm operation identity conflict')
                    expected=request['expected_revision']
            method='POST';path=BASE+'/commands';body={'contract_version':CONTRACT,
                'operation_id':args.operation_id,'intent':args.action,'selection':package['selection'],
                'package_digest':package_digest,'confirm':args.confirm,'expected_revision':expected}
        status,result=service.handle(method,path,token,body)
        if args.action=='prepare' and status==200:
            _write_private(Path(args.output),json.dumps(result,ensure_ascii=False,sort_keys=True).encode())
        print(json.dumps(result,sort_keys=True,ensure_ascii=False));return 0 if status==200 else 1
    except (OSError,ValueError,RuntimeError,PermissionError,KeyError,TypeError):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'RELEASE_CLI_UNAVAILABLE'}}));return 1

if __name__=='__main__':raise SystemExit(main())
