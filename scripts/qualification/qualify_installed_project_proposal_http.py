"""Ordinary external HTTP client against a separate noneditable installed Server OS process."""
from contextlib import contextmanager
from datetime import UTC,datetime,timedelta
from hashlib import sha256
from pathlib import Path
import argparse
import importlib.util
import sys
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

CONTRACT='forge-project-proposal-http/v1'
SOURCE=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('proposal_capture',Path(__file__).with_name('project_bootstrap_process.py'))
CAPTURE=importlib.util.module_from_spec(spec);spec.loader.exec_module(CAPTURE)
COMMAND_COUNTER=0
MODELED_OS_IDENTITY=False


def invocation(python,args):
    if not MODELED_OS_IDENTITY:return [str(python),'-I',*args]
    if args[0] != '-m':raise ValueError('qualification fixture supports modules only')
    code="import os,runpy,sys;from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter,NamedOperatorIdentity;MacOSGeneratedUIDIdentityAdapter.resolve=lambda self:NamedOperatorIdentity('r52-isolated-trusted-os-fixture',os.getuid());sys.argv=[sys.argv[1],*sys.argv[2:]];runpy.run_module(sys.argv[0],run_name='__main__')"
    return [str(python),'-I','-c',code,*args[1:]]


def command(python,args,root):
    global COMMAND_COUNTER
    COMMAND_COUNTER+=1
    report,stdout,stderr=CAPTURE.capture(invocation(python,args),case='setup-'+str(COMMAND_COUNTER),output=root.parent,cwd=root,env={'PATH':str(python.parent)+':/usr/bin:/bin','HOME':str(root)},expected=0)
    if not report['capture_complete'] or report['primary_failure']:raise RuntimeError('trusted setup command or capture failed')
    return json.loads(stdout)


def call(port,token,method,path,body=None):
    raw=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    request=Request('http://127.0.0.1:'+str(port)+path,method=method,data=raw,headers={'Authorization':'Bearer '+token.read_text().strip(),'X-Forge-Proposal-Audience':'synthetic-workspace','Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=15) as response:return response.status,json.loads(response.read())
    except HTTPError as error:
        try:return error.code,json.loads(error.read())
        finally:error.close()


@contextmanager
def server(python,root):
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    with (root/'server.private.log').open('ab') as log:
        process=subprocess.Popen(invocation(python,['-m','forge','--data-root',str(root/'runtime'),'server','run','--credential-file',str(root/'admin.private'),'--port',str(port),'--tick-interval','1']),cwd=root,stdout=log,stderr=log,start_new_session=True)
        try:
            deadline=time.monotonic()+15
            while True:
                if process.poll() is not None:raise RuntimeError('separate Server exited before readiness')
                try:
                    status,_=call(port,root/'alice.private','GET','/v1/onboarding/capability')
                    if status==200:break
                    raise RuntimeError('installed HTTP capability denied')
                except (URLError,ConnectionError):
                    if time.monotonic()>deadline:raise TimeoutError('installed HTTP Server startup')
                    time.sleep(0.05)
            yield port,process.pid
        finally:
            primary = sys.exc_info()[1]
            secondary = []
            try:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            except Exception as error: secondary.append(error)
            try:
                log.flush()
                raw=(root/'server.private.log').read_bytes()
                if len(raw)>65536: raise RuntimeError('private server log exceeds finite capture')
                (root.parent/('private-server-'+str(process.pid)+'.log')).write_bytes(raw)
            except Exception as error: secondary.append(error)
            if secondary:
                if primary is not None:
                    primary.add_note('diagnostics incomplete; secondary cleanup/capture: '+','.join(type(x).__name__ for x in secondary))
                else: raise secondary[0]


def installed_binding(python, wheel, revision):
    # Reuse qualified payload verification; this checks installation, not services.
    spec=importlib.util.spec_from_file_location('proposal_payload',Path(__file__).with_name('qualify_installed_project_bootstrap.py'))
    tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
    import fnmatch, tomllib, zipfile, configparser
    def git(*args):return subprocess.check_output(['git','-C',str(SOURCE),*args])
    if git('rev-parse','HEAD').decode().strip()!=revision or git('status','--porcelain').strip():raise ValueError('exact clean committed source required')
    manifest=tomllib.loads(git('show','HEAD:pyproject.toml').decode())
    patterns=manifest['tool']['setuptools']['package-data']['forge']
    expected={n:git('show','HEAD:'+n) for n in git('ls-tree','-r','--name-only','HEAD','--','forge').decode().splitlines() if n.endswith('.py') or any(fnmatch.fnmatchcase(n.removeprefix('forge/'),p) for p in patterns)}
    probe="import forge,json,importlib.metadata;from pathlib import Path;d=importlib.metadata.distribution('forge-autonomy');print(json.dumps({'package':str(Path(forge.__file__).resolve().parent),'version':d.version,'direct':json.loads(d.read_text('direct_url.json')),'entries':{e.name:e.value for e in d.entry_points if e.group=='console_scripts'}}))"
    actual=json.loads(subprocess.check_output([str(python),'-I','-c',probe],cwd=wheel.parent))
    product=Path(actual['package'])
    if product.is_relative_to(SOURCE) or actual['direct'].get('dir_info',{}).get('editable') or actual['direct'].get('archive_info',{}).get('hashes',{}).get('sha256')!=sha256(wheel.read_bytes()).hexdigest():raise ValueError('noneditable exact wheel required')
    with zipfile.ZipFile(wheel) as archive:
        payload=tool.verify_payload(archive,expected,product.parent)
        entries=[x for x in archive.namelist() if x.endswith('.dist-info/entry_points.txt')]
        if len(entries)!=1:raise ValueError('entrypoint ambiguity')
        parser=configparser.ConfigParser();parser.read_string(archive.read(entries[0]).decode())
        if dict(parser['console_scripts'])!=manifest['project']['scripts'] or actual['entries']!=manifest['project']['scripts']:raise ValueError('entrypoint mismatch')
    installed={str(p.relative_to(product.parent)) for p in product.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    if installed!=set(expected) or actual['version']!=json.loads(git('show','HEAD:product-version.json'))['version']:raise ValueError('installed inventory/version mismatch')
    return {'source_revision':revision,'source_tree':git('rev-parse','HEAD^{tree}').decode().strip(),'version':actual['version'],'wheel_sha256':sha256(wheel.read_bytes()).hexdigest(),'payload_files_verified':len(payload),'entrypoints_source_wheel_installed_verified':True}


def retain_receipt(output, receipt, primary):
    try:
        (output/'installed-project-proposal-http.public.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    except OSError as error:
        receipt['diagnostic_complete']=False
        receipt['receipt_write_failure']={'category':type(error).__name__}
        try: CAPTURE.retain(output/'installed-project-proposal-http.retention-failure.private.json',(json.dumps(receipt,sort_keys=True,indent=2)+'\n').encode())
        except OSError as secondary:
            sys.stderr.write(json.dumps({'result':'FAIL','primary_category':type(primary).__name__ if primary else None,'retention_failure':type(error).__name__,'fallback_failure':type(secondary).__name__})+'\n')
        if primary is None: raise
        primary.add_note('proposal receipt diagnostics incomplete: '+type(error).__name__)


def run(python,output,wheel=None,revision=None):
    output.mkdir(mode=0o700)
    binding=installed_binding(python,wheel,revision) if wheel is not None else {}
    receipt={'qualification':'INSTALLED_PROJECT_PROPOSAL_HTTP_COMPACT_V1','result':'FAIL','cases':[],'cleanup':False,'operator_identity_evidence':'MODELED_TRUSTED_OS_FIXTURE' if MODELED_OS_IDENTITY else 'ACTUAL_MACOS_GENERATED_UID','transport_evidence':'ACTUAL_INSTALLED_HTTP_SEPARATE_SERVER_OS',**binding}
    primary=None
    try:
        with tempfile.TemporaryDirectory(prefix='forge-proposal-http-',dir=output) as name:
            root=Path(name); (root/'admin.private').write_text(secrets.token_urlsafe(48));(root/'admin.private').chmod(0o600)
            command(python,['-m','forge','--data-root',str(root/'runtime'),'server','init'],root)
            command(python,['-m','forge.project_proposal_grant','--data-root',str(root/'runtime'),'init'],root)
            issued={}
            for principal in ['alice','bob']:
                issued[principal]=command(python,['-m','forge.project_proposal_grant','--data-root',str(root/'runtime'),'issue','--principal-id',principal,'--audience','synthetic-workspace','--dossier-id','dossier-'+principal,'--permission','PREPARE','--permission','READ','--kind','pb-render/1.0','--kind','pb-adoption-preview/1.0','--maximum-records','8','--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(root/(principal+'.private'))],root)
            basis=json.loads(subprocess.check_output(['git','-C',str(SOURCE),'show','HEAD:examples/project-bootstrap/authority-input.json']))
            adoption=json.loads(subprocess.check_output(['git','-C',str(SOURCE),'show','HEAD:examples/project-adoption/adopt-existing-vision-input.json']))
            with server(python,root) as (port,first_pid):
                alice=root/'alice.private';bob=root/'bob.private'
                status,cap=call(port,alice,'GET','/v1/onboarding/capability');assert status==200 and cap['project_registration'] is False
                receipt['cases'].append('actual-installed-http-capability-no-canonical-project')
                results=[];requests=[]
                profiles=[]
                for role in ['authority','child']:
                    original=json.loads(subprocess.check_output(['git','-C',str(SOURCE),'show','HEAD:examples/project-bootstrap/'+role+'-input.json']))
                    for mode,profile in [('GENESIS','LOCAL_POSIX'),('MANAGED','GITHUB_DOCUMENTS')]:
                        profiles.append(('pb-render/1.0',{**original,'mode':mode,'host_profile':profile}))
                for kind,value in [*profiles,('pb-adoption-preview/1.0',adoption)]:
                    body={'contract_version':CONTRACT,'instance_id':cap['instance_id'],'dossier_id':'dossier-alice','operation_id':'original-'+str(len(results)),'proposal_kind':kind,'input':value}
                    status,plan=call(port,alice,'POST','/v1/onboarding/plans',body);assert status==200,(status,plan)
                    assert plan['result']['state']=='PROPOSED_NOT_APPROVED'
                    local_input=root/('input-'+str(len(results))+'.json');local_input.write_text(json.dumps(value,ensure_ascii=False));export=root/('local-comparator-'+str(len(results)))
                    module='forge.project_bootstrap.cli' if kind=='pb-render/1.0' else 'forge.project_adoption.cli'
                    args=['-m',module,'render' if kind=='pb-render/1.0' else 'preview','--input',str(local_input),'--export',str(export)]
                    command(python,args,root)
                    for item in plan['result']['artifacts']:
                        assert (export/item['path']).read_bytes()==item['content'].encode() and sha256(item['content'].encode()).hexdigest()==item['sha256']
                    results.append(plan);requests.append(body);receipt['cases'].append('http-'+kind+'-'+value.get('role','adoption')+'-'+value.get('mode','supplied')+'-exact-installed-cli-parity')
                    assert call(port,alice,'POST','/v1/onboarding/plans',body)==(200,plan)
                    assert call(port,alice,'GET','/v1/onboarding/intents/'+body['operation_id']+'?dossier_id=dossier-alice')==(200,plan)
                    assert call(port,bob,'GET','/v1/onboarding/plans/'+plan['plan_id']+'?dossier_id=dossier-bob')[0]==403
                    assert call(port,root/'admin.private','POST','/v1/onboarding/plans',body)[0]==403
                changed=json.loads(json.dumps(requests[0]));changed['input']['product']['purpose']='Changed supplied fact.'
                assert call(port,alice,'POST','/v1/onboarding/plans',changed)[0]==409
                assert call(port,alice,'GET','/v1/projects')[0]==403
                receipt['cases'].extend(['exact-idempotency-original-intent','cross-caller-dossier-and-admin-denied','changed-same-key-conflicts'])
                # Successful independent Bob scope, not only negative isolation.
                bob_request={**requests[0],'dossier_id':'dossier-bob','operation_id':'bob-original'}
                bob_status,bob_plan=call(port,bob,'POST','/v1/onboarding/plans',bob_request);assert bob_status==200
                assert call(port,bob,'GET','/v1/onboarding/intents/bob-original?dossier_id=dossier-bob')==(200,bob_plan)
                assert call(port,alice,'GET','/v1/onboarding/plans/'+bob_plan['plan_id']+'?dossier_id=dossier-alice')[0]==403
                receipt['cases'].append('two-positive-independent-private-callers')
                store_path=root/'runtime'/'onboarding'/'proposals'/'store.json'
                original_store=store_path.read_bytes()
                corrupt=json.loads(original_store);corrupt['records'][results[0]['plan_id']]['result']['repository_quality']='PASS'
                store_path.write_text(json.dumps(corrupt));store_path.chmod(0o600)
                assert call(port,alice,'GET','/v1/onboarding/intents/original-0?dossier_id=dossier-alice')[0]==503
                assert call(port,alice,'POST','/v1/onboarding/plans',{**requests[0],'operation_id':'must-not-commit'})[0]==503
                store_path.write_bytes(original_store);store_path.chmod(0o600)
                assert call(port,alice,'GET','/v1/onboarding/intents/original-0?dossier_id=dossier-alice')==(200,results[0])
                store_path.unlink()
                assert call(port,alice,'GET','/v1/onboarding/intents/original-0?dossier_id=dossier-alice')[0]==503
                assert not store_path.exists()
                store_path.write_bytes(original_store);store_path.chmod(0o600)
                receipt['cases'].append('actual-private-store-corruption-missing-denial-exact-restoration')
                assert call(port,alice,'POST','/v1/onboarding/plans',{**requests[0],'actor':'owner'})[0]==400
                assert call(port,alice,'GET','/v1/onboarding/intents/original-0?dossier_id=dossier-alice&dossier_id=foreign')[0]==400
                receipt['cases'].append('closed-schema-query-and-no-actor-authority')
                reader=root/'readonly.private'
                command(python,['-m','forge.project_proposal_grant','--data-root',str(root/'runtime'),'issue','--principal-id','alice','--audience','synthetic-workspace','--dossier-id','dossier-alice','--permission','READ','--kind','pb-render/1.0','--maximum-records','8','--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(reader)],root)
                assert call(port,reader,'GET','/v1/onboarding/intents/original-0?dossier_id=dossier-alice')==(200,results[0])
                assert call(port,reader,'POST','/v1/onboarding/plans',requests[0])[0]==403
                assert 'POST /v1/onboarding/plans' not in call(port,reader,'GET','/v1/onboarding/capability')[1]['operations']
                expiring=root/'expiring.private'
                command(python,['-m','forge.project_proposal_grant','--data-root',str(root/'runtime'),'issue','--principal-id','alice','--audience','synthetic-workspace','--dossier-id','dossier-alice','--permission','READ','--kind','pb-render/1.0','--maximum-records','8','--expires-at',(datetime.now(UTC)+timedelta(seconds=3)).isoformat(),'--token-file',str(expiring)],root)
                assert call(port,expiring,'GET','/v1/onboarding/capability')[0]==200
                deadline=time.monotonic()+5
                while call(port,expiring,'GET','/v1/onboarding/capability')[0]==200:
                    if time.monotonic()>deadline:raise TimeoutError('actual finite grant expiry not enforced')
                    time.sleep(0.05)
                assert call(port,expiring,'GET','/v1/onboarding/intents/original-0?dossier_id=dossier-alice')[0]==401
                receipt['cases'].append('actual-owner-issued-readonly-and-real-time-expiry')
                # Real lost success body: client closes without reading the committed response.
                lost={**requests[0],'operation_id':'lost-success'}
                raw=json.dumps(lost).encode();headers=('POST /v1/onboarding/plans HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+alice.read_text().strip()+'\r\nX-Forge-Proposal-Audience: synthetic-workspace\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw))+'\r\nConnection: close\r\n\r\n').encode()
                with socket.create_connection(('127.0.0.1',port),timeout=3) as client:client.sendall(headers+raw);client.shutdown(socket.SHUT_WR)
                deadline=time.monotonic()+5
                while True:
                    status,lost_plan=call(port,alice,'GET','/v1/onboarding/intents/lost-success?dossier_id=dossier-alice')
                    if status==200:break
                    if time.monotonic()>deadline:raise TimeoutError('original lost-response intent unavailable')
                    time.sleep(0.05)
            with server(python,root) as (port,second_pid):
                assert first_pid!=second_pid
                for body,plan in zip(requests,results):assert call(port,root/'alice.private','GET','/v1/onboarding/intents/'+body['operation_id']+'?dossier_id=dossier-alice')==(200,plan)
                assert call(port,root/'alice.private','POST','/v1/onboarding/plans',lost)==(200,lost_plan)
                command(python,['-m','forge.project_proposal_grant','--data-root',str(root/'runtime'),'revoke','--grant-id',issued['alice']['grant_id']],root)
                assert call(port,root/'alice.private','GET','/v1/onboarding/intents/lost-success?dossier_id=dossier-alice')[0]==401
                receipt['cases'].extend(['real-lost-success-original-intent','separate-server-os-restart-exact-readback','actual-revocation-read-replay-denied'])
            with sqlite3.connect(root/'runtime'/'forge.db') as database:
                for table in ['mission_id_allocations','mission_state','governance_decisions']:assert database.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
            stored=json.loads((root/'runtime'/'onboarding'/'proposals'/'store.json').read_text());assert len(stored['records'])==len(results)+2
            receipt.update(result='PROJECT_PROPOSAL_HTTP_COMPACT_PASS',stored_records=len(results)+2,no_canonical_project=True,no_ep_model_mission_effects=True,separate_server_processes=True)
        receipt['cleanup']=not root.exists()
    except BaseException as error:
        primary=error
        receipt['failure']={'category':type(error).__name__,'diagnostics':getattr(error,'__notes__',[])};raise
    finally:
        retain_receipt(output,receipt,primary)
    print(receipt['result'],len(receipt['cases']))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--python',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--wheel',required=True,type=Path);parser.add_argument('--source-revision',required=True)
    parser.add_argument('--modeled-os-identity',action='store_true',help='Explicit isolated hosted OS identity fixture; never live macOS qualification')
    args=parser.parse_args();MODELED_OS_IDENTITY=args.modeled_os_identity;run(args.python,args.output_dir,args.wheel,args.source_revision)
