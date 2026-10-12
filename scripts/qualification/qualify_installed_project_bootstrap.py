"""Exact-wheel offline proposal qualification; private logs, bounded public receipt."""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

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
    payload = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith('forge/') and not name.endswith('/'):
                raw = archive.read(name)
                if (product.parent / name).read_bytes() != raw:
                    raise ValueError('installed payload mismatch')
                payload[name] = sha(raw)
    output = Path(args.output_dir);output.mkdir(mode=0o700,exist_ok=False)
    receipt = {'qualification':'INSTALLED_PROJECT_BOOTSTRAP_OFFLINE_V1','source_revision':args.source_revision,
               'source_tree':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^{tree}']).decode().strip(),
               'version':canonical_version(),'wheel_sha256':sha(wheel.read_bytes()),'payload_files_verified':len(payload),
               'bootstrap_payload':{k:v for k,v in payload.items() if '/project_bootstrap/' in k},
               'result':'FAIL','cases':[],'network_attempts':0,'cleanup':False,
               'boundary':'own disposable export proposals; no EP/Workspace/live provider/provisioning/approval/Mission'}
    logs = []
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
            def child(name, command, expected=0, cwd=None):
                result=subprocess.run([sys.executable,'-I','-c',WORKER,str(source),*command],cwd=cwd or root,capture_output=True,text=True,timeout=30,env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','HOME':str(root),'PYTHONHASHSEED':'17','LC_ALL':'C'})
                logs.append((name,result.stdout,result.stderr))
                if result.returncode!=expected:
                    raise AssertionError(f'{name}: unexpected exit {result.returncode}')
                receipt['cases'].append({'case':name,'expected_exit':expected,'actual_exit':result.returncode})
                return json.loads(result.stdout)
            catalog=child('catalog',['catalog'])
            console=Path(sys.executable).parent/'forge-project-bootstrap'
            direct_cli=subprocess.run([str(console),'catalog'],cwd=root,capture_output=True,text=True,timeout=30,env={'PATH':str(console.parent)+':/usr/bin:/bin','HOME':str(root)})
            logs.append(('actual-console-script',direct_cli.stdout,direct_cli.stderr))
            if direct_cli.returncode!=0 or json.loads(direct_cli.stdout)!=catalog:
                raise AssertionError('installed console entrypoint mismatch')
            receipt['cases'].append({'case':'actual-console-script','expected_exit':0,'actual_exit':0})
            child('input',['validate-input','--input',str(source_input)])
            first=root/'authority';r=child('authority-render',['render','--input',str(source_input),'--export',str(first)])
            child('authority-trusted-readback',['check-bundle','--bundle',str(first)])
            alternate=root/'alternate';alternate.mkdir()
            second=root/'authority-replay';r2=child('separate-process-replay',['render','--input',str(source_input),'--export',str(second)],cwd=alternate)
            if r['manifest_digest']!=r2['manifest_digest']:
                raise AssertionError('replay differs')
            receipt['authority_manifest_digest']=r['manifest_digest']
            validator=first/'engineering/baselines/portable-docs/1.0.0/validate.py'
            portable=subprocess.run([sys.executable,'-I','-S',str(validator),str(first)],cwd=alternate,capture_output=True,text=True,timeout=30)
            logs.append(('portable',portable.stdout,portable.stderr))
            if portable.returncode!=0 or json.loads(portable.stdout)['product_code_coverage']!='NOT_APPLICABLE_NO_PRODUCT_CODE':
                raise AssertionError('portable validation')
            receipt['cases'].append({'case':'portable-without-forge-runtime','actual_exit':0,'expected_exit':0})
            child('no-overwrite',['render','--input',str(source_input),'--export',str(first)],1)
            doc=first/'docs/product/VISION.md';original=doc.read_bytes();doc.write_bytes(b'tampered')
            child('tampered-payload',['check-bundle','--bundle',str(first)],1)
            negative=subprocess.run([sys.executable,'-I','-S',str(validator),str(first)],capture_output=True,text=True,timeout=30)
            logs.append(('portable-tampered',negative.stdout,negative.stderr))
            if negative.returncode!=1:raise AssertionError('portable tampering not detected')
            receipt['cases'].append({'case':'portable-tampered','expected_exit':1,'actual_exit':1})
            doc.write_bytes(original)
            child('restored-payload',['check-bundle','--bundle',str(first)])
            value['role']='child';value['identity']['repository_id']='test-client';source_input.write_text(json.dumps(value))
            child_bundle=root/'child';child('child-render',['render','--input',str(source_input),'--export',str(child_bundle)])
            if (child_bundle/'docs/product/VISION.md').exists():raise AssertionError('competing child authority')
            child('child-readback',['check-bundle','--bundle',str(child_bundle)])
            value['mode']='MANAGED';value['host_profile']='GITHUB_DOCUMENTS';source_input.write_text(json.dumps(value))
            managed=root/'managed';child('managed-template',['render','--input',str(source_input),'--export',str(managed)])
            if not (managed/'.github/workflows/validation.yml').is_file():raise AssertionError('managed asset missing')
            value['document_language']='fr';source_input.write_text(json.dumps(value));child('unsupported-language',['validate-input','--input',str(source_input)],1)
            outside=root/'outside';outside.mkdir();link=root/'link';link.symlink_to(outside,target_is_directory=True)
            value['document_language']='en';source_input.write_text(json.dumps(value));child('symlink-export',['render','--input',str(source_input),'--export',str(link/'escape')],1)
            if list(outside.iterdir()):raise AssertionError('outside export changed')
            receipt['result']='PROJECT_BOOTSTRAP_OFFLINE_PASS'
        receipt['cleanup']=not Path(tmp).exists()
    except BaseException as error:
        receipt['failure']={'category':type(error).__name__,'stage':'installed-offline-check'}
        if isinstance(error,subprocess.TimeoutExpired):
            logs.append(('timeout-original',str(error.stdout or ''),str(error.stderr or '')))
        raise
    finally:
        for i,(name,stdout,stderr) in enumerate(logs):
            # Private only: original failure logs retained before completion/cleanup.
            log=output/f'private-{i:02d}-{name}.log';log.write_text(stdout+'\n'+stderr);log.chmod(0o600)
        (output/'installed-project-bootstrap.public.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return 0 if receipt['result']=='PROJECT_BOOTSTRAP_OFFLINE_PASS' and receipt['cleanup'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--wheel',required=True);p.add_argument('--source-revision',required=True);p.add_argument('--output-dir',required=True)
    raise SystemExit(run(p.parse_args()))
