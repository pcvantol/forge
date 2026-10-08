#!/usr/bin/env python3
"""Real immutable-wheel maintenance qualification in owned disposable roots."""
from __future__ import annotations
import argparse
import fcntl
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

SOURCE = Path(__file__).resolve().parents[2]
CONTROLLER = SOURCE / 'scripts/update_installed_forge.py'
CRASH_PHASES = ('STAGED', 'BACKED_UP', 'MIGRATION_QUALIFIED', 'ACTIVATING')


def controller():
    spec = importlib.util.spec_from_file_location('qualified_maintenance_controller', CONTROLLER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_inputs(root):
    root = root.resolve()
    if root.exists():
        raise ValueError('fresh immutable input directory required')
    root.mkdir(mode=0o700)
    expected = controller().PRESERVATION_ARTIFACT_BINDING
    for version, field in [('2.7.39','installed_artifact_digest'),('2.8.1','wheel_sha256')]:
        with urllib.request.urlopen('https://pypi.org/pypi/forge-autonomy/'+version+'/json',timeout=30) as stream:
            metadata = json.load(stream)
        filename='forge_autonomy-'+version+'-py3-none-any.whl'
        asset=next(row for row in metadata['urls'] if row['filename']==filename)
        if 'sha256:'+asset['digests']['sha256'] != expected[field] or not asset['url'].startswith('https://files.pythonhosted.org/'):
            raise ValueError('published artifact selection differs from exact pin')
        with urllib.request.urlopen(asset['url'],timeout=30) as stream:
            (root/filename).write_bytes(stream.read())
        if 'sha256:'+digest(root/filename) != expected[field]:
            raise ValueError('published artifact bytes differ from exact pin')
    subprocess.run(['gh','release','download','forge-v2.8.1','--repo','pcvantol/forge',
                    '--pattern','forge-release-complete-2.8.1-*.json','--dir',str(root)],check=True,timeout=60)
    receipts=list(root.glob('forge-release-complete-2.8.1-*.json'))
    if len(receipts)!=1 or 'sha256:'+digest(receipts[0]) != expected['qualification_receipt_sha256']:
        raise ValueError('published terminal receipt differs from exact pin')


def tree(root):
    return {str(p.relative_to(root)): ('LINK:' + os.readlink(p) if p.is_symlink()
            else digest(p) if p.is_file() else 'DIRECTORY') for p in sorted(root.rglob('*'))}


def command(request):
    result = [str(Path(sys.executable).resolve()), '-B', '-I', str(CONTROLLER)]
    for key, value in request.payload.items():
        if value != '':
            result.extend(['--' + key.replace('_', '-'), str(value)])
    return result


def run(argv, root, *, env, check=True):
    done = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, timeout=60)
    if check and done.returncode != 0:
        raise AssertionError('owned product command failed: ' + done.stderr[-600:] + done.stdout[-600:])
    return done


def setup(root, inputs, source_revision):
    m = controller()
    root.mkdir(mode=0o700)
    for name in ('home', 'scratch', 'data', 'maintenance'):
        (root / name).mkdir(mode=0o700)
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(root/'home'),
           'CODEX_HOME': str(root/'home/codex'), 'TMPDIR': str(root/'scratch'),
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
    original = root / 'original'
    base = Path(sys.executable).resolve()
    run([str(base), '-I', '-m', 'venv', '--without-pip', str(original)], root, env=env)
    old = type('PublishedArtifact', (), {'version': '2.7.39',
        'wheel': str(inputs/'forge_autonomy-2.7.39-py3-none-any.whl'),
        'wheel_sha256': m.PRESERVATION_ARTIFACT_BINDING['installed_artifact_digest']})()
    wheel, manifest = m._validated_wheel(old)
    m._install_validated_wheel(original, wheel, manifest)
    run([str(original/'bin/forge'), '--data-root', str(root/'data'), 'server', 'init'], root, env=env)
    history_program = '''from forge.runtime import RuntimeBootstrap
import sys
db=RuntimeBootstrap(data_root=sys.argv[1],forge_version='2.7.39').open()
db.record_operational_event(component='forge_administration',level='INFO',event='maintenance_preservation_qualification',details={'operation':'PRESERVATION_QUALIFICATION','outcome':'ORIGINAL_HISTORY'})
db.close()
'''
    run([str(original/'bin/python'), '-B', '-I', '-c', history_program, str(root/'data')], root, env=env)
    before = m.readonly_database_snapshot(root/'data/forge.db')
    assert before['user_version'] == 40
    resolver = root / 'forge'
    resolver.write_text('#!/bin/sh\nexec ' + shlex.quote(str(original/'bin/forge')) + ' "$@"\n')
    resolver.chmod(0o700)
    request = m.UpdateRequest(operation_id='published-preservation-' + root.name,
        version='2.8.1', wheel=str(inputs/'forge_autonomy-2.8.1-py3-none-any.whl'),
        qualification_receipt=str(next(inputs.glob('forge-release-complete-2.8.1-*.json'))),
        controller_source=source_revision, controller_sha256='sha256:' + digest(CONTROLLER),
        data_root=str(root/'data'), runtime_root=str(root/'maintenance'),
        runtime_id=before['metadata']['runtime_id'], installation_id=before['metadata']['installation_id'],
        peer_configuration_digest=before['peer_state_digest'], resolver=str(resolver),
        resolver_sha256=m.file_digest(resolver), existing_interpreter=str(original/'bin/python'),
        existing_version='2.7.39', base_python=str(base),
        installed_wheel=str(inputs/'forge_autonomy-2.7.39-py3-none-any.whl'), **m.PRESERVATION_ARTIFACT_BINDING)
    untouched = tree(root)
    assessment = json.loads(run(command(request) + ['--assess-only'], root, env=env).stdout)
    assert assessment['state'] == 'UPDATE_AVAILABLE' and assessment['mutating'] is False
    assert tree(root) == untouched, 'assessment wrote installation bytes'
    request = replace(request, assessment_digest=assessment['assessment_digest'])
    return m, request, before, env


def crash(argv, root, phase, env):
    state_path = root/'data/artifacts/installation'/('published-preservation-' + root.name)/'operation.json'
    with (root/'interrupted-child.private.log').open('w') as log:
        child = subprocess.Popen(argv, cwd=root, env=env, stdout=log, stderr=log, start_new_session=True)
        hit = None
        try:
            deadline = time.monotonic() + 30
            while child.poll() is None and time.monotonic() < deadline:
                try:
                    state = json.loads(state_path.read_text())
                except (OSError, ValueError):
                    state = {}
                if state.get('phase') == phase:
                    os.killpg(child.pid, signal.SIGSTOP)
                    actual = json.loads(state_path.read_text())
                    if actual.get('phase') != phase:
                        os.killpg(child.pid, signal.SIGCONT)
                        continue
                    hit = {'phase': phase, 'owned_process_group': True, 'actual_durable_boundary': True}
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
                    observed = controller().readonly_database_snapshot(root/'data/forge.db')
                    hit['observed_live_schema_after_signal'] = observed['user_version']
                    current = root/'maintenance/current'
                    hit['resolver_selection_after_signal'] = (os.readlink(current)
                                                             if current.is_symlink() else None)
                    break
                time.sleep(.001)
            assert hit is not None, 'declared crash boundary NOT_HIT: ' + phase
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
    return hit


def case(root, inputs, source_revision, name):
    m, request, before, env = setup(root, inputs, source_revision)
    argv = command(request)
    boundary = crash(argv, root, name.removeprefix('crash-'), env) if name.startswith('crash-') else None
    done = run(argv, root, env=env)
    receipt = json.loads(done.stdout)
    assert receipt['state'] == 'COMPLETE' and receipt['version'] == '2.8.1'
    assert json.loads(run(argv, root, env=env).stdout) == receipt
    after = m.readonly_database_snapshot(root/'data/forge.db')
    preservation = m.verify_preservation(before, after, request)
    assert after['user_version'] == 45 and preservation['added_tables'] == sorted(m.NEW_SCHEMA_45_PRESERVATION_TABLES)
    assert all(receipt[key] == value for key,value in {
        'credential_disposition':'PRESERVED_UNCHANGED', 'service_disposition':'NOT_STARTED',
        'mission_disposition':'NOT_STARTED_OR_RESUMED', 'reset_disposition':'NOT_EXECUTED'}.items())
    assert digest(Path(receipt['backup']['path'])) == receipt['backup']['sha256'].removeprefix('sha256:')
    row = {'case': name, 'result':'PASS', 'from_schema':40, 'to_schema':45,
           'published_target':'2.8.1', 'same_original_receipt':True,
           'preserved_history_tables':preservation['preserved_table_count'],
           'project_input_required':False, 'provider_login_performed':False,
           'service_mission_reset_started':False, 'crash':boundary}
    if name == 'tampered-positive-control':
        candidate = Path(receipt['installed_readback']['resolved_executable']).parent.parent
        target = m._candidate_site_packages(candidate)/'forge/__init__.py'
        with target.open('ab') as handle:
            handle.write(b'\n# owned qualification corruption detector\n')
        denied = run(argv, root, env=env, check=False)
        assert denied.returncode == 1 and json.loads(denied.stdout)['status'] == 'ERROR'
        row.update(result='FAIL', expected_failure_control=True,
                   detected_by='EXACT_TARGET_PRODUCT_BYTES_REPLAY', actual_exit=denied.returncode)
    return row


def denials(root, inputs, source_revision):
    m, request, before, env = setup(root, inputs, source_revision)
    denied = []
    changes = [
        {'runtime_id':'foreign-runtime'}, {'installation_id':'foreign-installation'},
        {'peer_configuration_digest':'sha256:' + '0'*64},
        {'installed_source':'0'*40}, {'product_source':'0'*40},
        {'wheel_sha256':'sha256:' + '0'*64},
        {'qualification_receipt_sha256':'sha256:' + '0'*64},
        {'controller_sha256':'sha256:' + '0'*64},
        {'assessment_digest':'sha256:' + '0'*64},
    ]
    for change in changes:
        untouched = tree(root)
        done = run(command(replace(request, **change)), root, env=env, check=False)
        assert done.returncode == 1 and json.loads(done.stdout)['status'] == 'ERROR'
        assert tree(root) == untouched, 'denied binding created installation effects'
        denied.append(next(iter(change)))
    lock = root/'data/forge-runtime-mutation.lock'
    with lock.open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original_database = digest(root/'data/forge.db')
        done = run(command(request), root, env=env, check=False)
        assert done.returncode == 1
        assert digest(root/'data/forge.db') == original_database
        assert not (root/'data/artifacts/installation'/request.operation_id).exists()
    denied.append('REAL_RUNTIME_WRITER_LOCK')
    with (root/'active-product.private.log').open('w') as log:
        active = subprocess.Popen([request.existing_interpreter,'-B','-I','-c',
            'import forge,time;time.sleep(30)', request.data_root],cwd=root,env=env,stdout=log,stderr=log)
        try:
            assert active.poll() is None
            done = run(command(request),root,env=env,check=False)
            assert done.returncode == 1
            assert digest(root/'data/forge.db') == original_database
            assert not (root/'data/artifacts/installation'/request.operation_id).exists()
        finally:
            active.terminate()
            active.wait(timeout=5)
    denied.append('REAL_LOADED_PRODUCT_PROCESS')
    mutation = '''from forge.runtime import RuntimeBootstrap
import sys
db=RuntimeBootstrap(data_root=sys.argv[1],forge_version='2.7.39').open()
db.record_operational_event(component='forge_administration',level='INFO',event='maintenance_assessment_drift',details={'operation':'PRESERVATION_QUALIFICATION','outcome':'GENUINE_NEW_HISTORY'})
db.close()
'''
    run([request.existing_interpreter,'-B','-I','-c',mutation,request.data_root],root,env=env)
    untouched = tree(root)
    done = run(command(request),root,env=env,check=False)
    assert done.returncode == 1 and tree(root) == untouched
    denied.append('GENUINE_HISTORY_DRIFT_STALE_ASSESSMENT')
    source_file = m._candidate_site_packages(root/'original')/'forge/__init__.py'
    with source_file.open('ab') as handle:
        handle.write(b'\n# owned original product corruption test\n')
    untouched = tree(root)
    done = run(command(request),root,env=env,check=False)
    assert done.returncode == 1 and tree(root) == untouched
    denied.append('ACTUAL_ORIGINAL_PRODUCT_BYTES_DRIFT')
    return {'case':'scoped-denials','result':'PASS','negative_conditions':denied,
            'canonical_database_resolver_slot_effects_on_denial':0}


def qualify(args):
    if sys.version_info[:2] != (3,14):
        raise ValueError('Python3.14 required')
    exact = subprocess.check_output(['git','show',args.source_revision + ':scripts/update_installed_forge.py'],cwd=SOURCE)
    if exact != CONTROLLER.read_bytes():
        raise ValueError('qualification requires exact committed controller bytes')
    driver = subprocess.check_output(['git','show',args.source_revision + ':scripts/qualification/qualify_published_preservation_2739_281.py'],cwd=SOURCE)
    if driver != Path(__file__).read_bytes():
        raise ValueError('qualification requires exact committed driver bytes')
    root = args.output_dir.resolve()
    if root.exists():
        raise ValueError('fresh owned qualification output required')
    root.mkdir(mode=0o700)
    names = ['positive', 'scoped-denials', *('crash-' + phase for phase in CRASH_PHASES), 'tampered-positive-control']
    receipt = {'qualification':'PUBLISHED_2739_281_PRESERVATION', 'source_revision':args.source_revision,
               'controller_sha256':digest(CONTROLLER), 'result':'FAIL', 'cases':[],
               'source_tree_revision':subprocess.check_output(['git','rev-parse',args.source_revision+'^{tree}'],cwd=SOURCE,text=True).strip(),
               'immutable_artifact_binding':controller().PRESERVATION_ARTIFACT_BINDING,
               'limitations':['Disposable producer installations only; L1 actual installer continuation is not qualified.',
                   'Real published wheels, owning CLI migration and receipts; no approval/provider/EP/trust mocks.'],
               'cleanup':{'owned_runtime_home_credentials_scratch_removed':False}}
    work = root/'owned-cases'
    work.mkdir(mode=0o700)
    try:
        for name in names:
            execute = denials if name == 'scoped-denials' else case
            values = (work/name, args.inputs.resolve(), args.source_revision)
            receipt['cases'].append(execute(*values) if name == 'scoped-denials' else execute(*values, name))
        for filename, field in [('forge_autonomy-2.7.39-py3-none-any.whl','installed_artifact_digest'),
                                ('forge_autonomy-2.8.1-py3-none-any.whl','wheel_sha256')]:
            assert 'sha256:' + digest(args.inputs.resolve()/filename) == receipt['immutable_artifact_binding'][field]
        receipt['result']='PRESERVATION_PRODUCER_PASS'
    except Exception as error:
        (root/'failure.private.log').write_text(str(error))
        receipt['failure']={'type':type(error).__name__,'stage':name,'detail':'Declared producer gate failed'}
    finally:
        shutil.rmtree(work)
        receipt['cleanup']['owned_runtime_home_credentials_scratch_removed']=True
    (root/'published-preservation.public.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'result':receipt['result'],'case_count':len(receipt['cases']),'failure':receipt.get('failure')}))
    return 0 if receipt['result']=='PRESERVATION_PRODUCER_PASS' else 1


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--source-revision',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--fetch-inputs',action='store_true')
    args=parser.parse_args()
    if args.fetch_inputs:
        fetch_inputs(args.inputs)
    raise SystemExit(qualify(args))
