"""Exact-wheel offline proposal qualification; private logs, bounded public receipt."""
from __future__ import annotations

import argparse
import configparser
import copy
import fnmatch
import importlib.util
import os
import tomllib
import traceback
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

_process_spec=importlib.util.spec_from_file_location('bootstrap_owned_process',Path(__file__).with_name('project_bootstrap_process.py'))
_process=importlib.util.module_from_spec(_process_spec);_process_spec.loader.exec_module(_process)

WORKER = r'''
import importlib.metadata, json, os, pathlib, socket, sys
forbidden = pathlib.Path(sys.argv[1]).resolve()
if any(pathlib.Path(x).resolve().is_relative_to(forbidden) for x in sys.path if x):
    raise RuntimeError('development checkout in child path')
attempts = []
def guard(event, args):
    if event.startswith('socket.'):
        attempts.append(event)
        raise RuntimeError('offline network forbidden')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        if pathlib.Path(os.fsdecode(args[0])).resolve().is_relative_to(forbidden):
            raise RuntimeError('development checkout read forbidden')
sys.addaudithook(guard)
try:
    socket.socket()
except RuntimeError:
    pass
else:
    raise RuntimeError('offline guard not active')
attempts.clear()
entry = [x for x in importlib.metadata.distribution('forge-autonomy').entry_points if x.name == 'forge-project-bootstrap']
assert len(entry) == 1 and entry[0].value == 'forge.project_bootstrap.cli:main'
exit_code = entry[0].load()(sys.argv[2:])
assert attempts == [], 'product attempted networking'
raise SystemExit(exit_code)
'''


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verify_payload(archive: zipfile.ZipFile, expected: dict[str, bytes], product_parent: Path) -> dict[str, str]:
    names=archive.namelist()
    if len(names)!=len(set(names)):
        raise ValueError('duplicate wheel members')
    actual={name for name in names if name.startswith('forge/') and not name.endswith('/')}
    if actual!=set(expected):
        raise ValueError('wheel inventory differs from committed source')
    payload={}
    for name,source_bytes in expected.items():
        if archive.getinfo(name).file_size != len(source_bytes):
            raise ValueError("wheel member length differs from source")
        raw=archive.read(name)
        if raw!=source_bytes or (product_parent/name).read_bytes()!=raw:
            raise ValueError('committed source/wheel/installed mismatch')
        payload[name]=sha(raw)
    return payload


def run(args: argparse.Namespace) -> int:
    import forge
    from forge._version import canonical_version
    source = Path(__file__).resolve().parents[2]
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD']).decode().strip() != args.source_revision:
        raise ValueError('exact source mismatch')
    if subprocess.run(['git','-C',str(source),'diff','--quiet','HEAD']).returncode:
        raise ValueError('dirty qualifier source')
    if subprocess.check_output(['git','-C',str(source),'ls-files','--others','--exclude-standard','--','forge','scripts/qualification']).strip():
        raise ValueError('uncommitted source')
    product = Path(forge.__file__).resolve().parent
    if product.is_relative_to(source):
        raise ValueError('noneditable installed wheel required')
    meta = distribution('forge-autonomy')
    direct = meta.read_text('direct_url.json')
    if direct and json.loads(direct).get('dir_info',{}).get('editable'):
        raise ValueError('editable install')
    wheel = Path(args.wheel)
    # Enumerate exact tracked package inventory from committed source, independently of wheel.
    project_manifest=tomllib.loads(subprocess.check_output(['git','-C',str(source),'show','HEAD:pyproject.toml']).decode())
    source_version=json.loads(subprocess.check_output(['git','-C',str(source),'show','HEAD:product-version.json']))['version']
    patterns=project_manifest['tool']['setuptools']['package-data']['forge']
    tracked=subprocess.check_output(['git','-C',str(source),'ls-tree','-r','--name-only','HEAD','--','forge']).decode().splitlines()
    expected={name:subprocess.check_output(['git','-C',str(source),'show','HEAD:'+name]) for name in tracked
              if name.endswith('.py') or any(fnmatch.fnmatchcase(name.removeprefix('forge/'),p) for p in patterns)}
    payload = {}
    with zipfile.ZipFile(wheel) as archive:
        names=archive.namelist()
        payload=verify_payload(archive,expected,product.parent)
        info=[name for name in names if name.endswith('.dist-info/entry_points.txt')]
        if len(info)!=1:raise ValueError('wheel entrypoint metadata absent/ambiguous')
        entry=configparser.ConfigParser();entry.read_string(archive.read(info[0]).decode())
        scripts=project_manifest['project']['scripts']
        if dict(entry['console_scripts'])!=scripts or {e.name:e.value for e in meta.entry_points if e.group=='console_scripts'}!=scripts:
            raise ValueError('source/wheel/installed entrypoints mismatch')
    installed_members={str(x.relative_to(product.parent)) for x in product.rglob('*') if x.is_file() and '__pycache__' not in x.parts}
    if installed_members!=set(expected) or source_version!=canonical_version() or meta.version!=source_version:
        raise ValueError('installed inventory/version mismatch')
    if {s.strip() for s in meta.metadata['Requires-Python'].split(',')}!={s.strip() for s in project_manifest['project']['requires-python'].split(',')}:
        raise ValueError('installed interpreter compatibility mismatch')
    output = Path(args.output_dir);output.mkdir(mode=0o700,exist_ok=False)
    receipt = {'qualification':'INSTALLED_PROJECT_BOOTSTRAP_OFFLINE_V1','source_revision':args.source_revision,
               'source_tree':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^{tree}']).decode().strip(),
               'version':canonical_version(),'wheel_sha256':sha(wheel.read_bytes()),'payload_files_verified':len(payload),
               'bootstrap_payload':{k:v for k,v in payload.items() if '/project_bootstrap/' in k},
               'result':'FAIL','cases':[],'network_attempts':0,'network_measurement_scope':'audited installed product entrypoint workers; trusted portable/console source has no network code','cleanup':False,
               'boundary':'own disposable export proposals; no EP/Workspace/live provider/provisioning/approval/Mission'}
    receipt['committed_source_payload_verified']=len(expected)
    receipt['entrypoints_source_wheel_installed_verified']=True
    receipt['diagnostic_complete']=True
    receipt['secondary_failures']=[]
    primary=None
    try:
        with tempfile.TemporaryDirectory(prefix='forge-pb-offline-',dir=output) as tmp:
            root=Path(tmp)
            # Synthetic explicitly supplied references; no identity registration or remote claims.
            value={'contract_version':'pb-render/1.0','baseline':'portable-docs/1.0.0','mode':'GENESIS','role':'authority','document_language':'en',
                   'identity':{'status':'PROVISIONAL_REFERENCE','project_id':'test-product','repository_id':'test-core','authority_repository_id':'test-core','owner_reference':'synthetic-owner-reference'},
                   'product':{'name':'Portable sample','purpose':'Document an explicitly supplied goal.','users':'Project teams','non_goals':'No application code','constraints':'Offline proposals only','open_questions':['Technology remains undecided.']},
                   'source_references':[{'owner':'USER_DECLARED','reference':'synthetic-description','digest':'1'*64}],
                   'authority_contract_reference':'test-core:engineering/project-contract.json','license_profile':'UNDECIDED','security_profile':'DOCUMENT_ONLY','stack_profile':'NO_PRODUCT_CODE','host_profile':'LOCAL_POSIX'}
            source_input=root/'input.json';source_input.write_text(json.dumps(value))
            def execute(name, command, expected=0, cwd=None, env=None):
                report,stdout,stderr=_process.capture(command,case=name,output=output,cwd=cwd or root,
                    env=env or {'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','HOME':str(root),'PYTHONHASHSEED':'17','LC_ALL':'C'},expected=expected)
                receipt['cases'].append(report)
                if not report['capture_complete']:
                    receipt['diagnostic_complete']=False
                if report['primary_failure']:
                    receipt['failure']=report['primary_failure'] | {'case':name}
                    raise RuntimeError('primary bounded command failure')
                if not report['capture_complete']:
                    raise RuntimeError('incomplete diagnostic evidence')
                return stdout
            def child(name,command,expected=0,cwd=None):
                raw=execute(name,[sys.executable,'-I','-c',WORKER,str(source),*command],expected,cwd)
                return json.loads(raw)
            catalog=child('catalog',['catalog'])
            console=Path(sys.executable).parent/'forge-project-bootstrap'
            direct_cli=execute('actual-console-script',[str(console),'catalog'])
            if json.loads(direct_cli)!=catalog:
                raise AssertionError('installed console entrypoint mismatch')
            child('input',['validate-input','--input',str(source_input)])
            first=root/'authority';r=child('authority-render',['render','--input',str(source_input),'--export',str(first)])
            child('authority-trusted-readback',['check-bundle','--bundle',str(first)])
            alternate=root/'alternate';alternate.mkdir()
            second=root/'authority-replay';r2=child('separate-process-replay',['render','--input',str(source_input),'--export',str(second)],cwd=alternate)
            if r['manifest_digest']!=r2['manifest_digest']:
                raise AssertionError('replay differs')
            receipt['authority_manifest_digest']=r['manifest_digest']
            validator=first/'engineering/baselines/portable-docs/1.0.0/validate.py'
            portable=execute('portable-without-forge-runtime',[sys.executable,'-I','-S',str(validator),str(first)],cwd=alternate)
            if json.loads(portable)['product_code_coverage']!='NOT_APPLICABLE_NO_PRODUCT_CODE':
                raise AssertionError('portable validation')
            execute('actual-posix-wrapper',['/bin/sh',str(first/'scripts/validate.sh')],cwd=alternate)
            missing=root/'missing-tools';missing.mkdir()
            execute('missing-tool-control',['/bin/sh',str(first/'scripts/validate.sh')],expected=1,env={'PATH':str(missing)})
            child('no-overwrite',['render','--input',str(source_input),'--export',str(first)],1)
            doc=first/'docs/product/VISION.md';original=doc.read_bytes();doc.write_bytes(b'tampered')
            child('tampered-payload',['check-bundle','--bundle',str(first)],1)
            execute('portable-tampered',[sys.executable,'-I','-S',str(validator),str(first)],expected=1)
            doc.write_bytes(original)
            child('restored-payload',['check-bundle','--bundle',str(first)])
            wrapper=first/'scripts/validate.sh'
            validator_original=validator.read_bytes()
            validator.write_text("print('FAKE PASS')\n")
            execute('fake-validator-before-execution',['/bin/sh',str(wrapper)],expected=1)
            child('fake-validator-trusted-refusal',['check-bundle','--bundle',str(first)],1)
            validator.write_bytes(validator_original)
            baseline=first/'engineering/baselines/portable-docs/1.0.0/catalog.json'
            baseline_original=baseline.read_bytes();changed=json.loads(baseline_original)
            changed['qualification']='RELEASED';changed_raw=(json.dumps(changed,sort_keys=True,separators=(',',':'))+'\n').encode();baseline.write_bytes(changed_raw)
            coherent_lock=first/'engineering/baseline.lock.json';coherent_lock_original=coherent_lock.read_bytes()
            changed_lock=json.loads(coherent_lock_original);changed_lock['catalog_digest']=sha(changed_raw)
            coherent_lock.write_bytes((json.dumps(changed_lock,sort_keys=True,separators=(',',':'))+'\n').encode())
            manifest_file=first/'engineering/bootstrap-manifest.json';manifest_original=manifest_file.read_bytes();changed_manifest=json.loads(manifest_original)
            for entry in changed_manifest['artifacts']:
                if entry['relative_path'] in {'engineering/baselines/portable-docs/1.0.0/catalog.json','engineering/baseline.lock.json'}:
                    bytes_now=(first/entry['relative_path']).read_bytes();entry['bytes']=len(bytes_now);entry['expected_after_digest']=sha(bytes_now)
            changed_manifest.pop('manifest_digest');changed_manifest['manifest_digest']=sha((json.dumps(changed_manifest,sort_keys=True,separators=(',',':'))+'\n').encode())
            manifest_file.write_bytes((json.dumps(changed_manifest,sort_keys=True,separators=(',',':'))+'\n').encode())
            execute('coherent-baseline-refusal',['/bin/sh',str(wrapper)],expected=1)
            child('baseline-trusted-refusal',['check-bundle','--bundle',str(first)],1)
            baseline.write_bytes(baseline_original);coherent_lock.write_bytes(coherent_lock_original);manifest_file.write_bytes(manifest_original)
            lock=first/'engineering/baseline.lock.json';lock_original=lock.read_bytes()
            changed=json.loads(lock_original);changed['upgrade']='AUTOMATIC';lock.write_text(json.dumps(changed))
            execute('changed-lock-refusal',['/bin/sh',str(wrapper)],expected=1)
            lock.write_bytes(lock_original)
            schema_file=first/'engineering/baselines/portable-docs/1.0.0/input.schema.json';schema_original=schema_file.read_bytes()
            schema_file.write_text('{}')
            execute('changed-schema-refusal',['/bin/sh',str(wrapper)],expected=1)
            schema_file.write_bytes(schema_original)
            execute('restored-baseline-control',['/bin/sh',str(wrapper)])
            value['role']='child';value['identity']['repository_id']='test-client';source_input.write_text(json.dumps(value))
            child_bundle=root/'child';child('child-render',['render','--input',str(source_input),'--export',str(child_bundle)])
            if (child_bundle/'docs/product/VISION.md').exists():raise AssertionError('competing child authority')
            child('child-readback',['check-bundle','--bundle',str(child_bundle)])
            value['mode']='MANAGED';value['host_profile']='GITHUB_DOCUMENTS';source_input.write_text(json.dumps(value))
            managed=root/'managed';child('managed-template',['render','--input',str(source_input),'--export',str(managed)])
            if not (managed/'.github/workflows/validation.yml').is_file():raise AssertionError('managed asset missing')
            value['document_language']='fr';source_input.write_text(json.dumps(value));child('unsupported-language',['validate-input','--input',str(source_input)],1)
            value['document_language']='en'
            for label, mutate in [
                ('traversal-identity',lambda v:v['identity'].update(repository_id='../escape')),
                ('absolute-identity',lambda v:v['identity'].update(repository_id='/absolute')),
                ('case-identity',lambda v:v['identity'].update(repository_id='Test-Client')),
                ('unicode-identity',lambda v:v['identity'].update(repository_id='test-cafe\u0301')),
                ('external-include',lambda v:v.update(authority_contract_reference='https://untrusted.example/include')),
                ('unsupported-stack',lambda v:v.update(stack_profile='PYTHON_APP')),
                ('unsupported-security',lambda v:v.update(security_profile='CODEQL')),
                ('unknown-authority-field',lambda v:v.update(approval='APPROVED'))]:
                bad=copy.deepcopy(value);mutate(bad);source_input.write_text(json.dumps(bad))
                child(label,['validate-input','--input',str(source_input)],1)
                rejected=root/(label+'-export')
                child(label+'-no-effects',['render','--input',str(source_input),'--export',str(rejected)],1)
                if rejected.exists():raise AssertionError('refused input created export')
            source_input.write_text(json.dumps(value))
            outside=root/'outside';outside.mkdir();link=root/'link';link.symlink_to(outside,target_is_directory=True)
            value['document_language']='en';source_input.write_text(json.dumps(value));child('symlink-export',['render','--input',str(source_input),'--export',str(link/'escape')],1)
            if list(outside.iterdir()):raise AssertionError('outside export changed')
            receipt['result']='PROJECT_BOOTSTRAP_OFFLINE_PASS'
        receipt['cleanup']=not Path(tmp).exists()
    except BaseException as error:
        primary=error
        if 'failure' not in receipt:
            receipt['failure']={'category':type(error).__name__,'stage':'installed-offline-check'}
        receipt['result']='FAIL'
    finally:
        # Private logs already retained per command before scratch cleanup; public sink is independent.
        receipt['cleanup']=not Path(tmp).exists() if 'tmp' in locals() else False
        try:
            target=output/'installed-project-bootstrap.public.json'
            target.write_text(json.dumps(receipt,indent=2)+'\n')
        except OSError as error:
            receipt['diagnostic_complete']=False
            receipt['secondary_failures'].append({'stage':'public-retention','category':type(error).__name__})
            if primary is None:primary=error
    if primary is not None:
        raise primary
    return 0 if receipt['result']=='PROJECT_BOOTSTRAP_OFFLINE_PASS' and receipt['cleanup'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--wheel',required=True);p.add_argument('--source-revision',required=True);p.add_argument('--output-dir',required=True)
    raise SystemExit(run(p.parse_args()))
