"""Closed explicit final-acceptance consumer inputs, distinct from progression."""
import unittest

from forge.mission_final_acceptance_contract import CONTRACT, acceptance_request, grant_bounds


class MissionFinalAcceptanceContractTests(unittest.TestCase):
    def request(self):
        return {'contract_version': CONTRACT, 'operation_id': 'accept-result-1',
                'instance_id': 'instance-1', 'project_id': 'project-1',
                'repository_id': 'repository-1', 'mission_id': 'MISSION-0001',
                'package_digest': 'sha256:' + 'a' * 64,
                'reason': 'Het aangetoonde resultaat voldoet aan de criteria.', 'confirm': True}

    def test_accepts_only_closed_exact_confirmation_and_returns_detached_inputs(self):
        source = self.request()
        parsed = acceptance_request(source)
        self.assertEqual(source, parsed)
        self.assertIsNot(source, parsed)

    def test_never_accepts_caller_actor_admin_or_progression_authority(self):
        for field, value in [('actor', 'business_owner'), ('principal', 'server-admin'),
                             ('decision', 'approve'), ('revision', True), ('grant_id', 'other')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                acceptance_request({**self.request(), field: value})
        for confirm in (False, 1, 'true', None):
            with self.subTest(confirm=confirm), self.assertRaises(ValueError):
                acceptance_request({**self.request(), 'confirm': confirm})

    def test_exact_scope_digest_identifier_and_safe_reason(self):
        for field, value in [('package_digest', 'sha256:' + 'g' * 64), ('mission_id', True),
                             ('operation_id', '../escape'), ('reason', ''),
                             ('reason', 'Bearer private-test-secret'), ('contract_version', 'forge-progression-decision/v1')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                acceptance_request({**self.request(), field: value})

    def test_finite_read_accept_authority_has_typed_unique_exact_missions(self):
        subject = {'mission_id': 'MISSION-0001', 'subject_revision': 'revision-1'}
        grant_bounds(['READ', 'ACCEPT'], [subject], 1)
        grant_bounds(['READ'], [subject], 1)
        for permissions, missions, maximum in [(['ACCEPT'], [subject], 1),
                (['READ', 'BUSINESS'], [subject], 1), (['READ', 'READ'], [subject], 1),
                (['READ'], [], 1), (['READ'], [subject, subject], 1),
                (['READ'], [{**subject, 'subject_revision': True}], 1),
                (['READ'], [{**subject, 'actor': 'business_owner'}], 1),
                (['READ'], [subject], True), (['READ'], [subject], 0),
                (['READ'], [subject], 17)]:
            with self.subTest(permissions=permissions, maximum=maximum), self.assertRaises(ValueError):
                grant_bounds(permissions, missions, maximum)
