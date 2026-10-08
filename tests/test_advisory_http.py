"""Real source HTTP/service/provider process boundary; no internal advice mocks."""
from contextlib import ExitStack,closing
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from forge.advisory_contract import CONTRACT
from forge.advisory_context import AdvisoryContext
from forge.server_runtime import existing_instance

spec=spec_from_file_location('advisory_qualification',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_installed_advisory.py')
qual=module_from_spec(spec);spec.loader.exec_module(qual)

def request(cap,turn='first',mode='BUSINESS',revision=0):
    return {**{k:cap[k] for k in ['instance_id','project_id','repository_id','context_revision']},
            'contract_version':CONTRACT,'turn_id':turn,'conversation_id':'conversation-alice',
            'advisor_kind':mode,'objective':'Assess constraints and alternatives without applying decisions.',
            'expected_revision':revision,'selected_sources':[]}

class AdvisoryHTTPTests(unittest.TestCase):
    def test_actual_business_architecture_provider_and_replay_history(self):
        with TemporaryDirectory() as tmp:self.assertEqual(qual.flow(Path(tmp)/'advice')['provider_invocations'],2)

    def test_scoped_denials_current_revoke_stale_malformed_reads_and_no_governance_mutation(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'advice';grant=qual.configure(root)
            with qual.http(root) as port:
                token=root/'alice.private';status,cap=qual.call(port,token,'GET','/v1/advisory/capability');self.assertEqual(status,200)
                r=request(cap)
                for payload in [{**r,'role':'admin'},{**r,'expected_revision':True},{**r,'advisor_kind':'UX'},{**r,'context_revision':'missing'}]:
                    self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',payload)[0],400)
                for key in ['instance_id','project_id','repository_id']:
                    self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',{**r,key:'foreign'})[0],403)
                self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',{**r,'expected_revision':1})[0],409)
                for path in ['/v1/worksets','/v1/status','/v1/projects','/v1/reviews','/v1/workset-controls/serial-set']:
                    self.assertEqual(qual.call(port,token,'GET',path)[0],403)
                self.assertEqual(qual.call(port,root/'admin.private','GET','/v1/advisory/capability')[0],403)
                self.assertEqual(qual.call(port,root/'bob.private','GET','/v1/advisory/conversation-alice')[0],403)
                self.assertFalse((root/'provider-requests.private.jsonl').exists())
                status,out=qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r);self.assertEqual(status,200)
                before=(root/'runtime'/'forge.db').read_bytes()
                for path in ['/v1/advisory/capability','/v1/advisory/conversation-alice','/v1/advisory/conversation-alice/turns/first']:
                    self.assertEqual(qual.call(port,token,'GET',path)[0],200)
                self.assertEqual((root/'runtime'/'forge.db').read_bytes(),before)
                self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',{**r,'objective':'A different request.'})[0],409)
                records=grant._records();alice=next(r for r in records if r['principal_id']=='alice')
                grant.revoke(alice['grant_id'])
                self.assertEqual(qual.call(port,token,'GET','/v1/advisory/conversation-alice')[0],401)
                self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)[0],401)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
                import sqlite3
                with closing(sqlite3.connect(root/'runtime'/'forge.db')) as db:
                    for table in ['mission_id_allocations','mission_state','governance_decisions']:
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_injecting_malformed_unknown_usage_outputs_never_authoritative(self):
        for fault in ['inject','unsafe','foreign-reference','wrong-lens','unknown-usage']:
            with self.subTest(fault=fault),TemporaryDirectory() as tmp:
                root=Path(tmp)/'advice';qual.configure(root);(root/'fault.private').write_text(fault)
                with qual.http(root) as port:
                    token=root/'alice.private';_,cap=qual.call(port,token,'GET','/v1/advisory/capability');r=request(cap)
                    status,out=qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)
                    self.assertEqual(status,200);t=out['original_turn'];self.assertEqual(t['status'],'FAILED');self.assertIsNone(t['outcome']['output'])
                    self.assertEqual(t['execution'],'CONFIRMED');self.assertEqual(t['consumption'],1)
                    if fault=='unknown-usage':self.assertEqual(t['outcome']['usage_status'],'NOT_REPORTED');self.assertIsNone(t['outcome']['usage'])
                    self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)[1]['recorded'],False)
                    self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_selected_source_stale_foreign_and_revocation_protect_saved_history(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'advice';qual.configure(root)
            with qual.http(root) as port:
                token=root/'alice.private';_,cap=qual.call(port,token,'GET','/v1/advisory/capability');source=cap['available_sources'][0]
                self.assertEqual(qual.call(port,token,'GET','/v1/advisory/capability?source_id=foreign&source_version='+source['version'])[0],403)
                _,selected=qual.call(port,token,'GET','/v1/advisory/capability?source_id='+source['source_id']+'&source_version='+source['version'])
                r=request(selected);r['selected_sources']=[{'source_id':source['source_id'],'version':source['version']}]
                self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)[0],200)
                AdvisoryContext(root/'runtime',existing_instance(root/'runtime').instance_id).revoke(source['source_id'])
                self.assertEqual(qual.call(port,token,'GET','/v1/advisory/conversation-alice')[0],403)
                self.assertEqual(qual.call(port,token,'GET','/v1/advisory/conversation-alice/turns/first')[0],403)
                self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)[0],403)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_real_process_crash_before_after_result_and_lost_http_body(self):
        for stage in ['crash-before-provider','crash-after-result','lost-response']:
            with self.subTest(stage=stage),TemporaryDirectory() as tmp:
                case=qual.process_case(Path(tmp)/'advice',stage)
                self.assertTrue(case['same_identity'])
                self.assertEqual(case['provider_invocations'],0 if stage=='crash-before-provider' else 1)

    def test_unavailable_binary_retains_known_not_started_and_budget(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'advice';qual.configure(root);(root/'external-provider').unlink()
            with qual.http(root) as port:
                token=root/'alice.private';_,cap=qual.call(port,token,'GET','/v1/advisory/capability');r=request(cap)
                status,out=qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)
                self.assertEqual(status,200);self.assertEqual(out['original_turn']['execution'],'NOT_STARTED')
                self.assertEqual(out['original_turn']['status'],'FAILED');self.assertEqual(out['original_turn']['consumption'],1)
                self.assertFalse((root/'provider-requests.private.jsonl').exists())
                self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)[1]['recorded'],False)

    def test_owner_cli_parity_expiry_corrupted_store_and_no_budget_reset(self):
        from datetime import UTC,datetime,timedelta
        from unittest.mock import patch
        from io import StringIO
        from forge.advisory_grant import main as grant_main
        from forge.advisory_context import main as context_main
        from forge.advisory_cli import main as advice_main
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'advice';grant=qual.configure(root)
            with qual.http(root) as port:
                instance=existing_instance(root/'runtime');cap=qual.call(port,root/'alice.private','GET','/v1/advisory/capability')[1]
                limited=root/'limited.private'
                args=['--data-root',str(root/'runtime'),'issue','--principal-id','alice','--project-id',cap['project_id'],
                      '--repository-id',cap['repository_id'],'--conversation-id','conversation-alice','--maximum-turns','1',
                      '--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'--token-file',str(limited)]
                with patch('sys.stdout',new_callable=StringIO) as out:
                    self.assertEqual(grant_main(args),0);issued=json.loads(out.getvalue());self.assertNotIn(limited.read_text().strip(),out.getvalue())
                with patch('sys.stdout',new_callable=StringIO) as out:
                    self.assertEqual(advice_main(['--data-root',str(root/'runtime'),'--token-file',str(limited),'--provider-id',qual.utils.fixture.PROVIDER,'capability']),0)
                    self.assertEqual(json.loads(out.getvalue())['maximum_turns'],1)
                r=request(cap)
                _,response=qual.call(port,limited,'POST','/v1/advisory/conversation-alice/turns',r)
                self.assertEqual(qual.call(port,limited,'POST','/v1/advisory/conversation-alice/turns',{**r,'turn_id':'second','expected_revision':response['current_revision']})[0],409)
                inputs=root/'inputs';inputs.mkdir(mode=0o700);input_file=inputs/'turn.json';input_file.write_text(json.dumps(r));input_file.chmod(0o600)
                base=['--data-root',str(root/'runtime'),'--token-file',str(limited),'--provider-id',qual.utils.fixture.PROVIDER]
                for action in [['submit','--request-file',str(input_file)],['history','--conversation-id','conversation-alice'],['turn','--conversation-id','conversation-alice','--turn-id','first']]:
                    with patch('sys.stdout',new_callable=StringIO) as out:
                        self.assertEqual(advice_main(base+action),0);self.assertEqual(json.loads(out.getvalue())['contract_version'],CONTRACT)
                # Original wider grant cannot expand the persisted conversation's one-turn limit.
                self.assertEqual(qual.call(port,root/'alice.private','POST','/v1/advisory/conversation-alice/turns',{**r,'turn_id':'second','expected_revision':response['current_revision']})[0],409)
                with patch('sys.stdout',new_callable=StringIO):
                    self.assertEqual(grant_main(['--data-root',str(root/'runtime'),'revoke','--grant-id',issued['grant_id']]),0)
                    self.assertEqual(context_main(['--data-root',str(root/'runtime'),'revoke','--source-id','selected-context']),0)
                self.assertEqual(qual.call(port,limited,'GET','/v1/advisory/capability')[0],401)
                original=grant.path.read_bytes();records=grant._records()
                for item in records:item['expires_at']='2000-01-01T00:00:00+00:00'
                grant._save(records)
                self.assertEqual(qual.call(port,root/'alice.private','GET','/v1/advisory/conversation-alice')[0],401)
                grant.path.write_bytes(original)
                broken=json.loads(original);broken['records'][0]['maximum_turns']=True;grant.path.write_text(json.dumps(broken))
                self.assertEqual(qual.call(port,root/'alice.private','GET','/v1/advisory/capability')[0],401)
                grant.path.write_bytes(original)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_real_concurrent_send_is_bounded_without_second_invocation(self):
        from threading import Thread
        import time
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'advice';qual.configure(root);(root/'fault.private').write_text('slow')
            with qual.http(root) as port:
                token=root/'alice.private';_,cap=qual.call(port,token,'GET','/v1/advisory/capability');r=request(cap);first=[]
                worker=Thread(target=lambda:first.append(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)))
                worker.start()
                try:
                    deadline=time.monotonic()+10
                    while not (root/'provider-requests.private.jsonl').exists():
                        self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                    start=time.monotonic();status,out=qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)
                    self.assertEqual(status,409);self.assertEqual(out['error']['code'],'CONVERSATION_BUSY');self.assertLess(time.monotonic()-start,1)
                finally:worker.join(15)
                self.assertFalse(worker.is_alive());self.assertEqual(first[0][0],200)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_two_existing_configured_projects_and_principals_are_isolated(self):
        from datetime import UTC,datetime,timedelta
        from forge.execution_host_configuration import EngineeringPlatformPeerConfigurationService,read_peer_configuration
        from forge.advisory_grant import AdvisoryGrant
        with TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'alpha',Path(tmp)/'beta';qual.configure(a);qual.configure(b)
            cfg=EngineeringPlatformPeerConfigurationService(b/'runtime');old=read_peer_configuration(b/'runtime').configuration
            cfg.configure(binding_id=old.binding_id,endpoint=old.endpoint,expected_ep_instance_id=old.expected_ep_instance_id,
                          ep_consumer_id=old.ep_consumer_id,execution_host_id=old.execution_host_id,ep_project_id='project-beta',
                          ep_repository_id='repository-beta',repository_identity=old.repository_identity,credential_reference=qual.utils.SecretReference.parse(old.credential_reference),
                          operator_id='isolated-qualification',allow_loopback_http=True,replace=True,expected_revision=old.configuration_revision,expected_digest=old.configuration_digest)
            with qual.http(a) as pa,qual.http(b) as pb:
                instance=existing_instance(b/'runtime');g=AdvisoryGrant(b/'runtime',instance.instance_id)
                g.issue(principal_id='bob-beta',project_id='project-beta',repository_id='repository-beta',conversation_ids=('conversation-beta',),
                        expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),maximum_turns=8,token_path=b/'beta.private')
                _,ca=qual.call(pa,a/'alice.private','GET','/v1/advisory/capability')
                status,cb=qual.call(pb,b/'beta.private','GET','/v1/advisory/capability');self.assertEqual(status,200)
                self.assertEqual(cb['project_id'],'project-beta');self.assertEqual(cb['available_sources'],[])
                self.assertEqual(qual.call(pb,a/'alice.private','GET','/v1/advisory/capability')[0],401)
                self.assertEqual(qual.call(pa,b/'beta.private','GET','/v1/advisory/capability')[0],401)
                ra=request(ca);rb={**request(cb),'conversation_id':'conversation-beta'}
                self.assertEqual(qual.call(pa,a/'alice.private','POST','/v1/advisory/conversation-alice/turns',ra)[0],200)
                self.assertEqual(qual.call(pb,b/'beta.private','POST','/v1/advisory/conversation-beta/turns',rb)[0],200)
                self.assertEqual(qual.call(pa,a/'alice.private','GET','/v1/advisory/conversation-beta')[0],403)
                self.assertEqual(qual.call(pb,b/'beta.private','GET','/v1/advisory/conversation-alice')[0],403)

    def test_real_provider_timeout_cancel_and_cross_conversation_budget_do_not_regenerate(self):
        from datetime import UTC,datetime,timedelta
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'advice';grant=qual.configure(root);(root/'fault.private').write_text('timeout')
            with qual.http(root) as port:
                token=root/'alice.private';_,cap=qual.call(port,token,'GET','/v1/advisory/capability');r=request(cap)
                status,out=qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)
                self.assertEqual(status,200);t=out['original_turn'];self.assertEqual(t['execution'],'MAY_HAVE_HAPPENED')
                self.assertTrue(t['outcome']['diagnostic']['timed_out']);self.assertEqual(t['consumption'],1)
                cancel={'contract_version':CONTRACT,'expected_revision':out['current_revision'],'request_digest':t['request_digest']}
                status,ack=qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns/first/cancel',cancel)
                self.assertEqual(status,200);self.assertFalse(ack['provider_stopped']);self.assertEqual(ack['original_turn']['status'],'CANCEL_REQUESTED')
                self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',{**r,'turn_id':'new-id','expected_revision':ack['current_revision']})[0],409)
                other=root/'other.private';grant.issue(principal_id='alice',project_id=cap['project_id'],repository_id=cap['repository_id'],conversation_ids=('other-conversation',),
                    expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),maximum_turns=8,token_path=other)
                self.assertEqual(qual.call(port,other,'POST','/v1/advisory/other-conversation/turns',{**r,'conversation_id':'other-conversation','turn_id':'new-id'})[0],409)
                self.assertEqual(qual.call(port,token,'POST','/v1/advisory/conversation-alice/turns',r)[1]['recorded'],False)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
