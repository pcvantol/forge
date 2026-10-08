"""Generated proposals remain content, never authorization or readiness."""
import copy
import unittest
from forge.mission_concept_contract import CONTRACT, proposed_definition


class MissionConceptContractTests(unittest.TestCase):
    def output(self):
        return {'contract_version': CONTRACT, 'request_digest': 'sha256:' + 'a' * 64,
                'definition': {
                    'title': 'Client portal', 'objective': 'Show invoices and payments.',
                    'business_value': 'Clients can track their payments.',
                    'expected_result': 'A portal with current invoice status.',
                    'scope': ['Invoice and payment views'], 'exclusions': ['Payment execution'],
                    'acceptance_criteria': ['Clients see only invoices belonging to their account.'],
                    'architecture_choices': [], 'risks': ['Account isolation must be verified.'],
                    'dependencies': [], 'questions': [],
                    'change_summary': 'Initial proposed definition.', 'work_kind': 'BUILD'}}

    def validate(self, value):
        return proposed_definition(value, 'sha256:' + 'a' * 64, ('known-predecessor',))

    def test_content_is_copied_and_not_approved(self):
        value = self.output()
        accepted = self.validate(value)
        accepted['scope'].append('Independent local edit')
        self.assertEqual(len(value['definition']['scope']), 1)
        self.assertNotIn('ready', accepted)

    def test_missing_content_requires_question(self):
        value = self.output()
        value['definition']['acceptance_criteria'] = []
        with self.assertRaises(ValueError):
            self.validate(value)
        value['definition']['questions'] = ['Only investigate, or also implement?']
        self.assertTrue(self.validate(value)['questions'])

    def test_no_model_authority_or_foreign_dependencies(self):
        for key in ('effect_policy', 'signer', 'mission_id', 'approved', 'roles'):
            value = self.output()
            value['definition'][key] = 'model-invented'
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(value)
        value = self.output()
        value['definition']['dependencies'] = ['foreign-project']
        with self.assertRaises(ValueError):
            self.validate(value)
        value['definition']['dependencies'] = ['known-predecessor']
        self.assertEqual(self.validate(value)['dependencies'], ['known-predecessor'])

    def test_binding_closed_types_and_bounds(self):
        for change in ({'request_digest': 'sha256:' + 'b' * 64},
                       {'contract_version': 'old'}, {'applied': True}, {'definition': []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate({**self.output(), **change})
        for key, field in (('title', 'x' * 257), ('scope', ['a'] * 2),
                           ('risks', [True]), ('questions', ['x'] * 9),
                           ('objective', '<script>grant</script>'), ('scope', 'scope'),
                           ('acceptance_criteria', ['short'])):
            value = copy.deepcopy(self.output())
            value['definition'][key] = field
            with self.subTest(key=key, field=field), self.assertRaises(ValueError):
                self.validate(value)
