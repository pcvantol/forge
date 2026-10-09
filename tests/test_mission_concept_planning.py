"""Planning derives mechanical fields while preserving visible human meaning."""
import copy
import unittest
import test_mission_concept_contract as content
from forge.mission_concept_planning import derive_package, planning_profiles
from forge.candidate_decision_contract import architecture_inputs
from forge.advisory_contract import digest


def profiles():
    return {'BUILD': {'effect_policy': {'contract_version':'1.0',
        'mode':'BOUNDED_REPOSITORY_CHANGE', 'delivery':'GIT',
        'read_paths':['src/', 'tests/'], 'write_paths':['src/', 'tests/']},
        'constraints':['Preserve existing public contracts and account isolation.'],
        'technical_assumptions':['Use the configured repository and existing authentication.'],
        'required_capabilities':['bounded_repository_change'],
        'required_disciplines':['engineering', 'security'],
        'human_gates':['Explicit owner approval of the complete frozen definition.'],
        'maximum_actions':4, 'maximum_consecutive_no_progress_actions':2,
        'components':{'Invoice views':{'description':'Invoice status views within the existing portal.',
            'read_paths':['src/invoices/views.py','tests/test_invoice_views.py'],
            'write_paths':['src/invoices/views.py','tests/test_invoice_views.py']},
            'Payment views':{'description':'Payment status display; payment execution is excluded.',
                'read_paths':['src/payments/views.py','tests/test_payment_views.py'],
                'write_paths':['src/payments/views.py','tests/test_payment_views.py']},
            'Account isolation':{'description':'Isolate client account access to portal records.',
                'read_paths':['src/accounts/access.py','tests/test_accounts.py'],
                'write_paths':['src/accounts/access.py','tests/test_accounts.py']}}}}


class MissionConceptPlanningTests(unittest.TestCase):
    def test_cycle_missing_and_foreign_dependency_fail_closed(self):
        definition=content.MissionConceptContractTests().output()['definition']
        context={'instance_id':'instance','project_id':'project','repository_id':'repository',
                 'concept_dependency_references':['a','b'],'concept_dependency_catalog':[
                     {'candidate_id':'a','object_id':'oa','subject_revision':'sha256:'+'a'*64,'dependencies':['b']},
                     {'candidate_id':'b','object_id':'ob','subject_revision':'sha256:'+'b'*64,'dependencies':['a']}]}
        def prepare():
            return derive_package(definition,request_digest='sha256:'+'a'*64,context=context,
                profiles=profiles(),object_id='current',revision=1,
                provider_bounds={'input_token_bound':40000,'output_token_bound':8000})
        with self.assertRaisesRegex(ValueError,'cycle'):prepare()
        context['concept_dependency_catalog'][1]['dependencies']=['unresolved']
        with self.assertRaisesRegex(ValueError,'unresolved'):prepare()
        context['concept_dependency_catalog'][1]['dependencies']=[]
        definition['dependencies']=['outside'];definition['dependency_reasons']={'outside':'An unauthorized external subject should not be accepted.'}
        with self.assertRaises(ValueError):prepare()

    def derive(self, definition=None, config=None):
        context={'instance_id':'instance', 'project_id':'project', 'repository_id':'repository',
                 'concept_dependency_references':[]}
        return derive_package(definition or content.MissionConceptContractTests().output()['definition'],
            request_digest='sha256:'+'a'*64, context=context, profiles=config or profiles(),
            object_id='concept',revision=1,
            provider_bounds={'input_token_bound':40000,'output_token_bound':8000})

    def test_exact_full_definition_canonical_planning_and_no_execution(self):
        result=self.derive();package=result['package']
        self.assertEqual(result['package_digest'],digest(package))
        self.assertEqual(package['definition'],content.MissionConceptContractTests().output()['definition'])
        self.assertEqual(package['candidate']['scope'],['repository'])
        self.assertEqual(package['planning']['maximum_actions'],4)
        self.assertFalse(package['execution_started'])
        self.assertFalse(package['actions_predefined'])
        architecture_inputs(package['mission_preview'],package['planning'])

    def test_unresolved_substantive_choice_or_question_never_approval_package(self):
        for changes in ({'work_kind':'UNDECIDED','questions':['Only investigate or also implement?']},
                        {'questions':['Which invoice source is authoritative?']},
                        {'risks':[]}, {'exclusions':[]}):
            definition={**content.MissionConceptContractTests().output()['definition'],**changes}
            with self.subTest(changes=changes):
                result=self.derive(definition)
                self.assertFalse(result['approval_supported']);self.assertIsNone(result['package'])
                self.assertTrue(result['questions'])

    def test_mismatched_effect_and_unbounded_owner_template_rejected(self):
        for change in ({'maximum_actions':0}, {'maximum_actions':True},
                       {'maximum_consecutive_no_progress_actions':5},
                       {'human_gates':[]}, {'required_disciplines':['invented']},
                       {'constraints':['same','same']}, {'admin':True}):
            config=copy.deepcopy(profiles());config['BUILD'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):planning_profiles(config)
        config=profiles();config['INVESTIGATE']=config.pop('BUILD')
        with self.assertRaises(ValueError):planning_profiles(config)

    def test_human_scope_and_result_bind_canonical_subject_and_narrower_effects(self):
        first={**content.MissionConceptContractTests().output()['definition'],
               'scope':['Only invoice listing; do not implement payment views.'],'components':['Invoice views']}
        second={**first,'scope':['Only payment views; do not implement invoice listing.'],
                'components':['Payment views']}
        a,b=self.derive(first)['package'],self.derive(second)['package']
        self.assertNotEqual(a['subject_revision'],b['subject_revision'])
        self.assertNotEqual(a['mission_preview'],b['mission_preview'])
        self.assertIn('IN SCOPE: '+first['scope'][0],a['candidate']['architecture_constraints'])
        self.assertIn('EXPECTED RESULT: '+first['expected_result'],a['mission_preview']['engineering_constraints'])
        self.assertEqual(a['planning']['write_scopes'],['src/invoices/views.py','tests/test_invoice_views.py'])
        self.assertNotEqual(a['candidate']['effect_policy'],profiles()['BUILD']['effect_policy'])
        missing={**first,'components':[]}
        self.assertFalse(self.derive(missing)['approval_supported'])
        with self.assertRaises(ValueError):self.derive({**first,'components':['Outside project']})
        legacy=profiles();legacy['BUILD'].pop('components')
        self.assertFalse(self.derive(missing,legacy)['approval_supported'])

    def test_component_cannot_expand_or_copy_broad_profile_ceiling(self):
        for paths in (['outside/'],['src/'],['src/../escape']):
            config=profiles();config['BUILD']['components']['Invoice views']['write_paths']=paths
            with self.subTest(paths=paths),self.assertRaises(ValueError):planning_profiles(config)
