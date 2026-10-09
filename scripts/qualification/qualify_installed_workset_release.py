"""Exact-wheel approved workset release qualification with genuine runtime/EP-HTTP simulator."""
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
MODULES=('test_workset_release_subjects','test_workset_release_http','test_workset_release_chain',
         'test_workset_release_recovery','test_workset_release_concurrency',
         'test_workset_release_denials','test_workset_release_selection','test_workset_release_integrity')


def positive_control(root):
    spec=spec_from_file_location('release_installed_chain',SOURCE/'scripts/qualification/qualify_workset_release_chain.py')
    driver=module_from_spec(spec);spec.loader.exec_module(driver)
    driver.flow(root,failure_control=True)


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
                              capture_output=True,text=True,timeout=600)
        (output/'child.private.log').write_text(result.stdout+result.stderr)
        if result.returncode not in (0,1):raise RuntimeError('installed release child failed')
        receipt=json.loads((output/'installed-workset-release.public.json').read_text())
        assert receipt['artifact']==artifact and receipt['source_revision']==args.source_revision
        print(json.dumps({'result':receipt['result'],'case_count':receipt['case_count'],'failure':receipt['failure']}))
        return result.returncode
    for key in ('HOME','CODEX_HOME','TMPDIR'):
        assert Path(os.environ[key]).resolve().is_relative_to(output)
    package=Path(forge.__file__).resolve().parent
    schema=package/'api/approved-workset-release-v1.json'
    assert schema.read_bytes()==(SOURCE/'forge/api/approved-workset-release-v1.json').read_bytes()
    receipt={'qualification':'INSTALLED_APPROVED_WORKSET_RELEASE_V1',
        'source_revision':args.source_revision,'artifact':artifact,
        'schema_sha256':'sha256:'+sha256(schema.read_bytes()).hexdigest(),
        'result':'FAIL','case_count':0,'cases':[],'failure':None,
        'expected_failure_control':args.failure_control,
        'external_fault':'REVOKED_POSITIVE_RELEASE_GRANT' if args.failure_control else None,
        'limitations':['Actual noneditable HTTP/auth/G001/context/provider adapter/validator/storage/approvals/Intake/worklist services.',
            'External deterministic model executable, OS identity and repository transport only; live model quality not qualified.',
            'Actual isolated runtime/EP-HTTP simulator chain; no live EP or user target execution qualification.',
            'Future native release consumer is separately selected; running L4 remains on its old exact producer pin.'],
        'cleanup':{'owned_runtime_home_credentials_scratch_removed':False}}
    stage='positive-workset-activation' if args.failure_control else 'selected-service-matrix'
    try:
        if args.failure_control:
            with TemporaryDirectory() as tmp:positive_control(Path(tmp)/'control')
            raise AssertionError('positive workset release failure control not detected')
        sys.path.insert(0,str(SOURCE/'tests'))
        for name in MODULES:
            module=__import__(name)
            suite=unittest.defaultTestLoader.loadTestsFromModule(module)
            stage=name;stream=StringIO()
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
            (output/(name+'.private.log')).write_text(stream.getvalue())
            if not result.wasSuccessful():raise AssertionError('selected installed release boundary failed')
            receipt['cases'].append({'case':name,'test_count':result.testsRun,'result':'PASS'})
            receipt['case_count']+=result.testsRun
        assert receipt['case_count']>=23
        receipt['result']='APPROVED_WORKSET_RELEASE_PASS'
    except Exception as error:
        receipt['failure']={'type':type(error).__name__,'stage':stage,
                            'detail':'Declared workset release qualification gate failed'}
        if args.failure_control:
            assert isinstance(error,AssertionError) and 'revoked-positive-workset-activation-detected' in str(error)
    finally:
        for name in ('home','scratch','config'):
            path=output/'isolated'/name
            if path.exists():shutil.rmtree(path)
        receipt['cleanup']['owned_runtime_home_credentials_scratch_removed']=True
    (output/'installed-workset-release.public.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return 0 if receipt['result']=='APPROVED_WORKSET_RELEASE_PASS' else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--wheel',type=Path,required=True)
    p.add_argument('--source-revision',required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--child',action='store_true');p.add_argument('--failure-control',action='store_true')
    raise SystemExit(run(p.parse_args()))
