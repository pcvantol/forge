"""Owning HTTP authority/CAS/history tests with actual private R52 proposal bytes."""
import json,os,sys,unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import UTC,datetime,timedelta
from threading import Thread
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from importlib.util import spec_from_file_location,module_from_spec
from forge.server_runtime import ForgeServerRuntime
from forge.proposal_content_grant import ProposalContentGrant
from forge.proposal_content_service import ProposalContentService
from forge.project_proposal_grant import ProjectProposalGrant
from forge.project_proposal_storage import read,write
from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter,NamedOperatorIdentity

ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('r54_fixture',ROOT/'scripts/qualification/proposal_content_fixture.py');fixture=module_from_spec(spec);spec.loader.exec_module(fixture)
spec=spec_from_file_location('r54_wire',ROOT/'scripts/qualification/qualify_installed_proposal_content_http.py');wire=module_from_spec(spec);spec.loader.exec_module(wire)
BASE='/v1/project-proposal-decisions'

class ProposalContentHttpTest(unittest.TestCase):
    def setUp(self):
        if sys.platform!='darwin':
            identity=NamedOperatorIdentity('r54-explicit-source-os-fixture',os.getuid());p=patch.object(MacOSGeneratedUIDIdentityAdapter,'resolve',return_value=identity);p.start();self.addCleanup(p.stop)
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()/'synthetic'
        self.setup=fixture.configure(self.root);self.grant=ProposalContentGrant(self.root/'runtime',self.setup['instance_id']);self.grant.initialize()
        self.expiry=(datetime.now(UTC)+timedelta(hours=1)).isoformat()
        self.grants={}
        for name,roles in [('business',['BUSINESS']),('architecture',['ARCHITECTURE']),('both',['BUSINESS','ARCHITECTURE']),('reader',[])]:
            self.grants[name]=self.grant.issue(principal_id=self.setup['human_principal_id'] if roles else 'synthetic-observer',audience='synthetic-workspace',proposal_principal_id='synthetic-service',dossier_ids=['synthetic-dossier'],permissions=['READ','DECIDE'] if roles else ['READ'],roles=roles,expires_at=self.expiry,token_path=self.root/(name+'.private'))
        self.runtime=ForgeServerRuntime(data_root=self.root/'runtime',credential_file=self.root/'admin.private',host='127.0.0.1',port=0)
        self.server=self.runtime.server;self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)
        self.source=json.loads((ROOT/'examples/project-bootstrap/authority-input.json').read_text())

    def stop(self):self.server.shutdown();self.thread.join(3);self.server.server_close()

    def call(self,method,path,body=None,token='both',audience='synthetic-workspace',headers=None):
        req=Request('http://127.0.0.1:'+str(self.server.server_port)+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+(self.root/(token+'.private')).read_text().strip(),'X-Forge-Content-Audience':audience,'Content-Type':'application/json',**(headers or {})})
        try:
            with urlopen(req,timeout=15) as response:status,value=response.status,json.loads(response.read())
        except HTTPError as error:
            try:status,value=error.code,json.loads(error.read())
            finally:error.close()
        if path.startswith(BASE):
            from jsonschema import Draft202012Validator
            schema=json.loads((ROOT/'forge/api/project-proposal-decisions-v1.json').read_text());Draft202012Validator(schema).validate(value)
            if body is not None and status==200:Draft202012Validator(schema).validate(body)
        return status,value

    def prepare(self,operation='prepare-original',source=None):
        r={'contract_version':'forge-project-proposal-http/v1','instance_id':self.setup['instance_id'],'dossier_id':'synthetic-dossier','operation_id':operation,'proposal_kind':'pb-render/1.0','input':source or self.source}
        status,plan=self.call('POST','/v1/onboarding/plans',r,token='prepare');self.assertEqual(status,200,plan)
        status,view=self.call('GET',BASE+'/proposals/'+plan['plan_id']+'?dossier_id=synthetic-dossier');self.assertEqual(status,200,view)
        return plan,view

    def test_valid_r52_duplicate_questions_and_opaque_source_are_not_new_blockers(self):
        source=json.loads(json.dumps(self.source));source['product']['open_questions']=['Which database later?','Which database later?'];source['source_references'][0]['reference']='design <draft> supplied verbatim'
        plan,view=self.prepare(source=source)
        r=wire.request_for(view,'BUSINESS','accept-original')
        status,decision=self.call('POST',BASE+'/decisions',r,token='business');self.assertEqual(status,200,decision)
        self.assertEqual(decision['original_decision']['request']['acknowledged_open_points'],source['product']['open_questions'])
        self.assertEqual(decision['subject']['source_references'],source['source_references'])

    def test_partial_full_changes_successor_and_immutable_original(self):
        plan,view=self.prepare();before=(self.root/'runtime/onboarding/proposals/store.json').read_bytes()
        r=wire.request_for(view,'BUSINESS','business-one');status,partial=self.call('POST',BASE+'/decisions',r,token='business');self.assertEqual(status,200,partial);self.assertEqual(partial['state'],'DECISION_NEEDED')
        a=wire.request_for(partial,'ARCHITECTURE','architecture-one');status,complete=self.call('POST',BASE+'/decisions',a,token='architecture');self.assertEqual(status,200,complete);self.assertEqual(complete['state'],'CONTENT_APPROVED');self.assertFalse(complete['effects_authorized'])
        change=wire.request_for(complete,'BUSINESS','changes');change['decision']='REQUEST_CHANGES';change['reason']='Clarify the intended first audience.'
        status,changed=self.call('POST',BASE+'/decisions',change,token='business');self.assertEqual(status,200,changed);self.assertEqual(changed['state'],'CHANGES_REQUESTED')
        accept=wire.request_for(changed,'BUSINESS','reapprove');status,final=self.call('POST',BASE+'/decisions',accept,token='business');self.assertEqual(status,200,final);self.assertEqual(final['state'],'CONTENT_APPROVED');self.assertEqual(len(final['history']),4)
        status,original=self.call('GET',BASE+'/intents/business-one?dossier_id=synthetic-dossier');self.assertEqual(status,200);self.assertEqual(original['original_decision'],partial['original_decision']);self.assertEqual(original['decision_revision'],4)
        self.assertEqual((self.root/'runtime/onboarding/proposals/store.json').read_bytes(),before)
        status,old=self.call('GET','/v1/onboarding/plans/'+plan['plan_id']+'?dossier_id=synthetic-dossier',token='prepare');self.assertEqual((status,old),(200,plan))
        _,new=self.prepare('same-bytes-new-id');self.assertEqual(new['decision_revision'],0);self.assertEqual(new['state'],'DECISION_NEEDED')
        source=json.loads(json.dumps(self.source));source['product']['purpose']='A materially different supplied goal.'
        _,newer=self.prepare('new-content',source);self.assertNotEqual(newer['subject']['input_digest'],view['subject']['input_digest']);self.assertEqual(newer['history'],[])

    def test_role_scope_actor_stale_subject_and_ack_denials(self):
        _,view=self.prepare();r=wire.request_for(view,'ARCHITECTURE','wrong-role')
        self.assertEqual(self.call('POST',BASE+'/decisions',r,token='business')[0],403)
        self.assertEqual(self.call('POST',BASE+'/decisions',r,token='reader')[0],403)
        self.assertEqual(self.call('POST',BASE+'/decisions',r,token='prepare')[0],403)
        self.assertEqual(self.call('POST',BASE+'/decisions',r,token='admin')[0],403)
        self.assertEqual(self.call('POST',BASE+'/decisions',r,audience='different-audience')[0],403)
        self.assertEqual(self.call('POST',BASE+'/decisions',r,headers={'X-Actor':'owner','X-Role':'ARCHITECTURE'})[0],400)
        for key,value,expected in [('dossier_id','foreign-dossier',403),('instance_id','foreign-instance',403),('role','SECURITY',400),('actor','forged',400),('acknowledged_open_points',[],409)]:
            bad={**r,key:value};status,out=self.call('POST',BASE+'/decisions',bad);self.assertEqual(status,expected,out)
        bad=json.loads(json.dumps(r));bad['subject']['result_digest']='f'*64;self.assertEqual(self.call('POST',BASE+'/decisions',bad)[0],409)
        status,first=self.call('POST',BASE+'/decisions',r);self.assertEqual(status,200,first)
        self.assertEqual(self.call('POST',BASE+'/decisions',{**r,'operation_id':'new-stale'})[0],409)
        self.assertEqual(self.call('POST',BASE+'/decisions',{**r,'reason':'Changed same operation bytes.'})[0],409)
        self.assertEqual(len(self.grant._store()['records']),1)
        self.assertEqual(self.call('GET','/v1/onboarding/capability')[0],403)
        self.assertEqual(self.call('GET',BASE+'/not-an-operation')[0],404)
        self.assertEqual(self.call('GET',BASE+'/capability?extra=value')[0],404)
        self.assertEqual(self.call('GET',BASE+'/capability',headers={'X-Forge-Proposal-Audience':'ambiguous'})[0],400)

    def test_identical_concurrency_and_distinct_same_key_conflict_are_single_commit(self):
        from concurrent.futures import ThreadPoolExecutor
        _,view=self.prepare();r=wire.request_for(view,'BUSINESS','concurrent')
        with ThreadPoolExecutor(max_workers=2) as pool:answers=list(pool.map(lambda _:self.call('POST',BASE+'/decisions',r),range(2)))
        self.assertEqual([s for s,_ in answers],[200,200]);self.assertEqual(answers[0][1]['original_decision'],answers[1][1]['original_decision']);self.assertEqual(len(self.grant._store()['records']),1)
        r=wire.request_for(answers[0][1],'ARCHITECTURE','concurrent-changed')
        with ThreadPoolExecutor(max_workers=2) as pool:answers=list(pool.map(lambda x:self.call('POST',BASE+'/decisions',x),[r,{**r,'reason':'Different bytes, same key.'}]))
        self.assertEqual(sorted(s for s,_ in answers),[200,409]);self.assertEqual(len(self.grant._store()['records']),2)

    def test_missing_corrupt_initialized_own_and_source_store_never_empty_history(self):
        _,view=self.prepare();r=wire.request_for(view,'BUSINESS','retained');self.assertEqual(self.call('POST',BASE+'/decisions',r)[0],200)
        for path in [self.grant.store,self.grant.witness,self.root/'runtime/onboarding/proposals/store.json']:
            original=path.read_bytes()
            for failure in ('missing','corrupt'):
                if failure=='missing':path.unlink()
                else:path.write_bytes(b'{"corrupt":true}');path.chmod(0o600)
                status,body=self.call('GET',BASE+'/intents/retained?dossier_id=synthetic-dossier');self.assertNotEqual(status,200,body);self.assertNotEqual(status,404,body)
                path.write_bytes(original);path.chmod(0o600)
                status,restored=self.call('GET',BASE+'/intents/retained?dossier_id=synthetic-dossier');self.assertEqual(status,200,restored);self.assertEqual(restored['decision_revision'],1)
        store=self.grant._store();original=self.grant.store.read_bytes();key=next(iter(store['records']));store['records'][key]['revision']=7;self.grant.save_store(store)
        self.assertNotEqual(self.call('GET',BASE+'/capability')[0],200)
        self.grant.store.write_bytes(original);self.grant.store.chmod(0o600)

    def test_current_revoke_expiry_human_authority_and_historical_record_are_distinct(self):
        from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
        _,view=self.prepare();r=wire.request_for(view,'BUSINESS','historical');status,first=self.call('POST',BASE+'/decisions',r,token='business');self.assertEqual(status,200,first)
        self.grant.revoke(self.grants['business']['grant_id']);self.assertIn(self.call('GET',BASE+'/capability',token='business')[0],(401,403))
        status,history=self.call('GET',BASE+'/proposals/'+view['plan_id']+'?dossier_id=synthetic-dossier',token='reader');self.assertEqual(status,200,history);self.assertEqual(history['history'][0],first['original_decision'])
        records=self.grant._records();row=next(x for x in records if x['grant_id']==self.grants['architecture']['grant_id']);row['expires_at']='2000-01-01T00:00:00+00:00';self.grant.save_records(records)
        self.assertIn(self.call('GET',BASE+'/capability',token='architecture')[0],(401,403))
        with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root/'runtime')) as runtime:
            installation=runtime.repository.operators.context().installation_id
        import sqlite3
        with closing(sqlite3.connect(self.root/'runtime/forge.db')) as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM governance_authority WHERE installation_id=? AND capability=?',(installation,'BUSINESS_APPROVAL'))
        from forge.runtime.bootstrap import RuntimeBootstrap
        from forge.operator_identity import InstallationOperatorService
        before=self.grant.store.read_bytes()
        with RuntimeBootstrap(data_root=self.root/'runtime').open() as db:
            owner=InstallationOperatorService(db,MacOSGeneratedUIDIdentityAdapter().resolve);owner.revoke(owner.context())
        self.assertIn(self.call('GET',BASE+'/capability',token='both')[0],(401,403))
        self.assertIn(self.call('GET',BASE+'/proposals/'+view['plan_id']+'?dossier_id=synthetic-dossier',token='reader')[0],(401,403))
        self.assertEqual(self.grant.store.read_bytes(),before)
        with patch.object(MacOSGeneratedUIDIdentityAdapter,'resolve',return_value=NamedOperatorIdentity('foreign-human',os.getuid())):
            self.assertIn(self.call('GET',BASE+'/capability',token='reader')[0],(401,403))

    def test_revoke_after_commit_and_newer_decision_before_publication_deny_late_body(self):
        _,view=self.prepare();r=wire.request_for(view,'BUSINESS','late');original=ProposalContentService.submit
        def revoke_after(service,*args):
            result=original(service,*args);self.grant.revoke(self.grants['both']['grant_id']);return result
        with patch.object(ProposalContentService,'submit',revoke_after):
            status,body=self.call('POST',BASE+'/decisions',r);self.assertNotEqual(status,200,body);self.assertNotIn('original_decision',body)
        self.assertEqual(len(self.grant._store()['records']),1)
        status,current=self.call('GET',BASE+'/proposals/'+view['plan_id']+'?dossier_id=synthetic-dossier',token='reader');self.assertEqual(status,200,current)
        r=wire.request_for(current,'BUSINESS','newer-before-publication')
        def supersede_after(service,*args):
            result=original(service,*args)
            auth='Bearer '+(self.root/'architecture.private').read_text().strip();other=wire.request_for(result,'ARCHITECTURE','competing-newer')
            original(ProposalContentService(self.grant),auth,'synthetic-workspace',other);return result
        with patch.object(ProposalContentService,'submit',supersede_after):
            status,body=self.call('POST',BASE+'/decisions',r,token='business');self.assertNotEqual(status,200,body);self.assertNotIn('history',body)
        self.assertEqual(len(self.grant._store()['records']),3)

    def test_actual_real_time_expiry_and_finite_capacity_without_eviction(self):
        import time
        _,view=self.prepare();expiry=(datetime.now(UTC)+timedelta(seconds=2)).isoformat()
        self.grant.issue(principal_id='expiring-viewer',audience='synthetic-workspace',proposal_principal_id='synthetic-service',dossier_ids=['synthetic-dossier'],permissions=['READ'],roles=[],expires_at=expiry,token_path=self.root/'expiring.private')
        self.assertEqual(self.call('GET',BASE+'/capability',token='expiring')[0],200)
        time.sleep(2.1);self.assertIn(self.call('GET',BASE+'/capability',token='expiring')[0],(401,403))
        for n in range(8):
            r=wire.request_for(view,'BUSINESS' if n%2==0 else 'ARCHITECTURE','capacity-'+str(n));status,view=self.call('POST',BASE+'/decisions',r);self.assertEqual(status,200,view)
        self.assertEqual(view['decision_revision'],8);self.assertEqual(len(self.grant._store()['records']),8)
        r=wire.request_for(view,'BUSINESS','ninth');self.assertNotEqual(self.call('POST',BASE+'/decisions',r)[0],200)
        status,first=self.call('GET',BASE+'/intents/capacity-0?dossier_id=synthetic-dossier');self.assertEqual(status,200,first);self.assertEqual(first['original_decision']['revision'],1)

    def test_finite_owner_grant_does_not_delegate_an_unrelated_human_or_scope(self):
        args={'principal_id':'invented-human','audience':'synthetic-workspace','proposal_principal_id':'synthetic-service','dossier_ids':['synthetic-dossier'],'permissions':['READ','DECIDE'],'roles':['BUSINESS'],'expires_at':self.expiry,'token_path':self.root/'bad.private'}
        with self.assertRaises(PermissionError):self.grant.issue(**args)
        for change in ({'roles':[]},{'dossier_ids':[]},{'permissions':['DECIDE']},{'roles':['SECURITY']},{'expires_at':'2000-01-01T00:00:00+00:00'}):
            with self.subTest(change=change),self.assertRaises((ValueError,PermissionError)):self.grant.issue(**{**args,**change})
        with self.assertRaises(PermissionError):self.grant.issue(**{**args,'principal_id':self.setup['human_principal_id'],'proposal_principal_id':'other-service'})
        with self.assertRaises(ValueError):self.grant.issue(**{**args,'principal_id':self.setup['human_principal_id'],'token_path':self.grant.store})
        self.assertFalse((self.root/'bad.private').exists())

    def test_unsupported_managed_profile_does_not_gain_content_approval(self):
        value=json.loads(json.dumps(self.source));value.update(mode='MANAGED',host_profile='GITHUB_DOCUMENTS')
        r={'contract_version':'forge-project-proposal-http/v1','instance_id':self.setup['instance_id'],'dossier_id':'synthetic-dossier','operation_id':'managed','proposal_kind':'pb-render/1.0','input':value}
        status,plan=self.call('POST','/v1/onboarding/plans',r,token='prepare');self.assertEqual(status,200,plan)
        status,body=self.call('GET',BASE+'/proposals/'+plan['plan_id']+'?dossier_id=synthetic-dossier');self.assertEqual(status,409,body);self.assertEqual(body['error']['code'],'CONTENT_PROFILE_UNSUPPORTED')
        self.assertEqual(len(self.grant._store()['records']),0)

    def test_cli_parity_owner_issue_read_decide_revoke_closed_errors(self):
        from forge.proposal_content_cli import main
        from contextlib import redirect_stdout
        from io import StringIO
        def cli(*args):
            stream=StringIO()
            with redirect_stdout(stream):code=main(['--data-root',str(self.root/'runtime'),*args])
            return code,json.loads(stream.getvalue()) if stream.getvalue() else None
        _,view=self.prepare();self.assertEqual(cli('init')[0],0)
        args=['--token-file',str(self.root/'both.private'),'--audience','synthetic-workspace']
        code,cap=cli('capability',*args);self.assertEqual(code,0);self.assertEqual(cap['profile']['required_roles'],['BUSINESS','ARCHITECTURE'])
        code,actual=cli('read',*args,'--dossier-id','synthetic-dossier','--plan-id',view['plan_id']);self.assertEqual((code,actual),(0,view))
        r=wire.request_for(view,'BUSINESS','cli-decision');f=self.root/'request.private';f.write_text(json.dumps(r));f.chmod(0o600)
        code,result=cli('decide',*args,'--request-file',str(f));self.assertEqual(code,0,result)
        code,again=cli('intent',*args,'--dossier-id','synthetic-dossier','--operation-id','cli-decision');self.assertEqual(code,0,again);self.assertEqual(again['original_decision'],result['original_decision'])
        token=self.root/'cli-reader.private'
        code,issued=cli('issue','--principal-id','cli-observer','--proposal-principal-id','synthetic-service','--audience','synthetic-workspace','--expires-at',self.expiry,'--token-file',str(token),'--dossier-id','synthetic-dossier','--permission','READ');self.assertEqual(code,0,issued);self.assertNotIn(token.read_text().strip(),json.dumps(issued))
        self.assertEqual(cli('revoke','--grant-id',issued['grant_id'])[0],0)
        self.assertEqual(cli('capability','--token-file',str(token),'--audience','synthetic-workspace')[0],1)
        with patch('forge.proposal_content_cli.publish_cli',side_effect=OSError('closed publication failure')):
            self.assertEqual(cli('read',*args,'--dossier-id','synthetic-dossier','--plan-id',view['plan_id']),(1,None))
        f.write_text('{}');self.assertEqual(cli('decide',*args,'--request-file',str(f))[0],1)
        f.write_text('x'*257);f.chmod(0o600);self.assertEqual(cli('capability','--token-file',str(f),'--audience','synthetic-workspace')[0],1)

    def test_slow_request_body_holds_no_authority_lock_and_revoke_prevents_commit(self):
        import socket,time
        from threading import Event
        from http.client import HTTPResponse
        _,view=self.prepare();r=wire.request_for(view,'BUSINESS','late-body');raw=json.dumps(r).encode();ready=Event()
        handler=self.server.RequestHandlerClass;original=handler._body
        def observed(instance):ready.set();return original(instance)
        token=(self.root/'both.private').read_text().strip()
        header=('POST '+BASE+'/decisions HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+token+'\r\nX-Forge-Content-Audience: synthetic-workspace\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw))+'\r\nConnection: close\r\n\r\n').encode()
        with patch.object(handler,'_body',observed),socket.create_connection(('127.0.0.1',self.server.server_port),timeout=5) as client:
            client.sendall(header);self.assertTrue(ready.wait(2));start=time.monotonic();self.grant.revoke(self.grants['both']['grant_id']);self.assertLess(time.monotonic()-start,1)
            client.sendall(raw);response=HTTPResponse(client);response.begin();body=json.loads(response.read());self.assertIn(response.status,(401,403));self.assertNotIn('original_decision',body)
        self.assertEqual(len(self.grant._store()['records']),0)

    def test_genuine_old_r53_advise_token_has_no_content_decision_right(self):
        spec=spec_from_file_location('r53_existing_fixture',ROOT/'scripts/qualification/concept_advisory_fixture.py');old=module_from_spec(spec);spec.loader.exec_module(old)
        root=Path(self.tmp.name).resolve()/'old-advice-instance';grant=old.configure(root)
        runtime=ForgeServerRuntime(data_root=root/'runtime',credential_file=root/'admin.private',host='127.0.0.1',port=0,provider_id='concept-fixture')
        thread=Thread(target=runtime.server.serve_forever,daemon=True);thread.start()
        try:
            token=(root/'alice.private').read_text().strip();self.assertIsNotNone(grant.authenticate('Bearer '+token))
            req=Request('http://127.0.0.1:'+str(runtime.server.server_port)+BASE+'/capability',headers={'Authorization':'Bearer '+token,'X-Forge-Content-Audience':'synthetic-workspace'})
            with self.assertRaises(HTTPError) as caught:urlopen(req,timeout=5)
            try:self.assertEqual(caught.exception.code,403);self.assertEqual(json.loads(caught.exception.read())['error']['code'],'CONTENT_SCOPE_DENIED')
            finally:caught.exception.close()
            self.assertFalse((root/'provider-requests.private.jsonl').exists())
        finally:runtime.server.shutdown();thread.join(3);runtime.server.server_close()
