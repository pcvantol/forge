"""Actual scoped denials and owner CLI over genuinely approved r42 subjects."""
from datetime import UTC,datetime,timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,time,unittest
from test_workset_release_http import driver,provision,BASE,CONTRACT
from forge.workset_release_grant import main as owner_cli
from forge.workset_release_cli import main as release_cli
from forge.workspace_review_grant import _write_private


class ApprovedReleaseDenialTests(unittest.TestCase):
    def test_real_owner_issue_revoke_and_read_only_release_denial_without_extra_roles(self):
        ready,_=driver.cases()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'owner';body=driver.prepare_case(root,'approval');root.chmod(0o700)
            with ready.qual.http(root) as port:
                _,approved=ready.call(port,root/'owner.private','POST','/v1/mission-concepts/recovery-chat/approve',body)
                grant,record,selection=provision(root,approved);before=driver.counts(root)
                subjects_file=root/'subjects.private.json';_write_private(subjects_file,json.dumps(record['subjects']).encode())
                owner=['--data-root',str(root/'runtime'),'issue','--principal-id',record['principal_id'],
                    '--project-id',record['project_id'],'--repository-id',record['repository_id'],
                    '--expires-at',(datetime.now(UTC)+timedelta(hours=1)).isoformat(),
                    '--token-file',str(root/'read-release.private'),'--subjects-file',str(subjects_file),
                    '--permission','READ','--maximum-releases','1','--maximum-activations','1']
                with patch('sys.stdout',new_callable=StringIO) as output:
                    self.assertEqual(owner_cli(owner),0);issued=json.loads(output.getvalue())
                self.assertNotIn('token_digest',issued)
                token=root/'read-release.private'
                status,cap=ready.call(port,token,'GET',BASE+'/capability');self.assertEqual(status,200,cap)
                self.assertFalse(cap['release_supported']);self.assertFalse(cap['disarm_supported'])
                selection={**selection,'expires_at':(datetime.now(UTC)+timedelta(minutes=30)).isoformat()}
                status,prepared=ready.call(port,token,'POST',BASE+'/prepare',selection)
                self.assertEqual(status,200,prepared);self.assertFalse(prepared['release_supported'])
                self.assertIn('RELEASE_AUTHORITY_UNAVAILABLE',[g['code'] for g in prepared['gaps']])
                command={'contract_version':CONTRACT,'operation_id':'read-cannot-release','intent':'release',
                    'selection':selection,'package_digest':prepared['package_digest'],'confirm':True,'expected_revision':None}
                self.assertEqual(ready.call(port,token,'POST',BASE+'/commands',command)[0],403)
                with patch('sys.stdout',new_callable=StringIO) as output:
                    self.assertEqual(owner_cli(['--data-root',str(root/'runtime'),'revoke','--grant-id',issued['grant_id']]),0)
                    self.assertEqual(json.loads(output.getvalue())['state'],'REVOKED')
                self.assertEqual(ready.call(port,token,'GET',BASE+'/capability')[0],401)
                for key,value in [('principal_id','foreign-principal'),('project_id','foreign-project')]:
                    kwargs={k:record[k] for k in ('principal_id','project_id','repository_id','permissions','subjects','maximum_releases','maximum_activations','expires_at')}
                    kwargs[key]=value
                    with self.assertRaises(PermissionError):grant.issue(**kwargs,token_path=root/'denied.private')
                    self.assertFalse((root/'denied.private').exists())
                with self.assertRaises(ValueError):
                    grant.issue(**{k:record[k] for k in ('principal_id','project_id','repository_id','permissions','subjects','maximum_releases','maximum_activations','expires_at')},token_path=root/'release.private')
                with patch('sys.stdout',new_callable=StringIO):
                    self.assertEqual(owner_cli(['--data-root',str(root/'runtime'),'revoke','--grant-id','unknown-grant']),1)
                    self.assertEqual(release_cli(['--data-root',str(root/'runtime'),'--token-file',str(root/'release.private'),
                        'operation','--operation-id','unknown-operation']),1)
                self.assertEqual(driver.counts(root),before)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_invalid_semantics_scope_expiry_and_confirmation_have_no_release_side_effects(self):
        ready,_=driver.cases()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'denials';body=driver.prepare_case(root,'approval')
            with ready.qual.http(root) as port:
                _,approved=ready.call(port,root/'owner.private','POST','/v1/mission-concepts/recovery-chat/approve',body)
                grant,record,selection=provision(root,approved);token=root/'release.private';before=driver.counts(root)
                for changed in ({**selection,'actor':'primary_operator'},
                    {**selection,'progression_mode':'automatic-unbounded'},
                    {**selection,'maximum_activations':2},
                    {**selection,'subjects':selection['subjects']*2},
                    {**selection,'expires_at':(datetime.now(UTC)-timedelta(seconds=1)).isoformat()},
                    {**selection,'subjects':[{**selection['subjects'][0],'subject_revision':'sha256:'+'0'*64}]}):
                    with self.subTest(selection=changed):
                        self.assertIn(ready.call(port,token,'POST',BASE+'/prepare',changed)[0],(403,409))
                _,prepared=ready.call(port,token,'POST',BASE+'/prepare',selection)
                command={'contract_version':CONTRACT,'operation_id':'denied-command','intent':'release',
                    'selection':selection,'package_digest':prepared['package_digest'],'confirm':True,'expected_revision':None}
                for changed in ({**command,'actor':'primary_operator'},{**command,'confirm':1},
                    {**command,'package_digest':'sha256:'+'0'*64},{**command,'expected_revision':1},
                    {**command,'intent':'disarm','expected_revision':0}):
                    self.assertEqual(ready.call(port,token,'POST',BASE+'/commands',changed)[0],409)
                self.assertEqual(ready.call(port,token,'GET',BASE+'/operations/unknown')[0],404)
                self.assertEqual(ready.call(port,token,'GET','/v1/status')[0],403)
                self.assertEqual(driver.counts(root),before)
                # Genuine short-lived alias expires; no state/budget reset.
                short={k:record[k] for k in ('principal_id','project_id','repository_id','permissions','subjects','maximum_releases','maximum_activations')}
                grant.issue(**short,expires_at=(datetime.now(UTC)+timedelta(seconds=.3)).isoformat(),token_path=root/'expiring.private')
                time.sleep(.35)
                self.assertEqual(ready.call(port,root/'expiring.private','GET',BASE+'/capability')[0],401)
                self.assertEqual(driver.counts(root),before)
                # Actual private-storage corruption, not a mocked validator or approval.
                grant.path.write_text('{}');grant.path.chmod(0o600)
                self.assertEqual(ready.call(port,token,'GET',BASE+'/capability')[0],401)

    def test_legacy_context_stays_readable_but_missing_real_observation_cannot_be_invented(self):
        ready,_=driver.cases()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'legacy';body=driver.prepare_case(root,'approval')
            with ready.qual.http(root) as port:
                _,approved=ready.call(port,root/'owner.private','POST','/v1/mission-concepts/recovery-chat/approve',body)
                grant,record,selection=provision(root,approved)
                from forge.advisory_context import AdvisoryContext
                from forge.advisory_contract import digest
                context=AdvisoryContext(root/'runtime',record['instance_id']);records=context._read()
                for r in records:
                    r.pop('observed_at',None)
                    r['version']=digest({k:v for k,v in r.items() if k not in ('state','version')})
                # Exact historical owner-context wire shape, not a fabricated
                # Candidate/Mission/decision or runtime success.
                context._save(records)
                self.assertEqual(ready.call(port,root/'owner.private','GET','/v1/mission-concepts/capability')[0],200)
                status,error=ready.call(port,root/'release.private','POST',BASE+'/prepare',selection)
                self.assertEqual(status,409,error);self.assertEqual(error['error']['code'],'RELEASE_SOURCE_OBSERVATION_REQUIRED')
