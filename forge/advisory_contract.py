"""Versioned, bounded textual advice; no approval or execution representation."""
from hashlib import sha256
import json
import re
from .approved_worklist import identifier
from .models.producer import _URL_CREDENTIAL, _KNOWN_TOKEN, _BEARER_CREDENTIAL, _SECRET_ASSIGNMENT

CONTRACT = 'forge-advisory-conversation/v1'
MODES = ('BUSINESS', 'ARCHITECTURE')

class AdvisoryConflict(RuntimeError):
    def __init__(self, code):
        self.code=code
        super().__init__(code)

class AdvisoryUnsupported(ValueError):pass

def digest(value):
    return 'sha256:' + sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()

def text(value, maximum):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 and c not in '\n\t' for c in value)
            or '<' in value or '>' in value
            or any(pattern.search(value) for pattern in (_URL_CREDENTIAL,_KNOWN_TOKEN,_BEARER_CREDENTIAL,_SECRET_ASSIGNMENT))):
        raise ValueError('bounded safe plain text required')
    return value

def request(value):
    fields = {'contract_version','turn_id','instance_id','project_id','repository_id',
              'conversation_id','advisor_kind','objective','expected_revision','context_revision','selected_sources'}
    if not isinstance(value, dict) or set(value) != fields or value['contract_version'] != CONTRACT:
        raise ValueError('invalid advisory request shape')
    for k in ['turn_id','instance_id','project_id','repository_id','conversation_id']:
        identifier(value[k])
    if value['advisor_kind'] not in MODES:raise AdvisoryUnsupported('ADVISOR_UNSUPPORTED')
    if type(value['expected_revision']) is not int or value['expected_revision'] < 0:
        raise ValueError('unsupported mode or revision')
    if not isinstance(value['context_revision'], str) or re.fullmatch(r'sha256:[0-9a-f]{64}',value['context_revision']) is None:
        raise ValueError('invalid context revision')
    selections=value['selected_sources']
    if not isinstance(selections,list) or len(selections)>2:raise ValueError('invalid selected sources')
    for source in selections:
        if not isinstance(source,dict) or set(source)!={'source_id','version'}:raise ValueError('invalid source shape')
        identifier(source['source_id'])
        if not isinstance(source['version'],str) or re.fullmatch(r'sha256:[0-9a-f]{64}',source['version']) is None:raise ValueError('invalid source version')
    text(value['objective'],1000)
    return json.loads(json.dumps(value)), digest(value)

OUTPUT_SCHEMA = {'type':'object','additionalProperties':False,'required':['contract_version','request_digest','advisor_kind','summary','alternatives','questions','suggestions','evidence_references','applied'],
    'properties':{'contract_version':{'const':CONTRACT},'request_digest':{'type':'string'},
    'advisor_kind':{'enum':list(MODES)},'summary':{'type':'string','minLength':1,'maxLength':512},
    **{k:{'type':'array','maxItems':4,'items':{'type':'string','minLength':1,'maxLength':256}} for k in ['alternatives','questions','suggestions','evidence_references']},'applied':{'const':False}}}

def result(value, admitted, references):
    if (not isinstance(value, dict) or set(value) != set(OUTPUT_SCHEMA['required'])
            or value['contract_version'] != CONTRACT or value['request_digest'] != admitted['request_digest']
            or value['advisor_kind'] != admitted['request']['advisor_kind'] or value['applied'] is not False):
        raise ValueError('advice output binding invalid')
    text(value['summary'],512)
    for k in ['alternatives','questions','suggestions','evidence_references']:
        values=value[k]
        if not isinstance(values,list) or len(values)>4:raise ValueError('invalid advice list')
        for v in values:text(v,256)
    if any(v not in references for v in value['evidence_references']):raise ValueError('unproven advice reference')
    return json.loads(json.dumps(value))
