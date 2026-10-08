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
        'maximum_actions':4, 'maximum_consecutive_no_progress_actions':2}}


class MissionConceptPlanningTests(unittest.TestCase):
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
