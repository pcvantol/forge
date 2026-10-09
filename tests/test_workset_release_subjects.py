"""Read-bound release preparation uses genuine r42 admission without new effects."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from test_mission_concept_readiness import driver
from forge.advisory_grant import project_scope
from forge.server_runtime import existing_instance
from forge.workset_release_subjects import approved_subject, repository_truth


class ApprovedReleaseSubjectTests(unittest.TestCase):
    def test_existing_two_decisions_and_mission_are_verified_without_effects(self):
        ready,_=driver.cases()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'subject';body=driver.prepare_case(root,'approval')
            with ready.qual.http(root) as port:
                status,result=ready.call(port,root/'owner.private','POST',
                    '/v1/mission-concepts/recovery-chat/approve',body)
                self.assertEqual(status,200,result)
            # Only the external OS identity adapter is deterministic.
            with patch.object(ready.qual.utils.composition.MacOSGeneratedUIDIdentityAdapter,
                              'resolve',return_value=ready.qual.utils.fixture.IDENTITY):
                before=driver.counts(root)
                scope=project_scope(root/'runtime',existing_instance(root/'runtime').instance_id)
                subject=approved_subject(root/'runtime',scope,result['candidate_id'],result['intake_subject_revision'])
                self.assertEqual(subject['mission_id'],result['mission_id'])
                self.assertEqual(subject['candidate_decisions']['business'],result['business_decision'])
                self.assertEqual(repository_truth(root/'runtime',scope)['repository_id'],scope['repository_id'])
                with self.assertRaises(ValueError):
                    approved_subject(root/'runtime',scope,result['candidate_id'],'sha256:'+'0'*64)
                with self.assertRaises(PermissionError):
                    approved_subject(root/'runtime',{**scope,'project_id':'foreign'},result['candidate_id'],result['intake_subject_revision'])
                self.assertEqual(driver.counts(root),before)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
