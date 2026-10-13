"""Actual source HTTP controls; trusted OS identity fixture is not installed proof."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import tempfile
from threading import Thread, Event
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from forge.operator_identity import NamedOperatorIdentity, InstallationOperatorService
from forge.runtime import RuntimeBootstrap
from forge.server_runtime import ForgeServerRuntime
from forge.project_proposal_grant import ProjectProposalGrant, CONTRACT, KINDS
from forge.project_proposal_storage import read, write
from forge.project_bootstrap.service import digest
from forge.project_bootstrap.schema import canonical

class ProposalHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()/'runtime'
        self.identity=NamedOperatorIdentity('synthetic-r52-owner',501)
        fixture=patch('forge.operator_identity.MacOSGeneratedUIDIdentityAdapter.resolve',return_value=self.identity)
        fixture.start(); self.addCleanup(fixture.stop)
        with RuntimeBootstrap(data_root=self.root,forge_version='test').open() as db:
            InstallationOperatorService(db,lambda:self.identity).first_bind()
        admin=self.root/'admin';admin.write_text('synthetic-admin');admin.chmod(0o600)
        self.server=ForgeServerRuntime(data_root=self.root,credential_file=admin,host='127.0.0.1',port=0)
        self.grant=ProjectProposalGrant(self.root,self.server.instance.instance_id)
        self.grant.initialize()
        self.token=Path(self.temp.name)/'alice'
        self.issued=self.grant.issue(principal_id='alice',audience='synthetic-workspace',dossier_ids=['alice-dossier'],permissions=['PREPARE','READ'],kinds=list(KINDS),maximum_records=8,expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=self.token)
        self.http=self.server.server
        self.thread=Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.body={'contract_version':CONTRACT,'instance_id':self.grant.instance_id,'dossier_id':'alice-dossier','operation_id':'original','proposal_kind':KINDS[0],'input':json.loads(Path('examples/project-bootstrap/authority-input.json').read_text())}
    def stop(self):
        self.http.shutdown();self.thread.join(3);self.http.server_close()
    def call(self,method,path,body=None,token=None,audience='synthetic-workspace'):
        request=Request('http://127.0.0.1:'+str(self.http.server_address[1])+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+(token or self.token.read_text().strip()),'X-Forge-Proposal-Audience':audience,'Content-Type':'application/json'})
        try:
            with urlopen(request,timeout=8) as response:return response.status,json.loads(response.read())
        except HTTPError as error:
            with error:return error.code,json.loads(error.read())
    def get(self,plan):return self.call('GET','/v1/onboarding/plans/'+plan['plan_id']+'?dossier_id=alice-dossier')
    def test_exact_http_replay_get_does_not_render(self):
        status,plan=self.call('POST','/v1/onboarding/plans',self.body);self.assertEqual(status,200)
        with patch('forge.project_proposal_service.result',side_effect=AssertionError('GET must not render')):
            self.assertEqual(self.get(plan),(200,plan));self.assertEqual(self.call('POST','/v1/onboarding/plans',self.body),(200,plan))
        changed=deepcopy(self.body);changed['input']['product']['purpose']='Changed supplied purpose'
        self.assertEqual(self.call('POST','/v1/onboarding/plans',changed)[0],409)
    def test_coherent_corruption_rejected_and_exact_restoration(self):
        status,plan=self.call('POST','/v1/onboarding/plans',self.body);self.assertEqual(status,200)
        original=read(self.grant.store)
        for field,value in [('request_digest','0'*64),('observations','LIVE_VERIFIED'),('repository_quality','PASS')]:
            corrupt=deepcopy(original);r=corrupt['records'][plan['plan_id']]
            if field=='request_digest':r[field]=value
            else:r['result'][field]=value
            r['record_digest']=digest(canonical({k:v for k,v in r.items() if k not in {'record_digest','integrity_tag'}}))
            write(self.grant.store,corrupt)
            self.assertEqual(self.get(plan)[0],503)
        write(self.grant.store,original);self.assertEqual(self.get(plan),(200,plan))
    def test_initialized_missing_store_not_reset_even_before_grant(self):
        raw=self.grant.store.read_bytes();self.grant.store.unlink()
        with self.assertRaises(FileNotFoundError):self.grant.initialize()
        self.assertFalse(self.grant.store.exists())
        self.grant.store.write_bytes(raw);self.grant.store.chmod(0o600)
    def test_initialize_preserves_records_and_no_clobber_create(self):
        self.assertEqual(self.call('POST','/v1/onboarding/plans',self.body)[0],200)
        before=self.grant.store.read_bytes();self.grant.initialize();self.assertEqual(self.grant.store.read_bytes(),before)
        with self.assertRaises(ValueError):write(self.grant.store,{},create=True)
        self.assertEqual(self.grant.store.read_bytes(),before)
    def test_real_grant_revoke_after_commit_before_first_http_send(self):
        original=ProjectProposalGrant.publication
        @contextmanager
        def revoked_before_send(grant,*args,**kwargs):
            self.grant.revoke(self.issued['grant_id'])
            with original(grant,*args,**kwargs):yield
        with patch.object(ProjectProposalGrant,'publication',revoked_before_send):
            status,body=self.call('POST','/v1/onboarding/plans',self.body)
        self.assertEqual(status,403);self.assertEqual(body['error']['code'],'PROPOSAL_PUBLICATION_DENIED')
        self.assertEqual(len(read(self.grant.store)['records']),1)
        self.assertEqual(self.call('GET','/v1/onboarding/intents/original?dossier_id=alice-dossier')[0],401)

    def test_real_owned_lock_wait_cannot_send_after_publication_deadline(self):
        import time
        from http.client import RemoteDisconnected
        from forge.workspace_review_grant import _locked
        original=ProjectProposalGrant.publication
        locked=Event();release=Event()
        def holder():
            with _locked(self.grant.path):locked.set();release.wait(7)
        @contextmanager
        def blocked_publication(grant,*args,**kwargs):
            owner=Thread(target=holder);owner.start();self.assertTrue(locked.wait(2))
            try:
                with original(grant,*args,**kwargs):yield
            finally:release.set();owner.join(2)
        with patch.object(ProjectProposalGrant,'publication',blocked_publication):
            start=time.monotonic()
            with self.assertRaises(RemoteDisconnected):self.call('POST','/v1/onboarding/plans',self.body)
            self.assertLess(time.monotonic()-start,6.5)
        record=next(iter(read(self.grant.store)['records'].values()))
        self.assertEqual(self.call('GET','/v1/onboarding/intents/original?dossier_id=alice-dossier')[1]['plan_id'],record['plan_id'])

    def test_trusted_cli_init_issue_revoke_without_project(self):
        import io
        from forge.project_proposal_grant import main
        output=io.StringIO();token=Path(self.temp.name)/'cli-private'
        with patch('sys.stdout',output):
            self.assertEqual(main(['--data-root',str(self.root),'init']),0)
            self.assertEqual(main(['--data-root',str(self.root),'issue','--principal-id','cli','--audience','synthetic-workspace','--dossier-id','cli-dossier','--permission','READ','--kind',KINDS[0],'--maximum-records','1','--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(token)]),0)
            grant_id=json.loads(output.getvalue().splitlines()[-1])['grant_id']
            self.assertEqual(main(['--data-root',str(self.root),'revoke','--grant-id',grant_id]),0)
        self.assertNotIn(token.read_text().strip(),output.getvalue())

    def test_corrupt_unselected_counter_cannot_enable_admission(self):
        status,plan=self.call('POST','/v1/onboarding/plans',self.body);self.assertEqual(status,200)
        original=read(self.grant.store)
        for replacement in ['not-a-record', {**original['records'][plan['plan_id']],'dossier_id':'foreign'}]:
            broken=deepcopy(original);broken['records'][plan['plan_id']]=replacement;write(self.grant.store,broken)
            self.assertEqual(self.call('POST','/v1/onboarding/plans',{**self.body,'operation_id':'new-original'})[0],503)
            self.assertEqual(read(self.grant.store),broken)
        write(self.grant.store,original);self.assertEqual(self.get(plan),(200,plan))

    def test_actual_database_writer_contention_is_http503_without_effect(self):
        import sqlite3
        lock=sqlite3.connect(self.root/'forge.db');lock.execute('BEGIN IMMEDIATE')
        try:
            status,body=self.call('POST','/v1/onboarding/plans',self.body)
            self.assertEqual(status,503);self.assertEqual(body['error']['code'],'PROPOSAL_UNAVAILABLE_OR_INVALID')
            self.assertEqual(read(self.grant.store)['records'],{})
        finally:lock.rollback();lock.close()
        self.assertEqual(self.call('POST','/v1/onboarding/plans',self.body)[0],200)

    def test_both_profiles_authority_child_exact_owning_bytes(self):
        from forge.project_bootstrap.service import render
        for role in ['authority','child']:
            for mode,profile in [('GENESIS','LOCAL_POSIX'),('MANAGED','GITHUB_DOCUMENTS')]:
                body=deepcopy(self.body);body['operation_id']=role+'-'+mode
                value=json.loads(Path('examples/project-bootstrap/'+role+'-input.json').read_text())
                value.update(mode=mode,host_profile=profile);body['input']=value
                status,plan=self.call('POST','/v1/onboarding/plans',body);self.assertEqual(status,200)
                actual={x['path']:x['content'].encode() for x in plan['result']['artifacts']}
                self.assertEqual(actual,render(value))
                self.assertEqual(self.get(plan),(200,plan))

    def test_finite_capacity_replay_and_readonly_grant(self):
        token=Path(self.temp.name)/'limited'
        self.grant.issue(principal_id='limited',audience='synthetic-workspace',dossier_ids=['limited-dossier'],permissions=['READ','PREPARE'],kinds=[KINDS[0]],maximum_records=1,expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=token)
        body={**self.body,'dossier_id':'limited-dossier'}
        first=self.call('POST','/v1/onboarding/plans',body,token=token.read_text().strip());self.assertEqual(first[0],200)
        self.assertEqual(self.call('POST','/v1/onboarding/plans',body,token=token.read_text().strip()),first)
        self.assertEqual(self.call('POST','/v1/onboarding/plans',{**body,'operation_id':'second'},token=token.read_text().strip())[0],409)
        reader=Path(self.temp.name)/'reader'
        self.grant.issue(principal_id='limited',audience='synthetic-workspace',dossier_ids=['limited-dossier'],permissions=['READ'],kinds=[KINDS[0]],maximum_records=1,expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=reader)
        self.assertEqual(self.call('POST','/v1/onboarding/plans',body,token=reader.read_text().strip())[0],403)
        status,cap=self.call('GET','/v1/onboarding/capability',token=reader.read_text().strip());self.assertEqual(status,200);self.assertNotIn('POST /v1/onboarding/plans',cap['operations'])

    def test_concurrent_original_once_and_closed_request(self):
        results=[]
        workers=[Thread(target=lambda:results.append(self.call('POST','/v1/onboarding/plans',self.body))) for _ in range(3)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(5)
        self.assertEqual(len(results),3);self.assertTrue(all(x==results[0] and x[0]==200 for x in results));self.assertEqual(len(read(self.grant.store)['records']),1)
        self.assertEqual(self.call('POST','/v1/onboarding/plans',{**self.body,'actor':'owner'})[0],400)
        self.assertEqual(self.call('GET','/v1/onboarding/capability?unknown=x')[0],400)
        self.assertEqual(self.call('GET','/v1/onboarding/intents/original?dossier_id=alice-dossier&dossier_id=other')[0],400)

    def test_real_operator_revoke_during_render_denies_commit(self):
        from forge.project_proposal_service import result
        entered=Event(); proceed=Event(); response=[]
        def paused(*args):
            entered.set(); self.assertTrue(proceed.wait(3)); return result(*args)
        with patch('forge.project_proposal_service.result',side_effect=paused):
            worker=Thread(target=lambda:response.append(self.call('POST','/v1/onboarding/plans',self.body)))
            worker.start(); self.assertTrue(entered.wait(3))
            with RuntimeBootstrap(data_root=self.root,forge_version='test').open() as db:
                owner=InstallationOperatorService(db,lambda:self.identity); owner.revoke(owner.context())
            proceed.set(); worker.join(5)
        self.assertEqual(response[0][0],403)
        self.assertEqual(read(self.grant.store)['records'],{})

    def test_operator_revocation_serialized_with_actual_publication_boundary(self):
        entered=Event(); proceed=Event(); completed=Event(); errors=[]
        def revoke():
            try:
                with RuntimeBootstrap(data_root=self.root,forge_version='test').open() as db:
                    owner=InstallationOperatorService(db,lambda:self.identity)
                    context=owner.context(); entered.set(); proceed.wait(3)
                    owner.revoke(context)
                completed.set()
            except Exception as error: errors.append(error)
        worker=Thread(target=revoke); worker.start(); self.assertTrue(entered.wait(3))
        with self.grant.boundary():
            proceed.set(); self.assertFalse(completed.wait(0.1))
        worker.join(5);self.assertFalse(errors);self.assertTrue(completed.is_set())
        self.assertEqual(self.call('GET','/v1/onboarding/capability')[0],401)

    def test_scope_legacy_audience_and_revocation(self):
        self.assertEqual(self.call('POST','/v1/onboarding/plans',self.body,token='synthetic-admin')[0],403)
        self.assertEqual(self.call('POST','/v1/onboarding/plans',self.body,audience='foreign')[0],403)
        self.assertEqual(self.call('GET','/v1/projects')[0],403)
        self.grant.revoke(self.issued['grant_id'])
        self.assertEqual(self.call('GET','/v1/onboarding/capability')[0],401)

if __name__=='__main__':unittest.main()
