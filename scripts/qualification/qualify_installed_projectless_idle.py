"""Installed HTTP/restart proof; only external OS/keychain/Codex fixtures substituted."""
import argparse
from hashlib import sha256
from importlib.util import spec_from_file_location, module_from_spec
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SOURCE=Path(__file__).resolve().parents[2]
TOKEN='synthetic-installation-only-token'
ADMIN='synthetic-forge-server-token'


def child(root,port):
    from forge.secure_store import SecretState
    from forge.server_runtime import ForgeServerRuntime
    # External credential fixture, no actual Keychain read or write.
    with patch('forge.installation_pairing.MacOSKeychainSecureStoreAdapter.resolve',return_value=(SecretState.RESOLVABLE,TOKEN)):
        app=ForgeServerRuntime(data_root=root,credential_file=root/'server-credential',host='127.0.0.1',port=port,tick_interval=.05)
        app.serve_forever()


def run(args):
    spec=spec_from_file_location('projectless_installed_utils',SOURCE/'scripts/qualification/qualify_installed_http_successor.py')
    utils=module_from_spec(spec);spec.loader.exec_module(utils)
    artifact=utils._installed_wheel(args.wheel,source_revision=args.source_revision,verify_source=True)
    from forge.ep_simulator import EpSimulatorState, EpSimulatorServer
    from forge.runtime import RuntimeBootstrap
    from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
    from forge.provider_security import (PlanningProviderSecurityService,ProviderAuthenticationMode,
        CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,CODEX_CLI_CHATGPT_SESSION_TYPE)
    from forge.provider_context import ProviderExecutionContextService
    from forge.installation_pairing import InstallationPairingService
    from forge.secure_store import SecretState
    output=args.output_dir.resolve();output.mkdir(mode=0o700)
    receipt={'qualification':'PROJECTLESS_INSTALLED_HTTP_IDLE_V1','source_revision':args.source_revision,
             'artifact':artifact,'result':'FAIL','cases':[],'cleanup':False,
             'limits':'Synthetic external Codex login/OS identity/Keychain; actual installed Forge scheduler, canonical storage, authenticated HTTP and separate Server OS restart. EP simulator only; no live installer, VM or real credentials.'}
    try:
        with TemporaryDirectory(prefix='forge-r58-') as scratch:
            base=Path(scratch).resolve();root=base/'runtime'
            db=RuntimeBootstrap(data_root=root,forge_version='qualification').open()
            identity=NamedOperatorIdentity('synthetic-projectless-operator',os.getuid())
            operators=InstallationOperatorService(db,lambda:identity);context=operators.first_bind()
            executable=base/'codex';executable.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo "codex-cli 0.153.4"; exit 0; fi\nif [ "$1" = "login" ] && [ "$2" = "status" ]; then echo "Logged in using ChatGPT"; exit 0; fi\nexit 7\n');executable.chmod(0o700)
            class Store:
                def status(self,reference):return SecretState.RESOLVABLE
            PlanningProviderSecurityService(db,Store(),operators).configure(configuration_id='synthetic-codex',provider_id='codex-chatgpt-session',operator_context=context,
                authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
                external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,executable_path=str(executable),adapter_version='1.0',timeout_seconds=30,
                input_token_bound=64000,context_token_bound=128000,output_token_bound=16000)
            instance=db.runtime_identity.runtime_id;db.close()
            home=base/'provider-home';home.mkdir();config=base/'provider-config';config.mkdir()
            ProviderExecutionContextService(root).configure(provider_id='codex-chatgpt-session',provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
                executable_path=str(executable),provider_home=str(home),provider_config_home=str(config))
            credential=root/'server-credential';credential.write_text(ADMIN);credential.chmod(0o600)
            state=EpSimulatorState(bearer_token=TOKEN)
            ep=EpSimulatorServer(state);original=ep.server.RequestHandlerClass;reads=[]
            class Handler(original):
                def do_GET(self):
                    if self.path!='/v1/installation-compatibility':return super().do_GET()
                    if self.headers.get('Authorization')!='Bearer '+TOKEN or self.headers.get('EP-Instance-ID')!='synthetic-installation-ep' or self.headers.get('Forge-Instance-ID')!=instance:
                        return self._error(401,'AUTHENTICATION_REQUIRED')
                    reads.append('installation')
                    value=dict(contract_version='1.0',instance={'id':'synthetic-installation-ep'},producer={'id':'engineering-platform','version':'synthetic'},
                        authentication=dict(binding_id='installation',ep_instance_id='synthetic-installation-ep',forge_instance_id=instance,consumer_id='synthetic-consumer',purpose='INSTALLATION_READBACK'),
                        authority=dict(installation_readback=True,project_access=False,submission=False,execution=False,governance=False))
                    raw=json.dumps(value).encode();self.send_response(200);self.send_header('EP-Server-Instance','synthetic-installation-ep');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            ep.server.RequestHandlerClass=Handler
            with ep:
                with patch('forge.operator_identity.MacOSGeneratedUIDIdentityAdapter.resolve',return_value=identity):
                    InstallationPairingService(root).configure(operation_id='synthetic-installation',binding_id='installation',endpoint=ep.base_url,
                        ep_instance_id='synthetic-installation-ep',consumer_id='synthetic-consumer',credential_reference='keychain://synthetic/installation',allow_loopback_http=True)
                for case in ('initial','restart','uncertain-work'):
                    if case=='uncertain-work':
                        db=RuntimeBootstrap(data_root=root,forge_version='qualification').open()
                        db.save_dispatcher_state(status='ACTIVE',mission_sequence=('synthetic-uncertain',),active_mission_id='synthetic-uncertain');db.close()
                    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
                    log=output/(case+'.private.log')
                    with log.open('xb') as stream:
                        process=subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve()),'--child','--root',str(root),'--port',str(port)],cwd=base,stdout=stream,stderr=stream)
                        try:
                            deadline=time.monotonic()+15;body=None
                            while time.monotonic()<deadline:
                                assert process.poll() is None,'server exited before readback'
                                try:
                                    request=Request(f'http://127.0.0.1:{port}/v1/readiness/installation',headers={'Authorization':'Bearer '+ADMIN})
                                    try:
                                        with urlopen(request,timeout=2) as response:body=json.load(response)
                                    except HTTPError as error:
                                        with error:body=json.load(error)
                                    wanted='NOT_READY' if case=='uncertain-work' else 'IDLE'
                                    if body['scheduler']['state']==wanted:break
                                except OSError:pass
                                time.sleep(.05)
                            assert body is not None and body['scheduler']['state']==wanted
                            assert body['provider']['ready'] and body['component_connected']
                            assert body['service_ready']==(case!='uncertain-work') and body['ready']==(case!='uncertain-work')
                            assert body['execution_ready'] is False and body['project_authorized'] is False
                            receipt['cases'].append({'case':case,'scheduler':wanted,'service_ready':body['service_ready'],'component_connected':body['component_connected'],'pid':process.pid})
                        finally:
                            process.terminate()
                            try:process.wait(timeout=8)
                            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3);raise
                    assert process.returncode==0
                with sqlite3.connect(root/'forge.db') as db:
                    for table in ('mission_state','mission_id_allocations','execution_host_peer_configuration','scheduler_submissions'):
                        assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0
                assert reads
                receipt['installation_http_reads']=len(reads)
            receipt['result']='PASS'
        receipt['cleanup']=True
    finally:
        (output/'installed-projectless-idle.public.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'result':receipt['result'],'cases':len(receipt['cases']),'cleanup':receipt['cleanup']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--child',action='store_true');p.add_argument('--root',type=Path);p.add_argument('--port',type=int)
    p.add_argument('--wheel',type=Path);p.add_argument('--source-revision');p.add_argument('--output-dir',type=Path)
    args=p.parse_args()
    if args.child:child(args.root,args.port)
    else:run(args)
