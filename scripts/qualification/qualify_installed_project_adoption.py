"""Bounded exact-wheel offline supplied-inventory preview qualification."""
from __future__ import annotations
import argparse
import configparser
import copy
import fnmatch
import hashlib
import importlib.util
from importlib.metadata import distribution
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import zipfile

_spec = importlib.util.spec_from_file_location('qualified_bootstrap_tool', Path(__file__).with_name('qualify_installed_project_bootstrap.py'))
_tool = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_tool)

WORKER = r'''
import importlib.metadata,json,os,pathlib,socket,sys
forbidden=pathlib.Path(sys.argv[1]).resolve()
assert not any(pathlib.Path(x).resolve().is_relative_to(forbidden) for x in sys.path if x)
attempts=[]; descriptors={}; real_open=os.open; real_close=os.close; real_dup=os.dup
def deny_path(path):
    if pathlib.Path(path).resolve().is_relative_to(forbidden):
        attempts.append('source');raise PermissionError('development source forbidden')
def checked_open(path,flags,mode=0o777,*,dir_fd=None):
    candidate=pathlib.Path(os.fsdecode(path))
    if not candidate.is_absolute():
        if dir_fd is not None:
            if dir_fd not in descriptors:raise PermissionError('unknown descriptor provenance')
            candidate=descriptors[dir_fd]/candidate
        else:candidate=pathlib.Path.cwd()/candidate
    deny_path(candidate)
    fd=real_open(path,flags,mode,dir_fd=dir_fd);descriptors[fd]=candidate.resolve();return fd
def checked_close(fd):
    try:return real_close(fd)
    finally:descriptors.pop(fd,None)
def checked_dup(fd):
    value=real_dup(fd)
    if fd in descriptors:descriptors[value]=descriptors[fd]
    return value
os.open=checked_open;os.close=checked_close;os.dup=checked_dup
def guard(event,args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.posix_spawn','os.fork','os.forkpty'} or event.startswith('os.exec'):
        attempts.append('network-or-command');raise PermissionError('offline boundary')
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):deny_path(os.fsdecode(args[0]))
    if event in {'os.scandir','os.listdir'}:
        value=args[0]
        if isinstance(value,int):
            if value in descriptors:deny_path(descriptors[value])
        elif value is not None:deny_path(os.fsdecode(value))
sys.addaudithook(guard)
try:socket.socket()
except PermissionError:pass
else:raise RuntimeError('network guard inactive')
try:real_open(str(forbidden/'pyproject.toml'),os.O_RDONLY)
except PermissionError:pass
else:raise RuntimeError('source path guard inactive')
fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
try:
    try:
        for part in forbidden.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY,dir_fd=fd);os.close(fd);fd=child
    except PermissionError:pass
    else:raise RuntimeError('descriptor source guard inactive')
finally:os.close(fd)
attempts.clear()
entry=[x for x in importlib.metadata.distribution('forge-autonomy').entry_points if x.name=='forge-project-adoption']
assert len(entry)==1 and entry[0].value=='forge.project_adoption.cli:main'
result=entry[0].load()(sys.argv[2:]);assert not attempts,'product crossed offline boundary';raise SystemExit(result)
'''


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def run(args: argparse.Namespace) -> int:
    import forge
    from forge._version import canonical_version
    source = Path(__file__).resolve().parents[2]
    def git(*command):
        return subprocess.check_output(['git','-C',str(source),*command])
    if git('rev-parse','HEAD').decode().strip()!=args.source_revision or git('status','--porcelain').strip():
        raise ValueError('exact clean committed source required')
    product=Path(forge.__file__).resolve().parent
    if product.is_relative_to(source):raise ValueError('installed noneditable wheel required')
    meta=distribution('forge-autonomy');wheel=Path(args.wheel)
    direct=json.loads(meta.read_text('direct_url.json') or '{}')
    if direct.get('archive_info',{}).get('hashes',{}).get('sha256')!=sha(wheel.read_bytes()) or direct.get('dir_info',{}).get('editable'):
        raise ValueError('exact wheel identity mismatch')
    manifest=tomllib.loads(git('show','HEAD:pyproject.toml').decode());patterns=manifest['tool']['setuptools']['package-data']['forge']
    expected={name:git('show','HEAD:'+name) for name in git('ls-tree','-r','--name-only','HEAD','--','forge').decode().splitlines()
              if name.endswith('.py') or any(fnmatch.fnmatchcase(name.removeprefix('forge/'),p) for p in patterns)}
    with zipfile.ZipFile(wheel) as archive:
        payload=_tool.verify_payload(archive,expected,product.parent)
        entry_files=[name for name in archive.namelist() if name.endswith('.dist-info/entry_points.txt')]
        if len(entry_files)!=1:raise ValueError('entrypoint metadata ambiguity')
        entries=configparser.ConfigParser();entries.read_string(archive.read(entry_files[0]).decode())
        if dict(entries['console_scripts'])!=manifest['project']['scripts'] or {e.name:e.value for e in meta.entry_points if e.group=='console_scripts'}!=manifest['project']['scripts']:
            raise ValueError('source/wheel/installed entrypoints differ')
    installed={str(p.relative_to(product.parent)) for p in product.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    if installed!=set(expected) or meta.version!=canonical_version() or meta.version!=json.loads(git('show','HEAD:product-version.json'))['version']:
        raise ValueError('installed source inventory/version mismatch')
    output=Path(args.output_dir);output.mkdir(mode=0o700)
    receipt={'qualification':'INSTALLED_PROJECT_ADOPTION_OFFLINE_V1','source_revision':args.source_revision,
             'source_tree':git('rev-parse','HEAD^{tree}').decode().strip(),'version':meta.version,'wheel_sha256':sha(wheel.read_bytes()),
             'payload_files_verified':len(payload),'entrypoints_source_wheel_installed_verified':True,
             'adoption_payload':{k:v for k,v in payload.items() if '/project_adoption/' in k},
             'result':'FAIL','cases':[],'diagnostic_complete':True,'cleanup':False,'network_attempts':0,
             'guard_controls':'real socket, direct source and directory-descriptor source opens rejected before each installed worker',
             'boundary':'supplied synthetic observations only; no live EP inspection, target effects or Mission'}
    try:
        with tempfile.TemporaryDirectory(prefix='forge-adoption-offline-',dir=output) as directory:
            root=Path(directory);input_file=root/'input.json'
            value=json.loads(git('show','HEAD:examples/project-adoption/adopt-existing-vision-input.json'))
            def bind(item):
                item['inventory_digest']=sha((json.dumps(item['inventory'],ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode())
                return item
            def put(item):
                raw=(json.dumps(item,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode();input_file.write_bytes(raw);return sha(raw)
            def execute(name,argv,expected_exit=0,cwd=None,env=None):
                report,stdout,stderr=_tool._process.capture(argv,case=name,output=output,cwd=cwd or root,
                    env=env or {'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','HOME':str(root),'PYTHONHASHSEED':'17','LC_ALL':'C'},expected=expected_exit)
                receipt['cases'].append(report)
                if not report['capture_complete'] or report['primary_failure']:
                    receipt['diagnostic_complete']=False;raise RuntimeError('actual bounded command/diagnostic failure')
                return stdout
            def child(name,argv,expected_exit=0,cwd=None,env=None,isolate=True):
                flags=['-I'] if isolate else []
                raw=execute(name,[sys.executable,*flags,'-c',WORKER,str(source),*argv],expected_exit,cwd,env)
                return json.loads(raw)
            original_input=put(value)
            child('validate-supplied-input',['validate-input','--input',str(input_file)])
            first=root/'proposal';first_result=child('authority-preview',['preview','--input',str(input_file),'--export',str(first)])
            checked=child('authority-current-readback',['check-proposal','--proposal',str(first)]);assert checked['proposal_digest']==first_result['proposal_digest']
            plan=json.loads((first/'proposal.json').read_text());assert plan['state']=='PROPOSED_NOT_APPROVED' and plan['repository_quality']=='NOT_ASSESSED' and plan['input_digest']==original_input and plan['inventory_digest']==value['inventory_digest'] and plan['origin']==value['inventory']['origin']
            rows={x['artifact_path']:x for x in plan['entries']};vision=rows['docs/product/VISION.md'];architecture=rows['docs/architecture/ARCHITECTURE.md']
            assert vision['operation']=='LINK_EXISTING' and vision['mapping_only'] and vision['after']=={} and vision['before']['status']=='ABSENT'
            assert vision['mapping_source']['content']=='# Visie\nBestaande Nederlandse productrichting.\n' and architecture['operation']=='PROPOSE_ADDITION'
            assert architecture['after']['sha256']==sha(architecture['after']['content'].encode())
            frozen={p.name:sha(p.read_bytes()) for p in first.iterdir()};receipt['authority_proposal_digest']=plan['proposal_digest']
            alternate=root/'alternate';alternate.mkdir();second=root/'replay'
            replay_env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','HOME':str(alternate),'PYTHONHASHSEED':'931','TZ':'Pacific/Honolulu','LC_ALL':'C.UTF-8'}
            replay=child('separate-process-environment-replay',['preview','--input',str(input_file),'--export',str(second)],cwd=alternate,env=replay_env,isolate=False)
            assert replay['proposal_digest']==first_result['proposal_digest'] and {p.name:sha(p.read_bytes()) for p in second.iterdir()}==frozen
            console=Path(sys.executable).parent/'forge-project-adoption'
            summary=execute('actual-installed-console-summary',[str(console),'preview','--input',str(input_file)],cwd=alternate)
            assert b'Use the supplied existing document' in summary and b'Bestaande Nederlandse productrichting' not in summary
            child('no-overwrite',['preview','--input',str(input_file),'--export',str(first)],1)
            negative=json.loads(git('show','HEAD:examples/project-adoption/identity-conflict-input.json'));put(negative)
            target=root/'conflict';child('identity-conflict-preview',['preview','--input',str(input_file),'--export',str(target)])
            conflict=json.loads((target/'proposal.json').read_text());assert all(x['operation']=='CONFLICT' and x['after']=={} for x in conflict['entries'])
            for status in ['UNKNOWN','REFUSED','NOT_EXAMINED']:
                case=copy.deepcopy(value);case['mappings']=[]
                for doc in case['inventory']['documents']:
                    if doc['path']=='docs/architecture/ARCHITECTURE.md':doc['status']=status
                put(bind(case));target=root/status;child(status.lower()+'-preview',['preview','--input',str(input_file),'--export',str(target)])
                row=next(x for x in json.loads((target/'proposal.json').read_text())['entries'] if x['artifact_path']=='docs/architecture/ARCHITECTURE.md')
                assert row['operation']=='INSUFFICIENT_INFORMATION' and row['after']=={}
            for label in ['existing-change','identical-keep','excluded-source','dirty-absence','ambiguous-vision','identity-bytes-missing','code-quality-claim']:
                case=copy.deepcopy(value)
                doc=next(x for x in case['inventory']['documents'] if x['path']=='docs/architecture/ARCHITECTURE.md')
                expected_operation='CONFLICT'
                inspect_path='docs/architecture/ARCHITECTURE.md'
                if label in {'existing-change','identical-keep'}:
                    content='Existing architecture in original language.\n' if label=='existing-change' else architecture['after']['content']
                    doc.update(status='PRESENT',content=content,sha256=sha(content.encode()),mode=0o644,semantic_owner='Architecture',update_class='PROJECT_OWNED')
                    if label=='existing-change':case['mappings'].append({'artifact_path':inspect_path,'source_path':inspect_path,'choice':'PROPOSE_REPLACEMENT'})
                    expected_operation='PROPOSE_CHANGE' if label=='existing-change' else 'KEEP'
                elif label=='excluded-source':
                    case['inventory']['coverage']['excluded_paths']=[inspect_path];expected_operation='INSUFFICIENT_INFORMATION'
                elif label=='dirty-absence':case['inventory']['context']['untracked_paths']=[inspect_path]
                elif label=='ambiguous-vision':
                    inspect_path='docs/product/VISION.md';case['mappings']=[]
                    extra={'path':'docs/OTHER_VISION.md','status':'PRESENT','content':'Other supplied vision','sha256':sha(b'Other supplied vision'),'mode':0o644,'artifact_hint':'PB-A13'}
                    case['inventory']['documents'].append(extra);case['inventory']['coverage']['covered_paths'].append(extra['path'])
                elif label=='identity-bytes-missing':
                    extra={'path':'.engineering-platform/repository.json','status':'PRESENT','sha256':sha(b'unavailable declaration'),'mode':0o644}
                    case['inventory']['documents'].append(extra);case['inventory']['coverage']['covered_paths'].append(extra['path']);expected_operation='INSUFFICIENT_INFORMATION'
                elif label=='code-quality-claim':
                    inspect_path='docs/engineering/VALIDATION.md';case['requested_artifacts']=[inspect_path];case['mappings']=[]
                    case['inventory']['documents'].append({'path':inspect_path,'status':'ABSENT'});case['inventory']['coverage']['covered_paths'].append(inspect_path)
                put(bind(case));target=root/label;child(label,['preview','--input',str(input_file),'--export',str(target)])
                actual=json.loads((target/'proposal.json').read_text());row=next(x for x in actual['entries'] if x['artifact_path']==inspect_path)
                assert row['operation']==expected_operation and actual['repository_quality']=='NOT_ASSESSED'
                if label=='existing-change':
                    assert row['before']['content']==content and row['after']['sha256']==sha(row['after']['content'].encode()) and row['diff']
                if label=='identical-keep':assert row['after']['content']==content
                if label=='dirty-absence':assert 'SUPPLIED_CLEAN_LABEL_CONTRADICTS_CONTEXT' in actual['decisions']
            absent=copy.deepcopy(value);absent['inventory']['documents']=[x for x in absent['inventory']['documents'] if x['path']!='docs/architecture/ARCHITECTURE.md'];put(bind(absent));target=root/'notlisted'
            child('not-listed-never-absent',['preview','--input',str(input_file),'--export',str(target)])
            row=next(x for x in json.loads((target/'proposal.json').read_text())['entries'] if x['artifact_path']=='docs/architecture/ARCHITECTURE.md');assert row['operation']=='INSUFFICIENT_INFORMATION'
            corrupt=json.loads((target/'proposal.json').read_text());corrupt['entries'][0]['operation']='PROPOSE_ADDITION';corrupt.pop('proposal_digest');corrupt['proposal_digest']=sha((json.dumps(corrupt,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode())
            (target/'proposal.json').write_text(json.dumps(corrupt));child('unknown-as-absence-negative-control',['check-proposal','--proposal',str(target)],1)
            child_value=copy.deepcopy(value);child_value['bootstrap_input']=json.loads(git('show','HEAD:examples/project-bootstrap/child-input.json'))
            child_value['inventory']['origin']['repository_id']=child_value['bootstrap_input']['identity']['repository_id'];child_value['requested_artifacts']=['docs/engineering/HANDOFF.md'];child_value['mappings']=[]
            child_value['inventory']['documents']=[{'path':'docs/engineering/HANDOFF.md','status':'ABSENT'}];child_value['inventory']['coverage']['covered_paths']=['docs/engineering/HANDOFF.md'];put(bind(child_value));target=root/'child'
            child('child-proposal',['preview','--input',str(input_file),'--export',str(target)])
            child_plan=json.loads((target/'proposal.json').read_text());assert child_plan['entries'][0]['operation']=='PROPOSE_ADDITION' and child_plan['state']=='PROPOSED_NOT_APPROVED'
            changed=copy.deepcopy(value);changed['bootstrap_input']['product']['purpose']='Changed explicit product fact.';put(changed);target=root/'changed'
            changed_receipt=child('changed-input-new-binding',['preview','--input',str(input_file),'--export',str(target)]);assert changed_receipt['proposal_digest']!=first_result['proposal_digest']
            assert {p.name:sha(p.read_bytes()) for p in first.iterdir()}==frozen
            original=(first/'proposal.json').read_bytes();(first/'proposal.json').write_bytes(original+b' ');child('changed-plan-refused',['check-proposal','--proposal',str(first)],1);(first/'proposal.json').write_bytes(original)
            first.chmod(0o755);child('lost-private-root-refused',['check-proposal','--proposal',str(first)],1);first.chmod(0o700);child('restored-private-proposal',['check-proposal','--proposal',str(first)])
            for name,change in [('bad-digest',lambda x:x.update(inventory_digest='0'*64)),('cross-path-replace',lambda x:x['mappings'][0].update(choice='PROPOSE_REPLACEMENT')),('unknown-field',lambda x:x.update(extra=True))]:
                bad=copy.deepcopy(value);change(bad);put(bad);target=root/name;child(name,['preview','--input',str(input_file),'--export',str(target)],1);assert not target.exists()
            put(value);repo=root/'disposable-target';repo.mkdir();(repo/'.git').mkdir();sentinel=repo/'existing.txt';sentinel.write_bytes(b'unchanged synthetic target')
            target_before={str(p.relative_to(repo)):sha(p.read_bytes()) for p in repo.rglob('*') if p.is_file()}
            child('repository-export-refused',['preview','--input',str(input_file),'--export',str(repo/'proposal')],1)
            assert {str(p.relative_to(repo)):sha(p.read_bytes()) for p in repo.rglob('*') if p.is_file()}==target_before
            child('reserved-git-export-refused',['preview','--input',str(input_file),'--export',str(root/'.git')],1)
            alias=root/'alias';alias.symlink_to(root,target_is_directory=True);child('symlink-export-refused',['preview','--input',str(input_file),'--export',str(alias/'proposal')],1)
            assert sha(input_file.read_bytes())==original_input
            receipt['supplied_input_unchanged']=True;receipt['disposable_target_unchanged']=True;receipt['previous_proposal_and_pin_preserved']=True
        receipt['cleanup']=not root.exists();receipt['result']='PROJECT_ADOPTION_OFFLINE_PASS'
    except BaseException as error:
        receipt['failure']={'category':type(error).__name__};raise
    finally:
        (output/'installed-project-adoption.public.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print('PROJECT_ADOPTION_OFFLINE_PASS',len(receipt['cases']))
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--wheel',required=True);parser.add_argument('--source-revision',required=True);parser.add_argument('--output-dir',required=True)
    raise SystemExit(run(parser.parse_args()))
