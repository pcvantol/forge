"""Closed qualified EP snapshot validation; historical facts without invented metadata."""
from datetime import datetime
from hashlib import sha256
from importlib.resources import files
import re
from .project_bootstrap.schema import ContractError, canonical, load_json
from .project_adoption.service import document_path

CONTRACT = 'forge-ep-inspection-adoption-preview/v1'
KIND = 'ep-inspection-adoption-preview/1.0'
EP_REVISION = 'f3b56303b561a7193965f4aa41fd8da744a8c1c2'
EP_TREE = '28d957a5988d35bc3469e8767006595c7cb3d8f1'
EP_SCHEMA_SHA256 = 'fe289b3f5a00a837c1e2afdefc675e2fdc2427b8fd419017883347c0b6dc5e96'
EP_VERSION = '2.3.121'
MAX_RESPONSE = 1048576
MAX_DOCUMENT_BYTES = 16384
MAX_DOCUMENT_CHARACTERS = 8192


def _schema(value, rule):
    """Evaluate this finite pinned dialect only, without refs, imports or URI resolution."""
    if 'anyOf' in rule:
        for alternative in rule['anyOf']:
            try:
                _schema(value, alternative)
                return
            except ContractError:
                pass
        raise ContractError('EP schema alternative mismatch')
    kinds = rule.get('type')
    kinds = kinds if isinstance(kinds, list) else [kinds]
    types = {'object': lambda x: type(x) is dict, 'array': lambda x: type(x) is list,
             'string': lambda x: type(x) is str, 'integer': lambda x: type(x) is int,
             'boolean': lambda x: type(x) is bool, 'null': lambda x: x is None}
    # A const-only published node still has exact value/type semantics.
    if kinds != [None] and not any(k in types and types[k](value) for k in kinds):
        raise ContractError('EP schema type mismatch')
    if 'const' in rule and (type(value) is not type(rule['const']) or value != rule['const']):
        raise ContractError('EP schema constant mismatch')
    if 'enum' in rule and not any(type(value) is type(x) and value == x for x in rule['enum']):
        raise ContractError('EP schema selection mismatch')
    if type(value) is dict:
        properties = rule.get('properties', {})
        if rule.get('additionalProperties') is not False or set(value)-set(properties) or set(rule.get('required', []))-set(value):
            raise ContractError('EP closed fields mismatch')
        for key, item in value.items():
            _schema(item, properties[key])
    elif type(value) is list:
        if len(value) > rule.get('maxItems', 128):
            raise ContractError('EP array bound exceeded')
        for item in value:
            _schema(item, rule['items'])
    elif type(value) is str:
        if len(value) > rule.get('maxLength', 1048576) or ('pattern' in rule and re.fullmatch(rule['pattern'], value) is None):
            raise ContractError('EP string bound/format mismatch')
    elif type(value) is int and value < rule.get('minimum', value):
        raise ContractError('EP integer bound exceeded')


def observation(raw, binding):
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
        raise ContractError('finite original EP response required')
    schema_bytes = files('forge').joinpath('api/ep-preproject-local-inspection-v1.schema.json').read_bytes()
    if sha256(schema_bytes).hexdigest() != EP_SCHEMA_SHA256:
        raise ContractError('qualified EP schema asset mismatch')
    value = load_json(raw)
    schema = load_json(schema_bytes)['oneOf'][0]
    _schema(value, schema)
    for key in ('operation_id', 'source_ref', 'instance_id', 'host_id'):
        if value[key] != binding[key]:
            raise ContractError('EP original subject mismatch')
    if value['producer_version'] != EP_VERSION or value['outcome'] != 'COMPLETE' or value['http_status'] != 200 or value['error'] is not None or value['freshness'] != 'AS_OF_OBSERVATION_NOT_CONTINUOUS':
        raise ContractError('EP has no supported complete historical observation')
    obs = value['observation']
    if not isinstance(obs, dict):
        raise ContractError('EP observation absent')
    when = datetime.fromisoformat(obs['observed_at'].replace('Z', '+00:00'))
    if when.tzinfo is None:
        raise ContractError('EP observation time lacks timezone')
    selected = obs['selection']
    if len(set(selected)) != len(selected) or sorted(selected) != sorted(binding['paths']):
        raise ContractError('EP selected paths mismatch')
    for path in selected:
        document_path(path)
    documents = obs['documents']
    paths = [x['path'] for x in documents]
    if len({x.casefold() for x in paths}) != len(paths) or not set(paths) <= set(selected):
        raise ContractError('EP document selection mismatch')
    if set(obs['exclusions']) != {'ALL_UNSELECTED_CONTENT', 'ASSESSMENT_AND_REPOSITORY_EXECUTION'}:
        raise ContractError('EP selection exclusions mismatch')
    for doc in documents:
        if doc['state'] == 'ABSENT':
            if doc['sha256'] is not None or doc['content'] is not None:
                raise ContractError('EP absent document asserts bytes')
        elif doc['sha256'] is None:
            raise ContractError('EP present document lacks hash')
        elif doc['content'] is not None:
            if doc['path'] not in binding['content_paths'] or sha256(doc['content'].encode('utf-8')).hexdigest() != doc['sha256']:
                raise ContractError('EP document bytes/consent mismatch')
    declaration = obs['canonical_declaration']
    if (declaration['state'] == 'OBSERVED_DECLARATION_ONLY') != isinstance(declaration['identity'], dict):
        raise ContractError('EP declaration null semantics mismatch')
    git = obs['git']
    if (obs['state'] in ('EXISTING_GIT', 'UNBORN_GIT')) != isinstance(git, dict):
        raise ContractError('EP Git presence mismatch')
    if git:
        expected_present = git['state'] == 'EXISTING_GIT'
        if git['state'] != obs['state'] or any((git[key] is not None) != expected_present for key in ('head', 'tree')):
            raise ContractError('EP Git revision semantics mismatch')
    return value


def document_observations(value):
    """Typed shared-engine observations: unknown mode/owner stay unknown, never0644."""
    result = []
    for doc in value['observation']['documents']:
        item = {'path': doc['path'], 'status': doc['state'], 'mode': None,
                'semantic_owner': 'UNKNOWN', 'update_class': 'UNKNOWN'}
        if doc['state'] == 'PRESENT':
            item['sha256'] = doc['sha256']
            content = doc['content']
            if content is not None and len(content) <= MAX_DOCUMENT_CHARACTERS and len(content.encode('utf-8')) <= MAX_DOCUMENT_BYTES:
                item['content'] = content
            elif content is not None:
                item['limitation'] = 'R51_DOCUMENT_CONTENT_LIMIT_EXCEEDED'
        result.append(item)
    return result
