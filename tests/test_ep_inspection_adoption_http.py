"""Source HTTP regression with explicitly modeled EP peer; real installed producer proof is separate."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread, Event
from unittest.mock import patch
from importlib.util import spec_from_file_location, module_from_spec
from hashlib import sha256
import json
import os
import sys
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from forge.ep_inspection_contract import CONTRACT, EP_REVISION, EP_TREE, EP_SCHEMA_SHA256
from forge.ep_inspection_grant import InspectionAdoptionGrant
from forge.ep_inspection_service import InspectionAdoptionService
from forge.server_runtime import ForgeServerRuntime
from forge.project_bootstrap.schema import canonical
from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter, NamedOperatorIdentity
from test_ep_inspection_contract import wire

ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('r55_owner_fixture',ROOT/'scripts/qualification/proposal_content_fixture.py')
fixture=module_from_spec(spec);spec.loader.exec_module(fixture)
BASE='/v1/inspection-adoptions'


class InspectionAdoptionHTTPTests(unittest.TestCase):
    def setUp(self):
        if sys.platform!='darwin':
            identity=NamedOperatorIdentity('r55-explicit-source-os-fixture',os.getuid())
            patched=patch.object(MacOSGeneratedUIDIdentityAdapter,'resolve',return_value=identity)
            patched.start();self.addCleanup(patched.stop)
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve()/'synthetic'
        self.setup=fixture.configure(self.root)
        self.value=json.loads((ROOT/'examples/project-adoption/adopt-existing-vision-input.json').read_text())
        vision=next(d['content'] for d in self.value['inventory']['documents'] if d['path']=='docs/RICHTING.md')
        self.snapshot=wire();self.snapshot['observation'].update(state='DIRECTORY',git=None,
            selection=['docs/RICHTING.md','docs/architecture/ARCHITECTURE.md'],
            documents=[{'path':'docs/RICHTING.md','state':'PRESENT','content':vision,'sha256':sha256(vision.encode()).hexdigest()},
                       {'path':'docs/architecture/ARCHITECTURE.md','state':'ABSENT','content':None,'sha256':None}])
        self.peer_status=200;self.requests=[];self.block=False;self.entered=Event();self.release=Event()
        outer=self
        class Peer(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.requests.append((self.command,self.path))
                if outer.block:
                    outer.entered.set();outer.release.wait(10)
                raw=canonical(outer.snapshot) if outer.peer_status==200 else b'{"error":"SYNTHETIC_PEER_DENIED"}'
                self.send_response(outer.peer_status);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*_):pass
        self.peer=ThreadingHTTPServer(('127.0.0.1',0),Peer)
        self.peer_thread=Thread(target=self.peer.serve_forever,daemon=True);self.peer_thread.start()
        self.addCleanup(self.stop_peer)
        self.grant=InspectionAdoptionGrant(self.root/'runtime',self.setup['instance_id']);self.grant.initialize()
        (self.root/'ep.private').write_text('synthetic-ep-bearer');(self.root/'ep.private').chmod(0o600)
        self.pair={'pairing_id':'selected-original','endpoint':'http://127.0.0.1:'+str(self.peer.server_port),
            'producer_revision':EP_REVISION,'producer_tree':EP_TREE,'producer_schema_sha256':EP_SCHEMA_SHA256,
            'snapshot_digest':sha256(canonical(self.snapshot)).hexdigest(),
            'binding':{**{k:self.snapshot[k] for k in ('instance_id','host_id','source_ref','operation_id')},
                'consumer_id':'synthetic-forge','principal':'synthetic-peer','audience':'synthetic-transfer',
                'paths':self.snapshot['observation']['selection'],'content_paths':['docs/RICHTING.md']}}
        self.grant.bind(self.pair,self.root/'ep.private')
        self.issued=self.grant.issue(principal_id='synthetic-service',audience='synthetic-workspace',dossier_ids=['synthetic-dossier'],
            permissions=['READ','PREPARE'],pairing_id='selected-original',maximum_records=4,
            expires_at=(datetime.now(UTC)+timedelta(minutes=15)).isoformat(),token_path=self.root/'new.private')
        self.runtime=ForgeServerRuntime(data_root=self.root/'runtime',credential_file=self.root/'admin.private',host='127.0.0.1',port=0)
        self.thread=Thread(target=self.runtime.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop_forge)
        self.body={'contract_version':CONTRACT,'instance_id':self.setup['instance_id'],'dossier_id':'synthetic-dossier',
            'operation_id':'adopt-original','pairing_id':'selected-original','input':{k:self.value[k] for k in ('bootstrap_input','requested_artifacts','mappings')}}
        self.body['input']['requested_artifacts'].append('docs/roadmap/ROADMAP.md')

    def stop_peer(self):
        self.release.set();self.peer.shutdown();self.peer_thread.join(3);self.peer.server_close()

    def stop_forge(self):
        self.runtime.server.shutdown();self.thread.join(3);self.runtime.server.server_close()

    def call(self,method,path,body=None,token='new',audience='synthetic-workspace',headers=None):
        request=Request('http://127.0.0.1:'+str(self.runtime.server.server_port)+path,method=method,
            data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+(self.root/(token+'.private')).read_text().strip(),
                'X-Forge-Inspection-Audience':audience,'Content-Type':'application/json',**(headers or {})})
        try:
            with urlopen(request,timeout=15) as response:status,value=response.status,json.loads(response.read())
        except HTTPError as error:
            try:status,value=error.code,json.loads(error.read())
            finally:error.close()
        if path.startswith(BASE):
            from jsonschema import Draft202012Validator
            Draft202012Validator(json.loads((ROOT/'forge/api/inspection-adoptions-v1.json').read_text())).validate(value)
        return status,value

    def prepare(self,operation=None):
        body=deepcopy(self.body)
        if operation:body['operation_id']=operation
        status,value=self.call('POST',BASE+'/plans',body);self.assertEqual(status,200,value)
        return value

    def read(self,operation='adopt-original',**kwargs):
        return self.call('GET',BASE+'/intents/'+operation+'?dossier_id=synthetic-dossier',**kwargs)

    def test_actual_forge_http_closed_schemas_and_shared_rules(self):
        status,cap=self.call('GET',BASE+'/capability');self.assertEqual(status,200,cap)
        plan=self.prepare();status,same=self.read();self.assertEqual((status,same),(200,plan))
        result=json.loads(next(a['content'] for a in plan['result']['artifacts'] if a['path']=='proposal.json'))
        from jsonschema import Draft202012Validator
        Draft202012Validator(json.loads((ROOT/'forge/api/inspection-adoption-proposal-v1.json').read_text())).validate(result)
        entries={r['artifact_path']:r for r in result['entries']}
        self.assertEqual(entries['docs/product/VISION.md']['operation'],'LINK_EXISTING')
        self.assertEqual(entries['docs/architecture/ARCHITECTURE.md']['operation'],'PROPOSE_ADDITION')
        self.assertEqual(entries['docs/roadmap/ROADMAP.md']['operation'],'INSUFFICIENT_INFORMATION')
        self.assertTrue(all(method=='GET' for method,_ in self.requests))

    def test_idempotency_concurrency_conflict_and_new_operation(self):
        answers=[]
        threads=[Thread(target=lambda:answers.append(self.call('POST',BASE+'/plans',self.body))) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(15);self.assertFalse(thread.is_alive())
        self.assertEqual([a[0] for a in answers],[200,200]);self.assertEqual(answers[0][1],answers[1][1])
        changed=deepcopy(self.body);changed['input']['bootstrap_input']['product']['purpose']='Different purpose'
        self.assertEqual(self.call('POST',BASE+'/plans',changed)[0],409)
        self.assertEqual(len(self.grant._store()['records']),1)
        other=self.prepare('adopt-new');self.assertNotEqual(other['plan_id'],answers[0][1]['plan_id'])
        self.assertEqual(other['approval'],'NOT_PERFORMED')

    def test_old_grants_admin_scope_actor_headers_and_closed_input(self):
        for token in ('prepare','admin'):
            self.assertEqual(self.call('POST',BASE+'/plans',self.body,token=token)[0],403)
        self.assertEqual(self.call('GET',BASE+'/capability',audience='foreign')[0],403)
        for header in ('X-Actor','X-Viewer','X-Role'):
            self.assertEqual(self.call('GET',BASE+'/capability',headers={header:'trusted-owner'})[0],400)
        wrong=deepcopy(self.body);wrong['instance_id']='foreign'
        self.assertEqual(self.call('POST',BASE+'/plans',wrong)[0],403)
        wrong=deepcopy(self.body);wrong['endpoint']='http://example.invalid'
        self.assertEqual(self.call('POST',BASE+'/plans',wrong)[0],422)
        self.assertEqual(self.call('GET','/v1/onboarding/capability')[0],403)
        self.assertEqual(self.read('unknown')[0],404)

    def test_peer_denial_unavailable_and_coherent_wrong_payload_never_use_cache(self):
        self.prepare();original=self.grant.store.read_bytes()
        self.peer_status=403
        self.assertEqual(self.read()[0],424);self.assertEqual(self.grant.store.read_bytes(),original)
        self.peer_status=503
        status,body=self.read();self.assertEqual(status,424);self.assertEqual(body['error']['code'],'EP_HTTP_503')
        self.peer_status=200
        self.snapshot['observation']['documents'][0]['content']='Coherently altered content'
        self.snapshot['observation']['documents'][0]['sha256']=sha256(b'Coherently altered content').hexdigest()
        status,body=self.read();self.assertEqual(status,424);self.assertEqual(body['error']['code'],'EP_ORIGINAL_SNAPSHOT_MISMATCH')

    def test_late_peer_revoke_before_publication_denies_document(self):
        original=InspectionAdoptionService.handle
        outer=self
        def revoked(service,*arguments,**kwargs):
            status,body=original(service,*arguments,**kwargs)
            if status==200 and body.get('plan_id'):outer.peer_status=403
            return status,body
        with patch.object(InspectionAdoptionService,'handle',revoked):
            status,body=self.call('POST',BASE+'/plans',self.body)
        self.assertEqual(status,403);self.assertNotIn('result',body)
        self.assertEqual(len(self.grant._store()['records']),1)

    def test_no_own_authority_lock_across_peer_wait_or_late_own_revoke(self):
        self.block=True;answers=[]
        thread=Thread(target=lambda:answers.append(self.call('POST',BASE+'/plans',self.body)));thread.start()
        self.assertTrue(self.entered.wait(5));start=time.monotonic()
        self.grant.revoke(self.issued['grant_id']);self.assertLess(time.monotonic()-start,1)
        self.release.set();thread.join(15);self.assertFalse(thread.is_alive())
        self.assertEqual(answers[0][0],403)
        self.assertEqual(next(iter(self.grant._store()['records'].values()))['state'],'PREPARING')

    def test_initialized_storage_loss_corruption_pairing_revocation(self):
        self.prepare();original=self.grant.store.read_bytes();self.grant.store.unlink()
        self.assertEqual(self.read()[0],503)
        self.grant.store.write_bytes(original);self.grant.store.chmod(0o600)
        corrupted=json.loads(original);corrupted['records']={};self.grant.store.write_text(json.dumps(corrupted))
        self.assertEqual(self.read()[0],503)
        self.grant.store.write_bytes(original)
        self.grant.revoke_pair('selected-original')
        self.assertEqual(self.read()[0],401)
        self.assertEqual(self.grant.store.read_bytes(),original)

    def test_owner_cli_parity_original_intent_and_explicit_setup_boundaries(self):
        from forge.ep_inspection_cli import main
        from contextlib import redirect_stdout
        import io
        def cli(*arguments):
            out=io.StringIO()
            with redirect_stdout(out):exit_code=main(['--data-root',str(self.root/'runtime'),*map(str,arguments)])
            return exit_code,json.loads(out.getvalue()) if out.getvalue() else None
        self.assertEqual(cli('init')[0],0)
        token=self.root/'cli.private'
        code,issued=cli('issue','--principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier',
            '--permission','READ','--permission','PREPARE','--pairing-id','selected-original','--maximum-records','4',
            '--expires-at',(datetime.now(UTC)+timedelta(minutes=5)).isoformat(),'--token-file',token)
        self.assertEqual(code,0,issued)
        self.assertEqual(cli('capability','--token-file',token,'--audience','synthetic-workspace')[0],0)
        request_file=self.root/'request.private.json';request_file.write_bytes(canonical(self.body));request_file.chmod(0o600)
        code,prepared=cli('prepare','--token-file',token,'--audience','synthetic-workspace','--request-file',request_file)
        self.assertEqual(code,0,prepared)
        for action,selector,reference in [('read','--plan-id',prepared['plan_id']),('intent','--operation-id','adopt-original')]:
            self.assertEqual(cli(action,'--token-file',token,'--audience','synthetic-workspace','--dossier-id','synthetic-dossier',selector,reference),(0,prepared))
        config=self.root/'pair.private.json';alternative=deepcopy(self.pair);alternative['pairing_id']='cli-bound';config.write_bytes(canonical(alternative));config.chmod(0o600)
        self.assertEqual(cli('bind','--config-file',config,'--ep-token-file',self.root/'ep.private')[0],0)
        self.assertEqual(cli('revoke-pairing','--pairing-id','cli-bound')[0],0)
        with patch('forge.ep_inspection_cli.publish_cli',side_effect=OSError('synthetic bounded sink failure')):
            self.assertEqual(cli('capability','--token-file',token,'--audience','synthetic-workspace'),(1,None))
        self.assertEqual(cli('revoke','--grant-id',issued['grant_id'])[0],0)
        self.assertEqual(cli('capability','--token-file',token,'--audience','synthetic-workspace')[0],1)
        config.write_text('{}')
        self.assertEqual(cli('bind','--config-file',config,'--ep-token-file',self.root/'ep.private')[0],1)

    def test_explicit_read_only_and_real_expiry_never_expand_rights(self):
        self.prepare()
        self.grant.issue(principal_id='synthetic-service',audience='synthetic-workspace',dossier_ids=['synthetic-dossier'],
            permissions=['READ'],pairing_id='selected-original',maximum_records=4,
            expires_at=(datetime.now(UTC)+timedelta(seconds=2)).isoformat(),token_path=self.root/'reader.private')
        self.assertEqual(self.read(token='reader')[0],200)
        changed=deepcopy(self.body);changed['operation_id']='not-permitted'
        self.assertEqual(self.call('POST',BASE+'/plans',changed,token='reader')[0],403)
        time.sleep(2.05)
        self.assertEqual(self.read(token='reader')[0],401)
        self.assertEqual(len(self.grant._store()['records']),1)

    def test_finite_network_deadline_even_with_peer_wait(self):
        from forge.ep_inspection_peer import original,PeerError
        self.block=True;started=time.monotonic()
        try:
            with self.assertRaises(PeerError):original(self.grant.pair('selected-original'),deadline=time.monotonic()+.2)
            self.assertLess(time.monotonic()-started,1)
        finally:self.release.set()


    def test_explicit_new_snapshot_requires_new_pairing_and_proposal_without_old_approval(self):
        first=self.prepare()
        self.snapshot['operation_id']='op-explicit-new'
        self.snapshot['observation']['observed_at']='2026-10-15T18:13:58+00:00'
        pair=deepcopy(self.pair);pair['pairing_id']='explicit-new'
        pair['binding']['operation_id']='op-explicit-new'
        pair['snapshot_digest']=sha256(canonical(self.snapshot)).hexdigest()
        self.grant.bind(pair,self.root/'ep.private')
        self.grant.issue(principal_id='synthetic-service',audience='synthetic-workspace',dossier_ids=['synthetic-dossier'],
            permissions=['READ','PREPARE'],pairing_id='explicit-new',maximum_records=4,
            expires_at=(datetime.now(UTC)+timedelta(minutes=15)).isoformat(),token_path=self.root/'next.private')
        # The old immutable pairing cannot relabel a changed original observation.
        self.assertEqual(self.read()[0],424)
        body=deepcopy(self.body);body.update(operation_id='adopt-next',pairing_id='explicit-new')
        code,second=self.call('POST',BASE+'/plans',body,token='next')
        self.assertEqual(code,200,second)
        self.assertNotEqual(second['plan_id'],first['plan_id'])
        self.assertEqual(second['approval'],'NOT_PERFORMED')
        self.assertEqual(second['result']['source_binding']['operation_id'],'op-explicit-new')
        self.assertEqual(len(self.grant._store()['records']),2)
