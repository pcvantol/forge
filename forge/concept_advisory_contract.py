"""Finite pre-project briefing advice: no approval, patch or repository effect."""
import json
import re
from .advisory_contract import digest, text, MODES
from .approved_worklist import identifier

CONTRACT = 'forge-preproject-concept-advisory/v1'
LANGUAGES = ('en', 'nl', 'de', 'fr', 'es')
FIELDS = ('name', 'purpose', 'users', 'non_goals', 'constraints', 'open_questions')


def briefing(value):
    if not isinstance(value, dict) or set(value) != {'concept_id', 'revision', 'fields'}:
        raise ValueError('invalid briefing shape')
    identifier(value['concept_id'])
    if type(value['revision']) is not int or value['revision'] < 1:
        raise ValueError('invalid briefing revision')
    if not isinstance(value['fields'], dict) or set(value['fields']) != set(FIELDS):
        raise ValueError('closed briefing fields required')
    for content in value['fields'].values():
        if content is not None:
            text(content, 2000)
    return json.loads(json.dumps(value))


def request(value):
    keys = {'contract_version', 'instance_id', 'dossier_id', 'conversation_id',
            'operation_id', 'turn_id', 'expected_revision', 'briefing',
            'briefing_digest', 'advisor_kind', 'language', 'message',
            'transfer_policy_digest'}
    if not isinstance(value, dict) or set(value) != keys or value['contract_version'] != CONTRACT:
        raise ValueError('invalid concept advice request')
    for key in ('instance_id', 'dossier_id', 'conversation_id', 'operation_id', 'turn_id'):
        identifier(value[key])
    if type(value['expected_revision']) is not int or value['expected_revision'] < 0:
        raise ValueError('invalid conversation revision')
    source = briefing(value['briefing'])
    if value['briefing_digest'] != digest(source):
        raise ValueError('briefing digest mismatch')
    if not isinstance(value['transfer_policy_digest'], str) or re.fullmatch(r'sha256:[0-9a-f]{64}', value['transfer_policy_digest']) is None:
        raise ValueError('invalid explicit transfer binding')
    if value['advisor_kind'] not in MODES or value['language'] not in LANGUAGES:
        raise ValueError('unsupported role or language')
    text(value['message'], 4000)
    if len(json.dumps(value, ensure_ascii=True).encode()) > 32768:
        raise ValueError('finite request capacity exceeded')
    return json.loads(json.dumps(value)), digest(value)


_STRING = {'type': 'string', 'minLength': 1, 'maxLength': 2000}
_REFERENCE = {'type': 'string', 'minLength': 1, 'maxLength': 256}
_CHANGE = {'type': 'object', 'additionalProperties': False,
           'required': ['field', 'before', 'proposed', 'reason', 'references'],
           'properties': {'field': {'enum': list(FIELDS)},
                          'before': {'anyOf': [_STRING, {'type': 'null'}]},
                          'proposed': _STRING, 'reason': _STRING,
                          'references': {'type': 'array', 'minItems': 1, 'maxItems': 4, 'uniqueItems': True, 'items': _REFERENCE}}}
OUTPUT_SCHEMA = {'type': 'object', 'additionalProperties': False,
                 'required': ['contract_version', 'request_digest', 'briefing_digest',
                              'advisor_kind', 'language', 'answer', 'questions',
                              'assumptions', 'changes', 'applied'],
                 'properties': {'contract_version': {'const': CONTRACT},
                                'request_digest': _REFERENCE, 'briefing_digest': _REFERENCE,
                                'advisor_kind': {'enum': list(MODES)}, 'language': {'enum': list(LANGUAGES)},
                                'answer': _STRING,
                                'questions': {'type': 'array', 'maxItems': 6, 'items': _STRING},
                                'assumptions': {'type': 'array', 'maxItems': 6, 'items': _STRING},
                                'changes': {'type': 'array', 'maxItems': 6, 'items': _CHANGE},
                                'applied': {'const': False}}}


def result(value, admitted):
    r = admitted['request']
    if not isinstance(value, dict) or set(value) != set(OUTPUT_SCHEMA['required']):
        raise ValueError('invalid concept advice output')
    for key, expected in [('contract_version', CONTRACT), ('request_digest', admitted['request_digest']),
                          ('briefing_digest', r['briefing_digest']), ('advisor_kind', r['advisor_kind']),
                          ('language', r['language'])]:
        if value[key] != expected:
            raise ValueError('concept advice output binding mismatch')
    if value['applied'] is not False:
        raise ValueError('advice is never applied')
    text(value['answer'], 2000)
    for key in ('questions', 'assumptions'):
        if not isinstance(value[key], list) or len(value[key]) > 6:
            raise ValueError('finite advice list required')
        for item in value[key]:
            text(item, 2000)
    changes = value['changes']
    if not isinstance(changes, list) or len(changes) > 6:
        raise ValueError('finite changes required')
    allowed = admitted['context']['evidence_references']
    seen = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != set(_CHANGE['required']):
            raise ValueError('closed typed change required')
        field = change['field']
        if not isinstance(field, str) or field not in FIELDS or field in seen:
            raise ValueError('unknown or duplicate briefing field')
        if change['before'] != r['briefing']['fields'][field]:
            raise ValueError('change before-context mismatch')
        text(change['proposed'], 2000)
        text(change['reason'], 2000)
        refs = change['references']
        if not isinstance(refs, list) or not 1 <= len(refs) <= 4 or any(not isinstance(ref, str) or ref not in allowed for ref in refs) or len(set(refs)) != len(refs):
            raise ValueError('unproven change source reference')
        seen.add(field)
    if len(json.dumps(value, ensure_ascii=True).encode()) > 32768:
        raise ValueError('finite result capacity exceeded')
    return json.loads(json.dumps(value))
