"""Ordinary external HTTP client against a separate noneditable installed Server OS process."""
from contextlib import contextmanager
from datetime import UTC,datetime,timedelta
from hashlib import sha256
from pathlib import Path
import argparse
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


def command(python,args,root):
    value=subprocess.run([str(python),'-I',*args],cwd=root,capture_output=True,timeout=20)
    if value.returncode:raise RuntimeError('trusted setup command failed: '+value.stderr.decode()[:100])
    return json.loads(value.stdout)


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
        process=subprocess.Popen([str(python),'-I','-m','forge','--data-root',str(root/'runtime'),'server','run','--credential-file',str(root/'admin.private'),'--port',str(port),'--tick-interval','1'],cwd=root,stdout=log,stderr=log,start_new_session=True)
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
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def run(python,output):
    output.mkdir(mode=0o700)
    receipt={'qualification':'INSTALLED_PROJECT_PROPOSAL_HTTP_COMPACT_V1','result':'FAIL','cases':[],'cleanup':False}
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
                for kind,value in [('pb-render/1.0',basis),('pb-adoption-preview/1.0',adoption)]:
                    body={'contract_version':CONTRACT,'instance_id':cap['instance_id'],'dossier_id':'dossier-alice','operation_id':'original-'+str(len(results)),'proposal_kind':kind,'input':value}
                    status,plan=call(port,alice,'POST','/v1/onboarding/plans',body);assert status==200,(status,plan)
                    assert plan['result']['state']=='PROPOSED_NOT_APPROVED'
                    local_input=root/('input-'+str(len(results))+'.json');local_input.write_text(json.dumps(value,ensure_ascii=False));export=root/('local-comparator-'+str(len(results)))
                    module='forge.project_bootstrap.cli' if kind=='pb-render/1.0' else 'forge.project_adoption.cli'
                    args=['-m',module,'render' if kind=='pb-render/1.0' else 'preview','--input',str(local_input),'--export',str(export)]
                    command(python,args,root)
                    for item in plan['result']['artifacts']:
                        assert (export/item['path']).read_bytes()==item['content'].encode() and sha256(item['content'].encode()).hexdigest()==item['sha256']
                    results.append(plan);requests.append(body);receipt['cases'].append('http-'+kind+'-exact-installed-cli-parity')
                    assert call(port,alice,'POST','/v1/onboarding/plans',body)==(200,plan)
                    assert call(port,alice,'GET','/v1/onboarding/intents/'+body['operation_id']+'?dossier_id=dossier-alice')==(200,plan)
                    assert call(port,bob,'GET','/v1/onboarding/plans/'+plan['plan_id']+'?dossier_id=dossier-bob')[0]==403
                    assert call(port,root/'admin.private','POST','/v1/onboarding/plans',body)[0]==403
                changed=json.loads(json.dumps(requests[0]));changed['input']['product']['purpose']='Changed supplied fact.'
                assert call(port,alice,'POST','/v1/onboarding/plans',changed)[0]==409
                assert call(port,alice,'GET','/v1/projects')[0]==403
                receipt['cases'].extend(['exact-idempotency-original-intent','cross-caller-dossier-and-admin-denied','changed-same-key-conflicts'])
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
            stored=json.loads((root/'runtime'/'onboarding'/'proposals'/'store.json').read_text());assert len(stored['records'])==3
            receipt.update(result='PROJECT_PROPOSAL_HTTP_COMPACT_PASS',stored_records=3,no_canonical_project=True,no_ep_model_mission_effects=True,separate_server_processes=True)
        receipt['cleanup']=not root.exists()
    except BaseException as error:
        receipt['failure']={'category':type(error).__name__};raise
    finally:
        try:(output/'installed-project-proposal-http.public.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        except OSError:
            if receipt['result']=='PROJECT_PROPOSAL_HTTP_COMPACT_PASS':raise
    print(receipt['result'],len(receipt['cases']))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--python',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args();run(args.python,args.output_dir)
