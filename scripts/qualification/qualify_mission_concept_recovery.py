"""Kill/restart proof at external OS boundaries around actual concept stores.

No approval, lifecycle, provider result or persistence implementation is replaced.
Only OS identity and external model/repository transports use declared fixtures.
"""
from contextlib import ExitStack, closing
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Thread
from unittest.mock import patch
import json, os, sqlite3, subprocess, sys, time
import forge

SOURCE = Path(__file__).resolve().parents[2]


def cases():
    # Test adapters are explicit external boundaries; installed forge stays imported.
    sys.path.insert(0, str(SOURCE / 'tests'))
    import test_mission_concept_ready_http as ready
    import test_mission_concept_contract as content
    return ready, content


def counts(root):
    result = {}
    for path, tables in ((root/'runtime'/'governance'/'candidates.sqlite',
                          ('advisory_candidate_intents','advisory_candidate_registrations','candidate_decision_receipts','allocations')),
                         (root/'runtime'/'forge.db',('governance_decisions','mission_state'))):
        if not path.exists():
            result.update({table:0 for table in tables})
            continue
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
            present = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in tables:
                result[table] = db.execute('SELECT count(*) FROM '+table).fetchone()[0] if table in present else 0
    return result


def phase(root, stage, mode):
    ready, _ = cases(); q = ready.qual
    command = json.loads((root/'request.private.json').read_text())
    base = '/v1/mission-concepts/recovery-chat'
    def identity():
        hit = False
        if stage.startswith('crash-'):
            if mode == 'generation':
                expected = 'REASONING' if stage == 'crash-before-provider' else 'REVIEW'
                for path in (root/'runtime'/'advisory'/'transcripts').glob('concept-*.json'):
                    transcript = json.loads(path.read_text())
                    hit = bool(transcript['turns'] and transcript['turns'][-1]['status'] == expected)
            else:
                actual = counts(root)
                expected = {'crash-before-registration':(1,0,0,0,0),
                            'crash-after-registration':(1,1,0,0,0),
                            'crash-business-between-stores':(1,1,1,0,0),
                            'crash-after-business':(1,1,1,1,0),
                            'crash-architecture-between-stores':(1,1,2,1,0),
                            'crash-after-architecture':(1,1,2,2,0),
                            'crash-after-allocation':(1,1,2,2,0),
                            'crash-after-intake':(1,1,2,2,1)}[stage]
                hit = tuple(actual[k] for k in ('advisory_candidate_intents','advisory_candidate_registrations',
                           'governance_decisions','candidate_decision_receipts','mission_state')) == expected
                if stage=='crash-after-allocation':hit = hit and actual['allocations']==1
            if hit:
                (root/'boundary.ready.private').write_text(str(os.getpid()))
                time.sleep(20)
        return q.utils.fixture.IDENTITY
    with patch.object(q.utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',side_effect=identity), ExitStack() as stack:
        server = q.ForgeServerRuntime(data_root=root/'runtime', credential_file=root/'admin.private',
                    host='127.0.0.1',port=0,provider_id=q.utils.fixture.PROVIDER)
        worker = Thread(target=server.server.serve_forever,daemon=True); worker.start()
        stack.callback(server.server.server_close);stack.callback(worker.join,3);stack.callback(server.server.shutdown)
        port=server.server.server_address[1];token=root/'owner.private'
        if stage == 'read':
            path = base+'/turns/recovery-turn' if mode=='generation' else base+'/operations/approve-recovery'
            return ready.call(port,token,'GET',path)
        target=base+'/turns' if mode=='generation' else base+'/approve'
        if stage == 'new-key':
            command={**command,('turn_id' if mode=='generation' else 'operation_id'):'new-recovery-key'}
        if stage == 'lost-response':
            import socket
            raw=json.dumps(command).encode()
            with socket.create_connection(('127.0.0.1',port),timeout=15) as sock:
                headers=('POST '+target+' HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer '+
                    token.read_text().strip()+'\r\nContent-Type: application/json\r\nContent-Length: '+
                    str(len(raw))+'\r\nConnection: close\r\n\r\n').encode()
                sock.sendall(headers+raw);received=b''
                while b'\r\n\r\n' not in received:
                    piece=sock.recv(1);assert piece;received+=piece
                assert b'200' in received.splitlines()[0]
            return {'lost_body':True}
        return ready.call(port,token,'POST',target,command)


def prepare_case(root, mode):
    ready, content = cases();q=ready.qual
    grant=ready.configure(root)
    with q.http(root) as port:
        from forge.server_runtime import existing_instance
        from forge.mission_concept_setup import MissionConceptSetup
        from forge.mission_concept_contract import CONTRACT
        instance=existing_instance(root/'runtime')
        principal=sha256(q.utils.fixture.IDENTITY.generated_uid.encode()).hexdigest()[:16]
        issued=grant.issue(principal_id=principal,project_id=q.utils.PROJECT,
            repository_id=q.utils.fixture.SOURCE.repository_id,conversation_ids=['recovery-chat'],
            maximum_turns=8,expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=root/'owner.private')
        MissionConceptSetup(root/'runtime',instance.instance_id).configure(
            grant_id=issued['grant_id'],profiles=ready.profiles(),maximum_missions=2)
        _,context=ready.call(port,root/'owner.private','GET','/v1/mission-concepts/recovery-chat/context')
        request={k:context['context'][k] for k in ('instance_id','project_id','repository_id')}
        request.update(contract_version=CONTRACT,conversation_id='recovery-chat',turn_id='recovery-turn',
            expected_revision=0,context_revision=context['context_revision'],selected_sources=[],
            advisor_kind='ARCHITECTURE',objective='Build the client portal without executing payments.')
        ready.model_output(root,content.MissionConceptContractTests().output()['definition'])
        if mode == 'approval':
            status,out=ready.call(port,root/'owner.private','POST','/v1/mission-concepts/recovery-chat/turns',request)
            assert status==200,out
            _,prepared=ready.call(port,root/'owner.private','GET','/v1/mission-concepts/recovery-chat/package')
            request={'contract_version':CONTRACT,'operation_id':'approve-recovery','revision':1,
                     'package_digest':prepared['package_digest'],'confirm':True}
        path=root/'request.private.json';path.write_text(json.dumps(request));path.chmod(0o600)
    return request


def process_case(root, stage, mode):
    prepare_case(root, mode)
    source=Path(forge.__file__).resolve().is_relative_to(SOURCE)
    env=os.environ.copy()
    if source:env['PYTHONPATH']=str(SOURCE)
    prefix=[sys.executable]+([] if source else ['-I'])
    command=[*prefix,str(Path(__file__).resolve()),'--root',str(root),'--mode',mode,'--phase',stage]
    if stage.startswith('crash-'):
        with (root/'phase.private.log').open('w') as log:
            child=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+15
                while not (root/'boundary.ready.private').exists():
                    if child.poll() is not None or time.monotonic()>deadline:
                        raise AssertionError('actual '+stage+' boundary not reached: '+(root/'phase.private.log').read_text())
                    time.sleep(.02)
                assert int((root/'boundary.ready.private').read_text())==child.pid
                child.kill();child.wait(timeout=5)
            finally:
                if child.poll() is None:child.kill();child.wait()
    else:
        done=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=30)
        assert done.returncode==0,done.stderr
    def reopen(next_stage):
        done=subprocess.run([*command[:-1],next_stage],cwd=root,env=env,capture_output=True,text=True,timeout=30)
        assert done.returncode==0,done.stderr
        return json.loads(done.stdout)
    status,read=reopen('read');assert status==200,(status,read)
    if mode=='approval':
        assert read['state']==('COMPLETE' if stage in ('crash-after-intake','lost-response') else 'PENDING'),read['state']
    status,replayed=reopen('replay');assert status==200,(status,replayed)
    calls=len((root/'provider-requests.private.jsonl').read_text().splitlines()) if (root/'provider-requests.private.jsonl').exists() else 0
    actual=counts(root)
    if mode=='generation':
        assert read['original_turn']['invocation_id']==replayed['original_turn']['invocation_id']
        if stage=='crash-before-provider':
            assert calls==0 and replayed['original_turn']['execution']=='MAY_HAVE_HAPPENED'
        else:
            assert calls==1 and replayed['original_turn']['status']=='COMPLETE'
        assert all(n==0 for n in actual.values())
        assert reopen('new-key')[0]==409
    else:
        assert calls==1 and actual==dict(advisory_candidate_intents=1,advisory_candidate_registrations=1,
                    candidate_decision_receipts=2,allocations=1,governance_decisions=2,mission_state=1),actual
        status,later=reopen('read');assert status==200 and later['state']=='COMPLETE'
        assert later['mission_id']==replayed['mission_id']
        assert read['frozen_package']==later['frozen_package']
        status,alias=reopen('new-key');assert status==200 and alias['mission_id']==later['mission_id']
        assert counts(root)=={**actual,'advisory_candidate_intents':2},counts(root)
        with closing(sqlite3.connect((root/'runtime'/'governance'/'candidates.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
            assert db.execute('SELECT count(DISTINCT registration_key) FROM advisory_candidate_intents').fetchone()[0]==1
    return {'case':mode+'/'+stage,'result':'PASS','fresh_os_processes':True,'provider_invocations':calls,
            'counts':actual,'execution_started':False}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--mode',choices=['generation','approval'],required=True);p.add_argument('--phase',required=True)
    a=p.parse_args();print(json.dumps(phase(a.root,a.phase,a.mode)))
