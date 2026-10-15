"""Actual noneditable Forge -> authenticated EP original GET; isolated synthetic owner setup."""
from pathlib import Path
from contextlib import contextmanager
from copy import deepcopy
from tempfile import mkdtemp
from hashlib import sha256
from datetime import UTC, datetime, timedelta
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import spec_from_file_location, module_from_spec
import argparse
import http.client
import json
import os
import socket
import shutil
import subprocess
import sys
import time
import zipfile
import configparser

SOURCE = Path(__file__).resolve().parents[2]
spec = spec_from_file_location('r52_binding',Path(__file__).with_name('qualify_installed_project_proposal_http.py'))
BINDING = module_from_spec(spec)
spec.loader.exec_module(BINDING)
CONTRACT = 'forge-ep-inspection-adoption-preview/v1'
EP_REVISION = 'f3b56303b561a7193965f4aa41fd8da744a8c1c2'
EP_WHEEL_SHA = '1a54340ab348231896eb59bd6a55b014ba52d465f3c90dd481360b46a2cdf43e'


def private(path, value):
    path.write_bytes(value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2).encode())
    path.chmod(0o600)



def command_capture(arguments, *, module, output, cwd, env, commands, timeout=None):
    """Record primary process outcome before any caller diagnostic publication."""
    label = 'command-'+str(len(commands)+1)
    report, stdout, stderr = BINDING.CAPTURE.capture(arguments,case=label,output=output,cwd=cwd,env=env,expected=0,timeout=timeout)
    commands.append({'module':module,**report,'stdout_sha256':sha256(stdout).hexdigest(),
                     'stderr_sha256':sha256(stderr).hexdigest()})
    if report['primary_failure'] is not None:
        raise RuntimeError('installed owning command failed:'+label+':'+report['primary_failure']['category'])
    if not report['capture_complete'] or report['secondary_failures']:
        raise RuntimeError('installed owning command evidence incomplete:'+label)
    return json.loads(stdout)


def finish_receipt(output, receipt, commands, primary):
    """All fallible private retention precedes public success publication."""
    retention_error = None
    try:
        private(output/'commands.private.json',commands)
    except OSError as error:
        retention_error = error
        receipt['result'] = 'FAIL'
        receipt['diagnostic_complete'] = False
        receipt['failure_type'] = type(primary or error).__name__
        if primary is not None:
            primary.add_note('command diagnostic retention incomplete: '+type(error).__name__)
    effective_primary = primary or retention_error
    BINDING.retain_receipt(output,receipt,effective_primary)
    legacy = output/'installed-project-proposal-http.public.json'
    try:
        if legacy.exists():
            legacy.rename(output/'installed-inspection-adoption.public.json')
    except OSError as error:
        if effective_primary is None:
            raise
        effective_primary.add_note('receipt rename incomplete: '+type(error).__name__)
    if primary is None and retention_error is not None:
        raise retention_error


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def request(port_number, method, target, headers, body=None, lost=False, timeout=15):
    client = http.client.HTTPConnection('127.0.0.1',port_number,timeout=timeout)
    try:
        client.request(method,target,body=None if body is None else json.dumps(body).encode(),headers={**headers,'Content-Type':'application/json'})
        if lost:
            return None
        response = client.getresponse()
        raw = response.read(1048577)
        value = json.loads(raw)
        if target.startswith('/v1/inspection-adoptions/'):
            from jsonschema import Draft202012Validator
            Draft202012Validator(json.loads((SOURCE/'forge/api/inspection-adoptions-v1.json').read_text())).validate(value)
            if response.status == 200 and body is not None:
                Draft202012Validator(json.loads((SOURCE/'forge/api/inspection-adoptions-v1.json').read_text())).validate(body)
        return response.status,raw,value
    finally:
        client.close()


def recover_original(port_number, intent, headers, output):
    """Recover ONLY the original GET within the existing ten-second window.

    A pending projection can lose its publication CAS to the same operation's
    successful commit. No cached success, new POST or generic scope retry.
    """
    deadline = time.monotonic()+10
    attempts = 0
    while True:
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise RuntimeError('lost answer original readback deadline')
        code, raw, value = request(port_number,'GET',intent,headers,timeout=min(15,remaining))
        if code == 200:
            return code,raw,value
        attempts += 1
        private(output/('recovery-'+str(attempts)+'.private.json'),{'status':code,'response':value})
        if code == 403 and value.get('error',{}).get('code') == 'PROPOSAL_PUBLICATION_DENIED':
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise RuntimeError('lost answer original readback deadline')
            current, _, _ = request(port_number,'GET','/v1/inspection-adoptions/capability',headers,timeout=min(15,remaining))
            if current != 200:
                raise RuntimeError('lost answer current authority denied:'+str(current))
        elif code not in (202,404):
            raise RuntimeError('lost answer did not recover original:'+str(code))
        time.sleep(min(.05,max(0,deadline-time.monotonic())))


@contextmanager
def relay(ep_port, records, faults):
    """External HTTP audit relay, always forwards to the real separately installed EP."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            connection = http.client.HTTPConnection('127.0.0.1',ep_port,timeout=15)
            try:
                connection.request('GET',self.path,headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection')})
                response = connection.getresponse()
                raw = response.read(1048577)
                if response.status == 200 and faults.get('coherent_content'):
                    altered = json.loads(raw)
                    doc = next(d for d in altered['observation']['documents'] if d['content'] is not None)
                    doc['content'] += '\nUntrusted coherent alteration'
                    doc['sha256'] = sha256(doc['content'].encode()).hexdigest()
                    raw = json.dumps(altered).encode()
                records.append({'method':'GET','path':self.path,'status':response.status,'body_sha256':sha256(raw).hexdigest()})
                self.send_response(response.status)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            finally:
                connection.close()
        def do_POST(self):
            records.append({'method':'POST','path':self.path,'status':405})
            self.send_error(405)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        thread.join(3)
        server.server_close()
        if thread.is_alive():
            raise RuntimeError('own HTTP relay did not stop')


def tree(root):
    return {str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}


def run(args):
    output = args.output_dir
    output.mkdir(mode=0o700)
    receipt = {'result':'FAIL','cases':[],'cleanup':False,**BINDING.installed_binding(args.python,args.wheel,args.source_revision)}
    manifest = json.loads((SOURCE/'forge/api/ep-inspection-producer-runtime-v1.json').read_text())
    with zipfile.ZipFile(args.ep_wheel) as archive:
        payload = {name:sha256(archive.read(name)).hexdigest() for name in archive.namelist() if name.startswith('engineering_platform/') and not name.endswith('/')}
        entries = [name for name in archive.namelist() if name.endswith('.dist-info/entry_points.txt')]
        if payload != manifest['payload'] or len(entries) != 1:
            raise ValueError('exact qualified EP product payload required')
        parser = configparser.ConfigParser()
        parser.read_string(archive.read(entries[0]).decode())
        if dict(parser['console_scripts']) != manifest['console_scripts']:
            raise ValueError('exact qualified EP entrypoints required')
    probe = "import engineering_platform,importlib.metadata,json;from pathlib import Path;d=importlib.metadata.distribution('engineering-platform');print(json.dumps({'package':str(Path(engineering_platform.__file__).resolve().parent),'version':d.version,'direct':json.loads(d.read_text('direct_url.json')),'entries':{e.name:e.value for e in d.entry_points if e.group=='console_scripts'}}))"
    installed = json.loads(subprocess.check_output([str(args.ep_python),'-I','-c',probe],cwd=args.ep_wheel.parent))
    package = Path(installed['package'])
    actual_payload = {str(path.relative_to(package.parent)):sha256(path.read_bytes()).hexdigest() for path in package.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
    if actual_payload != payload or installed['version'] != manifest['version'] or installed['entries'] != manifest['console_scripts'] or installed['direct'].get('dir_info',{}).get('editable') or installed['direct'].get('archive_info',{}).get('hashes',{}).get('sha256') != sha256(args.ep_wheel.read_bytes()).hexdigest():
        raise ValueError('qualified EP installed bytes/version/noneditable wheel mismatch')
    receipt.update(ep_producer_revision=EP_REVISION,ep_wheel_sha256=sha256(args.ep_wheel.read_bytes()).hexdigest(),ep_payload_files_verified=len(payload),
                   ep_transport='ACTUAL_INSTALLED_EP_HTTP_VIA_EXTERNAL_AUDIT_RELAY',
                   operator_identity='MODELED_TRUSTED_OS_FIXTURE' if args.modeled_os_identity else 'ACTUAL_MACOS_GENERATED_UID',
                   snapshot_preparation='EXPLICIT_TESTOWNER_PREPARATION_SEPARATE_FROM_GET_ONLY_ADAPTER')
    def invocation(python, arguments):
        if not args.modeled_os_identity or python != args.python:
            return [str(python),'-I',*map(str,arguments)]
        code = "import os,runpy,sys;from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter,NamedOperatorIdentity;MacOSGeneratedUIDIdentityAdapter.resolve=lambda self:NamedOperatorIdentity('r55-declared-hosted-os-fixture',os.getuid());a=sys.argv[1:];sys.argv=a[1:] if a[0]=='-m' else a;runpy.run_module(sys.argv[0],run_name='__main__') if a[0]=='-m' else runpy.run_path(a[0],run_name='__main__')"
        return [str(python),'-I','-c',code,*map(str,arguments)]
    commands = []
    deadline = time.monotonic()+240
    processes = []
    ep_started = False
    primary = None
    root = None
    def command(python,module,*arguments,env=None):
        if time.monotonic() >= deadline:
            raise TimeoutError('prebooked qualification deadline')
        return command_capture(invocation(python,['-m',module,*arguments]),module=module,
                               output=output,cwd=root,env=env,commands=commands,timeout=min(30,deadline-time.monotonic()))

    @contextmanager
    def owned_fixture():
        nonlocal ep_started
        temporary = Path(mkdtemp(prefix='forge-r55-own-')).resolve()
        original_error = None
        try:
            yield temporary
        except BaseException as error:
            original_error = error
            raise
        finally:
            cleanup_error = None
            try:
                captured = 0
                ep_files = temporary/'ep-runtime'/'preproject-inspection-v1'
                for source in sorted(ep_files.rglob('*')):
                    if source.is_file() and not source.is_symlink():
                        raw = source.read_bytes()
                        captured += len(raw)
                        if captured > 2097152:
                            raise RuntimeError('original EP diagnostic capture bound exceeded')
                        target = output/'ep-private-capture'/source.relative_to(ep_files)
                        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                        private(target,raw)
            except BaseException as error:
                cleanup_error = error
                if original_error is not None:
                    original_error.add_note('original EP capture incomplete: '+type(error).__name__)
            if ep_started:
                try:
                    command_capture([str(args.ep_python),'-I','-m','engineering_platform.server','stop',
                        '--data-root',str(ep_root),'--expected-instance-id',ep_instance],module='owning-ep-cleanup',
                        output=output,cwd=temporary,env=env,commands=commands,timeout=30)
                    ep_started = False
                except BaseException as error:
                    cleanup_error = error
            try:
                if cleanup_error is None and not ep_started and all(p.poll() is not None for p in processes):
                    shutil.rmtree(temporary)
                else:
                    raise RuntimeError('own fixture retained: process stop unconfirmed')
            except BaseException as error:
                cleanup_error = cleanup_error or error
            if cleanup_error is not None:
                if original_error is not None:
                    original_error.add_note('owned cleanup incomplete: '+type(cleanup_error).__name__)
                else:
                    raise cleanup_error
    try:
        with owned_fixture() as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            ep_root = root/'ep-runtime'
            host = root/'host'
            workspace = root/'workspace'
            target = workspace/'synthetic'
            (target/'docs').mkdir(parents=True)
            (host/'.engineering').mkdir(parents=True)
            managed = root/'managed'
            (managed/'bin').mkdir(parents=True)
            (managed/'bin/codex').symlink_to(args.ep_native_launcher)
            env = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
            env.update(EP_MANAGED_CODEX_CLI_PREFIX=str(managed),PYTHONDONTWRITEBYTECODE='1')
            original_input = json.loads((SOURCE/'examples/project-adoption/adopt-existing-vision-input.json').read_text())
            vision = next(d['content'] for d in original_input['inventory']['documents'] if d['path']=='docs/RICHTING.md')
            (target/'docs/RICHTING.md').write_text(vision)
            private(host/'.engineering/engineering-platform.local.json',{'workspace':{'workspace_authorization':{
                'allowed_roots':[{'path':str(workspace),'repository_scope':'direct_children'}],
                'allowed_repositories':[],'denied_repositories':[],'symlink_policy':'reject','case_sensitivity':'host'}}})
            ep_port = port()
            initialized = command(args.ep_python,'engineering_platform.server','init','--data-root',ep_root,'--bind-port',ep_port,env=env)
            ep_instance = initialized['instance_id']
            def ep(module,action,*arguments,config=None):
                extra = []
                if config is not None:
                    config_path = root/('ep-config-'+str(len(commands))+'.private.json')
                    private(config_path,config)
                    extra = ['--config',str(config_path)]
                return command(args.ep_python,module,action,'--data-root',ep_root,'--expected-instance-id',ep_instance,*arguments,*extra,env=env)
            ep('engineering_platform.preproject_cli','init')
            ep('engineering_platform.preproject_cli','bind-source',config={'source_ref':'source-selected','host_root':str(host),'workspace_root':str(workspace),'child':'synthetic'})
            paths = ['docs/RICHTING.md','docs/architecture/ARCHITECTURE.md']
            issued = ep('engineering_platform.preproject_cli','issue',config={'grant_id':'selected-existing','source_ref':'source-selected',
                 'consumer_id':'forge-synthetic','principal':'synthetic-peer','audience':'synthetic-transfer',
                 'paths':paths,'content_paths':['docs/RICHTING.md'],'ttl_seconds':900,'max_operations':2})
            private(root/'ep-token.private',issued['credential'].encode())
            ep_started = True
            ep('engineering_platform.server','start','--bind-port',ep_port)
            first_ep = json.loads((ep_root/'runtime.json').read_text())['pid']
            headers = {'Authorization':'Bearer '+issued['credential'],'EP-Inspection-Contract':'1.0','EP-Instance-ID':ep_instance,
                       'EP-Host-ID':issued['host_id'],'EP-Consumer-ID':'forge-synthetic','EP-Principal':'synthetic-peer','EP-Audience':'synthetic-transfer'}
            status, raw, snapshot = request(ep_port,'POST','/v1/onboarding/inspections',headers,{'contract_version':'1.0','operation_id':'op-original','source_ref':'source-selected'})
            private(output/'ep-original.private.json',raw)
            if status != 200 or snapshot['outcome'] != 'COMPLETE':
                raise RuntimeError('actual EP owner preparation refused:'+str(status))
            receipt['inspection_posts_by_testowner_before_adapter'] = 1
            receipt['cases'].append('actual-owner-prepared-original-on-qualified-installed-ep')
            source_manifest = tree(target)
            ep_ledger = tree(ep_root/'preproject-inspection-v1')
            canonical = lambda v:(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
            audited = []
            faults = {}
            with relay(ep_port,audited,faults) as relay_port:
                forge_root = root/'forge'
                # Existing ordinary fixture binds the actual Mac owner and initializes R52; no project.
                fixture = Path(__file__).with_name('proposal_content_fixture.py')
                setup = command_capture(invocation(args.python,[str(fixture),str(forge_root)]),module='owning-fixture',
                                        output=output,cwd=root,env=None,commands=commands)
                def forge(action,*arguments):
                    return command(args.python,'forge.ep_inspection_cli','--data-root',forge_root/'runtime',action,*arguments)
                forge('init')
                pairing = {'pairing_id':'selected-original','endpoint':'http://127.0.0.1:'+str(relay_port),
                           'producer_revision':EP_REVISION,'producer_tree':'28d957a5988d35bc3469e8767006595c7cb3d8f1',
                           'producer_schema_sha256':'fe289b3f5a00a837c1e2afdefc675e2fdc2427b8fd419017883347c0b6dc5e96',
                           'snapshot_digest':sha256(canonical(snapshot)).hexdigest(),
                           'binding':{'instance_id':ep_instance,'host_id':issued['host_id'],'consumer_id':'forge-synthetic',
                                      'principal':'synthetic-peer','audience':'synthetic-transfer','source_ref':'source-selected','operation_id':'op-original',
                                      'paths':paths,'content_paths':['docs/RICHTING.md']}}
                private(root/'pairing.private.json',pairing)
                forge('bind','--config-file',root/'pairing.private.json','--ep-token-file',root/'ep-token.private')
                own_issued = forge('issue','--principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier',
                      '--permission','READ','--permission','PREPARE','--pairing-id','selected-original','--maximum-records','4',
                      '--expires-at',(datetime.now(UTC)+timedelta(minutes=15)).isoformat(),'--token-file',root/'forge-token.private')
                forged_headers = {'Authorization':'Bearer '+(root/'forge-token.private').read_text().strip(),'X-Forge-Inspection-Audience':'synthetic-workspace'}
                value = {k:original_input[k] for k in ('bootstrap_input','requested_artifacts','mappings')}
                value['requested_artifacts'].append('docs/roadmap/ROADMAP.md')
                body = {'contract_version':CONTRACT,'instance_id':setup['instance_id'],'dossier_id':'synthetic-dossier',
                        'operation_id':'adopt-original','pairing_id':'selected-original','input':value}
                @contextmanager
                def forge_server():
                    listen = port()
                    with (output/'forge-server.private.log').open('ab') as log:
                        child = subprocess.Popen(invocation(args.python,['-m','forge','--data-root',str(forge_root/'runtime'),'server','run',
                            '--credential-file',str(forge_root/'admin.private'),'--port',str(listen),'--tick-interval','1']),cwd=root,stdout=log,stderr=log)
                        processes.append(child)
                        try:
                            stop = time.monotonic()+15
                            while True:
                                if child.poll() is not None:
                                    raise RuntimeError('installed Forge Server exited')
                                try:
                                    code,_,cap = request(listen,'GET','/v1/inspection-adoptions/capability',forged_headers)
                                    if code != 200:
                                        raise RuntimeError('new capability denied:'+str(code))
                                    break
                                except ConnectionError:
                                    if time.monotonic() >= stop:
                                        raise
                                    time.sleep(.05)
                            yield listen
                        finally:
                            child.terminate()
                            try:child.wait(timeout=5)
                            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
                audit_start = len(audited)
                with forge_server() as forge_port:
                    request(forge_port,'POST','/v1/inspection-adoptions/plans',forged_headers,body,lost=True)
                    intent = '/v1/inspection-adoptions/intents/adopt-original?dossier_id=synthetic-dossier'
                    code, original_raw, proposal = recover_original(forge_port,intent,forged_headers,output)
                    private(output/'forge-original.private.json',original_raw)
                    generated = json.loads(next(a['content'] for a in proposal['result']['artifacts'] if a['path']=='proposal.json'))
                    from jsonschema import Draft202012Validator
                    Draft202012Validator(json.loads((SOURCE/'forge/api/inspection-adoption-proposal-v1.json').read_text())).validate(generated)
                    entries = {x['artifact_path']:x for x in generated['entries']}
                    assert entries['docs/product/VISION.md']['operation']=='LINK_EXISTING'
                    assert entries['docs/product/VISION.md']['mapping_source']['content']==vision
                    assert entries['docs/product/VISION.md']['mapping_source']['mode'] is None
                    assert entries['docs/architecture/ARCHITECTURE.md']['operation']=='PROPOSE_ADDITION'
                    assert entries['docs/roadmap/ROADMAP.md']['operation']=='INSUFFICIENT_INFORMATION'
                    receipt['cases'].append('actual-installed-http-dutch-link-real-absence-addition-unknown-roadmap')
                    receipt['cases'].append('lost-answer-original-intent-no-repost-or-second-proposal')
                    code,_,same = request(forge_port,'POST','/v1/inspection-adoptions/plans',forged_headers,body)
                    assert code==200 and same==proposal
                    receipt['cases'].append('identical-explicit-operation-replay-original-result')
                    concurrent = []
                    workers = [Thread(target=lambda:concurrent.append(request(forge_port,'POST','/v1/inspection-adoptions/plans',forged_headers,body))) for _ in range(2)]
                    for worker in workers:worker.start()
                    for worker in workers:
                        worker.join(15)
                        assert not worker.is_alive()
                    assert len(concurrent)==2 and all(code==200 and same==proposal for code,_,same in concurrent)
                    changed = deepcopy(body)
                    changed['input']['bootstrap_input']['product']['purpose']='Changed exact request'
                    assert request(forge_port,'POST','/v1/inspection-adoptions/plans',forged_headers,changed)[0]==409
                    foreign = {**forged_headers,'X-Forge-Inspection-Audience':'foreign'}
                    assert request(forge_port,'GET',intent,foreign)[0]==403
                    old = {**forged_headers,'Authorization':'Bearer '+(forge_root/'prepare.private').read_text().strip()}
                    assert request(forge_port,'POST','/v1/inspection-adoptions/plans',old,body)[0]==403
                    faults['coherent_content'] = True
                    assert request(forge_port,'GET',intent,forged_headers)[0]==424
                    faults.clear()
                    assert request(forge_port,'GET',intent,forged_headers)[2]==proposal
                    receipt['cases'].append('actual-installed-concurrency-key-conflict-old-grant-audience-and-coherent-payload-rejection')

                ep('engineering_platform.server','stop')
                ep('engineering_platform.server','start','--bind-port',ep_port)
                second_ep = json.loads((ep_root/'runtime.json').read_text())['pid']
                assert first_ep != second_ep
                with forge_server() as forge_port:
                    code,_,same = request(forge_port,'GET',intent,forged_headers)
                    assert code==200 and same==proposal
                receipt['cases'].append('separate-forge-and-ep-server-os-restarts-original-proposal-readback')
                # Relevant restored fault in ONLY this disposable Forge installation.
                # The same real HTTP detector must fail when the original-digest guard is removed.
                installed_peer = Path(subprocess.check_output([str(args.python),'-I','-c',
                    'import forge.ep_inspection_peer;print(forge.ep_inspection_peer.__file__)'],cwd=root).decode().strip())
                original_peer = installed_peer.read_bytes()
                guard = b"if sha256(canonical(value)).hexdigest() != pairing['snapshot_digest']:"
                assert original_peer.count(guard)==1
                faults['coherent_content'] = True
                detected = False
                try:
                    installed_peer.write_bytes(original_peer.replace(guard,b"if False and sha256(canonical(value)).hexdigest() != pairing['snapshot_digest']:"))
                    shutil.rmtree(installed_peer.parent/'__pycache__',ignore_errors=True)
                    with forge_server() as forge_port:
                        probe = "import http.client,json,sys;c=http.client.HTTPConnection('127.0.0.1',int(sys.argv[1]),timeout=15);c.request('GET',sys.argv[2],headers=json.load(sys.stdin));r=c.getresponse();r.read();assert r.status==424, 'restored wrong-original-digest fault escaped rejection'"
                        negative = subprocess.run([str(args.python),'-I','-c',probe,str(forge_port),intent],
                            input=json.dumps(forged_headers).encode(),capture_output=True,cwd=root,timeout=20)
                        private(output/'restored-fault.stdout.private',negative.stdout)
                        private(output/'restored-fault.stderr.private',negative.stderr)
                        assert negative.returncode!=0 and b'restored wrong-original-digest fault' in negative.stderr
                        detected = True
                finally:
                    installed_peer.write_bytes(original_peer)
                    shutil.rmtree(installed_peer.parent/'__pycache__',ignore_errors=True)
                    assert installed_peer.read_bytes()==original_peer
                assert detected
                with forge_server() as forge_port:
                    assert request(forge_port,'GET',intent,forged_headers)[0]==424
                    faults.clear()
                    assert request(forge_port,'GET',intent,forged_headers)[2]==proposal
                    forge('issue','--principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier',
                          '--permission','READ','--pairing-id','selected-original','--maximum-records','4',
                          '--expires-at',(datetime.now(UTC)+timedelta(seconds=2)).isoformat(),'--token-file',root/'short-reader.private')
                    short_headers = {**forged_headers,'Authorization':'Bearer '+(root/'short-reader.private').read_text().strip()}
                    assert request(forge_port,'GET',intent,short_headers)[0]==200
                    time.sleep(2.05)
                    assert request(forge_port,'GET',intent,short_headers)[0]==401
                    receipt['cases'].append('real-short-read-grant-expiry-denies-installed-http-no-disclosure')
                    forge('revoke','--grant-id',own_issued['grant_id'])
                    assert request(forge_port,'GET',intent,forged_headers)[0]==401
                receipt['cases'].append('real-restored-digest-fault-detector-red-original-installed-bytes-restored-and-green')
                receipt['cases'].append('actual-owning-cli-revoke-denies-installed-http-without-cached-disclosure')
                receipt['final_installed_bytes_reverified'] = BINDING.installed_binding(args.python,args.wheel,args.source_revision)['wheel_sha256']==receipt['wheel_sha256']

                assert all(x['method']=='GET' and x['path']=='/v1/onboarding/inspections/op-original' for x in audited[audit_start:])
                receipt['adapter_gets'] = len(audited)-audit_start
                receipt['adapter_inspection_posts'] = 0
                private(output/'adapter-http-audit.private.json',audited[audit_start:])
                assert tree(target)==source_manifest and tree(ep_root/'preproject-inspection-v1')==ep_ledger
                receipt['target_and_ep_inspection_ledger_unchanged']=True
                private(output/'forge-store.private.json',(forge_root/'runtime/onboarding/inspection-adoption/store.json').read_bytes())
                private(output/'ep-ledger-file-digests.private.json',ep_ledger)
                receipt['proposal_records']=len(json.loads((forge_root/'runtime/onboarding/inspection-adoption/store.json').read_text())['records'])
                assert receipt['proposal_records']==1
            ep('engineering_platform.server','stop')
            ep_started = False
            receipt['separate_ep_server_pids'] = first_ep != second_ep
            receipt['separate_forge_processes'] = len({p.pid for p in processes})>=4
            receipt['result']='EP_INSPECTION_ADOPTION_HTTP_PASS'
            private(output/'commands.private.json',commands)
        receipt['cleanup'] = not root.exists() and all(p.poll() is not None for p in processes)
        if not receipt['cleanup']:
            raise RuntimeError('owned fixture cleanup incomplete')
    except BaseException as error:
        primary = error
        receipt['result']='FAIL'
        receipt['failure_type']=type(error).__name__
        raise
    finally:
        # If EP start was uncertain, keep root/diagnostics rather than pretending cleanup.
        receipt['ep_stop_pending'] = ep_started
        if ep_started:
            receipt['result']='FAIL'
        finish_receipt(output,receipt,commands,primary)
    print(receipt['result'],len(receipt['cases']))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('python','wheel','ep-python','ep-wheel','ep-native-launcher','output-dir'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--source-revision',required=True)
    parser.add_argument('--modeled-os-identity',action='store_true')
    run(parser.parse_args())
