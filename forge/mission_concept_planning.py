"""Derive a reviewable canonical plan from content and current owner bounds.

Nothing here approves a subject or asserts that its requirements are satisfied.
The caller must obtain configuration through the actual scoped owner route.
"""
from .advisory_contract import digest, text
from .mission_concept_contract import CONTRACT, WORK_KINDS, proposed_definition
from .models.mission_effect import MissionEffectPolicy
from .models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from .models.mission_recommendation import RequiredDiscipline
from .models.criterion_assessment import CriterionAssessmentContract, CriterionEvidenceRequirement, ApprovedRepositoryEvidenceSource
from .models.criterion_observation import canonical_digest
from .governance_authority import ArchitecturePlanningEvidence
from .lifecycle import MissionCandidate
import json

PROFILE_FIELDS = ('effect_policy', 'constraints', 'technical_assumptions',
                  'required_capabilities', 'required_disciplines', 'human_gates',
                  'maximum_actions', 'maximum_consecutive_no_progress_actions')


def planning_profiles(value):
    """Closed finite setup input; no automatic policy/capacity expansion."""
    if not isinstance(value, dict) or not value or set(value) - set(WORK_KINDS[:-1]):
        raise ValueError('explicit supported bounded work profiles required')
    expected_mode = {'INVESTIGATE': 'READ_ONLY_ASSESSMENT',
                     'DESIGN': 'ARCHITECTURE_DESIGN_ONLY',
                     'DOCUMENT': 'DOCUMENTATION_ONLY',
                     'BUILD': 'BOUNDED_REPOSITORY_CHANGE'}
    for kind, profile in value.items():
        if not isinstance(profile, dict) or set(profile) != set(PROFILE_FIELDS):
            raise ValueError('closed trusted planning profile required')
        effect = MissionEffectPolicy.from_dict(profile['effect_policy'])
        if effect.mode != expected_mode[kind]:
            raise ValueError('work kind and allowed effect differ')
        if (effect.mode in {'ARCHITECTURE_DESIGN_ONLY', 'DOCUMENTATION_ONLY'}
                and any(path.endswith('/') for path in effect.write_paths)):
            raise ValueError('document work requires exact document paths')
        for key in PROFILE_FIELDS[1:6]:
            fields = profile[key]
            if (not isinstance(fields, list) or not 1 <= len(fields) <= 8
                    or any(not isinstance(item, str) for item in fields)
                    or len(set(fields)) != len(fields)):
                raise ValueError('substantive bounded profile fields required')
            for item in fields:
                text(item, 1000)
            if key == 'required_disciplines':
                for item in fields:
                    RequiredDiscipline(item)
        actions, no_progress = (profile[k] for k in PROFILE_FIELDS[-2:])
        if (type(actions) is not int or type(no_progress) is not int
                or not 1 <= no_progress <= actions <= 64):
            raise ValueError('finite actual Action ceilings required')
    return value


def derive_package(definition, *, request_digest, context, profiles,
                   object_id, revision, provider_bounds):
    """Freeze full human meaning and required technical constraints together."""
    proposed_definition({'contract_version': CONTRACT, 'request_digest': request_digest,
                         'definition': definition}, request_digest,
                        context['concept_dependency_references'])
    planning_profiles(profiles)
    profile = profiles.get(definition['work_kind'])
    missing = list(definition['questions'])
    if profile is None:
        missing.append('The requested kind of work has no authorized project profile.')
    if not definition['exclusions']:
        missing.append('Which work should explicitly remain outside this Mission?')
    if not definition['risks']:
        missing.append('Which risks or assumptions need attention before approval?')
    if not definition['scope'] or not definition['acceptance_criteria']:
        missing.append('What result is in scope and how will we recognize completion?')
    if missing:
        return {'contract_version': CONTRACT, 'object_id': object_id, 'revision': revision,
                'definition': definition, 'questions': missing,
                'approval_supported': False, 'package': None}
    catalog = {r['candidate_id']:r for r in context.get('concept_dependency_catalog',[])}
    if any(dep not in catalog for dep in definition['dependencies']):
        raise ValueError('current exact dependency binding required')
    graph = {key:row['dependencies'] for key,row in catalog.items()}
    verified = set()
    def visit(node, path):
        if node in path:
            raise ValueError('dependency cycle detected')
        if node in verified:
            return
        for predecessor in graph.get(node,[]):
            if predecessor not in graph:
                raise ValueError('unresolved scoped dependency')
            visit(predecessor,path | {node})
        verified.add(node)
    for node in graph:
        visit(node,set())
    for key in ('input_token_bound', 'output_token_bound'):
        if type(provider_bounds.get(key)) is not int or provider_bounds[key] < 1:
            raise ValueError('current provider bounds unavailable')
    source = {'instance_id': context['instance_id'], 'project_id': context['project_id'],
              'repository_id': context['repository_id'], 'object_id': object_id,
              'revision': revision, 'request_digest': request_digest,
              'context_revision': digest(context)}
    key = digest(source)[7:39]
    effect = MissionEffectPolicy.from_dict(profile['effect_policy'])
    repository_source = (ApprovedRepositoryEvidenceSource.from_dict(context['concept_repository_source'])
                         if context.get('concept_repository_source') is not None else None)
    if repository_source is not None and repository_source.repository_id != context['repository_id']:
        raise ValueError('repository planning source outside actual project binding')
    candidate = MissionCandidate(
        id='concept-candidate-' + key, recommendation_id='concept-recommendation-' + key,
        title=definition['title'], objective=definition['objective'],
        scope=(context['repository_id'],),
        acceptance_criteria=tuple(definition['acceptance_criteria']),
        architecture_constraints=tuple(dict.fromkeys([
            *profile['constraints'], *definition['architecture_choices'],
            *('EXCLUDED: ' + item for item in definition['exclusions'])])),
        dependencies=tuple(definition['dependencies']), effect_policy=effect)
    subject_revision = canonical_digest(candidate.to_dict())
    # These are exactly the existing GovernedCandidateIntake identities.
    from .governed_candidate_intake import GovernedCandidateIntake
    decision_id = GovernedCandidateIntake._decision_id('architecture', candidate.id, subject_revision)
    contracts = tuple(CriterionAssessmentContract(criterion,
        (CriterionEvidenceRequirement('criterion-' + digest(criterion)[7:39], kind='effect_report'),))
        for criterion in candidate.acceptance_criteria)
    preview = ArchitectureMission(
        id='MISSION-PREVIEW', candidate_id=candidate.id, title=candidate.title,
        summary=candidate.objective, business_objective=candidate.objective,
        business_value=definition['business_value'], architecture_review_reference=decision_id,
        mission_recommendation_reference=candidate.recommendation_id, scope=candidate.scope,
        engineering_constraints=candidate.architecture_constraints,
        acceptance_criteria=candidate.acceptance_criteria,
        technical_assumptions=tuple(profile['technical_assumptions']),
        dependencies=candidate.dependencies,
        required_capabilities=tuple(profile['required_capabilities']),
        required_disciplines=tuple(RequiredDiscipline(item) for item in profile['required_disciplines']),
        risks=tuple(definition['risks']), status=ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
        criterion_assessment_contracts=contracts, maximum_actions=profile['maximum_actions'],
        maximum_consecutive_no_progress_actions=profile['maximum_consecutive_no_progress_actions'],
        effect_policy=effect, repository_evidence_source=repository_source)
    planning = ArchitecturePlanningEvidence(
        scope=candidate.scope, write_scopes=effect.write_paths,
        non_goals=tuple(definition['exclusions']), risk_inputs=tuple(definition['risks']),
        human_gates=tuple(profile['human_gates']), dependencies=candidate.dependencies,
        context_input_bound=provider_bounds['input_token_bound'],
        context_output_bound=provider_bounds['output_token_bound'], provenance_revision=subject_revision,
        criterion_assessment_contracts=contracts, maximum_actions=profile['maximum_actions'],
        maximum_consecutive_no_progress_actions=profile['maximum_consecutive_no_progress_actions'],
        mission_spec_digest=canonical_digest(preview.to_dict()), effect_policy=effect,
        repository_evidence_source=repository_source)
    body = {'contract_version': CONTRACT, 'source': source, 'definition': definition,
            'candidate': candidate.to_dict(), 'subject_revision': subject_revision,
            'mission_preview': preview.to_dict(), 'planning': planning.to_dict(),
            'trusted_profile_digest': digest(profile), 'decision_effects':
            ['REGISTER_CANDIDATE', 'BUSINESS_APPROVAL', 'ARCHITECTURE_APPROVAL', 'GOVERNED_INTAKE'],
            'execution_started': False, 'actions_predefined': False,
            'consequences': {'repository_effect': effect.to_dict(),
                             'human_gates': profile['human_gates'],
                             'exclusions': definition['exclusions'], 'risks': definition['risks']}}
    body['dependency_bindings'] = [{'candidate_id':dep,'subject_revision':catalog[dep]['subject_revision'],
                                  'object_id':catalog[dep]['object_id'],'reason':definition['dependency_reasons'][dep],
                                  'kind':'REQUIRES','state':'PROPOSED'} for dep in definition['dependencies']]
    body = json.loads(json.dumps(body))
    return {'contract_version': CONTRACT, 'object_id': object_id, 'revision': revision,
            'definition': definition, 'questions': [], 'approval_supported': True,
            'package': body, 'package_digest': digest(body)}
