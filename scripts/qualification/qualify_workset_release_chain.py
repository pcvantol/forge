"""Actual chat-first A→B approvals/release/runtime through existing EP HTTP simulator.

Only external model process, OS identity, repository and EP transports are
explicit synthetic adapters. Canonical subjects, admission, decisions, release,
claims, runtime, criterion completion and final acceptance are production code.
"""
from contextlib import ExitStack,closing
from datetime import UTC,datetime,timedelta
from hashlib import sha256
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import json,subprocess,sys,os,time,sqlite3
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[2]
if '--source-development' in sys.argv:sys.path.insert(0,str(SOURCE))
spec=spec_from_file_location('release_serial_fixture',SOURCE/'scripts/qualification/qualify_installed_worklist_activation.py')
serial=module_from_spec(spec);spec.loader.exec_module(serial);utils=serial.utils


def chat_setup(root,endpoint,scenario,*,release=True,maximum_activations=2,approve_unreleased_c=False):
    sys.path.insert(0,str(SOURCE/'tests'))
    import test_mission_concept_ready_http as ready
    import test_mission_concept_contract as content
    from forge.advisory_context import AdvisoryContext
    from forge.execution_host_configuration import EngineeringPlatformPeerConfigurationService
    from forge.mission_concept_setup import MissionConceptSetup
    from forge.server_runtime import existing_instance
    from forge.workset_release_grant import WorksetReleaseGrant,CONTRACT
    from forge.workset_release_cli import main as release_cli
    from forge.workspace_review_grant import _write_private
    from io import StringIO
    grant=ready.configure(root)
    root.chmod(0o700)
    target,baseline,manifest=utils._effect_target_fixture(root,scenario)
    from forge.execution_host_configuration import read_peer_configuration
    binding=read_peer_configuration(root/'runtime').configuration
    EngineeringPlatformPeerConfigurationService(root/'runtime').configure(binding_id=binding.binding_id,
        endpoint=endpoint,expected_ep_instance_id=binding.expected_ep_instance_id,
        ep_consumer_id=binding.ep_consumer_id,execution_host_id=binding.execution_host_id,
        ep_project_id=binding.ep_project_id,ep_repository_id=binding.ep_repository_id,
        repository_identity=binding.repository_identity,credential_reference=utils.SecretReference.parse(binding.credential_reference),
        operator_id='isolated-qualification',allow_loopback_http=True,replace=True,expected_revision=binding.configuration_revision,expected_digest=binding.configuration_digest)
    policy=utils._effect_policy(scenario)
    profile={'effect_policy':policy.to_dict(),'constraints':['Preserve the approved repository effect boundary.'],
        'technical_assumptions':['Use existing source evidence and canonical runtime.'],
        'required_capabilities':[utils.HOST],'required_disciplines':['platform_architecture'],
        'human_gates':['protected-delivery'],'maximum_actions':4,'maximum_consecutive_no_progress_actions':2,
        'components':{'Deployment boundary':{'description':'Assess the existing deployment boundary.',
            'read_paths':['docs/design.md'],'write_paths':list(policy.write_paths)}}}
    kind={'READ_ONLY_ASSESSMENT':'INVESTIGATE','DOCUMENTATION_ONLY':'DOCUMENT','ARCHITECTURE_DESIGN_ONLY':'DESIGN'}[policy.mode]
    approved=[]
    with ready.qual.http(root) as port:
        instance=existing_instance(root/'runtime');operator=sha256(utils.fixture.IDENTITY.generated_uid.encode()).hexdigest()[:16]
        token=root/'chat-owner.private';issued=grant.issue(principal_id=operator,project_id=utils.PROJECT,
            repository_id=utils.fixture.SOURCE.repository_id,conversation_ids=['a','b','c'],maximum_turns=8,
            expires_at=(datetime.now(UTC)+timedelta(hours=2)).isoformat(),token_path=token)
        MissionConceptSetup(root/'runtime',instance.instance_id).configure(grant_id=issued['grant_id'],profiles={kind:profile},maximum_missions=3 if approve_unreleased_c else 2)
        context=AdvisoryContext(root/'runtime',instance.instance_id);context.revoke('selected-context')
        revision=utils.fixture._read(root/'effect-target.private.json')['source_revision']
        with patch('forge.completion.repository_observer.GitHubRepositoryArtifactReader.read',return_value=(target/'docs/design.md').read_bytes()):
            context.publish(source_id='execution-source',revision=revision,path='docs/design.md')
        for conversation in ('a','b','c'):
            definition={**content.MissionConceptContractTests().output()['definition'],
                'title':'Assessment '+conversation.upper(),'objective':'Assess the approved deployment boundary '+conversation.upper()+'.',
                'work_kind':kind,'components':['Deployment boundary'],'scope':['Deployment boundary'],
                'acceptance_criteria':['Explain the deployment boundary with source evidence.'],
                'risks':['scope-drift'],'exclusions':['Do not perform effects outside the approved mode.'],
                'dependencies':[approved[0]['candidate_id']] if conversation=='b' else [],
                'dependency_reasons':{approved[0]['candidate_id']:'B requires the accepted source evidence from A.'} if conversation=='b' else {}}
            ready.model_output(root,definition)
            status,current=ready.call(port,token,'GET','/v1/mission-concepts/'+conversation+'/context');assert status==200,current
            request={k:current['context'][k] for k in ('instance_id','project_id','repository_id')}
            request.update(contract_version='forge-chat-first-mission/v1',conversation_id=conversation,turn_id='initial',
                expected_revision=0,context_revision=current['context_revision'],selected_sources=[],advisor_kind='ARCHITECTURE',objective=definition['objective'])
            status,turn=ready.call(port,token,'POST','/v1/mission-concepts/'+conversation+'/turns',request);assert status==200,turn
            if conversation=='c' and not approve_unreleased_c:continue  # Genuine unapproved concept remains outside.
            status,prepared=ready.call(port,token,'GET','/v1/mission-concepts/'+conversation+'/package');assert status==200 and prepared['approval_supported'],prepared
            status,result=ready.call(port,token,'POST','/v1/mission-concepts/'+conversation+'/approve',{
                'contract_version':'forge-chat-first-mission/v1','operation_id':'approve-'+conversation,
                'revision':prepared['revision'],'package_digest':prepared['package_digest'],'confirm':True});assert status==200,result
            approved.append(result)
        selected=approved[:2]
        subjects=[{'candidate_id':a['candidate_id'],'subject_revision':a['intake_subject_revision']} for a in selected]
        release_grant=WorksetReleaseGrant(root/'runtime',instance.instance_id)
        record=release_grant.issue(principal_id=operator,project_id=utils.PROJECT,repository_id=utils.fixture.SOURCE.repository_id,
            permissions=['READ','RELEASE','DISARM'],subjects=subjects,maximum_releases=1,maximum_activations=2,
            expires_at=(datetime.now(UTC)+timedelta(hours=2)).isoformat(),token_path=root/'release.private')
        prefix=['--data-root',str(root/'runtime'),'--token-file',str(root/'release.private')]
        prepared_path=root/'prepared.private.json'
        with patch('sys.stdout',new_callable=StringIO):
            assert release_cli(prefix+['prepare','--mission-id',approved[0]['mission_id'],'--mission-id',approved[1]['mission_id'],
                '--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--maximum-activations',str(maximum_activations),
                '--progression-mode','continuous','--output',str(prepared_path)])==0
        package=json.loads(prepared_path.read_text());assert package['release_supported'],package
        from forge.workset_release_service import BASE
        # Reads/prepare and unconfirmed release have not created a workset.
        with utils.RuntimeBootstrap(data_root=root/'runtime',forge_version='qualification').open() as db:
            assert db._connection.execute('SELECT count(*) FROM approved_worksets').fetchone()[0]==0
        released={'workset_id':package['package']['definition']['workset_id']}
        if release:
            with patch('sys.stdout',new_callable=StringIO):
                assert release_cli(prefix+['release','--prepared-file',str(prepared_path),'--operation-id','release-a-b','--confirm'])==0
            status,released=ready.call(port,root/'release.private','GET',BASE+'/operations/release-a-b');assert status==200,released
            assert 'DEPENDENCY_NOT_PROVEN' in released['current']['items'][1]['blocking_reasons']
            assert [i['mission_id'] for i in released['current']['items']]==[a['mission_id'] for a in selected]
        utils.fixture._write(root/'release-case.private.json',{'workset_id':released['workset_id'],
            'grant_id':record['grant_id'],'mission_ids':[a['mission_id'] for a in selected],
            **({'unreleased_mission_id':approved[2]['mission_id']} if approve_unreleased_c else {})})
        utils.fixture._write(root/'effect-scenario.private.json',{'scenario':scenario})
    return target,baseline,manifest


def phase(root,scenario,name,endpoint):
    from forge.approved_worklist import ApprovedWorklistService,candidate_source,projection
    from forge.lifecycle import RecommendationLifecycleStore
    from forge.runtime.service import ForgeRuntimeService
    from forge.server_runtime import _ResumeOnlyLoop
    data=utils.fixture._read(root/'release-case.private.json');key=data['workset_id']
    original_transport=utils.fixture._CodexTransport.__call__
    def transport(adapter,command,**kwargs):
        result=original_transport(adapter,command,**kwargs)
        if 'exec' in command and result.returncode==0:
            path=Path(command[command.index('--output-last-message')+1]);document=json.loads(path.read_text())
            proposal=document['result']['proposals'][0];proposal['scope']=utils.fixture.SOURCE.repository_id
            path.write_text(json.dumps(document))
        return result
    with ExitStack() as stack:
        stack.enter_context(patch.object(utils.fixture._CodexTransport,'__call__',transport))
        runtime=utils._open(root,stack,effect_scenario=scenario)
        original_run=subprocess.run
        def github(command,**kwargs):
            if command[:2]==['gh','api']:
                repo=utils.fixture.SOURCE.github_repository
                assert command[-1] in {'repos/'+repo,'repos/'+repo+'/commits/main'}
                value={'default_branch':'main','full_name':repo} if command[-1]=='repos/'+repo else {'sha':utils._fixture_git(root,root/'synthetic-target','rev-parse','HEAD')}
                return subprocess.CompletedProcess(command,0,json.dumps(value),'')
            return original_run(command,**kwargs)
        stack.enter_context(patch('subprocess.run',github))
        with RecommendationLifecycleStore(candidate_source(root/'runtime')) as store:
            service=ApprovedWorklistService(runtime,store)
            if name=='tick':ForgeRuntimeService(_ResumeOnlyLoop(runtime),runtime.states,runtime_database=runtime.database).tick()
            elif name=='pause-claim':
                def identity():
                    if at_boundary(root,'crash-after-claim'):
                        (root/'boundary.ready.private').write_text(str(os.getpid()))
                        while not (root/'boundary.continue.private').exists():time.sleep(0.02)
                    return utils.fixture.IDENTITY
                with patch.object(utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity):
                    ForgeRuntimeService(_ResumeOnlyLoop(runtime),runtime.states,runtime_database=runtime.database).tick()
            elif name=='release' or name.startswith('crash-') or name=='lost-response':
                from forge.workset_release_cli import main
                from io import StringIO
                def identity():
                    if name.startswith('crash-') and at_boundary(root,name):
                        (root/'boundary.ready.private').write_text(str(os.getpid()))
                        while not (root/'boundary.continue.private').exists():time.sleep(0.02)
                    return utils.fixture.IDENTITY
                with patch.object(utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity), \
                        patch('sys.stdout',new_callable=StringIO) as output:
                    code=main(['--data-root',str(root/'runtime'),'--token-file',str(root/'release.private'),
                        'release','--prepared-file',str(root/'prepared.private.json'),
                        '--operation-id','release-a-b','--confirm'])
                    assert code==0,output.getvalue()
                if name=='lost-response':os._exit(23)
            elif name.startswith('accept-'):
                index=int(name[-1])-1;mission_id=data['mission_ids'][index];pending=runtime.states.get(mission_id).pause_reason
                decision={k:pending[k] for k in ('requirement_id','subject_digest','mission_state_revision','completion_digest','terminal_evidence_digest','policy_revision')}
                decision.update(schema_version='forge-final-acceptance-decision/v1',decision_id='release-final-'+str(index),decision='accept',reason='Real source-bound synthetic evidence inspected.')
                context=runtime.repository.operators.context()
                runtime.accept_final_completion(mission_id,decision,authenticated_principal_reference='local-operator:v1:'+runtime.repository._operator_id(context))
            elif name=='revoke':
                from forge.workset_release_grant import WorksetReleaseGrant
                WorksetReleaseGrant(root/'runtime',runtime.database.runtime_identity.runtime_id).revoke(data['grant_id'])
            elif name in ('disarm','pause-disarm'):
                from forge.workset_release_cli import main
                from io import StringIO
                def identity():
                    if name=='pause-disarm' and at_boundary(root,'crash-disarm-intent'):
                        (root/'boundary.ready.private').write_text(str(os.getpid()))
                        while not (root/'boundary.continue.private').exists():time.sleep(.02)
                    return utils.fixture.IDENTITY
                with patch.object(utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity),patch('sys.stdout',new_callable=StringIO) as output:
                    assert main(['--data-root',str(root/'runtime'),'--token-file',str(root/'release.private'),
                        'disarm','--original-operation-id','release-a-b','--operation-id','withdraw','--confirm'])==0,output.getvalue()
            elif name!='read':raise ValueError('unknown qualification phase')
            states=[runtime.database.get_document('mission_state',m) for m in data['mission_ids']]
            value=service._get(key);read=projection(root/'runtime',runtime.database.runtime_identity.runtime_id,key,'qualification')
            return {'phase':name,'states':states,'workset':value,'read':read,
                'allocations':runtime.database._connection.execute('SELECT count(*) FROM mission_id_allocations').fetchone()[0],
                'governance_decisions':runtime.database._connection.execute('SELECT count(*) FROM governance_decisions').fetchone()[0],
                'provider_invocations':len(utils.fixture._read(root/'provider-inputs.private.json',[])),
                'pid':__import__('os').getpid(),'candidate_count':store._connection.execute('SELECT count(*) FROM candidates').fetchone()[0]}


def flow(root,scenario='effect-read-only',*,failure_control=False,disarm=False,phase_runner=None,maximum_activations=2):
    phase_runner=phase_runner or phase
    simulator=utils.EpSimulatorState(project_id=utils.PROJECT,repository_id=utils.fixture.SOURCE.repository_id,
        repository_identity=utils.fixture.SOURCE.github_repository,consumer_id=utils.CONSUMER,
        instance_id=utils.INSTANCE,bearer_token=utils.TOKEN,
        scenario=utils.EpSimulatorScenario(name=scenario,effect_declaration_supported=True))
    server=utils.EpSimulatorServer(simulator);requests=utils._count_ep_http_requests(server)
    records=[]
    with server:
        target,baseline,manifest=chat_setup(root,server.base_url,scenario,maximum_activations=maximum_activations)
        initial=phase_runner(root,scenario,'read',server.base_url);records.append(initial)
        assert initial['allocations']==2 and initial['governance_decisions']==6 and initial['provider_invocations']==0
        for index in (1,2):
            current=phase_runner(root,scenario,'tick',server.base_url);records.append(current)
            if failure_control and index==2:
                data=utils.fixture._read(root/'release-case.private.json')
                from forge.workset_release_grant import WorksetReleaseGrant
                from forge.server_runtime import existing_instance
                grant=WorksetReleaseGrant(root/'runtime',existing_instance(root/'runtime').instance_id)
                revoked=next(r for r in grant._records() if r['grant_id']==data['grant_id'])['state']=='REVOKED'
                detected=revoked and 'RELEASE_CAPABILITY_UNAVAILABLE' in current['read']['items'][1]['blocking_reasons'] and current['provider_invocations']==1
                assert len(simulator.submission_ids())==index,'revoked-positive-workset-activation-detected' if detected else current
            else:assert len(simulator.submission_ids())==index,current
            assert current['allocations']==2 and current['workset']['consumed_activations']==index,current
            submission=simulator.submission_ids()[-1];payload=simulator.submitted_payload(submission)
            assert payload['constraints']['effect_contract']['mode']==utils._effect_policy(scenario).mode
            snapshot=utils._effect_target_snapshot(target);source_manifest={p:snapshot[p] for p in manifest}
            revision,_=utils._execute_effect_fixture(root,target,baseline,payload)
            simulator.complete(submission,delivery_revision=revision)
            readback,artifact=simulator.terminal_documents(submission)
            readback,result,terminal=utils.qualified_effect_result(payload,readback,artifact,source_manifest=source_manifest)
            simulator.seed_terminal(submission,readback,terminal);simulator.seed_effect_result(submission,result)
            pending=phase_runner(root,scenario,'tick',server.base_url);records.append(pending)
            assert pending['states'][index-1]['status']=='AWAITING_APPROVAL',pending
            waiting=phase_runner(root,scenario,'tick',server.base_url);records.append(waiting)
            assert len(simulator.submission_ids())==index
            accepted=phase_runner(root,scenario,'accept-'+str(index),server.base_url);records.append(accepted)
            assert accepted['states'][index-1]['status']=='COMPLETED'
            if index==maximum_activations and maximum_activations<2:
                blocked=phase_runner(root,scenario,'tick',server.base_url);records.append(blocked)
                assert 'ACTIVATION_LIMIT_EXHAUSTED' in blocked['read']['items'][1]['blocking_reasons'],blocked['read']['continuation']
                assert blocked['read']['items'][1]['eligibility']=='BLOCKED'
                assert blocked['read']['continuation']['state']=='BLOCKED'
                assert blocked['workset']['consumed_activations']==blocked['provider_invocations']==1
                assert blocked['allocations']==2 and blocked['governance_decisions']==8
                assert len(blocked['workset']['claims'])==1 and len(simulator.submission_ids())==1
                assert blocked['states'][1]['status']=='APPROVED_PLANNABLE'
                assert len((root/'provider-requests.private.jsonl').read_text().splitlines())==3
                return records
            if index==1 and failure_control:phase_runner(root,scenario,'revoke',server.base_url)
            if index==1 and disarm:
                phase_runner(root,scenario,'disarm',server.base_url)
                denied=phase_runner(root,scenario,'tick',server.base_url)
                assert len(simulator.submission_ids())==1 and denied['workset']['consumed_activations']==1
                return records+[denied]
        idle=phase_runner(root,scenario,'tick',server.base_url);records.append(idle)
        assert idle['read']['continuation']['state']=='IDLE' and idle['allocations']==2
        assert idle['workset']['consumed_activations']==idle['provider_invocations']==2 and idle['governance_decisions']==10, {k:idle[k] for k in ('governance_decisions','provider_invocations','allocations')}
        assert idle['candidate_count']==2 and len((root/'provider-requests.private.jsonl').read_text().splitlines())==3
        assert len(simulator.submission_ids())==2 and sum(r.startswith('POST ') for r in requests)==2
        return records


def at_boundary(root,name):
    journals=list((root/'runtime'/'governance'/'workset-release').glob('*.json'))
    with closing(sqlite3.connect((root/'runtime'/'forge.db').resolve().as_uri()+'?mode=ro',uri=True)) as db:
        row=db.execute('SELECT document FROM approved_worksets').fetchone()
        value=json.loads(row[0]) if row else None
        count=db.execute("SELECT count(*) FROM governance_decisions WHERE decision_id LIKE 'workset:%'").fetchone()[0]
    if name=='crash-before-intent':return not journals and value is None
    if name=='crash-after-intent':return bool(journals) and value is None
    if name=='crash-after-propose':return bool(value) and 'release_capability' not in value
    if name=='crash-before-business':return bool(value) and 'release_capability' in value and count==0
    if name=='crash-business-between-stores':return count==1 and not value['decisions']
    if name=='crash-after-business':return count==1 and set(value['decisions'])=={'business'}
    if name=='crash-architecture-between-stores':return count==2 and set(value['decisions'])=={'business'}
    if name=='crash-after-architecture':return count==2 and set(value['decisions'])=={'business','architecture'} and value['release']=='DISARMED'
    if name=='crash-disarm-intent':
        return bool(value) and value['release']=='AUTO_WHEN_ELIGIBLE' and any('withdraw' in json.loads(p.read_text())['operations'] for p in journals)
    if name=='crash-after-claim':return bool(value) and len(value['claims'])==1 and next(iter(value['claims'].values())).get('mission_id') is None
    if name=='crash-after-arm':return bool(value) and value['release']=='AUTO_WHEN_ELIGIBLE'
    raise ValueError('unknown crash boundary')


def phase_command(root,scenario,name,endpoint):
    command=[sys.executable,'-I',str(Path(__file__).resolve()),'--phase',name,'--root',str(root),
             '--scenario',scenario,'--endpoint',endpoint]
    import forge
    if Path(forge.__file__).resolve().is_relative_to(SOURCE):command.append('--source-development')
    return command


def crash_recovery(root,stage,*,withdraw_between=False,revoke_between=False,alias_after_revoke=False):
    simulator=utils.EpSimulatorState(project_id=utils.PROJECT,repository_id=utils.fixture.SOURCE.repository_id,
        repository_identity=utils.fixture.SOURCE.github_repository,consumer_id=utils.CONSUMER,
        instance_id=utils.INSTANCE,bearer_token=utils.TOKEN,
        scenario=utils.EpSimulatorScenario(name='release-recovery',effect_declaration_supported=True))
    with utils.EpSimulatorServer(simulator) as server:
        chat_setup(root,server.base_url,'effect-read-only',release=False)
        process=subprocess.Popen(phase_command(root,'effect-read-only',stage,server.base_url),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+20
            while not (root/'boundary.ready.private').exists() and process.poll() is None and time.monotonic()<deadline:
                time.sleep(0.02)
            if stage=='lost-response':
                stdout,stderr=process.communicate(timeout=20);assert process.returncode==23,stderr
            else:
                assert (root/'boundary.ready.private').exists(),process.communicate(timeout=1)
                process.kill();stdout,stderr=process.communicate(timeout=5);assert process.returncode<0
        finally:
            if process.poll() is None:process.kill();process.communicate(timeout=5)
        (root/'terminated-boundary.private.log').write_text(stdout+stderr)
        data=utils.fixture._read(root/'release-case.private.json')
        with patch.object(utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',return_value=utils.fixture.IDENTITY):
            if revoke_between:
                from forge.workset_release_grant import WorksetReleaseGrant
                from forge.server_runtime import existing_instance
                instance=existing_instance(root/'runtime')
                grant=WorksetReleaseGrant(root/'runtime',instance.instance_id)
                original=next(r for r in grant._records() if r['grant_id']==data['grant_id'])
                grant.revoke(data['grant_id'])
                if alias_after_revoke:
                    (root/'release.private').unlink()
                    grant.issue(principal_id=original['principal_id'],project_id=original['project_id'],
                        repository_id=original['repository_id'],permissions=original['permissions'],
                        subjects=original['subjects'],maximum_releases=original['maximum_releases'],
                        maximum_activations=original['maximum_activations'],expires_at=original['expires_at'],
                        token_path=root/'release.private')
            if withdraw_between:phase(root,'effect-read-only','disarm',server.base_url)
        if revoke_between or withdraw_between:
            recovered=subprocess.run(phase_command(root,'effect-read-only','release',server.base_url),capture_output=True,text=True,timeout=30)
            assert recovered.returncode!=0,'withdrawn/revoked release resumed effects'
            with closing(sqlite3.connect((root/'runtime'/'forge.db').resolve().as_uri()+'?mode=ro',uri=True)) as db:
                row=json.loads(db.execute('SELECT document FROM approved_worksets').fetchone()[0])
                assert row['release']=='DISARMED' and set(row['decisions'])=={'business'}
                assert db.execute('SELECT count(*) FROM governance_decisions').fetchone()[0]==5
            return {'case':stage,'result':'WITHDRAWN_OR_REVOKED_REMAINDER_DENIED'}
        result=process_phase(root,'effect-read-only','release',server.base_url)
        again=process_phase(root,'effect-read-only','release',server.base_url)
        assert result['allocations']==again['allocations']==2
        assert result['governance_decisions']==again['governance_decisions']==6
        assert result['workset']['release']=='AUTO_WHEN_ELIGIBLE' and result['workset']==again['workset']
        assert result['workset']['claims']=={} and result['provider_invocations']==0 and not simulator.submission_ids()
        assert len((root/'provider-requests.private.jsonl').read_text().splitlines())==3
        return {'case':stage,'result':'COLD_RECOVERY_PASS','original_workset_revision':result['workset']['revision']}


def race(root,*,activation=False,revoke_before_start=False,withdraw=False):
    simulator=utils.EpSimulatorState(project_id=utils.PROJECT,repository_id=utils.fixture.SOURCE.repository_id,
        repository_identity=utils.fixture.SOURCE.github_repository,consumer_id=utils.CONSUMER,
        instance_id=utils.INSTANCE,bearer_token=utils.TOKEN,
        scenario=utils.EpSimulatorScenario(name='release-race',effect_declaration_supported=True))
    with utils.EpSimulatorServer(simulator) as server:
        chat_setup(root,server.base_url,'effect-read-only',release=activation or withdraw)
        name='pause-disarm' if withdraw else 'pause-claim' if activation else 'crash-after-business'
        first=subprocess.Popen(phase_command(root,'effect-read-only',name,server.base_url),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+20
            while not (root/'boundary.ready.private').exists() and first.poll() is None and time.monotonic()<deadline:time.sleep(0.02)
            assert (root/'boundary.ready.private').exists()
            if revoke_before_start:
                from forge.workset_release_grant import WorksetReleaseGrant
                from forge.server_runtime import existing_instance
                with patch.object(utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',return_value=utils.fixture.IDENTITY):
                    instance=existing_instance(root/'runtime');data=utils.fixture._read(root/'release-case.private.json')
                    WorksetReleaseGrant(root/'runtime',instance.instance_id).revoke(data['grant_id'])
            else:
                second=subprocess.run(phase_command(root,'effect-read-only','disarm' if withdraw else 'tick' if activation else 'release',server.base_url),capture_output=True,text=True,timeout=30)
                assert second.returncode!=0 and ('RuntimeServiceBusy' in second.stderr or 'RELEASE_BUSY' in second.stderr),second.stderr
            (root/'boundary.continue.private').write_text('continue')
            stdout,stderr=first.communicate(timeout=30)
            if revoke_before_start:
                assert first.returncode!=0,stdout
                result=process_phase(root,'effect-read-only','tick',server.base_url)
                assert result['allocations']==2 and result['workset']['consumed_activations']==1
                assert result['provider_invocations']==0 and not simulator.submission_ids()
                assert all(s['status']=='APPROVED_PLANNABLE' for s in result['states'])
                assert 'RELEASE_CAPABILITY_UNAVAILABLE' in result['read']['items'][0]['blocking_reasons']
            else:
                assert first.returncode==0,stderr
                result=json.loads(stdout)
                if withdraw:
                    replay=process_phase(root,'effect-read-only','disarm',server.base_url)
                    assert result['workset']==replay['workset'] and result['workset']['release']=='DISARMED'
                elif activation:
                    assert result['workset']['consumed_activations']==1 and len(simulator.submission_ids())==1
                else:
                    replay=process_phase(root,'effect-read-only','release',server.base_url)
                    assert result['workset']==replay['workset'] and result['governance_decisions']==6
            return {'case':'disarm-race' if withdraw else 'revoke-before-start' if revoke_before_start else 'activation-race' if activation else 'release-race',
                'result':'REAL_PROCESS_RACE_PASS','consumed_activations':result['workset']['consumed_activations']}
        finally:
            if first.poll() is None:first.kill();first.communicate(timeout=5)


def process_phase(root,scenario,name,endpoint):
    command=phase_command(root,scenario,name,endpoint)
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    if result.returncode:raise AssertionError(result.stderr[-6000:])
    return json.loads(result.stdout)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--phase',required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--scenario',default='effect-read-only');p.add_argument('--endpoint',required=True)
    p.add_argument('--source-development',action='store_true');a=p.parse_args()
    print(json.dumps(phase(a.root,a.scenario,a.phase,a.endpoint)))
