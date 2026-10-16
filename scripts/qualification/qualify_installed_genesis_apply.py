"""First small real installed Forge/EP Genesis chain; own synthetic targets only.

This does not replace the later negative/recovery matrix or final-main proof.
It requires the separately qualified producer pin before initializing a target.
"""
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from importlib.util import spec_from_file_location, module_from_spec
import json
import fnmatch
import configparser
import signal
import tomllib
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location('genesis_owning_qualification', HERE/'qualify_installed_genesis_bootstrap.py')
G = module_from_spec(spec); spec.loader.exec_module(G)
C = G.C
CONTRACT = 'forge-genesis-apply/v1'


def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()


def private(path, value):
    with path.open('xb') as stream:
        os.chmod(path,0o600)
        stream.write(value if isinstance(value,bytes) else canonical(value))


def probe(python, code, cwd):
    return json.loads(subprocess.check_output([str(python),'-I','-c',code],cwd=cwd,timeout=20))


def ep_payload(args):
    """Noneditable original wheel payload and actual packaged schema readback."""
    if sha256(args.ep_wheel.read_bytes()).hexdigest()!=args.ep_wheel_sha256:
        raise ValueError('qualified EP wheel digest differs')
    def git(*command):
        return subprocess.check_output(['git','-C',str(args.ep_source_root),*command],timeout=30)
    actual_tree=git('rev-parse',args.ep_source_revision+'^{tree}').decode().strip()
    if actual_tree!=args.producer_pin['producer_tree']:
        raise ValueError('actual qualified EP Git tree differs')
    manifest=tomllib.loads(git('show',args.ep_source_revision+':pyproject.toml').decode())
    patterns=manifest['tool']['setuptools']['package-data']['engineering_platform']
    def selected(name):
        relative=name.removeprefix('src/engineering_platform/')
        return relative.endswith('.py') or any(len(relative.split('/'))==len(pattern.split('/'))
            and all(fnmatch.fnmatchcase(part,rule) for part,rule in zip(relative.split('/'),pattern.split('/'))) for pattern in patterns)
    names=git('ls-tree','-r','--name-only',args.ep_source_revision,'--','src/engineering_platform').decode().splitlines()
    expected={name.removeprefix('src/'):git('show',args.ep_source_revision+':'+name) for name in names if selected(name)}
    with zipfile.ZipFile(args.ep_wheel) as wheel:
        members=wheel.namelist()
        if len(members)!=len(set(members)) or any(name.startswith('/') or '..' in Path(name).parts for name in members):
            raise ValueError('EP wheel member alias')
        if any(not name.startswith('engineering_platform/') and '.dist-info/' not in name for name in members):
            raise ValueError('unexpected EP wheel payload namespace')
        from email.parser import BytesParser
        metadata=[n for n in wheel.namelist() if n.endswith('.dist-info/METADATA')]
        if len(metadata)!=1:raise ValueError('EP metadata ambiguity')
        name=BytesParser().parsebytes(wheel.read(metadata[0]))['Name']
        if name!=manifest['project']['name']:raise ValueError('EP package identity differs')
        code="import json,engineering_platform,importlib.metadata;from pathlib import Path;d=importlib.metadata.distribution("+repr(name)+");print(json.dumps({'package':str(Path(engineering_platform.__file__).resolve().parent),'version':d.version,'direct':json.loads(d.read_text('direct_url.json')),'entries':{e.name:e.value for e in d.entry_points if e.group=='console_scripts'}}))"
        info=probe(args.ep_python,code,args.ep_wheel.parent); package=Path(info['package'])
        if package.is_relative_to(args.ep_source_root.resolve()) or package.is_relative_to(G.SOURCE):raise ValueError('EP must be outside development checkout')
        if info['direct'].get('dir_info',{}).get('editable') or info['direct'].get('archive_info',{}).get('hashes',{}).get('sha256')!=args.ep_wheel_sha256:
            raise ValueError('noneditable qualified EP wheel required')
        if info['version']!=args.producer_pin['producer_version']:
            raise ValueError('EP installed version differs')
        payload=[n for n in wheel.namelist() if n.startswith('engineering_platform/') and not n.endswith('/')]
        if set(payload)!=set(expected):raise ValueError('EP source/wheel inventory differs')
        for name in payload:
            if wheel.read(name)!=expected[name] or (package.parent/name).read_bytes()!=expected[name]:
                raise ValueError('EP source/wheel/installed payload differs')
        installed={str(path.relative_to(package.parent)) for path in package.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
        if installed!=set(expected):raise ValueError('EP installed inventory differs')
        entries=[name for name in members if name.endswith('.dist-info/entry_points.txt')]
        if len(entries)!=1:raise ValueError('EP entrypoint ambiguity')
        parser=configparser.ConfigParser();parser.read_string(wheel.read(entries[0]).decode())
        if dict(parser['console_scripts'])!=manifest['project']['scripts'] or info['entries']!=manifest['project']['scripts']:
            raise ValueError('EP source/wheel/installed entrypoints differ')
        args.ep_package=package

        schema=wheel.read('engineering_platform/schemas/genesis-local-bootstrap-v1.schema.json')
        if sha256(schema).hexdigest()!=args.producer_pin['producer_schema_sha256']:
            raise ValueError('EP qualified schema differs')
        return {'version':info['version'],'payload_files_verified':len(payload),'wheel_sha256':args.ep_wheel_sha256,
                'source_revision':args.ep_source_revision,'source_tree':actual_tree,'source_payload_entrypoints_exact':True}


def apply_call(port, token, method, path, body=None):
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    request=Request('http://127.0.0.1:'+str(port)+path,method=method,
        data=canonical(body) if body is not None else None,
        headers={'Authorization':'Bearer '+token.read_text().strip(),
                 'X-Forge-Genesis-Apply-Audience':'synthetic-workspace','Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=35) as response:return response.status,json.loads(response.read())
    except HTTPError as error:
        try:return error.code,json.loads(error.read())
        finally:error.close()


def verify_b8r(rows, request, operation, documents, target, grant_id):
    """Compare actual owning registration rows with the committed declaration."""
    identity=documents['identity']
    expected_project=identity['project_id'];expected_repository=identity['repository_id']
    if any(len(rows[table])!=1 for table in ('ep_genesis_operations','ep_project_registrations','ep_repository_registrations','ep_local_repository_bindings')):
        raise ValueError('one original registered authority required')
    original=rows['ep_genesis_operations'][0]
    if (original['operation_id']!=request['operation_id'] or original['grant_id']!=grant_id
            or original['request_digest']!=sha256(canonical(request)).hexdigest()
            or json.loads(original['original_request'])!=request or original['state']!='COMPLETE'
            or original['project_id']!=expected_project or original['repository_id']!=expected_repository):
        raise ValueError('original EP operation/registration binding differs')
    project=rows['ep_project_registrations'][0];repository=rows['ep_repository_registrations'][0];binding=rows['ep_local_repository_bindings'][0]
    declaration=json.loads(request['bundle']['files']['.engineering-platform/repository.json']['utf8'])
    expected_surface={**declaration,'validation':{**declaration['validation'],'description':declaration['validation'].get('description')},
                      'requirements':{'host':{},'tools':{}},'integrations':{}}
    if (project['project_id']!=expected_project or project['status']!='ACTIVE'
            or json.loads(project['attachment_contract'])!={'schema_version':declaration['schema_version'],'authority_repository_id':identity['authority_repository_id']}
            or (repository['project_id'],repository['repository_id'],repository['authority_repository_id'],repository['role'])
            !=(expected_project,expected_repository,identity['authority_repository_id'],'authority')
            or json.loads(repository['attachment_contract'])!=expected_surface
            or (binding['project_id'],binding['repository_id'],binding['state'])!=(expected_project,expected_repository,'BOUND')
            or Path(binding['local_root'])!=target.resolve()):
        raise ValueError('committed B8R registration/declaration/physical binding differs')
    known=json.loads(original['evidence'])['known']
    if (known.get('commit_ref')!=operation['commit'] or known.get('tree')!=operation['tree']
            or known.get('committed_declaration_verified') is not True):
        raise ValueError('committed B8R operation evidence differs')
    return {'project_id':expected_project,'repository_id':expected_repository,'committed_registration_and_target_binding_verified':True}


def group_active(group):
    """A zombie is exited evidence, never a running worker or signal target."""
    listing=subprocess.check_output(['ps','-axo','pgid=,stat='],text=True,timeout=3)
    for line in listing.splitlines():
        parts=line.split()
        if len(parts)!=2:raise RuntimeError('process group state unavailable')
        if int(parts[0])==group and not parts[1].startswith(('Z','X')):return True
    return False


def require_worker_groups_exited(evidence):
    for value in evidence:
        for attempt in value['attempts']:
            group=attempt.get('process',{}).get('process_group')
            if group:
                try:os.killpg(group,0)
                except ProcessLookupError:continue
                except PermissionError:
                    if not group_active(group):continue
                    raise
                if group_active(group):raise RuntimeError('own EP worker group remains active or uncertain')


class EPServer:
    def __init__(self,args,root,output):
        self.args,self.root,self.output=args,root,output
        self.data=root/'s'; self.workspace=root/'w'; self.workspace.mkdir(mode=0o700)
        self.target=self.workspace/'r'
        self.env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
        self.env.update(PATH=str(args.ep_python.parent)+':'+str(args.ep_native/'bin')+':/usr/bin:/bin',
                        EP_MANAGED_CODEX_CLI_PREFIX=str(args.ep_native),PYTHONDONTWRITEBYTECODE='1')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.command_counter=0
        self.instance=self.command('server','init','--bind-host','127.0.0.1','--bind-port',str(self.port))['instance_id']
        self.command('genesis_cli','init')
        self.process=None;self.log=None

    def command(self,module,*arguments):
        command=[str(self.args.ep_python),'-I','-m','engineering_platform.'+module,*arguments,'--data-root',str(self.data)]
        if hasattr(self,'instance'):command+=['--expected-instance-id',self.instance]
        self.command_counter+=1
        case='ep-owner-'+str(self.command_counter)
        report,stdout,stderr=C.BINDING.CAPTURE.capture(command,case=case,output=self.output,cwd=self.root,env=self.env,expected=0)
        primary=None
        if report['primary_failure'] or not report['capture_complete']:
            primary=RuntimeError('own EP owner command failed: '+module)
            primary.capture_report=report
        try:
            C.BINDING.CAPTURE.retain(self.output/(case+'.capture.private.json'),canonical(report))
        except OSError as retention:
            if primary is None:primary=retention
            else:primary.add_note('EP command report retention failed: '+type(retention).__name__)
        if primary is not None:raise primary
        value=json.loads(stdout)
        if module=='genesis_cli' and arguments and arguments[0]=='issue' and 'credential' in value:
            # A successful credential-bearing stdout is a secret container.
            # Preserve its digest and redacted metadata, then remove only that
            # exact newly owned container; failed diagnostics remain private.
            raw_path=self.output/('private-'+case+'-0.log')
            if raw_path.read_bytes()!=stdout:raise RuntimeError('own credential capture changed')
            C.BINDING.CAPTURE.retain(self.output/(case+'.redacted.private.json'),canonical({
                'stdout_sha256':sha256(stdout).hexdigest(),'result':{k:v for k,v in value.items() if k!='credential'},'credential_container_removed':True}))
            raw_path.unlink()
        return value

    def issue(self,request):
        validator=self.root/'v.py'
        raw=self.args.external_validator.read_bytes()
        if sha256(raw).hexdigest()!=self.args.validator_digest:raise ValueError('original qualified external validator differs')
        private(validator,raw)
        config=self.root/'grant.private.json'
        private(config,dict(grant_id='r57-owner-genesis',issuance_id='r57-owner-issuance',consumer_id='forge-r57',principal='synthetic-r57-owner',
            target_name='r',workspace_root=str(self.workspace),validator_path=str(validator),request=request,ttl_seconds=3600))
        answer=self.command('genesis_cli','issue','--config',str(config))
        token=self.root/'ep-token.private';private(token,answer.pop('credential').encode())
        return answer,token

    def start(self):
        self.log=(self.output/'ep-server.private.log').open('ab');os.chmod(self.output/'ep-server.private.log',0o600)
        self.process=subprocess.Popen([str(self.args.ep_python),'-I','-m','engineering_platform.server','serve','--data-root',str(self.data),
            '--expected-instance-id',self.instance],cwd=self.root,env=self.env,stdout=self.log,stderr=self.log,start_new_session=True)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if os.waitid(os.P_PID,self.process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is not None:raise RuntimeError('own EP Server exited')
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1',self.port))==0:return
            time.sleep(.05)
        raise TimeoutError('own EP Server did not listen')

    def facts(self):
        with sqlite3.connect((self.data/'epdata.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            counts={table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in (
                'ep_genesis_operations','ep_project_registrations','ep_repository_registrations','ep_local_repository_bindings',
                'ep_submissions','ep_execution_runs','engineering_transactions')}
            operations=[json.loads(row[0]) for row in db.execute('SELECT evidence FROM ep_genesis_operations')]
            db.row_factory=sqlite3.Row
            rows={table:[dict(row) for row in db.execute('SELECT * FROM '+table)] for table in (
                'ep_genesis_operations','ep_project_registrations','ep_repository_registrations','ep_local_repository_bindings')}
        return counts,operations,rows

    def stop(self):
        if self.process is None:return
        process=self.process
        primary=None
        try:
            # Never reap the original Popen child before its whole session is
            # frozen/inventoried. Its unreaped PID prevents PGID reuse even
            # when the Server leader has already exited.
            os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            try:os.killpg(process.pid,signal.SIGSTOP)
            except ProcessLookupError:pass
            spec=spec_from_file_location('r57_verified_ep_process_identity',self.args.ep_package/'provider_process_identity.py')
            module=module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
            owned={};groups={process.pid}
            parent=module.capture_process_identity(process.pid,process.pid)
            if parent is not None:owned[parent.pid]=parent
            # Own signed producer ledger is diagnostic ownership evidence,
            # never PID-only authority. Missing/corrupt inventory stays red.
            _,evidence,_=self.facts()
            for operation in evidence:
                for attempt in operation['attempts']:
                    raw=attempt.get('process')
                    if raw:
                        identity=module.ProcessIdentity(**raw);groups.add(identity.process_group)
                        state=module.verify_process_identity(identity)
                        if state=='MISMATCH':raise RuntimeError('own recorded EP worker identity changed')
                        if state=='MATCH':
                            os.kill(identity.pid,signal.SIGSTOP);owned[identity.pid]=identity
            deadline=time.monotonic()+5
            while True:
                changed=False
                listing=subprocess.check_output(['ps','-axo','pid=,ppid=,pgid=,lstart=,comm='],text=True,timeout=3)
                for line in listing.splitlines():
                    parts=line.split(maxsplit=8)
                    if len(parts)!=9:continue
                    pid,ppid,group=map(int,parts[:3])
                    if pid in owned or (ppid not in owned and group!=process.pid):continue
                    birth=' '.join(parts[3:8])
                    identity=module.ProcessIdentity(pid,group,sha256(f'{pid}|{group}|{birth}'.encode()).hexdigest(),module._canonical_executable_identity(parts[8][:512]))
                    state=module.verify_process_identity(identity)
                    if state=='NOT_ACTIVE':continue
                    if state!='MATCH':raise RuntimeError('own descendant identity changed')
                    os.kill(pid,signal.SIGSTOP);owned[pid]=identity;groups.add(group);changed=True
                if not changed:break
                if time.monotonic()>=deadline:raise TimeoutError('own descendant freeze did not stabilize')
            for identity in reversed(list(owned.values())):
                if identity.pid==process.pid:continue
                state=module.verify_process_identity(identity)
                if state=='MATCH':os.kill(identity.pid,signal.SIGKILL)
                elif state!='NOT_ACTIVE':raise RuntimeError('own descendant identity changed before stop')
        except BaseException as error:primary=error
        finally:
            # This exact still-unreaped child's original PGID remains owned,
            # including an already-exited leader and inherited-pipe children.
            try:
                os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                except PermissionError:
                    # Darwin can refuse signaling a group containing only
                    # already-exited zombies. Never waive a live/unknown group.
                    if group_active(process.pid):raise
                process.wait(timeout=15)
                if 'groups' in locals():
                    deadline=time.monotonic()+5
                    for group in groups:
                        while True:
                            try:os.killpg(group,0)
                            except ProcessLookupError:break
                            except PermissionError:
                                if not group_active(group):break
                                raise
                            if not group_active(group):break
                            if time.monotonic()>=deadline:raise RuntimeError('own process group active or uncertain after stop')
                            time.sleep(.05)
            except BaseException as stop_error:
                if primary is None:primary=stop_error
                else:primary.add_note('own Server stop incomplete: '+type(stop_error).__name__)
            self.process=None
            if self.log is not None:self.log.close();self.log=None
        if primary is not None:raise primary


def run(args):
    args.output_dir.mkdir(mode=0o700)
    report={'qualification':'R57_FIRST_SMALL_REAL_INSTALLED_CHAIN','result':'FAIL','cleanup':False,'cases':[],
            'scope':'SYNTHETIC_NEW_LOCAL_DOCUMENT_ONLY; NOT_PROJECT_READINESS; NOT_FULL_MATRIX',
            'human_decisions':'SYNTHETIC_TECHNICAL_NOT_REAL_OWNER_APPROVAL'}
    primary=None;ep=None;root=args.scratch_root
    try:
        pin=probe(args.python,'import json;from forge.genesis_apply_peer import QUALIFIED_PRODUCER;print(json.dumps(QUALIFIED_PRODUCER))',args.wheel.parent)
        if not isinstance(pin,dict) or pin.get('producer_revision')!=args.ep_source_revision or pin.get('producer_tree')!=args.ep_source_tree:
            raise ValueError('actual qualified producer handoff/pin required before test effects')
        args.producer_pin=pin
        report['forge']=C.BINDING.installed_binding(args.python,args.wheel,args.source_revision)
        report['ep']=ep_payload(args)
        if root.parent!=Path('/private/tmp') or not root.name.isalnum() or len(root.name)>5:
            raise ValueError('exclusive finite short synthetic root required')
        root.mkdir(mode=0o700)
        private(root/'.r57-owner.json',dict(assignment='L3-GENESIS-EP-APPLY-COORDINATOR-V1-20261016',source=args.source_revision,uid=os.getuid(),identity=[root.stat().st_dev,root.stat().st_ino]))
        ep=EPServer(args,root,args.output_dir)
        counter=0
        def command(arguments,cwd):
            nonlocal counter
            counter+=1
            return G.capture_command(args.python,arguments,cwd,args.output_dir,'r57-setup-'+str(counter))
        forge=root/'f';setup=command([str(HERE/'proposal_content_fixture.py'),str(forge)],root)
        data=['--data-root',str(forge/'runtime')];expiry=(datetime.now(UTC)+timedelta(hours=1)).isoformat()
        command(['-m','forge.proposal_content_cli',*data,'init'],forge)
        command(['-m','forge.proposal_content_cli',*data,'issue','--principal-id',setup['human_principal_id'],'--proposal-principal-id','synthetic-service',
                 '--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--permission','READ','--permission','DECIDE','--role','BUSINESS','--role','ARCHITECTURE',
                 '--expires-at',expiry,'--token-file',str(forge/'decide.private')],forge)
        with C.server(args.python,forge,args.output_dir) as (port,forge_pid,_):
            original=json.loads(subprocess.check_output(['git','-C',str(G.SOURCE),'show',args.source_revision+':examples/project-bootstrap/authority-input.json']))
            status,proposal=C.call(port,forge/'prepare.private','POST','/v1/onboarding/plans',dict(contract_version='forge-project-proposal-http/v1',
                instance_id=setup['instance_id'],dossier_id='synthetic-dossier',operation_id='original-proposal',proposal_kind='pb-render/1.0',input=original))
            assert status==200,(status,proposal)
            status,content=C.call(port,forge/'decide.private','GET','/v1/project-proposal-decisions/proposals/'+proposal['plan_id']+'?dossier_id=synthetic-dossier');assert status==200
            for role in ('BUSINESS','ARCHITECTURE'):
                status,content=C.call(port,forge/'decide.private','POST','/v1/project-proposal-decisions/decisions',C.request_for(content,role,'content-'+role.lower()));assert status==200
            scope=['--proposal-principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier','--source-plan-id',proposal['plan_id'],'--expires-at',expiry]
            command(['-m','forge.genesis_bootstrap_cli',*data,'init'],forge)
            command(['-m','forge.genesis_bootstrap_cli',*data,'issue','--principal-id','synthetic-service',*scope,'--permission','READ','--permission','PREPARE','--token-file',str(forge/'bootstrap.private')],forge)
            effects=['CREATE_NEW_TARGET','INITIALIZE_LOCAL_GIT','WRITE_EXACT_MANIFEST_FILES','RUN_EXTERNALLY_PINNED_VALIDATION','CREATE_LOCAL_COMMIT','REGISTER_COMMITTED_AUTHORITY_ATTACHMENT']
            request=dict(contract_version=G.CONTRACT,instance_id=setup['instance_id'],dossier_id='synthetic-dossier',operation_id='original-plan',
                source_plan_id=proposal['plan_id'],source_subject=content['subject'],expected_content_revision=2,target=dict(ep_instance_id=ep.instance,placement_ref='owner-placement',target_ref='owner-target'),
                effects=effects,expires_at=expiry,expected_plan_revision=0,previous_plan_id=None,blocking_open_points=[])
            status,view=C.call(port,forge/'bootstrap.private','POST','/v1/genesis-bootstrap/plans',request);assert status==200,(status,view)
            plan=view['plan'];exact=forge/'exact-plans.private';private(exact,[dict(plan_id=plan['plan_id'],plan_digest=plan['plan_digest'])])
            command(['-m','forge.genesis_bootstrap_cli',*data,'issue','--principal-id',setup['human_principal_id'],*scope,'--permission','READ','--permission','DECIDE_EFFECT','--exact-plans-file',str(exact),'--token-file',str(forge/'effect.private')],forge)
            decision=dict(contract_version=G.CONTRACT,instance_id=setup['instance_id'],dossier_id='synthetic-dossier',operation_id='original-effect-decision',plan_id=plan['plan_id'],plan_digest=plan['plan_digest'],
                purpose='GENESIS_BOOTSTRAP_EFFECT_ONLY/1.0',decision='APPROVE_EFFECT',reason='Synthetic exact technical effect qualification only.',expected_decision_revision=0,previous_decision_id=None)
            status,view=C.call(port,forge/'effect.private','POST','/v1/genesis-bootstrap/decisions',decision);assert status==200,(status,view)
            decision=view['original_decision'];documents=plan['documents']
            ep_request=dict(contract_version='1.0',operation_id='original-apply',target_ref=plan['target']['target_ref'],
                effect_plan_binding=dict(plan_id=plan['plan_id'],plan_revision=plan['plan_revision'],plan_digest=plan['plan_digest'],decision_id=decision['decision_id'],decision_digest=decision['decision_digest'],
                    proposal_id=proposal['plan_id'],proposal_digest=plan['source_subject']['result_digest'],source_instance_id=setup['instance_id'],source_actor_id=decision['principal_id'],context_id='synthetic-dossier'),
                bundle=dict(contract_version='pb-render/1.0',kind='RENDERED_PROPOSAL_EXAMPLE',files={r['path']:dict(sha256=r['sha256'],utf8=r['content']) for r in documents['files']}))
            args.validator_digest=documents['validation']['validator_sha256']
            ep_grant,ep_token=ep.issue(ep_request);ep.start()
            command(['-m','forge.genesis_apply_cli',*data,'init'],forge)
            config={**pin,'pairing_id':'original-owner-pair','endpoint':'http://127.0.0.1:'+str(ep.port),
                'binding':dict(instance_id=ep.instance,host_id=sha256((os.uname().nodename+':'+str(os.geteuid())).encode()).hexdigest(),consumer_id='forge-r57',principal='synthetic-r57-owner',operation_id='original-apply'),
                'ep_grant_id':ep_grant['grant_id'],'expires_at':ep_grant['expires_at'],'plan_id':plan['plan_id'],'plan_digest':plan['plan_digest'],
                'decision_id':decision['decision_id'],'decision_digest':decision['decision_digest'],'placement_ref':'owner-placement','target_ref':'owner-target',
                'request_digest':sha256(canonical(ep_request)).hexdigest(),'input_digest':plan['source_subject']['input_digest']}
            config_path=forge/'peer-config.private';private(config_path,config)
            command(['-m','forge.genesis_apply_cli',*data,'bind-peer','--config-file',str(config_path),'--credential-file',str(ep_token)],forge)
            command(['-m','forge.genesis_apply_cli',*data,'issue','--principal-id',setup['human_principal_id'],*scope,'--permission','READ','--permission','REQUEST_APPLY','--permission','RESUME','--exact-plans-file',str(exact),'--token-file',str(forge/'apply.private')],forge)
            body=dict(contract_version=CONTRACT,instance_id=setup['instance_id'],dossier_id='synthetic-dossier',operation_id='original-apply',plan_id=plan['plan_id'],plan_digest=plan['plan_digest'],decision_id=decision['decision_id'],decision_digest=decision['decision_digest'],pairing_id='original-owner-pair')
            try:
                status,result=apply_call(port,forge/'apply.private','POST','/v1/genesis-apply/operations',body)
            except (OSError,TimeoutError) as lost:
                status,result=503,{'transport_failure':type(lost).__name__}
            report['initial_apply_status']=status
            deadline=time.monotonic()+300
            reads=0
            # Only bounded authenticated original GETs follow uncertainty or
            # in-progress evidence. No retry POST and no inferred completion.
            while status!=200 or result['state']!='COMPLETE':
                if reads>=40 or time.monotonic()>=deadline:raise TimeoutError('original EP operation did not prove completion')
                if status not in (200,503):raise RuntimeError('original operation refused')
                time.sleep(5);reads+=1
                status,result=apply_call(port,forge/'apply.private','GET','/v1/genesis-apply/operations/original-apply?dossier_id=synthetic-dossier')
                if status==200 and result['state'] in ('PARTIAL','EFFECT_UNCERTAIN'):
                    raise RuntimeError('own EP result requires explicit recovery, not automatic resume')
            report['bounded_original_reads']=reads
            from jsonschema import Draft202012Validator
            schema=json.loads(subprocess.check_output([str(args.python),'-I','-c',"from importlib.resources import files;print(files('forge').joinpath('api/genesis-apply-v1.json').read_text())"],cwd=root))
            Draft202012Validator(schema).validate(result)
            operation=result['original_ep_operation'];assert result['project_readiness']=='NOT_ASSESSED' and result['mission']=='NOT_REQUESTED'
            status,replay=apply_call(port,forge/'apply.private','POST','/v1/genesis-apply/operations',body);assert status==200
            assert replay['original_ep_operation']['commit']==operation['commit'] and replay['explicit_attempts']==1
            counts,evidence,registered_rows=ep.facts();assert all(counts[t]==1 for t in ('ep_genesis_operations','ep_project_registrations','ep_repository_registrations','ep_local_repository_bindings'))
            assert all(counts[t]==0 for t in ('ep_submissions','ep_execution_runs','engineering_transactions'))
            git=lambda *a:subprocess.check_output(['/usr/bin/git','-C',str(ep.target),*a],timeout=20)
            assert git('rev-parse','HEAD').decode().strip()==operation['commit']
            assert git('rev-parse','HEAD^{tree}').decode().strip()==operation['tree']
            assert len(git('rev-list','--all').splitlines())==1
            for row in documents['files']:
                assert git('show','HEAD:'+row['path'])==row['content'].encode()
                assert git('ls-tree','HEAD','--',row['path']).startswith(b'100644 blob ')
            b8r=verify_b8r(registered_rows,ep_request,operation,documents,ep.target,ep_grant['grant_id'])
            assert operation['validator_sha256']==documents['validation']['validator_sha256']==sha256(args.external_validator.read_bytes()).hexdigest()
            assert operation['validation']['artifacts']==37 and operation['validation']['manifest_digest']==documents['manifest_digest']
            assert len(evidence)==1 and 'VALIDATE_DOCS' in evidence[0]['completed_steps'] and 'REGISTER_AND_ATTACH' in evidence[0]['completed_steps']
            report.update(cases=['actual-r52-r54-r56-original-http-chain','separate-test-owner-issued-ep-grant','actual-forge-to-ep-post-get',
                'independent-37-committed-byte-and-mode-readback','one-commit-tree-trusted-validator-and-b8r','same-original-replay-no-second-admission'],
                operation_id=operation['operation_id'],commit=operation['commit'],tree=operation['tree'],ep_counts=counts,b8r=b8r,explicit_attempts=replay['explicit_attempts'])
        report['chain_assertions']='PASS'
    except BaseException as error:
        primary=error;report['failure']={'category':type(error).__name__}
        if hasattr(error,'capture_report'):report['failure']['command_outcome']=error.capture_report
    finally:
        try:
            if ep is not None:ep.stop()
            if root.exists():
                # Preserve failures, scratch and credentials for safe owning
                # recovery; successful cleanup is exclusive own-root only.
                if primary is None:
                    marker=json.loads((root/'.r57-owner.json').read_bytes());info=root.stat()
                    if marker['uid']!=os.getuid() or marker['identity']!=[info.st_dev,info.st_ino]:raise RuntimeError('own scratch identity changed')
                    require_worker_groups_exited(evidence)
                    shutil.rmtree(root);report['cleanup']=True
            else:report['cleanup']=True
        except BaseException as cleanup:
            report['cleanup_failure']={'category':type(cleanup).__name__}
            if primary is None:primary=cleanup
            else:primary.add_note('own cleanup failed: '+type(cleanup).__name__)
        report['result']='PASS' if primary is None and report['cleanup'] else 'FAIL'
        try:private(args.output_dir/'first-real-installed-chain.public.json',report)
        except OSError as retention:
            if primary is None:primary=retention
            else:primary.add_note('receipt retention failed: '+type(retention).__name__)
    if primary is not None:raise primary
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('python','wheel','ep-python','ep-wheel','ep-native','external-validator','ep-source-root','output-dir','scratch-root'):
        p.add_argument('--'+field,type=Path,required=True)
    for field in ('source-revision','ep-source-revision','ep-source-tree','ep-wheel-sha256'):
        p.add_argument('--'+field,required=True)
    args=p.parse_args();print(json.dumps(run(args),sort_keys=True))


if __name__=='__main__':main()
