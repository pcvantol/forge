"""Scoped HTTP hold producer: actual product authority/storage/runtime, external fixtures only."""
from contextlib import ExitStack,contextmanager,closing
from datetime import UTC,datetime,timedelta
from hashlib import sha256
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from threading import Thread
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import argparse
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

_SOURCE=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('serial_fixture',_SOURCE/'scripts/qualification/qualify_installed_worklist_activation.py')
serial=module_from_spec(spec);spec.loader.exec_module(serial);utils=serial.utils
from forge.approved_worklist import ApprovedWorklistService,candidate_source
from forge.lifecycle import RecommendationLifecycleStore
from forge.server_runtime import ForgeServerRuntime,existing_instance
from forge.workspace_worklist_control_grant import WorkspaceWorklistControlGrant,main as grant_main
from forge.workspace_worklist_grant import WorkspaceWorklistGrant
from forge.worklist_control import REQUEST
import forge
from jsonschema import Draft202012Validator,FormatChecker

_SCHEMA=json.loads((Path(forge.__file__).parent/'api'/'workspace-worklist-control-v1.json').read_text())
_VALIDATOR=Draft202012Validator(_SCHEMA,format_checker=FormatChecker())


def request(port,token,method,path,body=None):
    data=None if body is None else json.dumps(body).encode()
    req=Request(f'http://127.0.0.1:{port}'+path,data=data,method=method,
        headers={'Authorization':'Bearer '+token.read_text().strip(),'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=10) as response:
            document=json.loads(response.read())
            if path.startswith('/v1/workset-controls/') and response.status==200:
                _VALIDATOR.validate(document)
                if body is not None:_VALIDATOR.validate(body)
            return response.status,document
    except HTTPError as error:
        try:return error.code,json.loads(error.read())
        finally:error.close()

@contextmanager
def http_owner(root,*,pause_intent=False):
    with ExitStack() as stack:
        runtime=utils._open(root,stack);runtime.close()
        if pause_intent:
            def identity():
                with closing(sqlite3.connect((root/'runtime'/'forge.db').resolve().as_uri()+'?mode=ro',uri=True)) as db:
                    value=json.loads(db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('serial-set',)).fetchone()[0])
                if any(o['state']=='PENDING' for o in value.get('control_operations',{}).values()):
                    (root/'intent-boundary.ready.private').write_text(str(os.getpid()));time.sleep(20)
                return utils.fixture.IDENTITY
            stack.enter_context(patch.object(utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity))
        admin=root/'admin.private';
        if not admin.exists():admin.write_text('a'*48);admin.chmod(0o600)
        server=ForgeServerRuntime(data_root=root/'runtime',credential_file=admin,host='127.0.0.1',port=0,provider_id=utils.fixture.PROVIDER)
        thread=Thread(target=server.server.serve_forever,daemon=True);thread.start()
        stack.callback(server.server.server_close);stack.callback(thread.join,3);stack.callback(server.server.shutdown)
        yield server.server.server_address[1]


def provision(root,*,bob=True,expiry=None):
    expiry=expiry or (datetime.now(UTC)+timedelta(hours=1)).isoformat()
    with http_owner(root) as port:
        instance=existing_instance(root/'runtime')
        grant=WorkspaceWorklistControlGrant(root/'runtime',instance.instance_id)
        result=grant.issue(principal_id='alice',workset_ids=('serial-set',),expires_at=expiry,token_path=root/'alice.private')
        if bob:
            with ExitStack() as stack:
                runtime=utils._open(root,stack)
                with RecommendationLifecycleStore(candidate_source(root/'runtime')) as lifecycle:
                    service=ApprovedWorklistService(runtime,lifecycle)
                    original=service._get('serial-set')['definition'];other=json.loads(json.dumps(original));other['workset_id']='bob-set'
                    service.propose(other)
            grant.issue(principal_id='bob',workset_ids=('bob-set',),expires_at=expiry,token_path=root/'bob.private')
        WorkspaceWorklistGrant(root/'runtime',instance.instance_id).issue(principal_id='alice',workset_ids=('serial-set',),expires_at=expiry,token_path=root/'read.private')
    return result


def body(current,*,op='hold-1',intent='hold',hold=None):
    return {'contract_version':REQUEST,'operation_id':op,'intent':intent,
            'instance_id':current['instance_id'],'workset_id':current['workset_id'],
            'definition_revision':current['definition_revision'],'expected_revision':current['workset_revision'],
            'hold_operation_id':None if hold is None else hold['operation_id'],
            'expected_hold_revision':None if hold is None else hold['control_revision'],'reason_code':'USER_REQUEST'}


def command_phase(root,phase):
    with http_owner(root,pause_intent=phase=='crash-intent') as port:
        token=root/'alice.private';path='/v1/workset-controls/serial-set'
        if phase=='race-command':
            (root/'race-hold.ready.private').write_text(str(os.getpid()))
            deadline=time.monotonic()+12
            while not (root/'race-go.private').exists():
                if time.monotonic()>deadline:raise AssertionError('race release expired')
                time.sleep(0.01)
            status,response=request(port,token,'POST',path+'/commands',utils.fixture._read(root/'hold-request.private.json'))
            return {'status':status,'response':response,'pid':os.getpid()}
        status,read=request(port,token,'GET',path);assert status==200
        if phase=='read':return read
        if phase=='lost-response':
            payload=body(read['current']);utils.fixture._write(root/'hold-request.private.json',payload)
            raw=json.dumps(payload).encode();sock=socket.create_connection(('127.0.0.1',port),timeout=10)
            auth=token.read_text().strip()
            headers=(f'POST {path}/commands HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {auth}\r\nContent-Type: application/json\r\nContent-Length: {len(raw)}\r\nConnection: close\r\n\r\n').encode()
            try:
                sock.sendall(headers+raw);received=b''
                while b'\r\n\r\n' not in received:
                    chunk=sock.recv(1);assert chunk;received+=chunk
                assert received.startswith(b'HTTP/1.0 200') or received.startswith(b'HTTP/1.1 200')
            finally:sock.close()
            return {'response_body_lost':True,'pid':os.getpid()}
        if phase=='recover-read':
            status,response=request(port,token,'GET',path+'/commands/hold-1')
            return {'status':status,'response':response,'pid':os.getpid()}
        if phase=='hold':payload=body(read['current']);utils.fixture._write(root/'hold-request.private.json',payload)
        elif phase=='unhold':payload=body(read['current'],op='unhold-1',intent='unhold',hold=read['current']['hold']);utils.fixture._write(root/'unhold-request.private.json',payload)
        elif phase in {'replay','crash-intent'}:payload=utils.fixture._read(root/'hold-request.private.json')
        else:raise ValueError('unknown command phase')
        status,response=request(port,token,'POST',path+'/commands',payload)
        return {'status':status,'response':response,'pid':os.getpid()}


def source_flow(root,*,phase_runner=None,failure_control=False):
    phase_runner=phase_runner or (lambda root,phase:command_phase(root,phase))
    root.mkdir();target,baseline,manifest=utils._effect_target_fixture(root,'effect-read-only')
    simulator=utils.EpSimulatorState(project_id=utils.PROJECT,repository_id=utils.fixture.SOURCE.repository_id,
        repository_identity=utils.fixture.SOURCE.github_repository,consumer_id=utils.CONSUMER,instance_id=utils.INSTANCE,
        bearer_token=utils.TOKEN,scenario=utils.EpSimulatorScenario(name='effect-read-only',effect_declaration_supported=True))
    server=utils.EpSimulatorServer(simulator);server.__enter__();endpoint=server.base_url
    def complete():
        sid=simulator.submission_ids()[-1];payload=simulator.submitted_payload(sid)
        current=utils._effect_target_snapshot(target);source_manifest={path:current[path] for path in manifest}
        revision,observation=utils._execute_effect_fixture(root,target,baseline,payload)
        simulator.complete(sid,delivery_revision=revision)
        readback,artifact=simulator.terminal_documents(sid)
        readback,result,terminal=utils.qualified_effect_result(payload,readback,artifact,source_manifest=source_manifest)
        simulator.seed_terminal(sid,readback,terminal);simulator.seed_effect_result(sid,result)
    records=[]
    try:
        serial._phase(root,'effect-read-only','setup',endpoint);provision(root)
        before=serial._phase(root,'effect-read-only','read',endpoint)
        held=phase_runner(root,'hold');assert held['status']==200,held;receipt=held['response']['original_receipt']
        assert receipt['effect']['held'] and receipt['effect']['admitted_mission_ids']==[]
        if failure_control:
            grant=WorkspaceWorklistControlGrant(root/'runtime',before['runtime_id'])
            with http_owner(root):
                r=grant._records()[0];grant.revoke(r['grant_id'])
        with http_owner(root) as port:
            token=root/'alice.private';path='/v1/workset-controls/serial-set'
            status,replayed=request(port,token,'POST',path+'/commands',utils.fixture._read(root/'hold-request.private.json'))
            assert status==200,'positive control grant replay gate failed'
            assert replayed['original_receipt']==receipt and replayed['recorded'] is False
            status,conflict=request(port,token,'POST',path+'/commands',{**utils.fixture._read(root/'hold-request.private.json'),'reason_code':'TEMPORARY_WAIT'})
            assert status==409;records.append({'case':'same-id-different-payload','status':status})
            instance=existing_instance(root/'runtime');grant=WorkspaceWorklistControlGrant(root/'runtime',instance.instance_id)
            grant.issue(principal_id='observer',workset_ids=('serial-set',),expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=root/'observer.private')
            status,value=request(port,root/'observer.private','GET',path+'/commands/hold-1');assert status==403
            records.append({'case':'same-workset-foreign-principal-operation-denied','status':status})
            for token_name,foreign in [('bob.private',path),('read.private',path),('alice.private','/v1/workset-controls/bob-set')]:
                status,_=request(port,root/token_name,'POST',foreign+'/commands',utils.fixture._read(root/'hold-request.private.json'))
                assert status==403;records.append({'case':'scope-'+token_name+'-'+foreign.rsplit('/',1)[-1],'status':status})
            status,current=request(port,token,'GET',path);assert status==200
            for name,payload in [('stale',{**body(current['current'],op='stale'),'expected_revision':1}),
                                  ('wrong-instance',{**body(current['current'],op='instance'),'instance_id':'foreign-instance'}),
                                  ('wrong-definition',{**body(current['current'],op='definition'),'definition_revision':'sha256:'+'0'*64}),
                                  ('malformed-role',{**body(current['current'],op='role'),'actor':'business_owner'})]:
                status,_=request(port,token,'POST',path+'/commands',payload)
                assert status==({'wrong-instance':403,'malformed-role':400}.get(name,409));records.append({'case':name,'status':status})
            for forbidden in ['/v1/status','/v1/worksets','/v1/reviews','/v1/projects','/v1/worksets/serial-set/arm']:
                status,_=request(port,token,'GET' if forbidden!='/v1/worksets/serial-set/arm' else 'POST',forbidden,{})
                assert status==403;records.append({'case':'noncontrol-route-'+forbidden.rsplit('/',1)[-1],'status':status})
            status,bob=request(port,root/'bob.private','GET','/v1/workset-controls/bob-set');assert status==200
            status,_=request(port,root/'bob.private','POST','/v1/workset-controls/bob-set/commands',body(bob['current'],op='bob-hold'));assert status==200
            status,bob_held=request(port,root/'bob.private','GET','/v1/workset-controls/bob-set');assert status==200
            with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                original=db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('bob-set',)).fetchone()[0]
            for fault in ('repeated-request-bool','current-hold-revision-bool','current-hold-reason-malformed'):
                value=json.loads(original);entry=value['control_operations']['bob-hold']
                if fault=='repeated-request-bool':
                    assert entry['request']['expected_revision']==1
                    entry['receipt']['request']['expected_revision']=True
                    entry['receipt_digest']=utils.canonical_digest(entry['receipt'])
                elif fault=='current-hold-revision-bool':
                    assert value['control_revision']==1;value['operator_hold']['control_revision']=True
                else:value['operator_hold']['reason_code']=[]
                with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                    with db:db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?',(json.dumps(value,sort_keys=True),'bob-set'))
                try:
                    if fault=='repeated-request-bool':
                        status,_=request(port,root/'bob.private','GET','/v1/workset-controls/bob-set/commands/bob-hold');assert status==503
                        status,_=request(port,root/'bob.private','POST','/v1/workset-controls/bob-set/commands',entry['request']);assert status==503
                    else:
                        status,_=request(port,root/'bob.private','GET','/v1/workset-controls/bob-set');assert status==503
                        status,_=request(port,root/'bob.private','POST','/v1/workset-controls/bob-set/commands',body(bob_held['current'],op='malformed-current-unhold',intent='unhold',hold=bob_held['current']['hold']));assert status==503
                    with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                        assert json.loads(db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('bob-set',)).fetchone()[0])==value
                finally:
                    with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                        with db:db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?',(original,'bob-set'))
            records.append({'case':'repeated-request-and-current-hold-strict-types','variants':3,'get_and_command':503,'canonical_mutation':False})
            status,bob_unheld=request(port,root/'bob.private','POST','/v1/workset-controls/bob-set/commands',body(bob_held['current'],op='bob-unhold',intent='unhold',hold=bob_held['current']['hold']))
            assert status==200 and not bob_unheld['original_receipt']['effect']['held']
            assert all(not i['released'] for i in bob_unheld['current_readback']['worklist']['items'])
            status,alice_held=request(port,token,'GET',path);assert status==200 and alice_held['current']['held']
            records.append({'case':'two-principal-hold-unhold-no-implicit-arm','other_held':True,'bob_released':False})

            db=root/'runtime'/'forge.db';before_bytes=sha256(db.read_bytes()).hexdigest()
            for method,route in [('GET',path),('GET',path+'/commands/hold-1'),('GET',path+'/commands/unknown')]:
                status,value=request(port,token,method,route);assert status in {200,404}
            assert before_bytes==sha256(db.read_bytes()).hexdigest();records.append({'case':'readonly-status-operation','database_changed':False})
        blocked=serial._phase(root,'effect-read-only','tick',endpoint);assert blocked['allocations']==blocked['provider_invocations']==0
        records.append({'case':'held-future-not-admitted','allocations':0,'provider_invocations':0})
        unheld=phase_runner(root,'unhold');assert unheld['status']==200 and not unheld['response']['original_receipt']['effect']['held']
        replay=phase_runner(root,'replay');assert replay['status']==200 and replay['response']['original_receipt']==receipt
        assert replay['response']['current_readback']['current']['held'] is False
        records.append({'case':'old-hold-replay-after-unhold','current_held':False,'original_held':True})
        serial._phase(root,'effect-read-only','hold',endpoint)
        with http_owner(root) as port:
            status,late=request(port,root/'alice.private','POST','/v1/workset-controls/serial-set/commands',utils.fixture._read(root/'unhold-request.private.json'))
            assert status==200 and late['original_receipt']['effect']['held'] is False
            assert late['current_readback']['current']['held'] is True
        records.append({'case':'late-unhold-receipt-keeps-current-owner-hold','original_held':False,'current_held':True})
        serial._phase(root,'effect-read-only','unhold',endpoint)

        first=serial._phase(root,'effect-read-only','tick',endpoint);assert first['allocations']==first['provider_invocations']==1
        with http_owner(root) as port:
            status,read=request(port,root/'alice.private','GET','/v1/workset-controls/serial-set');assert status==200
            payload=body(read['current'],op='hold-active')
            status,value=request(port,root/'alice.private','POST','/v1/workset-controls/serial-set/commands',payload)
            assert status==200 and value['original_receipt']['effect']['admitted_mission_ids']==[first['states'][0]['mission_id']],(status,value)
        complete()
        pending=serial._phase(root,'effect-read-only','tick',endpoint);assert pending['states'][0]['status']=='AWAITING_APPROVAL' and pending['allocations']==1
        records.append({'case':'active-mission-not-cancelled','status':pending['states'][0]['status'],'allocations':1})
        with http_owner(root) as port:
            status,read=request(port,root/'alice.private','GET','/v1/workset-controls/serial-set')
            payload=body(read['current'],op='unhold-final-wait',intent='unhold',hold=read['current']['hold'])
            status,value=request(port,root/'alice.private','POST','/v1/workset-controls/serial-set/commands',payload);assert status==200
        waiting=serial._phase(root,'effect-read-only','tick',endpoint)
        assert waiting['allocations']==1 and waiting['states'][0]['status']=='AWAITING_APPROVAL'
        records.append({'case':'unhold-does-not-remove-final-acceptance','allocations':1,'status':'AWAITING_APPROVAL'})
        with http_owner(root) as port:
            status,read=request(port,root/'alice.private','GET','/v1/workset-controls/serial-set')
            status,value=request(port,root/'alice.private','POST','/v1/workset-controls/serial-set/commands',body(read['current'],op='hold-before-final'));assert status==200
        serial._phase(root,'effect-read-only','accept-1',endpoint)
        still=serial._phase(root,'effect-read-only','tick',endpoint);assert still['allocations']==1
        with http_owner(root) as port:
            status,read=request(port,root/'alice.private','GET','/v1/workset-controls/serial-set')
            payload=body(read['current'],op='unhold-active',intent='unhold',hold=read['current']['hold'])
            status,value=request(port,root/'alice.private','POST','/v1/workset-controls/serial-set/commands',payload);assert status==200
        second=serial._phase(root,'effect-read-only','tick',endpoint);assert second['allocations']==second['provider_invocations']==2
        complete()
        pending=serial._phase(root,'effect-read-only','tick',endpoint);assert pending['states'][1]['status']=='AWAITING_APPROVAL'
        serial._phase(root,'effect-read-only','accept-2',endpoint)
        final=serial._phase(root,'effect-read-only','tick',endpoint);assert final['allocations']==2 and all(s['status']=='COMPLETED' for s in final['states'])
        records.append({'case':'hold-unhold-real-canonical-a-b','allocations':2,'provider_invocations':2,'submissions':len(simulator.submission_ids()),'consumed_activations':2})
        return records
    finally:
        server.__exit__(None,None,None)

@contextmanager
def prepared(root):
    root.mkdir();utils._effect_target_fixture(root,'effect-read-only')
    simulator=utils.EpSimulatorState(project_id=utils.PROJECT,repository_id=utils.fixture.SOURCE.repository_id,
        repository_identity=utils.fixture.SOURCE.github_repository,consumer_id=utils.CONSUMER,instance_id=utils.INSTANCE,
        bearer_token=utils.TOKEN,scenario=utils.EpSimulatorScenario(name='effect-read-only',effect_declaration_supported=True))
    with utils.EpSimulatorServer(simulator) as server:
        serial._phase(root,'effect-read-only','setup',server.base_url);provision(root)
        yield server.base_url,simulator


def source_denials(root):
    outcomes=[]
    with prepared(root) as (endpoint,simulator):
        path='/v1/workset-controls/serial-set';token=root/'alice.private'
        with http_owner(root) as port:
            instance=existing_instance(root/'runtime');grant=WorkspaceWorklistControlGrant(root/'runtime',instance.instance_id)
            status,read=request(port,token,'GET',path);payload=body(read['current'])
            for name,document in [('empty',{}),('bool-revision',{**payload,'expected_revision':True}),
                  ('bad-intent',{**payload,'intent':'arm'}),('bad-reason',{**payload,'reason_code':'free text secret'}),
                  ('bad-digest',{**payload,'definition_revision':'invalid'}),
                  ('bad-hold-target',{**payload,'hold_operation_id':'foreign'}),
                  ('unhold-without-target',{**payload,'intent':'unhold'})]:
                status,value=request(port,token,'POST',path+'/commands',document);assert status==400
                outcomes.append({'case':'malformed-'+name,'status':status})
            expires=(datetime.now(UTC)+timedelta(seconds=1)).isoformat()
            issued=grant.issue(principal_id='short',workset_ids=('serial-set',),expires_at=expires,token_path=root/'short.private')
            time.sleep(1.1)
            for method,target in [('POST',path+'/commands'),('GET',path+'/commands/hold-1')]:
                status,value=request(port,root/'short.private',method,target,payload);assert status==401
            outcomes.append({'case':'expired-command-and-operation-read','status':401})
            issued=grant.issue(principal_id='revoked',workset_ids=('serial-set',),expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=root/'revoked.private')
            grant.revoke(issued['grant_id']);grant.revoke(issued['grant_id'])
            for method,target in [('POST',path+'/commands'),('GET',path+'/commands/hold-1')]:
                status,value=request(port,root/'revoked.private',method,target,payload);assert status==401
            outcomes.append({'case':'revoked-command-and-operation-read','status':401})
            # Public owner hold is intentionally a different provenance.
            serial._phase(root,'effect-read-only','hold',endpoint)
            status,read=request(port,token,'GET',path);assert status==200 and not read['current']['hold']['owned_by_principal']
            targeted=body(read['current'],op='foreign-unhold',intent='unhold',hold=read['current']['hold'])
            status,value=request(port,token,'POST',path+'/commands',targeted);assert status==409
            outcomes.append({'case':'local-owner-hold-not-removed','status':409})
            # Compatibility fixture from the earlier bool-only workset format;
            # remove additive provenance in this disposable root and restore exact bytes.
            with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                original_document=db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('serial-set',)).fetchone()[0]
                legacy=json.loads(original_document);legacy.pop('operator_hold',None);legacy.pop('control_revision',None)
                with db:db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?',(json.dumps(legacy,sort_keys=True),'serial-set'))
            try:
                status,legacy_read=request(port,token,'GET',path)
                assert status==200 and legacy_read['current']['hold_provenance']=='LEGACY_UNKNOWN'
                target=body(legacy_read['current'],op='legacy-unhold',intent='unhold',hold={'operation_id':'unknown-owner-hold','control_revision':1})
                status,_=request(port,token,'POST',path+'/commands',target);assert status==409
            finally:
                with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                    with db:db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?',(original_document,'serial-set'))
                    assert db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('serial-set',)).fetchone()[0]==original_document
            outcomes.append({'case':'legacy-unknown-hold-provenance-preserved','status':409})

            serial._phase(root,'effect-read-only','unhold',endpoint)
            status,read=request(port,token,'GET',path);own=body(read['current'],op='own-hold')
            status,value=request(port,token,'POST',path+'/commands',own);assert status==200
            old_hold=value['original_receipt']['effect']['hold']
            serial._phase(root,'effect-read-only','hold',endpoint)
            status,read=request(port,token,'GET',path)
            status,value=request(port,token,'POST',path+'/commands',body(read['current'],op='changed-provenance-unhold',intent='unhold',hold=old_hold));assert status==409
            outcomes.append({'case':'concurrent-owner-hold-provenance-retained','status':409})
            serial._phase(root,'effect-read-only','unhold',endpoint)
            # Declared disposable private-store corruption, restored byte-for-byte.
            store=grant.path;original=store.read_bytes();store.write_text('{broken')
            try:
                status,value=request(port,token,'POST',path+'/commands',payload);assert status==401
            finally:store.write_bytes(original)
            outcomes.append({'case':'uncertain-grant-store-denied-restored','status':401})
            # Declared disposable coherent corruption over an actual persisted
            # command: recompute receipt hash, then check semantic joins via HTTP.
            from copy import deepcopy
            variants=('principal','contradictory-held','cancelled','missing-effect-field','outcome','schema',
                      'workset-revision','control-revision','hold-provenance','target','admitted-set','intent-revision',
                      'hold-control-bool','effect-observation','fabricated-canonical-admission')
            statuses=[]
            for fault in variants:
                with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                    original_document=db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('serial-set',)).fetchone()[0]
                    corrupted=json.loads(original_document);entry=corrupted['control_operations']['own-hold']
                    replay_payload=deepcopy(entry['request']);receipt=entry['receipt'];effect=receipt['effect']
                    if fault=='principal':receipt['principal_id']='foreign-principal'
                    elif fault=='contradictory-held':effect.update(held=False,hold=None,hold_provenance='NONE')
                    elif fault=='cancelled':effect['ongoing_work_cancelled']=True
                    elif fault=='missing-effect-field':effect.pop('boundary')
                    elif fault=='outcome':receipt['outcome']='FAILED'
                    elif fault=='schema':receipt['contract_version']='invented/v999'
                    elif fault=='workset-revision':effect['workset_revision']=999
                    elif fault=='control-revision':effect['control_revision']=999
                    elif fault=='hold-provenance':effect['hold']['operation_id']='other-hold'
                    elif fault=='target':receipt['only_target_hold_removed']='other-hold'
                    elif fault=='admitted-set':effect['admitted_mission_ids']=['foreign-mission']
                    elif fault=='intent-revision':entry['intent_revision']=999
                    elif fault=='hold-control-bool':effect['hold']['control_revision']=True
                    elif fault=='effect-observation':effect['observed_at']='not-a-timestamp'
                    elif fault=='fabricated-canonical-admission':
                        member=corrupted['definition']['members'][0]
                        entry['admission_bindings']=[{'kind':'CANONICAL_CANDIDATE_INTAKE','candidate_id':member['candidate_id'],
                            'subject_revision':member['subject_revision'],'mission_id':'MISSION-NONEXISTENT',
                            'installation_id':corrupted['installation_id'],'envelope_digest':'sha256:'+'0'*64}]
                        effect['admitted_mission_ids']=['MISSION-NONEXISTENT']
                    entry['receipt_digest']=utils.canonical_digest(receipt)
                    with db:db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?',(json.dumps(corrupted,sort_keys=True),'serial-set'))
                try:
                    status,_=request(port,token,'GET',path+'/commands/own-hold');assert status==503,fault
                    status,_=request(port,token,'POST',path+'/commands',replay_payload);assert status==503,fault
                    statuses.append({'fault':fault,'get':503,'replay':503})
                    with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                        assert json.loads(db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('serial-set',)).fetchone()[0])==corrupted
                finally:
                    with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                        with db:db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?',(original_document,'serial-set'))
                        assert db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('serial-set',)).fetchone()[0]==original_document
            outcomes.append({'case':'uncertain-rehashed-command-receipt-binding-denied-restored','variants':statuses,'canonical_mutation':False})
            # Owner CLI is exercised without printing any bearer.
            from contextlib import redirect_stdout
            from io import StringIO
            with redirect_stdout(StringIO()):
                assert grant_main(['--data-root',str(root/'runtime'),'issue','--principal-id','cli','--workset-id','serial-set','--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(root/'cli.private')])==0
                cli_record=grant._records()[-1]
                assert grant_main(['--data-root',str(root/'runtime'),'revoke','--grant-id',cli_record['grant_id']])==0
                assert grant_main(['--data-root',str(root/'runtime'),'revoke','--grant-id','unknown'])==1
            outcomes.append({'case':'supported-owner-cli-provision-revoke','status':'PASS'})
            with ExitStack() as stack:
                runtime=utils._open(root,stack)
                runtime.repository.operators.revoke(runtime.repository.operators.context())
            status,value=request(port,token,'POST',path+'/commands',payload);assert status==403
            status,value=request(port,token,'GET',path);assert status==403
            outcomes.append({'case':'current-operator-revoked','status':403})
        with closing(sqlite3.connect((root/'runtime'/'forge.db').resolve().as_uri()+'?mode=ro',uri=True)) as db:
            assert db.execute('SELECT COUNT(*) FROM mission_id_allocations').fetchone()[0]==0
        assert not simulator.submission_ids() and not utils.fixture._read(root/'provider-inputs.private.json',[])
    return outcomes

class InstalledPhases:
    def __init__(self,args):self.args=args
    def start(self,root,phase,endpoint=None):
        command=[sys.executable,'-I',str(Path(__file__).resolve()),'--wheel',str(self.args.wheel.resolve()),
                 '--source-revision',self.args.source_revision,'--output-dir',str(self.args.output_dir.resolve()),
                 '--child-phase',phase,'--case-root',str(root.resolve())]
        if endpoint:command+=['--endpoint',endpoint]
        return subprocess.Popen(command,cwd=root,env=utils._child_env(root/'isolated-control'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def __call__(self,root,phase):
        child=self.start(root,phase)
        stdout,stderr=child.communicate(timeout=40)
        (root/('control-'+phase+'.private.log')).write_text(stdout+stderr)
        assert child.returncode==0,(phase,child.returncode,stderr[-1200:])
        return json.loads(stdout)


def process_recovery(root,runner):
    with prepared(root) as (endpoint,simulator):
        read=runner(root,'read');utils.fixture._write(root/'hold-request.private.json',body(read['current']))
        child=runner.start(root,'crash-intent')
        try:
            deadline=time.monotonic()+15
            while not (root/'intent-boundary.ready.private').exists():
                if child.poll() is not None:raise AssertionError('intent child exited before external OS barrier')
                if time.monotonic()>deadline:raise AssertionError('intent boundary was not reached')
                time.sleep(0.01)
            child.kill();stdout,stderr=child.communicate(timeout=5)
            assert child.returncode<0
        finally:
            if child.poll() is None:child.kill();child.communicate(timeout=5)
        observed=runner(root,'recover-read');assert observed['status']==200
        assert observed['response']['operation']['state']=='PENDING' and not observed['response']['current']['held']
        recovered=runner(root,'replay');assert recovered['status']==200 and recovered['response']['original_receipt']['effect']['held']
        replay=runner(root,'replay');assert replay['response']['recorded'] is False
        assert not simulator.submission_ids() and not utils.fixture._read(root/'provider-inputs.private.json',[])
        return {'case':'real-sigkill-after-durable-intent','pids':[child.pid,recovered['pid'],replay['pid']],
                'original_pending_observed':True,'same_operation_recovered':True,'provider_invocations':0,'submissions':0}


def lost_response(root,runner):
    with prepared(root) as (endpoint,simulator):
        lost=runner(root,'lost-response');assert lost['response_body_lost']
        read=runner(root,'recover-read');assert read['status']==200 and read['response']['operation']['state']=='APPLIED'
        replay=runner(root,'replay');assert replay['status']==200 and replay['response']['recorded'] is False
        assert read['response']['operation']['original_receipt']==replay['response']['original_receipt']
        assert not simulator.submission_ids() and not utils.fixture._read(root/'provider-inputs.private.json',[])
        return {'case':'lost-http-receipt-real-process-reopen','pids':[lost['pid'],read['pid'],replay['pid']],
                'same_original_receipt':True,'provider_invocations':0,'submissions':0}


def concurrent_claim(root,runner):
    with prepared(root) as (endpoint,simulator):
        read=runner(root,'read');utils.fixture._write(root/'hold-request.private.json',body(read['current']))
        children=[runner.start(root,phase,endpoint) for phase in ('race-hold','race-tick')]
        try:
            deadline=time.monotonic()+15
            while not all((root/(phase+'.ready.private')).exists() for phase in ('race-hold','race-tick')):
                if time.monotonic()>deadline:raise AssertionError('concurrency barrier expired')
                time.sleep(0.01)
            (root/'race-go.private').write_text('go')
            observations=[]
            for phase,child in zip(('race-hold','race-tick'),children):
                stdout,stderr=child.communicate(timeout=30);(root/(phase+'.private.log')).write_text(stdout+stderr)
                assert child.returncode==0,(phase,stderr[-1000:]);observations.append(json.loads(stdout))
            after=serial._phase(root,'effect-read-only','read',endpoint)
            hold=observations[0]
            if hold['status']==200:
                receipt=hold['response']['original_receipt']
            else:
                assert hold['status'] in {409,503}
                with http_owner(root) as port:
                    token=root/'alice.private';path='/v1/workset-controls/serial-set'
                    status,value=request(port,token,'GET',path+'/commands/hold-1')
                    if status==200:
                        assert value['operation']['state']=='APPLIED';receipt=value['operation']['original_receipt']
                    else:
                        assert status==404
                        status,value=request(port,token,'GET',path)
                        status,value=request(port,token,'POST',path+'/commands',body(value['current'],op='known-denied-race-followup'))
                        assert status==200;receipt=value['original_receipt']
            assert after['allocations']<=1 and after['provider_invocations']<=1
            assert len(simulator.submission_ids())==after['allocations']
            assert len(receipt['effect']['admitted_mission_ids'])==after['allocations']
            held=serial._phase(root,'effect-read-only','read',endpoint);assert held['workset']['held']
            return {'case':'real-concurrent-hold-versus-canonical-claim','pids':[c.pid for c in children],
                    'initial_hold_http_status':hold['status'],'allocations':after['allocations'],
                    'provider_invocations':after['provider_invocations'],'receipt_admitted_count':len(receipt['effect']['admitted_mission_ids']),
                    'ongoing_work_cancelled':receipt['effect']['ongoing_work_cancelled']}
        finally:
            for child in children:
                if child.poll() is None:child.kill();child.communicate(timeout=5)


def admitted_before_hold(root,runner):
    with prepared(root) as (endpoint,simulator):
        utils.fixture._write(root/'external-pause.private.json',{'boundary':'github-before-start'})
        child=runner.start(root,'admitted-pause',endpoint)
        try:
            deadline=time.monotonic()+15
            while not (root/'external-pause.ready.private').exists():
                if child.poll() is not None:raise AssertionError('admission child exited before actual external boundary')
                if time.monotonic()>deadline:raise AssertionError('admission boundary expired')
                time.sleep(0.01)
            child.kill();child.communicate(timeout=5);assert child.returncode<0
        finally:
            if child.poll() is None:child.kill();child.communicate(timeout=5)
            (root/'external-pause.private.json').unlink(missing_ok=True)
        observed=serial._phase(root,'effect-read-only','read',endpoint)
        assert observed['allocations']==1 and observed['provider_invocations']==0
        assert observed['states'][0]['status']=='APPROVED_PLANNABLE'
        mission_id=observed['states'][0]['mission_id']
        # Explicit disposable correlation-loss fault over a real canonical intake,
        # not an invented Mission/approval or a replacement positive A/B driver.
        with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
            value=json.loads(db.execute('SELECT document FROM approved_worksets WHERE workset_id=?',('serial-set',)).fetchone()[0])
            value['claims']['synthetic-candidate-a']['mission_id']=None
            with db:db.execute('UPDATE approved_worksets SET document=? WHERE workset_id=?',(json.dumps(value,sort_keys=True),'serial-set'))
        held=runner(root,'hold');assert held['status']==200
        assert held['response']['original_receipt']['effect']['admitted_mission_ids']==[mission_id]
        resumed=serial._phase(root,'effect-read-only','tick',endpoint)
        assert resumed['allocations']==resumed['provider_invocations']==1 and resumed['workset']['held']
        assert resumed['states'][0]['mission_id']==mission_id and resumed['states'][0]['status']=='WAITING_FOR_EXECUTION'
        assert len(simulator.submission_ids())==1
        return {'case':'already-admitted-before-hold-continues-with-canonical-correlation-recovery',
                'killed_pid':child.pid,'missing_claim_correlation_fixture':True,'allocations':1,
                'provider_invocations':1,'submissions':1,'same_canonical_mission':True,'hold_remains':True}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--source-revision',required=True)
    parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--failure-control',action='store_true')
    parser.add_argument('--child-phase');parser.add_argument('--case-root',type=Path);parser.add_argument('--endpoint')
    args=parser.parse_args(argv)
    artifact=utils._installed_wheel(args.wheel,source_revision=args.source_revision,verify_source=not args.child_phase)
    output=args.output_dir.resolve()
    if args.child_phase:
        marker=output/'qualification-owner.private.json'
        if args.case_root is None or args.case_root.resolve().parent!=output or not marker.is_file() or json.loads(marker.read_text())['source_revision']!=args.source_revision:
            raise ValueError('child must belong to fresh owned qualification')
        original=socket.socket.connect
        def loopback_only(sock,address):
            assert address[0]=='127.0.0.1','non-test network attempted'
            return original(sock,address)
        with patch('socket.socket.connect',loopback_only):
            phase=args.child_phase
            if phase=='admitted-pause':result=serial._phase(args.case_root,'effect-read-only','tick',args.endpoint)
            elif phase=='race-hold':result=command_phase(args.case_root,'race-command')
            elif phase=='race-tick':
                (args.case_root/(phase+'.ready.private')).write_text(str(os.getpid()))
                deadline=time.monotonic()+12
                while not (args.case_root/'race-go.private').exists():
                    if time.monotonic()>deadline:raise AssertionError('race release expired')
                    time.sleep(0.01)
                try:
                    value=serial._phase(args.case_root,'effect-read-only','tick',args.endpoint)
                    result={'allocations':value['allocations'],'pid':os.getpid()}
                except (serial.RuntimeServiceBusy,serial.RuntimeResolutionError) as error:
                    if isinstance(error,serial.RuntimeResolutionError) and str(error)!='another mutating Forge runtime owns this data root':raise
                    result={'busy':True,'pid':os.getpid()}
            else:result=command_phase(args.case_root,phase)
        print(json.dumps(result,sort_keys=True));return 0
    if output.exists():raise ValueError('fresh qualification output required')
    output.mkdir(parents=True);(output/'qualification-owner.private.json').write_text(json.dumps({'source_revision':args.source_revision}))
    runner=InstalledPhases(args);outcomes=[];failure=None;cleanup=[]
    cases=[('flow',lambda root:source_flow(root,phase_runner=runner,failure_control=args.failure_control))]
    if not args.failure_control:cases += [('denials',source_denials),('crash',lambda root:[process_recovery(root,runner)]),('lost',lambda root:[lost_response(root,runner)]),('race',lambda root:[concurrent_claim(root,runner)]),('admitted',lambda root:[admitted_before_hold(root,runner)])]
    try:
        for name,run in cases:
            root=output/('case-'+name)
            try:outcomes.extend(run(root))
            except Exception:
                (output/(name+'-failure.private.log')).write_text(traceback.format_exc())
                for log in root.glob('*.private.log'):
                    shutil.copyfile(log,output/(name+'-'+log.name))
                raise
            finally:
                if root.exists():shutil.rmtree(root)
                cleanup.append({'case':name,'owned_runtime_home_credentials_scratch_removed':not root.exists()})
    except Exception as error:
        failure={'type':type(error).__name__,'stage':'positive-command-replay' if args.failure_control and str(error)=='positive control grant replay gate failed' else 'selected-matrix','detail':'Declared qualification gate failed'}
    receipt={'qualification':'INSTALLED_SCOPED_WORKLIST_HOLD_V1','scope':'HOLD_UNHOLD_HTTP_PRODUCER_ONLY',
             'result':'WORKLIST_CONTROL_PASS' if failure is None else 'FAIL','source_revision':args.source_revision,
             'artifact':artifact,'cases':outcomes,'case_count':len(outcomes),'failure':failure,
             'expected_failure_control':args.failure_control,'external_fault':'REVOKED_CONTROL_GRANT' if args.failure_control else None,
             'cleanup':cleanup,'qualifier_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
             'limitations':['Synthetic canonical decisions and external EP/LLM/OS/Git fixtures; no live EP/provider/operational activation.',
                            'Producer-only hold/unhold; no Workspace mutation consumer or full PRM/IAM family claim.',
                            'Declared disposable storage-input faults cover legacy provenance, rehashed receipt binding and missing claim correlation; no auth/command mocks or approval seeding.']}
    (output/'installed-worklist-control.public.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:receipt[k] for k in ('result','source_revision','case_count','failure')}))
    return 0 if failure is None else 1

if __name__=='__main__':raise SystemExit(main())
