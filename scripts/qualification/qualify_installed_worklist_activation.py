"""Real serial approved-workset flow with only external EP/LLM/OS/GitHub fixtures."""
from contextlib import ExitStack,closing
from datetime import UTC,datetime,timedelta
from importlib.util import spec_from_file_location,module_from_spec
import json
import sqlite3
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

_SOURCE=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('worklist_http_fixture',_SOURCE/'scripts/qualification/qualify_installed_http_successor.py')
utils=module_from_spec(spec);spec.loader.exec_module(utils)
from forge.approved_worklist import ApprovedWorklistService,CONTRACT,projection
from forge.lifecycle import RecommendationLifecycleStore
from forge.runtime.service import ForgeRuntimeService
from forge.server_runtime import _ResumeOnlyLoop


def _phase(root,scenario,phase,endpoint):
    if phase=='setup':
        utils._configure(root,endpoint)
        utils.fixture._write(root/'effect-scenario.private.json',{'scenario':scenario})
    case=utils.fixture._read(root/'case.private.json',{}).get('case','positive')
    with ExitStack() as stack:
        runtime=utils._open(root,stack,effect_scenario=scenario)
        original=subprocess.run
        def external_github(command,**kwargs):
            if command[:2]==['gh','api']:
                repository=utils.fixture.SOURCE.github_repository
                assert command[-1] in {'repos/'+repository,'repos/'+repository+'/commits/main'}
                document=({'default_branch':'main','full_name':repository} if command[-1]=='repos/'+repository else
                          {'sha':utils._fixture_git(root,root/'synthetic-target','rev-parse','HEAD')})
                return subprocess.CompletedProcess(command,0,json.dumps(document),'')
            return original(command,**kwargs)
        stack.enter_context(patch('subprocess.run',external_github))
        with RecommendationLifecycleStore(root/'runtime'/'governance'/'candidates.sqlite') as lifecycle:
            service=ApprovedWorklistService(runtime,lifecycle)
            if phase=='setup':
                members=[]
                for suffix in ('-a','-b'):
                    c,bridge,m,p=utils._candidate_fixture(lifecycle,runtime,effect_scenario=scenario,suffix=suffix)
                    bridge.approve_business(c.id,actor=utils.GOVERNANCE_ACTOR,occurred_at='2026-10-07T00:00:00Z',rationale='Exact synthetic worklist member.',human_gates=p.human_gates)
                    if not(case=='unapproved' and suffix=='-b'):bridge.approve_architecture(c.id,m,p,actor=utils.GOVERNANCE_ACTOR,occurred_at='2026-10-07T00:00:01Z',rationale='Exact synthetic technical scope.')
                    members.append({'candidate_id':c.id,'subject_revision':utils.canonical_digest(c.to_dict()),
                        'mission':m.to_dict(),'planning':p.to_dict(),'dependencies':[] if not members else [members[0]['candidate_id']],
                        'truth':utils._initial_truth(utils.fixture._read(root/'effect-target.private.json')['source_revision']).to_dict(),
                        'progression_policy':{'profile_id':utils.GOVERNANCE_PROFILE,'profile_revision':'1','policy_revision':'1','mode':'continuous','required_decision_role':'platform_architect','higher_scope_obligations':list(p.human_gates)}})
                value=service.propose({'contract_version':CONTRACT,'workset_id':'serial-set','profile_id':utils.GOVERNANCE_PROFILE,
                    'expires_at':(datetime.now(UTC)+(timedelta(seconds=1) if case=='expired' else timedelta(hours=1))).isoformat(),'maximum_activations':2,'members':members})
                for role in ('business','architecture'):
                    value=service.decide('serial-set',expected_revision=value['revision'],role=role,actor=utils.GOVERNANCE_ACTOR)
                try:service.control('serial-set',expected_revision=value['revision'],operation='arm')
                except ValueError:
                    if case!='unapproved':raise
                if case in {'hold','revoke','disarm'}:
                    value=service._get('serial-set');service.control('serial-set',expected_revision=value['revision'],operation=case)
                elif case=='stale':lifecycle.update_candidate(members[0]['candidate_id'],title='Unapproved changed subject')
                elif case=='operator-revoked':runtime.repository.operators.revoke(runtime.repository.operators.context())
            elif phase=='tick':
                ForgeRuntimeService(_ResumeOnlyLoop(runtime),runtime.states,runtime_database=runtime.database).tick()
            elif phase.startswith('accept-'):
                value=service._get('serial-set')
                member=value['definition']['members'][int(phase[-1])-1]
                mission_id=value['claims'][member['candidate_id']]['mission_id']
                pending=runtime.states.get(mission_id).pause_reason
                decision={k:pending[k] for k in ('requirement_id','subject_digest','mission_state_revision','completion_digest','terminal_evidence_digest','policy_revision')}
                decision.update({'schema_version':'forge-final-acceptance-decision/v1','decision_id':'worklist-final-'+phase[-1],
                    'decision':'accept','reason':'Actual synthetic criterion artifacts were proven.'})
                context=runtime.repository.operators.context()
                runtime.accept_final_completion(mission_id,decision,authenticated_principal_reference='local-operator:v1:'+runtime.repository._operator_id(context))
            elif phase in {'hold','unhold','revoke','disarm'}:
                value=service._get('serial-set');service.control('serial-set',expected_revision=value['revision'],operation=phase)
            elif phase!='read':raise ValueError('unsupported phase')
            states=[json.loads(row[0]) for row in runtime.database._connection.execute('SELECT document FROM mission_state ORDER BY mission_id')]
            value=service._get('serial-set')
            read=projection(Path(runtime.data_root),runtime.database.runtime_identity.runtime_id,'serial-set','qualification-reader')
            return {'phase':phase,'states':states,'workset':value,'read':read,
                'allocations':runtime.database._connection.execute('SELECT COUNT(*) FROM mission_id_allocations').fetchone()[0],
                'provider_invocations':len(utils.fixture._read(root/'provider-inputs.private.json',[])),
                'pid':__import__('os').getpid(),'runtime_id':runtime.database.runtime_identity.runtime_id}


def source_flow(root,scenario,*,phase_runner=None,failure_control=False):
    phase_runner=phase_runner or _phase
    root.mkdir()
    target,baseline,manifest=utils._effect_target_fixture(root,scenario)
    simulator=utils.EpSimulatorState(project_id=utils.PROJECT,repository_id=utils.fixture.SOURCE.repository_id,
        repository_identity=utils.fixture.SOURCE.github_repository,consumer_id=utils.CONSUMER,
        instance_id=utils.INSTANCE,bearer_token=utils.TOKEN,
        scenario=utils.EpSimulatorScenario(name=scenario,effect_declaration_supported=True,
            identity_readback_supported=scenario.endswith('-lost-ack'),
            connection_loss_at=frozenset({'submission-after-accept-once'}) if scenario.endswith('-lost-ack') else frozenset()))
    server=utils.EpSimulatorServer(simulator);requests=utils._count_ep_http_requests(server)
    records=[]
    with server:
        setup=phase_runner(root,scenario,'setup',server.base_url);records.append(setup)
        assert setup['allocations']==setup['provider_invocations']==0 and len(setup['workset']['definition']['members'])==2
        for index in (1,2):
            initial=phase_runner(root,scenario,'tick',server.base_url);records.append(initial)
            assert initial['allocations']==initial['provider_invocations']==index,initial
            assert len(simulator.submission_ids())==index
            submission_id=simulator.submission_ids()[-1];payload=simulator.submitted_payload(submission_id)
            current=utils._effect_target_snapshot(target)
            current_manifest={path:current[path] for path in manifest}
            revision,observation=utils._execute_effect_fixture(root,target,baseline,payload)
            simulator.complete(submission_id,delivery_revision=revision)
            readback,artifact=simulator.terminal_documents(submission_id)
            readback,result,terminal=utils.qualified_effect_result(payload,readback,artifact,source_manifest=current_manifest)
            simulator.seed_terminal(submission_id,readback,terminal);simulator.seed_effect_result(submission_id,result)
            pending=phase_runner(root,scenario,'tick',server.base_url);records.append(pending)
            assert pending['states'][-1]['status']=='AWAITING_APPROVAL',pending
            held=phase_runner(root,scenario,'tick',server.base_url);records.append(held)
            assert held['allocations']==held['provider_invocations']==index and len(simulator.submission_ids())==index
            accepted=phase_runner(root,scenario,'accept-'+str(index),server.base_url);records.append(accepted)
            assert accepted['states'][-1]['status']=='COMPLETED'
            if failure_control and index==1:phase_runner(root,scenario,'revoke',server.base_url)
        idle=phase_runner(root,scenario,'tick',server.base_url);records.append(idle)
        assert idle['read']['continuation']['state']=='IDLE' and idle['allocations']==idle['provider_invocations']==2
        assert idle['workset']['consumed_activations']==2 and len(simulator.submission_ids())==2
        return records


def source_denial(root,case,*,phase_runner=None):
    phase_runner=phase_runner or _phase
    root.mkdir()
    utils._effect_target_fixture(root,'effect-read-only')
    utils.fixture._write(root/'case.private.json',{'case':case})
    simulator=utils.EpSimulatorState(project_id=utils.PROJECT,repository_id=utils.fixture.SOURCE.repository_id,
        repository_identity=utils.fixture.SOURCE.github_repository,consumer_id=utils.CONSUMER,
        instance_id=utils.INSTANCE,bearer_token=utils.TOKEN,
        scenario=utils.EpSimulatorScenario(name='worklist-denial',effect_declaration_supported=True))
    server=utils.EpSimulatorServer(simulator);requests=utils._count_ep_http_requests(server)
    with server:
        setup=phase_runner(root,'effect-read-only','setup',server.base_url)
        if case=='expired':time.sleep(1.1)
        try:after=phase_runner(root,'effect-read-only','tick',server.base_url)
        except PermissionError as error:
            if case!='operator-revoked':raise
            with closing(sqlite3.connect((root/'runtime'/'forge.db').resolve().as_uri()+'?mode=ro',uri=True)) as db:
                value=json.loads(db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('serial-set',)).fetchone()[0])
                allocations=db.execute('SELECT COUNT(*) FROM mission_id_allocations').fetchone()[0]
            after={'workset':value,'allocations':allocations,'provider_invocations':len(utils.fixture._read(root/'provider-inputs.private.json',[])),
                'observed_denial':type(error).__name__}
        assert after['allocations']==after['provider_invocations']==after['workset']['consumed_activations']==0
        assert after['workset']['claims']=={} and not simulator.submission_ids()
        assert not any(request.startswith('POST ') for request in requests)
        return {'case':case,'setup':setup,'after':after}


def _summary(records):
    final=records[-1]
    return {'trace':[{'phase':r['phase'],'pid':r['pid'],'runtime_id':r['runtime_id'],'allocations':r['allocations'],
        'provider_invocations':r['provider_invocations'],'missions':[{'mission_id':s['mission_id'],'status':s['status'],
            'state_revision':s['revision'],'actions':len(s['actions']),'execution_receipts':len(s['execution_history']),
            'completion_digest':utils.canonical_digest(s.get('completion'))} for s in r['states']]} for r in records],
        'preapproved_members':[m['candidate_id'] for m in records[0]['workset']['definition']['members']],
        'release_before_first_intake':records[0]['allocations']==0 and records[0]['workset']['release']=='AUTO_WHEN_ELIGIBLE',
        'final_claims':final['workset']['claims'],'consumed_activations':final['workset']['consumed_activations'],
        'final_continuation':final['read']['continuation'],'provider_invocations':final['provider_invocations']}


class InstalledPhases:
    def __init__(self,args):
        self.args=args;self.observed=None;self.stage=None

    def command(self,root,scenario,phase,endpoint):
        import sys
        return [sys.executable,'-I',str(Path(__file__).resolve()),'--wheel',str(self.args.wheel.resolve()),
            '--source-revision',self.args.source_revision,'--output-dir',str(self.args.output_dir.resolve()),
            '--child-phase',phase,'--case-root',str(root),'--scenario',scenario,'--endpoint',endpoint]

    def __call__(self,root,scenario,phase,endpoint):
        self.stage='B-activation' if self.args.failure_control and phase=='tick' and (root/'revoked-before-b.private').exists() else phase
        done=subprocess.run(self.command(root,scenario,phase,endpoint),cwd=root,
            env=utils._child_env(root/'isolated'),capture_output=True,text=True,timeout=30)
        number=len(list(root.glob('phase-*.private.log')))
        (root/f'phase-{number:03d}.private.log').write_text(done.stdout+done.stderr)
        if done.returncode:raise RuntimeError('installed worklist phase failed: '+phase)
        document=json.loads(done.stdout);self.observed=document
        if phase=='revoke':(root/'revoked-before-b.private').touch()
        return document


def main(argv=None):
    import argparse
    from hashlib import sha256
    import os
    import shutil
    import socket
    import sys
    from urllib.parse import urlparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--source-revision',required=True)
    parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--failure-control',action='store_true')
    parser.add_argument('--child-phase');parser.add_argument('--case-root',type=Path)
    parser.add_argument('--scenario');parser.add_argument('--endpoint')
    args=parser.parse_args(argv)
    if not sys.flags.isolated or sys.flags.optimize or sys.version_info[:2]!=(3,14):
        raise RuntimeError('qualification requires isolated assertion-enabled Python3.14')
    if args.child_phase:
        utils._installed_wheel(args.wheel,source_revision=args.source_revision)
        if args.case_root is None or not args.case_root.is_dir():raise ValueError('fresh owned case required')
        selected=urlparse(args.endpoint)
        if selected.scheme!='http' or selected.hostname!='127.0.0.1' or not selected.port:
            raise ValueError('qualification requires its explicit loopback EP simulator')
        original=socket.socket.connect
        def only_simulator(sock,address):
            assert address==('127.0.0.1',selected.port),'non-test network attempted'
            return original(sock,address)
        with patch('socket.socket.connect',only_simulator):
            try:result=_phase(args.case_root,args.scenario,args.child_phase,args.endpoint)
            except PermissionError as error:
                if utils.fixture._read(args.case_root/'case.private.json',{}).get('case')!='operator-revoked':raise
                with closing(sqlite3.connect((args.case_root/'runtime'/'forge.db').resolve().as_uri()+'?mode=ro',uri=True)) as db:
                    value=json.loads(db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('serial-set',)).fetchone()[0])
                    allocations=db.execute('SELECT COUNT(*) FROM mission_id_allocations').fetchone()[0]
                result={'workset':value,'allocations':allocations,'provider_invocations':len(utils.fixture._read(args.case_root/'provider-inputs.private.json',[])),
                    'observed_denial':type(error).__name__,'pid':os.getpid()}
        print(json.dumps(result,sort_keys=True));return 0
    artifact=utils._installed_wheel(args.wheel,source_revision=args.source_revision,verify_source=True)
    output=args.output_dir.resolve()
    if output.exists():raise ValueError('qualification output must be fresh')
    output.mkdir(parents=True)
    runner=InstalledPhases(args);results=[];failure=None;stage=None;observed=None
    cases=([('effect-read-only','positive')] if args.failure_control else
           [(scenario,'positive') for scenario in utils._EFFECT_BASE_SCENARIOS]+
           [(scenario+'-lost-ack','positive') for scenario in utils._EFFECT_BASE_SCENARIOS]+
           [(case,'negative') for case in ('unapproved','expired','hold','revoke','disarm','stale','operator-revoked')])
    cleanup=[]
    try:
        for name,kind in cases:
            root=output/('case-'+name)
            try:
                if kind=='positive':
                    records=source_flow(root,name,phase_runner=runner,failure_control=args.failure_control)
                    result=_summary(records);result.update({'case':name,'status':'PASS','kind':kind})
                    if args.failure_control:raise AssertionError('faulted positive flow unexpectedly passed')
                else:
                    record=source_denial(root,name,phase_runner=runner)
                    result={'case':name,'status':'EXPECTED_DENIAL','kind':kind,'allocations':record['after']['allocations'],
                        'provider_invocations':record['after']['provider_invocations'],'claims':record['after']['workset']['claims'],
                        'observed_denial':record['after'].get('observed_denial'),
                        'blocking_reasons':[item['blocking_reasons'] for item in record['after'].get('read',{}).get('items',[])]}
                results.append(result)
            finally:
                for directory in ('runtime','synthetic-target','home','scratch','config','isolated'):
                    owned=root/directory
                    if owned.exists():shutil.rmtree(owned)
                cleanup.append({'case':name,'owned_runtime_target_home_config_scratch_removed':all(not (root/d).exists() for d in ('runtime','synthetic-target','home','scratch','config','isolated'))})
    except Exception as error:
        failure=type(error).__name__;stage=runner.stage
        observed=runner.observed
    receipt={'qualification':'INSTALLED_SERIAL_APPROVED_WORKLIST_V1','source_revision':args.source_revision,'artifact':artifact,
        'qualifier_sha256':'sha256:'+sha256(Path(__file__).read_bytes()).hexdigest(),
        'result':'FAIL' if failure else 'SERIAL_APPROVED_WORKLIST_PASS','cases':results,'case_count':len(results),
        'expected_case_count':len(cases),'failure_type':failure,'failure_stage':stage,
        'observed_allocations':None if observed is None else observed['allocations'],
        'observed_provider_invocations':None if observed is None else observed['provider_invocations'],
        'external_fault':'RELEASE_REVOKED_BEFORE_B' if args.failure_control else None,
        'cleanup':cleanup,'scope':'SERIAL_PREAPPROVED_WORKLIST_SUBSET',
        'limitations':['Synthetic canonical decisions are not independent live people.',
            'EP HTTP simulator and declared external LLM/OS/GitHub/local-Git fixtures; no live EP/provider/target writes.',
            'No full PRM/FCO family claim; projection qualification label remains separately gated.']}
    (output/'installed-worklist-activation.public.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'result':receipt['result'],'source_revision':args.source_revision,'cases':len(results),'failure_type':failure,'failure_stage':stage}))
    return 1 if failure else 0


if __name__=='__main__':raise SystemExit(main())
