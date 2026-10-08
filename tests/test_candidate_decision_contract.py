"""Closed requests cannot supply identities, implicit confirmation or planning."""
import unittest
from forge.candidate_decision_contract import CONTRACT, decision_request

class CandidateDecisionContractTests(unittest.TestCase):
    def request(self):
        return dict(contract_version=CONTRACT,operation_id='operation',instance_id='instance',project_id='project',repository_id='repository',candidate_id='candidate',subject_revision='sha256:'+'a'*64,kind='BUSINESS',rationale='Explicit user decision on exact Candidate.',confirm=True,human_gates=['Owner reviews the exact declared scope.'])
    def test_closed_explicit_business_request(self):
        self.assertEqual(decision_request(self.request()),self.request())
        for change in ({'actor':'business_owner'},{'role':'business_owner'},{'confirm':1},{'human_gates':[]},{'human_gates':['gate','gate']},{'subject_revision':True},{'rationale':'<script>approve</script>'},{'kind':'ARCHITECTURE'}):
            with self.subTest(change=change),self.assertRaises((ValueError,TypeError,KeyError)):
                decision_request({**self.request(),**change})
