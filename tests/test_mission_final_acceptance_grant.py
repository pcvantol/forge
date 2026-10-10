"""Separate finite end-acceptance access over real admitted Mission setup."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from test_mission_concept_readiness import driver
from forge.advisory_grant import project_scope
from forge.candidate_decision_grant import signer
from forge.governed_continuation import _mission_subject_revision
from forge.mission_final_acceptance_grant import MissionFinalAcceptanceGrant
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.server_runtime import existing_instance


class MissionFinalAcceptanceGrantTests(unittest.TestCase):
    def test_real_admission_separate_read_accept_expiry_revoke_and_binding_integrity(self):
        ready, _ = driver.cases()
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / 'acceptance-grant'
            body = driver.prepare_case(root, 'approval')
            with ready.qual.http(root) as port:
                status, approved = ready.call(port, root / 'owner.private', 'POST',
                    '/v1/mission-concepts/recovery-chat/approve', body)
                self.assertEqual(200, status, approved)
                instance = existing_instance(root / 'runtime')
                grant = MissionFinalAcceptanceGrant(root / 'runtime', instance.instance_id)
                scope = project_scope(root / 'runtime', instance.instance_id)
                operator = signer(root / 'runtime', instance.instance_id, 'solo', ('READ',))['operator_id']
                with InstalledDynamicMissionRuntime.open_for_governance_read(str(root / 'runtime')) as runtime:
                    revision = _mission_subject_revision(runtime.states.get(approved['mission_id']))
                arguments = dict(principal_id=operator, project_id=scope['project_id'],
                    repository_id=scope['repository_id'], profile_id='solo', permissions=['READ', 'ACCEPT'],
                    missions=[{'mission_id': approved['mission_id'], 'subject_revision': revision}],
                    maximum_acceptances=1, expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    token_path=root / 'accept.private')
                before = driver.counts(root)
                issued = grant.issue(**arguments)
                token = 'Bearer ' + (root / 'accept.private').read_text().strip()
                principal = grant.authorize(token, approved['mission_id'], 'ACCEPT')
                self.assertTrue(principal.reference.startswith('forge-mission-final-acceptance-principal:v1:'))
                self.assertEqual(issued['grant_id'], principal.grant_id)
                self.assertEqual(before, driver.counts(root))
                for old in ('owner.private', 'admin.private', 'bob.private'):
                    self.assertIsNone(grant.authenticate('Bearer ' + (root / old).read_text().strip()))
                for invalid in (None, '', 'Basic token', 'Bearer ', 'Bearer bad\nvalue', 'Bearer ' + 'x' * 257):
                    self.assertIsNone(grant.authenticate(invalid))
                with self.assertRaises(PermissionError):
                    grant.authorize(token, 'MISSION-UNSELECTED', 'ACCEPT')
                with self.assertRaises(PermissionError):
                    grant.authorize(token, approved['mission_id'], 'BUSINESS')
                with self.assertRaises(PermissionError):
                    grant.issue(**{**arguments, 'principal_id': 'unassigned-business-person',
                        'token_path': root / 'wrong-actor.private'})
                with self.assertRaises(PermissionError):
                    grant.issue(**{**arguments, 'repository_id': 'different-repository',
                        'token_path': root / 'wrong-repository.private'})
                with self.assertRaises(PermissionError):
                    grant.issue(**{**arguments, 'missions': [{'mission_id': approved['mission_id'],
                        'subject_revision': 'different-revision'}], 'token_path': root / 'wrong-subject.private'})
                for expiry in (datetime.now(UTC) - timedelta(seconds=1), datetime.now(UTC) + timedelta(days=31)):
                    with self.assertRaises(ValueError):
                        grant.issue(**{**arguments, 'expires_at': expiry.isoformat()})
                with self.assertRaises(ValueError):
                    grant.issue(**{**arguments, 'token_path': grant.path})
                with self.assertRaises(ValueError):
                    grant.revoke('unknown-grant')
                original = grant.path.read_bytes()
                for field, changed in [('operator_binding_version', True), ('token_digest', 'invalid'),
                                       ('maximum_acceptances', True), ('instance_id', 'other-instance')]:
                    document = json.loads(original)
                    document['records'][0][field] = changed
                    grant.path.write_text(json.dumps(document))
                    self.assertIsNone(grant.authenticate(token))
                grant.path.write_bytes(original)
                record = json.loads(original)
                record['records'][0]['expires_at'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
                grant.path.write_text(json.dumps(record))
                self.assertIsNone(grant.authenticate(token))
                grant.path.write_bytes(original)
                grant.revoke(issued['grant_id'])
                self.assertIsNone(grant.authenticate(token))
                with self.assertRaises(PermissionError):
                    grant.authorize(token, approved['mission_id'], 'ACCEPT')
                reader = grant.issue(**{**arguments, 'principal_id': 'scoped-independent-reader',
                    'permissions': ['READ'], 'token_path': root / 'read.private'})
                read_token = 'Bearer ' + (root / 'read.private').read_text().strip()
                self.assertEqual(reader['grant_id'], grant.authorize(read_token, approved['mission_id']).grant_id)
                with self.assertRaises(PermissionError):
                    grant.authorize(read_token, approved['mission_id'], 'ACCEPT')
                self.assertEqual(before, driver.counts(root))
