"""Real private/canonical receipt corruption is rejected, never seeded success."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from test_workset_release_http import driver,provision,BASE,CONTRACT
from forge.approved_worklist import ApprovedWorklistService,candidate_source
from forge.lifecycle import RecommendationLifecycleStore
from forge.worklist_control import control_runtime
from forge.workset_release_journal import ReleaseJournal,private_packet


class ApprovedReleaseIntegrityTests(unittest.TestCase):
    def test_actual_original_receipt_and_private_intent_tampering_are_unavailable(self):
        ready,_=driver.cases()
        for fault in ('original-receipt','intent-digest','operation-digest','private-permission','invalid-json'):
            with self.subTest(fault=fault),TemporaryDirectory() as tmp:
                root=Path(tmp)/fault;body=driver.prepare_case(root,'approval')
                with ready.qual.http(root) as port:
                    _,approved=ready.call(port,root/'owner.private','POST','/v1/mission-concepts/recovery-chat/approve',body)
                    grant,record,selection=provision(root,approved);token=root/'release.private'
                    _,prepared=ready.call(port,token,'POST',BASE+'/prepare',selection)
                    command={'contract_version':CONTRACT,'operation_id':'real-release','intent':'release',
                        'selection':selection,'package_digest':prepared['package_digest'],'confirm':True,'expected_revision':None}
                    status,released=ready.call(port,token,'POST',BASE+'/commands',command);self.assertEqual(status,200,released)
                    before=driver.counts(root)
                    p=grant.authorize('Bearer '+token.read_text().strip());journal=ReleaseJournal(root/'runtime',p.reference)
                    if fault=='original-receipt':
                        # Deliberate corruption of existing product-generated receipt
                        # metadata in this isolated negative case; no new approved
                        # subject, decision, admission or acceptance is fabricated.
                        with control_runtime(root/'runtime') as runtime,RecommendationLifecycleStore(candidate_source(root/'runtime')) as store:
                            service=ApprovedWorklistService(runtime,store);value=service._get(released['workset_id'])
                            value['release_commands']['real-release']['ongoing_work_cancelled']=True
                            service._save(value,value['revision'])
                    elif fault=='private-permission':journal.path.chmod(0o644)
                    elif fault=='invalid-json':journal.path.write_text('not-json')
                    else:
                        document=json.loads(journal.path.read_text())
                        if fault=='intent-digest':next(iter(document['intents'].values()))['package_digest']='sha256:'+'0'*64
                        else:document['operations']['real-release']['request_digest']='sha256:'+'0'*64
                        journal.path.write_text(json.dumps(document));journal.path.chmod(0o600)
                    self.assertEqual(ready.call(port,token,'GET',BASE+'/operations/real-release')[0],503)
                    self.assertEqual(driver.counts(root),before)
                    self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_no_follow_and_bounded_private_packet_reader(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);root.chmod(0o700);source=root/'packet';source.write_bytes(b'1234');source.chmod(0o600)
            self.assertEqual(private_packet(source,4),b'1234')
            with self.assertRaises(ValueError):private_packet(source,3)
            link=root/'link';link.symlink_to(source)
            with self.assertRaises(OSError):private_packet(link)
            source.chmod(0o644)
            with self.assertRaises(ValueError):private_packet(source)

    def test_exact_alias_capacity_denies_before_corrupting_original_readback(self):
        ready,_=driver.cases()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'capacity';body=driver.prepare_case(root,'approval')
            with ready.qual.http(root) as port:
                _,approved=ready.call(port,root/'owner.private','POST','/v1/mission-concepts/recovery-chat/approve',body)
                grant,record,selection=provision(root,approved);token=root/'release.private'
                _,prepared=ready.call(port,token,'POST',BASE+'/prepare',selection)
                command={'contract_version':CONTRACT,'operation_id':'original','intent':'release',
                    'selection':selection,'package_digest':prepared['package_digest'],'confirm':True,'expected_revision':None}
                status,original=ready.call(port,token,'POST',BASE+'/commands',command);self.assertEqual(status,200,original)
                before=driver.counts(root)
                for n in range(127):
                    status,replay=ready.call(port,token,'POST',BASE+'/commands',{**command,'operation_id':'alias-'+str(n)})
                    self.assertEqual(status,200,replay);self.assertEqual(replay['original_receipt'],original['original_receipt'])
                self.assertEqual(ready.call(port,token,'POST',BASE+'/commands',{**command,'operation_id':'over-capacity'})[0],409)
                status,current=ready.call(port,token,'GET',BASE+'/operations/original')
                self.assertEqual(status,200,current);self.assertEqual(current['original_receipt'],original['original_receipt'])
                self.assertEqual(driver.counts(root),before)
