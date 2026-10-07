"""Exact installed readproducer over real canonical workset/governance/auth/HTTP.

Only external Codex/OS/credential adapters reuse the qualified FCI fixtures.
"""
from contextlib import ExitStack,contextmanager
from copy import deepcopy
from datetime import UTC,datetime,timedelta
from hashlib import sha256
from importlib.util import module_from_spec,spec_from_file_location
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from jsonschema import Draft202012Validator,FormatChecker
import forge
from forge.approved_worklist import ApprovedWorklistService,CONTRACT,projection
from forge.lifecycle import RecommendationLifecycleStore
from forge.server_runtime import ForgeServerRuntime,existing_instance
from forge.workspace_worklist_grant import WorkspaceWorklistGrant
from unittest.mock import patch


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--source-revision',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--failure-control',action='store_true')
    parser.add_argument('--child',action='store_true')
    args=parser.parse_args(argv)
    if not sys.flags.isolated or sys.flags.optimize or sys.version_info[:2]!=(3,14):
        raise RuntimeError('qualification requires isolated assertion-enabled Python3.14')
    source=Path(__file__).resolve().parents[2]
    spec=spec_from_file_location('qualified_http_fixture',source/'scripts/qualification/qualify_installed_http_successor.py')
    utils=module_from_spec(spec);spec.loader.exec_module(utils)
    output=args.output_dir.resolve()
    if not args.child:
        artifact=utils._installed_wheel(args.wheel,source_revision=args.source_revision)
        if output.exists():raise ValueError('qualification output must be fresh')
        output.mkdir(parents=True)
        (output/'artifact.parent.private.json').write_text(json.dumps(artifact))
        command=[sys.executable,'-I',str(Path(__file__).resolve()),'--wheel',str(args.wheel.resolve()),
            '--source-revision',args.source_revision,'--output-dir',str(output),'--child']
        if args.failure_control:command.append('--failure-control')
        done=subprocess.run(command,cwd=output,env=utils._child_env(output/'isolated'),
            capture_output=True,text=True,timeout=120)
        (output/'child.private.log').write_text(done.stdout+done.stderr)
        if done.returncode not in (0,1):raise RuntimeError('isolated read qualification process failed')
        receipt=json.loads((output/'installed-worklist-read.public.json').read_text())
        assert receipt['artifact']==artifact and receipt['source_revision']==args.source_revision
        print(json.dumps(receipt,sort_keys=True));return done.returncode
    artifact=json.loads((output/'artifact.parent.private.json').read_text())
    root=output/'isolated';root.mkdir()
    for folder in ['home','config','scratch']:(root/folder).mkdir()
    checks=[];result=None;error=None;stage='setup';observed_read_status=None
    try:
        with ExitStack() as stack:
            utils._configure(root,'http://127.0.0.1:9')
            runtime=utils._open(root,stack)
            data=Path(runtime.data_root)
            lifecycle=stack.enter_context(RecommendationLifecycleStore(data/'governance'/'candidates.sqlite'))
            candidate,bridge,mission,planning=utils._candidate_fixture(lifecycle,runtime,suffix='-read')
            bridge.approve_business(candidate.id,actor=utils.GOVERNANCE_ACTOR,occurred_at='2026-10-07T00:00:00Z',
                                    rationale='Synthetic value approval.',human_gates=planning.human_gates)
            bridge.approve_architecture(candidate.id,mission,planning,actor=utils.GOVERNANCE_ACTOR,
                                        occurred_at='2026-10-07T00:00:01Z',rationale='Synthetic technical approval.')
            expiry=(datetime.now(UTC)+timedelta(hours=1)).isoformat()
            definition={'contract_version':CONTRACT,'workset_id':'alice-set','profile_id':utils.GOVERNANCE_PROFILE,
                'expires_at':expiry,'maximum_activations':1,'members':[{'candidate_id':candidate.id,
                 'subject_revision':bridge.decision_ids(candidate.id)[0],'mission':mission.to_dict(),
                 'planning':planning.to_dict(),'dependencies':[],'truth':{},'progression_policy':{}}]}
            service=ApprovedWorklistService(runtime,lifecycle);value=service.propose(definition)
            for role in ['business','architecture']:
                value=service.decide('alice-set',expected_revision=value['revision'],role=role,actor=utils.GOVERNANCE_ACTOR)
            value=service.control('alice-set',expected_revision=value['revision'],operation='arm')
            other=deepcopy(definition);other['workset_id']='bob-set';service.propose(other)
            instance=existing_instance(data);grant=WorkspaceWorklistGrant(data,instance.instance_id)
            alice=root/'alice-token';bob=root/'bob-token'
            alice_record=grant.issue(principal_id='alice',workset_ids=('alice-set',),expires_at=expiry,token_path=alice)
            grant.issue(principal_id='bob',workset_ids=('bob-set',),expires_at=expiry,token_path=bob)
            admin=root/'admin-token';admin.write_text('a'*48);admin.chmod(0o600)
            server=ForgeServerRuntime(data_root=data,credential_file=admin,host='127.0.0.1',port=0)
            thread=Thread(target=server.server.serve_forever,daemon=True);thread.start()
            stack.callback(server.server.server_close);stack.callback(thread.join,3);stack.callback(server.server.shutdown)
            port=server.server.server_address[1];endpoint=f'http://127.0.0.1:{port}'
            attempted=[];original=socket.socket.connect
            def connect(sock,address):
                if address!=('127.0.0.1',port):
                    attempted.append('FORBIDDEN_TRANSPORT');raise AssertionError('readproducer attempted non-test network')
                return original(sock,address)
            stack.enter_context(patch('socket.socket.connect',connect))
            stack.enter_context(patch('subprocess.run',side_effect=AssertionError('readproducer invoked external process')))
            auth='Bearer '+alice.read_text().strip();auth_b='Bearer '+bob.read_text().strip()
            def request(path,method='GET',credential=auth):
                req=Request(endpoint+path,headers={'Authorization':credential},method=method)
                try:
                    with urlopen(req,timeout=4) as response:return response.status,json.load(response)
                except HTTPError as exc:
                    with exc:return exc.code,json.load(exc)
            schema=json.loads((Path(forge.__file__).parent/'api/workspace-worklist-v1.json').read_text())
            before=sha256((data/'forge.db').read_bytes()).hexdigest()
            if args.failure_control:grant.revoke(alice_record['grant_id'])
            stage='positive-read'
            code,snapshot=request('/v1/worksets/alice-set');observed_read_status=code;assert code==200
            stage='scoped-negatives'
            Draft202012Validator(schema,format_checker=FormatChecker()).validate(snapshot)
            assert snapshot['scope']['principal_id']=='alice' and snapshot['scope']['project_id'] is None
            assert snapshot['items'][0]['mission_id'] is None and snapshot['items'][0]['approved'] is True
            assert snapshot['activation_support']=='NOT_YET_QUALIFIED'
            assert snapshot['items'][0]['blocking_reasons']==['ACTIVATION_NOT_YET_QUALIFIED']
            checks.append('scoped-complete-schema-bound-read')
            assert request('/v1/worksets')[1]['workset_ids']==['alice-set']
            assert request('/v1/worksets/bob-set')[0]==403
            assert request('/v1/worksets/alice-set',credential=auth_b)[0]==403
            assert request('/v1/worksets/bob-set',credential=auth_b)[1]['scope']['principal_id']=='bob'
            for path in ['/v1/status','/v1/reviews','/v1/missions','/v1/worksets/alice-set/hold']:
                assert request(path,'POST' if path.endswith('hold') else 'GET')[0]==403
            assert request('/v1/worksets/alice-set',credential='Bearer wrong')[0]==401
            assert request('/v1/worksets/alice-set')[1]['snapshot_revision']==snapshot['snapshot_revision']
            assert sha256((data/'forge.db').read_bytes()).hexdigest()==before
            checks.extend(['two-actor-scope-isolation','mutation-and-unrelated-route-denial','stable-snapshot-zero-storage-mutation'])
            value=service.control('alice-set',expected_revision=value['revision'],operation='hold')
            held=request('/v1/worksets/alice-set')[1]
            assert 'WORKSET_HELD' in held['items'][0]['blocking_reasons']
            assert held['snapshot_revision']!=snapshot['snapshot_revision']
            checks.append('real-control-transition-readback')
            source_db=data/'governance'/'candidates.sqlite';missing=source_db.with_suffix('.withheld')
            source_db.rename(missing)
            try:assert request('/v1/worksets/alice-set')[0]==503
            finally:missing.rename(source_db)
            checks.append('source-outage-denial')
            grant.revoke(alice_record['grant_id']);assert request('/v1/worksets/alice-set')[0]==401
            checks.append('current-revocation-denial')
            assert not attempted
            for table in ['mission_state','mission_id_allocations','scheduler_submissions','action_derivations','execution_receipts']:
                assert runtime.database._connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0
            assert not (root/'provider-inputs.private.json').exists()
            checks.append('zero-allocation-planning-provider-and-ep-effects')
            result='WORKLIST_READ_PASS'
    except (AssertionError,ValueError,RuntimeError,OSError) as exc:
        result='FAIL';error=type(exc).__name__
    finally:
        shutil.rmtree(root)
    receipt={'result':result,'qualification':'INSTALLED_SCOPED_WORKLIST_READ_V1',
        'source_revision':args.source_revision,'artifact':artifact,'checks':checks,
        'failure_type':error,'failure_stage':stage if error else None,'observed_read_status':observed_read_status,
        'forge_processes':1,'environment':'ISOLATED_CHILD_HOME_CONFIG_SCRATCH','external_fault':'revoked-positive-read-credential' if args.failure_control else None,
        'expected_failure_control':bool(args.failure_control),'cleanup':{'owned_runtime_home_credentials_scratch_removed':not root.exists()},
        'limitations':['Read producer foundation; serial activation not yet qualified.','Synthetic separate canonical approvals are not independent live people.','No live EP/provider/operational activation or publication.']}
    (output/'installed-worklist-read.public.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps(receipt,sort_keys=True));return 0 if result=='WORKLIST_READ_PASS' else 1

if __name__=='__main__':raise SystemExit(main())
