"""Exact-wheel chat-first producer qualification with genuine canonical services."""
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from io import StringIO
import argparse,json,os,shutil,subprocess,sys,unittest
import forge

SOURCE=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('concept_installed_utils',SOURCE/'scripts/qualification/qualify_installed_http_successor.py')
utils=module_from_spec(spec);spec.loader.exec_module(utils)
MODULES=('test_mission_concept_contract','test_mission_concept_provider',
         'test_mission_concept_planning','test_mission_concept_ready_http',
         'test_mission_concept_dependencies','test_mission_concept_resolver',
         'test_mission_concept_recovery','test_mission_concept_output_boundaries',
         'test_mission_concept_readiness')


def positive_control(root):
    spec=spec_from_file_location('concept_recovery_control',SOURCE/'scripts/qualification/qualify_mission_concept_recovery.py')
    driver=module_from_spec(spec);spec.loader.exec_module(driver)
    ready,_=driver.cases();body=driver.prepare_case(root,'approval')
    with ready.qual.http(root) as port:
        token=root/'owner.private';path='/v1/mission-concepts/recovery-chat/approve'
        status,result=ready.call(port,token,'POST',path,body);assert status==200,result
        from forge.advisory_grant import AdvisoryGrant
        from forge.server_runtime import existing_instance
        instance=existing_instance(root/'runtime');grant=AdvisoryGrant(root/'runtime',instance.instance_id)
        principal=grant.authorize('Bearer '+token.read_text().strip(),'recovery-chat')
        grant.revoke(principal.grant_id)
        # A positive gate must fail when its real prerequisite is revoked.
        assert ready.call(port,token,'POST',path,body)[0]==200,'revoked-positive-concept-replay-detected'


def run(args):
    output=args.output_dir.resolve()
    artifact=utils._installed_wheel(args.wheel,source_revision=args.source_revision,verify_source=True)
    if not args.child:
        if output.exists():raise ValueError('qualification output must be fresh')
        output.mkdir()
        command=[sys.executable,'-I',str(Path(__file__).resolve()),'--wheel',str(args.wheel.resolve()),
            '--source-revision',args.source_revision,'--output-dir',str(output),'--child']
        if args.failure_control:command.append('--failure-control')
        result=subprocess.run(command,cwd=output,env=utils._child_env(output/'isolated'),
                              capture_output=True,text=True,timeout=360)
        (output/'child.private.log').write_text(result.stdout+result.stderr)
        if result.returncode not in (0,1):raise RuntimeError('installed concept child failed')
        receipt=json.loads((output/'installed-mission-concepts.public.json').read_text())
        assert receipt['artifact']==artifact and receipt['source_revision']==args.source_revision
        print(json.dumps({'result':receipt['result'],'case_count':receipt['case_count'],'failure':receipt['failure']}))
        return result.returncode
    for key in ('HOME','CODEX_HOME','TMPDIR'):
        assert Path(os.environ[key]).resolve().is_relative_to(output)
    package=Path(forge.__file__).resolve().parent
    schema=package/'api/mission-concepts-v1.json'
    assert schema.read_bytes()==(SOURCE/'forge/api/mission-concepts-v1.json').read_bytes()
    receipt={'qualification':'INSTALLED_CHAT_FIRST_MISSION_PRODUCER_V1',
        'source_revision':args.source_revision,'artifact':artifact,
        'schema_sha256':'sha256:'+sha256(schema.read_bytes()).hexdigest(),
        'result':'FAIL','case_count':0,'cases':[],'failure':None,
        'expected_failure_control':args.failure_control,
        'external_fault':'REVOKED_POSITIVE_CONCEPT_GRANT' if args.failure_control else None,
        'limitations':['Actual noneditable HTTP/auth/G001/context/provider adapter/validator/storage/approvals/Intake/worklist services.',
            'External deterministic model executable, OS identity and repository transport only; live model quality not qualified.',
            'Logical governed-activation readiness is distinct from unobserved execution resources; no controller/start/EP-submit.',
            'Native consumer and UX acceptance are separately owned by L4.'],
        'cleanup':{'owned_runtime_home_credentials_scratch_removed':False}}
    stage='positive-concept-replay' if args.failure_control else 'selected-service-matrix'
    try:
        if args.failure_control:
            with TemporaryDirectory() as tmp:positive_control(Path(tmp)/'control')
            raise AssertionError('positive concept failure control not detected')
        sys.path.insert(0,str(SOURCE/'tests'))
        for name in MODULES:
            module=__import__(name)
            suite=unittest.defaultTestLoader.loadTestsFromModule(module)
            stage=name;stream=StringIO()
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
            (output/(name+'.private.log')).write_text(stream.getvalue())
            if not result.wasSuccessful():raise AssertionError('selected installed concept boundary failed')
            receipt['cases'].append({'case':name,'test_count':result.testsRun,'result':'PASS'})
            receipt['case_count']+=result.testsRun
        assert receipt['case_count']>=20
        receipt['result']='CHAT_FIRST_MISSION_PRODUCER_PASS'
    except Exception as error:
        receipt['failure']={'type':type(error).__name__,'stage':stage,
                            'detail':'Declared concept producer qualification gate failed'}
        if args.failure_control:
            assert isinstance(error,AssertionError) and 'revoked-positive-concept-replay-detected' in str(error)
    finally:
        for name in ('home','scratch','config'):
            path=output/'isolated'/name
            if path.exists():shutil.rmtree(path)
        receipt['cleanup']['owned_runtime_home_credentials_scratch_removed']=True
    (output/'installed-mission-concepts.public.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return 0 if receipt['result']=='CHAT_FIRST_MISSION_PRODUCER_PASS' else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--wheel',type=Path,required=True)
    p.add_argument('--source-revision',required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--child',action='store_true');p.add_argument('--failure-control',action='store_true')
    raise SystemExit(run(p.parse_args()))
