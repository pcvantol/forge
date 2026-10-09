"""Generated content proposals; authority and mechanical fields stay server owned."""
import json
from .advisory_contract import text, digest, request as advisory_request
from .advisory_contract import CONTRACT as ADVISORY_CONTRACT

CONTRACT = 'forge-chat-first-mission/v1'
CONTENT_FIELDS = ('title', 'objective', 'business_value', 'expected_result',
                  'scope', 'exclusions', 'acceptance_criteria',
                  'architecture_choices', 'risks', 'dependencies', 'questions',
                  'change_summary', 'work_kind', 'dependency_reasons', 'possible_subresults', 'components')
LIST_FIELDS = CONTENT_FIELDS[4:11] + ('components',)
WORK_KINDS = ('INVESTIGATE', 'DESIGN', 'BUILD', 'DOCUMENT', 'UNDECIDED')


def refine_request(value):
    """Reuse existing bounded turn fields under a distinct output contract."""
    if not isinstance(value, dict) or value.get('contract_version') != CONTRACT:
        raise ValueError('versioned concept request required')
    advisory_request({**value, 'contract_version': ADVISORY_CONTRACT})
    copied = json.loads(json.dumps(value))
    return copied, digest(copied)

OUTPUT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['contract_version', 'request_digest', 'definition'],
    'properties': {
        'contract_version': {'const': CONTRACT},
        'request_digest': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'},
        'definition': {
            'type': 'object', 'additionalProperties': False,
            'required': list(CONTENT_FIELDS),
            'properties': {
                **{k: {'type': 'string', 'minLength': 1,
                       'maxLength': 256 if k == 'title' else 1000}
                   for k in CONTENT_FIELDS if k not in LIST_FIELDS},
                **{k: {'type': 'array', 'maxItems': 8,
                       'items': {'type': 'string', 'minLength': 1, 'maxLength': 1000}}
                   for k in LIST_FIELDS},
                'work_kind': {'enum': list(WORK_KINDS)},
                'possible_subresults': {'type':'array','maxItems':4,'items':{
                    'type':'object','additionalProperties':False,
                    'required':['title','expected_result','acceptance_criteria'],
                    'properties':{'title':{'type':'string','minLength':1,'maxLength':256},
                        'expected_result':{'type':'string','minLength':20,'maxLength':1000},
                        'acceptance_criteria':{'type':'array','minItems':1,'maxItems':4,
                            'items':{'type':'string','minLength':20,'maxLength':1000}}}}},
                'dependency_reasons': {'type':'object','maxProperties':8,
                                      'additionalProperties':{'type':'string','minLength':20,'maxLength':1000}},
            },
        },
    },
}


def proposed_definition(value, request_digest, allowed_dependencies, work_profiles=None):
    """Validate content only; never interpret model text as an authority grant.

    Missing substantive content is preserved as a question-bearing concept.
    Completeness for approval additionally requires trusted planning/readiness.
    """
    if (not isinstance(value, dict) or set(value) != set(OUTPUT_SCHEMA['required'])
            or value['contract_version'] != CONTRACT
            or value['request_digest'] != request_digest):
        raise ValueError('concept output binding differs')
    definition = value['definition']
    if not isinstance(definition, dict) or set(definition) != set(CONTENT_FIELDS):
        raise ValueError('closed concept content required')
    for key in CONTENT_FIELDS:
        field = definition[key]
        if key == 'possible_subresults':
            if not isinstance(field,list) or len(field)>4:
                raise ValueError('finite possible subresults required')
            titles=set()
            for result in field:
                if not isinstance(result,dict) or set(result)!={'title','expected_result','acceptance_criteria'}:
                    raise ValueError('closed human subresult proposal required')
                text(result['title'],256);text(result['expected_result'],1000)
                criteria=result['acceptance_criteria']
                if (result['title'] in titles or len(result['expected_result'].strip())<20
                        or not isinstance(criteria,list) or not 1<=len(criteria)<=4
                        or any(not isinstance(c,str) for c in criteria) or len(set(criteria))!=len(criteria)):
                    raise ValueError('distinct substantive subresults required')
                for criterion in criteria:
                    text(criterion,1000)
                    if len(criterion.strip())<20:
                        raise ValueError('testable subresult criterion required')
                titles.add(result['title'])
            continue
        if key == 'dependency_reasons':
            if not isinstance(field,dict) or set(field) != set(definition['dependencies']):
                raise ValueError('exact dependency reasons required')
            for reason in field.values():
                text(reason,1000)
                if len(reason.strip()) < 20:
                    raise ValueError('substantive dependency reason required')
            continue
        if key == 'work_kind':
            if field not in WORK_KINDS:
                raise ValueError('explicit supported proposed work kind required')
            continue
        if key in LIST_FIELDS:
            if (not isinstance(field, list) or len(field) > 8
                    or any(not isinstance(item, str) for item in field)
                    or len(field) != len(set(field))):
                raise ValueError('bounded unique concept content required')
            for item in field:
                text(item, 1000)
        else:
            text(field, 256 if key == 'title' else 1000)
    if work_profiles is not None:
        allowed_components = work_profiles.get(definition['work_kind'],{}).get('components',{})
        if any(name not in allowed_components for name in definition['components']):
            raise ValueError('component outside trusted project catalog')
        if not definition['components'] and not definition['questions']:
            raise ValueError('missing component choice requires a content question')
    if any(item not in allowed_dependencies for item in definition['dependencies']):
        raise ValueError('dependency outside authorized catalog')
    if (not definition['scope'] or not definition['acceptance_criteria']
            or any(len(item.strip()) < 20 for item in definition['acceptance_criteria'])
            or definition['work_kind'] == 'UNDECIDED'):
        if not definition['questions']:
            raise ValueError('incomplete concept requires substantive questions')
    return json.loads(json.dumps(definition))
