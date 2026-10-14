import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from contextlib import contextmanager
from importlib.util import spec_from_file_location,module_from_spec
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from forge.server_runtime import ForgeServerRuntime
from forge.concept_advisory_contract import digest
from tests.test_concept_advisory_contract import example
spec=spec_from_file_location('concept_fixture',Path(__file__).resolve().parents[1]/'scripts/qualification/concept_advisory_fixture.py')
fixture=module_from_spec(spec);spec.loader.exec_module(fixture)

@contextmanager
def http(root):
    runtime=ForgeServerRuntime(data_root=root/'runtime',credential_file=root/'admin.private',host='127.0.0.1',port=0,provider_id='concept-fixture')
    thread=Thread(target=runtime.server.serve_forever,daemon=True);thread.start()
    try:yield runtime.server.server_address[1]
    finally:runtime.server.shutdown();thread.join(3);runtime.server.server_close()

def call(port,token,method,path,body=None,audience='synthetic-workspace'):
    r=Request('http://127.0.0.1:'+str(port)+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token.read_text().strip(),'X-Forge-Concept-Audience':audience,'Content-Type':'application/json'})
    try:
        with urlopen(r,timeout=15) as response:
            value=json.loads(response.read())
            if path.startswith('/v1/concept-advisory/'):
                from jsonschema import Draft202012Validator
                schema=json.loads((Path(__file__).resolve().parents[1]/'forge/api/concept-advisory-v1.json').read_text())
                Draft202012Validator(schema).validate(value)
                if body is not None:Draft202012Validator(schema).validate(body)
            return response.status,value
    except HTTPError as error:
        try:return error.code,json.loads(error.read())
        finally:error.close()

class ConceptHttpTest(unittest.TestCase):
    def setUp(self):
        import sys,os
        if sys.platform != "darwin":
            from unittest.mock import patch
            from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter,NamedOperatorIdentity
            fixture_identity=NamedOperatorIdentity("r53-source-test-modeled-os",os.getuid())
            guard=patch.object(MacOSGeneratedUIDIdentityAdapter,"resolve",return_value=fixture_identity)
            guard.start();self.addCleanup(guard.stop)

    def test_business_updated_briefing_architecture_exact_replay_and_restart(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';fixture.configure(root)
            with http(root) as port:
                alice=root/'alice.private';status,cap=call(port,alice,'GET','/v1/concept-advisory/capability');self.assertEqual(status,200,cap)
                r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'])
                status,out=call(port,alice,'POST','/v1/concept-advisory/turns',r);self.assertEqual(status,200,out);self.assertEqual(out['original_turn']['status'],'COMPLETE',out)
                self.assertEqual(call(port,alice,'POST','/v1/concept-advisory/turns',r)[1]['original_turn'],out['original_turn'])
                revised=json.loads(json.dumps(r));revised.update(operation_id='second',turn_id='second',advisor_kind='ARCHITECTURE',expected_revision=1)
                revised['briefing']['revision']=2;revised['briefing']['fields']['users']='Explicitly accepted local volunteers';revised['briefing_digest']=digest(revised['briefing'])
                status,arch=call(port,alice,'POST','/v1/concept-advisory/turns',revised);self.assertEqual(status,200,arch);self.assertEqual(arch['original_turn']['status'],'COMPLETE',arch)
                self.assertEqual(call(port,root/'bob.private','GET','/v1/concept-advisory/history?dossier_id=dossier-alice&conversation_id=conversation-alice')[0],403)
                self.assertEqual(call(port,root/'admin.private','GET','/v1/concept-advisory/capability')[0],403)
                self.assertEqual(call(port,alice,'GET','/v1/onboarding/capability')[0],403)
                self.assertEqual(call(port,alice,'GET','/v1/concept-advisory/capability',audience='foreign')[0],403)
            with http(root) as port:
                recovered=call(port,alice,'GET','/v1/concept-advisory/intents/operation-one?dossier_id=dossier-alice&conversation_id=conversation-alice')
                self.assertEqual(recovered[0],200,recovered);self.assertEqual(recovered[1]['original_turn'],out['original_turn'])
            calls=[json.loads(line) for line in (root/'provider-requests.private.jsonl').read_text().splitlines()]
            self.assertEqual(len(calls),2);self.assertEqual(calls[1]['prior_turns'][0]['request'],r)
            self.assertEqual(calls[1]['request']['briefing']['revision'],2)

    def test_uncertain_timeout_invalid_model_and_no_regeneration(self):
        for fault in ('timeout','inject','foreign'):
            with self.subTest(fault=fault),TemporaryDirectory() as tmp:
                root=Path(tmp).resolve()/'synthetic';fixture.configure(root);(root/'fault.private').write_text(fault)
                with http(root) as port:
                    token=root/'alice.private';_,cap=call(port,token,'GET','/v1/concept-advisory/capability')
                    r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'])
                    status,out=call(port,token,'POST','/v1/concept-advisory/turns',r);self.assertEqual(status,200,out)
                    self.assertEqual(out['original_turn']['status'],'UNCERTAIN' if fault=='timeout' else 'FAILED');self.assertIsNone(out['original_turn']['outcome']['output'])
                    self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',r)[1]['original_turn'],out['original_turn'])
                    newer={**r,'operation_id':'newer','turn_id':'newer','expected_revision':1}
                    status,new=call(port,token,'POST','/v1/concept-advisory/turns',newer)
                    self.assertEqual(status,409 if fault=='timeout' else 200,new)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1 if fault=='timeout' else 2)

    def test_current_start_revocation_and_publication_revoke(self):
        from unittest.mock import patch
        from forge.concept_advisory_provider import ConceptAdvisoryProvider
        for boundary in ('start','after-result'):
            with self.subTest(boundary=boundary),TemporaryDirectory() as tmp:
                root=Path(tmp).resolve()/'synthetic';grant=fixture.configure(root)
                record=next(x for x in grant._records() if x['principal_id']=='alice')
                with http(root) as port:
                    token=root/'alice.private';_,cap=call(port,token,'GET','/v1/concept-advisory/capability')
                    r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'])
                    if boundary=='start':
                        original=ConceptAdvisoryProvider.commit_transport
                        def replaced(provider,*args):
                            grant.revoke(record['grant_id']);return original(provider,*args)
                        with patch.object(ConceptAdvisoryProvider,'commit_transport',replaced):
                            self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',r)[0],403)
                        self.assertFalse((root/'provider-requests.private.jsonl').exists())
                    else:
                        original=ConceptAdvisoryProvider.validate_output
                        def replaced(provider,*args):
                            output=original(provider,*args);grant.revoke(record['grant_id']);return output
                        with patch.object(ConceptAdvisoryProvider,'validate_output',replaced):
                            self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',r)[0],403)
                        self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
                        self.assertEqual(next(iter(grant._store()['records'].values()))['status'],'COMPLETE')
                    self.assertEqual(call(port,token,'GET','/v1/concept-advisory/history?dossier_id=dossier-alice&conversation_id=conversation-alice')[0],401)

    def test_quota_unchanged_operator_source_conflicts_and_storage_failure(self):
        from datetime import UTC,datetime,timedelta
        from forge.concept_advisory_service import provider_profile
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';grant=fixture.configure(root)
            profile=provider_profile(root/'runtime','concept-fixture')
            with self.assertRaises(PermissionError):
                grant.issue(principal_id='alice',audience='synthetic-workspace',dossier_ids=['new-dossier'],conversation_ids=['new-conversation'],permissions=['READ','ADVISE'],maximum_turns=7,maximum_tokens=384000,maximum_seconds=16,provider_id='concept-fixture',transfer_policy_digest=profile['transfer_policy_digest'],expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=root/'new.private')
            with http(root) as port:
                token=root/'alice.private';_,cap=call(port,token,'GET','/v1/concept-advisory/capability')
                r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'])
                self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',{**r,'transfer_policy_digest':digest({})})[0],403)
                self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',r)[0],200)
                for changed in ({**r,'message':'Different'}, {**r,'operation_id':'new'}, {**r,'operation_id':'new','turn_id':'new','expected_revision':0}):
                    self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',changed)[0],409)
                revised=json.loads(json.dumps(r));revised.update(operation_id='new',turn_id='new',expected_revision=1);revised['briefing']['fields']['users']='Silently changed';revised['briefing_digest']=digest(revised['briefing'])
                self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',revised)[0],409)
                original=grant.store.read_bytes();grant.store.write_text('{}');grant.store.chmod(0o600)
                self.assertNotEqual(call(port,token,'GET','/v1/concept-advisory/history?dossier_id=dossier-alice&conversation_id=conversation-alice')[0],200)
                grant.store.write_bytes(original)
                grant.store.unlink();self.assertEqual(call(port,token,'GET','/v1/concept-advisory/history?dossier_id=dossier-alice&conversation_id=conversation-alice')[0],503)
                self.assertFalse(grant.store.exists());grant.store.write_bytes(original);grant.store.chmod(0o600)
                self.assertEqual(call(port,token,'GET','/v1/concept-advisory/history?dossier_id=dossier-alice&conversation_id=conversation-alice')[0],200)

    def test_principal_budget_survives_owner_issued_new_audience_and_conversation(self):
        from datetime import UTC,datetime,timedelta
        from forge.concept_advisory_service import provider_profile
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';grant=fixture.configure(root);profile=provider_profile(root/'runtime','concept-fixture')
            def issue(audience,dossier,conversation,token):
                return grant.issue(principal_id='charlie',audience=audience,dossier_ids=[dossier],conversation_ids=[conversation],permissions=['READ','ADVISE'],maximum_turns=1,maximum_tokens=48000,maximum_seconds=2,provider_id='concept-fixture',transfer_policy_digest=profile['transfer_policy_digest'],expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=token)
            issue('synthetic-workspace','charlie-a','conversation-a',root/'charlie-a.private')
            with http(root) as port:
                _,cap=call(port,root/'charlie-a.private','GET','/v1/concept-advisory/capability')
                r=example();r.update(instance_id=cap['instance_id'],dossier_id='charlie-a',conversation_id='conversation-a',transfer_policy_digest=profile['transfer_policy_digest'])
                self.assertEqual(call(port,root/'charlie-a.private','POST','/v1/concept-advisory/turns',r)[0],200)
                issue('new-workspace','charlie-b','conversation-b',root/'charlie-b.private')
                r.update(operation_id='other',turn_id='other',dossier_id='charlie-b',conversation_id='conversation-b')
                status,error=call(port,root/'charlie-b.private','POST','/v1/concept-advisory/turns',r,audience='new-workspace')
                self.assertEqual(status,409,error);self.assertEqual(error['error']['code'],'CONCEPT_QUOTA_EXHAUSTED')
            self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_actual_canonical_policy_change_before_prepare_denies_old_transfer(self):
        from unittest.mock import patch
        from forge.concept_advisory_provider import ConceptAdvisoryProvider
        from forge.worklist_control import control_runtime
        from forge.provider_security import PlanningProviderSecurityService,ProviderAuthenticationMode,CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,CODEX_CLI_CHATGPT_SESSION_TYPE
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';grant=fixture.configure(root)
            with http(root) as port:
                _,cap=call(port,root/'alice.private','GET','/v1/concept-advisory/capability')
                r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'])
                from forge.concept_advisory_service import provider_profile
                original=provider_profile
                def changed(*args):
                    old=original(*args)
                    with control_runtime(root/'runtime') as runtime:
                        operators=runtime.repository.operators
                        PlanningProviderSecurityService(runtime.database,None,operators).configure(configuration_id='synthetic-config',provider_id='concept-fixture',operator_context=operators.context(),expected_version=1,
                          authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
                          executable_path=str(root/'external-provider'),adapter_version='codex-cli-chatgpt-session-v1',profile='explicit-synthetic-profile',timeout_seconds=2,input_token_bound=41000,context_token_bound=49000,output_token_bound=8000)
                    return old
                with patch('forge.concept_advisory_service.provider_profile',changed):
                    status,error=call(port,root/'alice.private','POST','/v1/concept-advisory/turns',r)
                self.assertEqual(status,403,error);self.assertFalse((root/'provider-requests.private.jsonl').exists());self.assertEqual(grant._store()['records'],{})

    def test_owning_cli_issue_submit_private_parity_revoke_and_errors(self):
        from unittest.mock import patch
        from io import StringIO
        from datetime import UTC,datetime,timedelta
        from forge.concept_advisory_cli import main
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';grant=fixture.configure(root)
            prefix=['--data-root',str(root/'runtime')]
            def cli(args,expected=0):
                with patch('sys.stdout',new_callable=StringIO) as output:
                    self.assertEqual(main(prefix+args),expected);return json.loads(output.getvalue())
            self.assertEqual(cli(['init'])['state'],'PRIVATE_CONCEPT_ADVICE_INITIALIZED')
            profile=cli(['provider-profile','--provider-id','concept-fixture'])
            token=root/'cli.private'
            issued=cli(['issue','--principal-id','cli-principal','--audience','synthetic-workspace','--provider-id','concept-fixture','--transfer-policy-digest',profile['transfer_policy_digest'],'--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(token),'--dossier-id','cli-dossier','--conversation-id','cli-conversation','--permission','READ','--permission','ADVISE','--maximum-turns','2','--maximum-tokens','96000','--maximum-seconds','4'])
            self.assertNotIn(token.read_text().strip(),json.dumps(issued));auth=['--token-file',str(token),'--audience','synthetic-workspace']
            cap=cli(['capability',*auth]);r=example();r.update(instance_id=cap['instance_id'],dossier_id='cli-dossier',conversation_id='cli-conversation',transfer_policy_digest=profile['transfer_policy_digest'])
            file=root/'request.private.json';file.write_text(json.dumps(r));file.chmod(0o600)
            output=cli(['submit',*auth,'--request-file',str(file)]);self.assertEqual(output['original_turn']['status'],'COMPLETE')
            self.assertEqual(cli(['intent',*auth,'--dossier-id','cli-dossier','--conversation-id','cli-conversation','--operation-id','operation-one'])['original_turn'],output['original_turn'])
            self.assertEqual(cli(['history',*auth,'--dossier-id','cli-dossier','--conversation-id','cli-conversation'])['revision'],1)
            self.assertEqual(cli(['revoke','--grant-id',issued['grant_id']])['state'],'REVOKED')
            cli(['capability',*auth],expected=1)
            cli(['provider-profile','--provider-id','unconfigured'],expected=1)

    def test_finite_grant_issue_limits_and_current_read_only_no_model_right(self):
        from datetime import UTC,datetime,timedelta
        from forge.concept_advisory_service import provider_profile
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';grant=fixture.configure(root);profile=provider_profile(root/'runtime','concept-fixture')
            args=dict(principal_id='limited',audience='synthetic-workspace',dossier_ids=['limited'],conversation_ids=['limited'],permissions=['READ'],maximum_turns=2,maximum_tokens=96000,maximum_seconds=4,provider_id='concept-fixture',transfer_policy_digest=profile['transfer_policy_digest'],expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=root/'limited.private')
            for field,bad in [('dossier_ids',[]),('conversation_ids',['duplicate','duplicate']),('permissions',['PREPARE']),('maximum_turns',True),('maximum_tokens',384001),('maximum_seconds',961),('expires_at',(datetime.now(UTC)-timedelta(hours=1)).isoformat()),('transfer_policy_digest',digest({})),('token_path',grant.store.parent/'bad.private')]:
                with self.subTest(field=field),self.assertRaises((ValueError,PermissionError)):grant.issue(**{**args,field:bad})
            grant.issue(**args)
            with http(root) as port:
                token=root/'limited.private';_,cap=call(port,token,'GET','/v1/concept-advisory/capability')
                self.assertEqual(cap['permissions'],['READ']);r=example();r.update(instance_id=cap['instance_id'],dossier_id='limited',conversation_id='limited',transfer_policy_digest=profile['transfer_policy_digest'])
                self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',r)[0],403)
                self.assertEqual(call(port,token,'GET','/v1/concept-advisory/intents/unknown?dossier_id=limited&conversation_id=limited')[0],404)
                self.assertEqual(call(port,token,'GET','/v1/concept-advisory/unknown')[0],404)
            self.assertFalse((root/'provider-requests.private.jsonl').exists())

    def test_five_language_provider_route_preserves_original_messages(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';fixture.configure(root)
            messages={'en':'Who is the first audience?','nl':'Wie is de eerste doelgroep?','de':'Wer ist die erste Zielgruppe?','fr':'Quel est le premier public ?','es':'¿Cuál es el primer público?'}
            with http(root) as port:
                _,cap=call(port,root/'alice.private','GET','/v1/concept-advisory/capability')
                for index,(language,message) in enumerate(messages.items()):
                    r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'],language=language,message=message,operation_id='language-'+language,turn_id='language-'+language,expected_revision=index)
                    status,output=call(port,root/'alice.private','POST','/v1/concept-advisory/turns',r);self.assertEqual(status,200,output)
                    self.assertEqual(output['original_turn']['request']['message'],message);self.assertEqual(output['original_turn']['outcome']['output']['language'],language)
                calls=[json.loads(line) for line in (root/'provider-requests.private.jsonl').read_text().splitlines()]
                self.assertEqual([v['request']['message'] for v in calls],list(messages.values()))

    def test_concurrent_existing_turn_is_read_only_without_mutating_runtime(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';fixture.configure(root)
            with http(root) as port:
                token=root/'alice.private';_,cap=call(port,token,'GET','/v1/concept-advisory/capability')
                r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'])
                _,original=call(port,token,'POST','/v1/concept-advisory/turns',r)
                with patch('forge.concept_advisory_service.control_runtime',side_effect=AssertionError('read replay must not open mutating composition')):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        replies=list(pool.map(lambda _:call(port,token,'POST','/v1/concept-advisory/turns',r),range(2)))
                self.assertEqual([status for status,_ in replies],[200,200],replies)
                self.assertTrue(all(body['original_turn']==original['original_turn'] for _,body in replies))
            self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_cli_actual_profile_drift_and_revocation_before_output_denies_private_bytes(self):
        from io import StringIO
        from unittest.mock import patch
        from forge.concept_advisory_cli import main
        from forge.concept_advisory_service import ConceptAdvisoryService,profile_from_policy
        from dataclasses import replace
        from forge.worklist_control import control_runtime
        from forge.concept_advisory_provider import ConceptAdvisoryProvider
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';grant=fixture.configure(root)
            with http(root) as port:
                token=root/'alice.private';_,cap=call(port,token,'GET','/v1/concept-advisory/capability')
                r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'])
                self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',r)[0],200)
            args=['--data-root',str(root/'runtime'),'intent','--token-file',str(token),'--audience','synthetic-workspace','--dossier-id','dossier-alice','--conversation-id','conversation-alice','--operation-id','operation-one']
            with control_runtime(root/'runtime') as runtime:
                policy=ConceptAdvisoryProvider(runtime,'concept-fixture').configuration.current_policy()
            changed=profile_from_policy(replace(policy,version=policy.version+1))
            with patch('forge.concept_advisory_service.provider_profile',return_value=changed),patch('sys.stdout',new_callable=StringIO) as output:
                self.assertEqual(main(args),1);self.assertNotIn('original_turn',output.getvalue())
            original=ConceptAdvisoryService.read
            def revoked(service,*values,**kw):
                doc=original(service,*values,**kw);grant.revoke(next(x['grant_id'] for x in grant._records() if x['principal_id']=='alice'));return doc
            with patch.object(ConceptAdvisoryService,'read',revoked),patch('sys.stdout',new_callable=StringIO) as output:
                self.assertEqual(main(args),1);self.assertNotIn('original_turn',output.getvalue())

    def test_cli_real_nonblocking_descriptor_publication_and_bounded_wait(self):
        from unittest.mock import patch
        from forge.concept_advisory_cli import publish_cli
        from forge.concept_advisory_service import ConceptAdvisoryService
        from threading import Thread
        import os,time
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';grant=fixture.configure(root);authorization='Bearer '+(root/'alice.private').read_text().strip()
            document=ConceptAdvisoryService(grant).capability(authorization,'synthetic-workspace')
            readfd,writefd=os.pipe();received=[]
            def consume():
                with os.fdopen(readfd,'rb') as reader:received.append(reader.read())
            thread=Thread(target=consume);thread.start()
            with os.fdopen(writefd,'w') as stream,patch('sys.stdout',stream):
                publish_cli(grant,authorization,'synthetic-workspace',document);self.assertTrue(os.get_blocking(writefd))
            thread.join(3);self.assertFalse(thread.is_alive());self.assertEqual(json.loads(received[0]),document)
            readfd,writefd=os.pipe()
            try:
                with os.fdopen(writefd,'w') as stream,patch('sys.stdout',stream),patch('forge.concept_advisory_cli.select.select',return_value=([],[],[])):
                    started=time.monotonic()
                    with self.assertRaises(TimeoutError):publish_cli(grant,authorization,'synthetic-workspace',document)
                    self.assertLess(time.monotonic()-started,6.5);self.assertTrue(os.get_blocking(writefd))
                self.assertEqual(os.read(readfd,16),b'')
            finally:os.close(readfd)

    def test_cli_actual_database_contention_and_publication_sqlite_fail_closed(self):
        from io import StringIO
        from unittest.mock import patch
        from forge.concept_advisory_cli import main
        from forge.concept_advisory_grant import ConceptAdvisoryGrant
        import sqlite3
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';grant=fixture.configure(root)
            args=['--data-root',str(root/'runtime'),'history','--token-file',str(root/'alice.private'),'--audience','synthetic-workspace','--dossier-id','dossier-alice','--conversation-id','conversation-alice']
            with sqlite3.connect(root/'runtime'/'forge.db') as writer:
                writer.execute('BEGIN IMMEDIATE')
                with patch('sys.stdout',new_callable=StringIO) as output:
                    self.assertEqual(main(args),1);document=json.loads(output.getvalue());self.assertEqual(document['error']['code'],'CONCEPT_CLI_UNAVAILABLE')
                    self.assertNotIn(str(root),output.getvalue())
                writer.rollback()
            with patch.object(ConceptAdvisoryGrant,'publication',side_effect=sqlite3.OperationalError('private publication database fault')),patch('sys.stdout',new_callable=StringIO) as output:
                self.assertEqual(main(args),1);self.assertEqual(output.getvalue(),'')
            self.assertFalse((root/'provider-requests.private.jsonl').exists())

    def test_known_original_readback_distinguishes_initialization_contention_from_unknown_start(self):
        from forge.runtime.bootstrap import RuntimeBootstrap
        import fcntl
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';fixture.configure(root)
            with http(root) as port:
                token=root/'alice.private';_,cap=call(port,token,'GET','/v1/concept-advisory/capability')
                r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'])
                lock=RuntimeBootstrap(data_root=root/'runtime').resolver.initialization_lock_path
                with lock.open('a+') as lease:
                    fcntl.flock(lease.fileno(),fcntl.LOCK_EX)
                    self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',r)[0],503)
                    missing=call(port,token,'GET','/v1/concept-advisory/intents/operation-one?dossier_id=dossier-alice&conversation_id=conversation-alice')
                    self.assertEqual(missing[0],404);self.assertEqual(missing[1]['error']['code'],'CONCEPT_TURN_NOT_FOUND')
                    fcntl.flock(lease.fileno(),fcntl.LOCK_UN)
                self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',r)[1]['original_turn']['status'],'COMPLETE')
                self.assertEqual(call(port,token,'POST','/v1/concept-advisory/turns',r)[1]['recorded'],False)
            self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
