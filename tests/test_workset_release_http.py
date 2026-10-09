"""Actual bounded HTTP release over r42 canonical admission, not seeded results."""
from datetime import UTC,datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from jsonschema import Draft202012Validator
from test_mission_concept_readiness import driver
from forge.advisory_grant import project_scope
from forge.server_runtime import existing_instance
from forge.workset_release_grant import WorksetReleaseGrant,CONTRACT
from forge.workset_release_service import BASE


def provision(root,result,permissions=('READ','RELEASE','DISARM')):
    instance=existing_instance(root/'runtime');scope=project_scope(root/'runtime',instance.instance_id)
    grant=WorksetReleaseGrant(root/'runtime',instance.instance_id)
    from forge.candidate_decision_grant import signer
    operator=signer(root/'runtime',instance.instance_id,'solo',('READ',))['operator_id']
    subjects=[{'candidate_id':result['candidate_id'],'subject_revision':result['intake_subject_revision']}]
    receipt=grant.issue(principal_id=operator,project_id=scope['project_id'],repository_id=scope['repository_id'],
        permissions=permissions,subjects=subjects,maximum_releases=1,maximum_activations=1,
        expires_at=(datetime.now(UTC)+timedelta(hours=2)).isoformat(),token_path=root/'release.private')
    selection={'contract_version':CONTRACT,'subjects':subjects,
        'expires_at':(datetime.now(UTC)+timedelta(hours=1)).isoformat(),
        'maximum_activations':1,'progression_mode':'continuous'}
    return grant,receipt,selection


class ApprovedReleaseHTTPTests(unittest.TestCase):
    def test_exact_release_original_current_disarm_replay_and_real_revoke(self):
        ready,_=driver.cases()
        validator=Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'forge/api/approved-workset-release-v1.json').read_text()))
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'release';body=driver.prepare_case(root,'approval')
            with ready.qual.http(root) as port:
                status,approved=ready.call(port,root/'owner.private','POST',
                    '/v1/mission-concepts/recovery-chat/approve',body)
                self.assertEqual(status,200,approved);before=driver.counts(root)
                grant,record,selection=provision(root,approved);token=root/'release.private'
                for old in ('owner.private','admin.private','bob.private'):
                    self.assertEqual(ready.call(port,root/old,'GET',BASE+'/capability')[0],403)
                status,cap=ready.call(port,token,'GET',BASE+'/capability');self.assertEqual(status,200,cap);validator.validate(cap)
                from forge.workset_release_service import WorksetReleaseService
                prepared_local=WorksetReleaseService(root/'runtime',grant).prepare('Bearer '+token.read_text().strip(),selection)
                status,prepared=ready.call(port,token,'POST',BASE+'/prepare',selection)
                self.assertEqual(status,200,prepared);validator.validate(prepared);self.assertTrue(prepared['release_supported'])
                self.assertEqual(driver.counts(root),before)
                request={'contract_version':CONTRACT,'operation_id':'release-once','intent':'release',
                    'selection':selection,'package_digest':prepared['package_digest'],'confirm':True,'expected_revision':None}
                status,result=ready.call(port,token,'POST',BASE+'/commands',request)
                self.assertEqual(status,200,result);validator.validate(result);self.assertEqual(result['state'],'COMPLETE')
                self.assertEqual(result['original_receipt']['original_release'],'AUTO_WHEN_ELIGIBLE')
                self.assertEqual(result['current']['items'][0]['mission_id'],approved['mission_id'])
                self.assertEqual(result['current']['items'][0]['eligibility'],'ELIGIBLE',result)
                self.assertFalse(result['execution_ready'])
                after=driver.counts(root);self.assertEqual(after['governance_decisions'],before['governance_decisions']+2)
                self.assertEqual(after['allocations'],before['allocations']);self.assertEqual(after['mission_state'],before['mission_state'])
                for operation in ('release-once','release-alias'):
                    status,replay=ready.call(port,token,'POST',BASE+'/commands',{**request,'operation_id':operation})
                    self.assertEqual(status,200,replay);validator.validate(replay);self.assertEqual(replay['original_receipt'],result['original_receipt'])
                self.assertEqual(driver.counts(root),after)
                self.assertEqual(ready.call(port,token,'POST',BASE+'/commands',{**request,'confirm':False})[0],409)
                disarm={**request,'operation_id':'disarm-once','intent':'disarm','expected_revision':result['current']['workset_revision']}
                status,withdrawn=ready.call(port,token,'POST',BASE+'/commands',disarm)
                self.assertEqual(status,200,withdrawn);validator.validate(withdrawn);self.assertIn('NOT_RELEASED',withdrawn['current']['items'][0]['blocking_reasons'])
                status,old=ready.call(port,token,'GET',BASE+'/operations/release-once')
                self.assertEqual(status,200,old);self.assertEqual(old['original_receipt'],result['original_receipt'])
                self.assertEqual(old['current']['workset_revision'],withdrawn['current']['workset_revision'])
                status,replay=ready.call(port,token,'POST',BASE+'/commands',{**request,'operation_id':'release-after-disarm'})
                self.assertEqual(status,200,replay);self.assertIn('NOT_RELEASED',replay['current']['items'][0]['blocking_reasons'])
                grant.revoke(record['grant_id'])
                self.assertEqual(ready.call(port,token,'GET',BASE+'/capability')[0],401)
                self.assertEqual(ready.call(port,token,'POST',BASE+'/commands',request)[0],401)
                self.assertEqual(driver.counts(root),after)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
