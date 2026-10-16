"""Exact original portable document bytes for a pre-admission Genesis effect plan."""
from copy import deepcopy
from .project_bootstrap.schema import canonical, load_json, validate, ContractError
from .project_bootstrap.service import assets, digest, safe_path, BASE_PATH, BASELINE, CATALOG_DIGEST

CONTRACT = 'forge-genesis-bootstrap-effect-plan/v1'
PROFILE = 'CREATE_GENESIS_LOCAL/1.0'
EFFECT_PURPOSE = 'GENESIS_BOOTSTRAP_EFFECT_ONLY/1.0'
EFFECTS = ('CREATE_NEW_TARGET', 'INITIALIZE_LOCAL_GIT', 'WRITE_EXACT_MANIFEST_FILES',
           'RUN_EXTERNALLY_PINNED_VALIDATION', 'CREATE_LOCAL_COMMIT', 'REGISTER_COMMITTED_AUTHORITY_ATTACHMENT')


def frozen_bundle(record):
    """Called only after owning R52 sealed-record/scope validation; never render."""
    value = record['input']
    expected = {'baseline':BASELINE,'role':'authority','mode':'GENESIS','host_profile':'LOCAL_POSIX',
                'stack_profile':'NO_PRODUCT_CODE','security_profile':'DOCUMENT_ONLY'}
    if record['proposal_kind'] != 'pb-render/1.0' or any(value.get(k) != v for k,v in expected.items()):
        raise ContractError('unsupported original Genesis document proposal')
    registry, selected = assets()
    rows = record['result']['artifacts']
    if not isinstance(rows,list) or not 1 <= len(rows) <= 64:
        raise ContractError('finite original document inventory required')
    paths = [r['path'] for r in rows]
    required = set(registry['common_paths']+registry['authority_paths'])
    required.update(BASE_PATH+'/'+name for name in (*selected,'catalog.json'))
    manifest_path = 'engineering/bootstrap-manifest.json'
    required.add(manifest_path)
    if paths != sorted(required):
        raise ContractError('exact portable Genesis document inventory required')
    payload = {}
    for row in rows:
        if set(row) != {'path','mode','sha256','content'} or row['mode'] != 0o644:
            raise ContractError('original portable mode/fields invalid')
        safe_path(row['path'])
        raw = row['content'].encode('utf-8')
        if len(raw) > 131072 or digest(raw) != row['sha256']:
            raise ContractError('original document bytes invalid')
        payload[row['path']] = raw
    for name, raw in {**selected,'catalog.json':canonical(registry)}.items():
        if payload[BASE_PATH+'/'+name] != raw:
            raise ContractError('original baseline differs from qualified installed pin')
    if payload['engineering/render-input.json'] != canonical(value):
        raise ContractError('original frozen input differs')
    manifest = load_json(payload[manifest_path])
    validate(manifest,load_json(selected['manifest.schema.json']))
    if manifest['input_digest'] != digest(canonical(value)) or record['result']['input_digest'] != manifest['input_digest']:
        raise ContractError('original input binding differs')
    if manifest['manifest_digest'] != digest(canonical({k:v for k,v in manifest.items() if k!='manifest_digest'})) or manifest['renderer_source_digest'] != digest(selected['render_core.py']):
        raise ContractError('original manifest/self-reference pin differs')
    inventory = {r['relative_path']:r for r in manifest['artifacts']}
    if len(inventory) != len(manifest['artifacts']) or set(inventory) != required-{manifest_path}:
        raise ContractError('original manifest inventory differs')
    for path, row in inventory.items():
        if row['expected_after_digest'] != digest(payload[path]) or row['bytes'] != len(payload[path]) or row['input_digest'] != manifest['input_digest'] or row['source_digest'] != manifest['renderer_source_digest']:
            raise ContractError('original manifest document binding differs')
    identity = value['identity']
    declaration = load_json(payload['.engineering-platform/repository.json'])
    expected_declaration = {'schema_version':'1.0','project':{'id':identity['project_id'],'authority_repository_id':identity['authority_repository_id']},
                            'repository':{'id':identity['repository_id'],'role':'authority'},'validation':{'kind':'command','entrypoint':'bash scripts/validate.sh'}}
    if declaration != expected_declaration or identity['repository_id'] != identity['authority_repository_id']:
        raise ContractError('original identity/declaration incompatible')
    files = [{**deepcopy(r),'bytes':len(payload[r['path']]),'expected_before':'ABSENT'} for r in rows]
    return {'files':files,'bundle_digest':digest(canonical(rows)), 'manifest_digest':manifest['manifest_digest'],
            'manifest_file_sha256':digest(payload[manifest_path]),'manifest_self_reference':manifest['self_reference'],
            'renderer_version':manifest['renderer_version'],'renderer_source_digest':manifest['renderer_source_digest'],
            'baseline':BASELINE,'catalog_asset_sha256':CATALOG_DIGEST,'catalog_canonical_digest':digest(canonical(registry)),
            'identity':{k:identity[k] for k in ('project_id','repository_id','authority_repository_id')},
            'validation':{'profile':'PORTABLE_HASH_SCHEMA_PROFILE','entrypoint':'bash scripts/validate.sh',
                          'script_sha256':digest(payload['scripts/validate.sh']),'file_mode':'0644',
                          'validator_path':BASE_PATH+'/validate.py','validator_sha256':digest(selected['validate.py']),
                          'required_python':'3.14','isolation':'ISOLATED_NO_SITE_PACKAGES',
                          'external_trust':'EP_OWNER_QUALIFIED_PIN_REQUIRED'}}


def plan_request(value):
    from .approved_worklist import identifier, timestamp
    fields = {'contract_version','instance_id','dossier_id','operation_id','source_plan_id','source_subject',
              'expected_content_revision','target','effects','expires_at','expected_plan_revision','previous_plan_id','blocking_open_points'}
    if not isinstance(value,dict) or set(value)!=fields or value['contract_version']!=CONTRACT or len(canonical(value))>65536:
        raise ContractError('closed finite Genesis plan request required')
    for name in ('instance_id','dossier_id','operation_id','source_plan_id'):
        identifier(value[name])
    target=value['target']
    if not isinstance(target,dict) or set(target)!={'ep_instance_id','placement_ref','target_ref'}:
        raise ContractError('opaque EP placement and target references required')
    for text in target.values():identifier(text)
    if value['effects']!=list(EFFECTS):raise ContractError('exact finite Genesis effect set required')
    timestamp(value['expires_at'])
    for name,maximum in [('expected_plan_revision',7),('expected_content_revision',8)]:
        if type(value[name]) is not int or not 0<=value[name]<=maximum:raise ContractError('finite expected revision required')
    if value['expected_plan_revision']==0:
        if value['previous_plan_id'] is not None:raise ContractError('first plan has no predecessor')
    else:identifier(value['previous_plan_id'])
    points=value['blocking_open_points']
    if not isinstance(points,list) or len(points)>32 or any(not isinstance(p,str) or not 1<=len(p)<=1024 for p in points):
        raise ContractError('finite original blocking open points required')
    # Reuse the exact R54 source-subject parser, without inventing a second subject language.
    from .proposal_content_contract import decision_request, PROFILE_ID
    sample={'contract_version':'forge-project-proposal-content-decision/v1','instance_id':value['instance_id'],
            'dossier_id':value['dossier_id'],'operation_id':value['operation_id'],'plan_id':value['source_plan_id'],
            'subject':value['source_subject'],'profile_id':PROFILE_ID,'role':'BUSINESS','decision':'REQUEST_CHANGES',
            'expected_decision_revision':0,'previous_decision_id':None,'reason':'source subject validation only','acknowledged_open_points':[]}
    decision_request(sample)
    return load_json(canonical(value)),digest(canonical(value))


def plan_document(record, content, request, principal):
    """Freeze existing bytes and decision references; no render, clock or EP operation."""
    request,request_digest=plan_request(request)
    if request['source_plan_id']!=record['plan_id'] or request['source_subject']!=content['subject'] or request['expected_content_revision']!=content['decision_revision']:
        raise ContractError('exact original proposal/content revision differs')
    points=record['input']['product']['open_questions']
    if any(p not in points for p in request['blocking_open_points']):
        raise ContractError('blocking open point is not in original proposal')
    bundle=frozen_bundle(record)
    decisions=[{'decision_id':r['decision_id'],'revision':r['revision'],'request_digest':r['request_digest'],
                'role':r['request']['role'],'decision':r['request']['decision'],'human_binding':r['human_binding'],'grant_id':r['grant_id']}
               for r in content['history']]
    binding=[request['instance_id'],principal['principal_id'],principal['audience'],request['dossier_id'],request['operation_id']]
    plan={'contract_version':CONTRACT,'profile_id':PROFILE,'effect_purpose':EFFECT_PURPOSE,
          'plan_id':'bootstrap-plan-'+digest(canonical(binding))[:32],'plan_revision':request['expected_plan_revision']+1,
          'previous_plan_id':request['previous_plan_id'],'instance_id':request['instance_id'],
          'principal_id':principal['principal_id'],'audience':principal['audience'],'dossier_id':request['dossier_id'],
          'operation_id':request['operation_id'],'request_digest':request_digest,
          'source_subject':deepcopy(content['subject']),'content_revision':content['decision_revision'],
          'content_history_digest':digest(canonical(content['history'])),'original_content_decisions':decisions,
          'state':'EP_ADMISSION_REQUIRED','identity_state':'PROPOSED_NOT_RESERVED','reservation':'NOT_REQUESTED',
          'target':{**request['target'],'required_before':'ABSENT','absence_evidence':'NOT_OBSERVED_BY_FORGE',
                    'placement_semantics':'EP_OWNER_ALLOWED_DIRECT_CHILD_NEW_TARGET'},
          'effects':list(EFFECTS),'expires_at':request['expires_at'],
          'retention':'RETAIN_ORIGINAL_EVIDENCE_NO_AUTOMATIC_ROLLBACK','maximum_execution_seconds':300,
          'open_questions':deepcopy(points),'blocking_open_points':request['blocking_open_points'],
          'documents':bundle,'target_write':'NOT_PERFORMED','ep_admission':'NOT_REQUESTED','ep_credential':'NOT_ISSUED',
          'execution_authorized':False,'project_readiness':'NOT_ASSESSED','mission':'NOT_REQUESTED'}
    plan['plan_digest']=digest(canonical(plan))
    if len(canonical(plan))>1048576:raise ContractError('finite effect plan result required')
    return plan


class BootstrapConflict(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def effect_request(value):
    from .approved_worklist import identifier
    from .proposal_content_contract import hash_value
    from .advisory_contract import text
    fields = {'contract_version','instance_id','dossier_id','operation_id','plan_id','plan_digest','purpose',
              'decision','reason','expected_decision_revision','previous_decision_id'}
    if not isinstance(value,dict) or set(value)!=fields or value['contract_version']!=CONTRACT or value['purpose']!=EFFECT_PURPOSE or len(canonical(value))>65536:
        raise ContractError('closed exact Genesis effect decision required')
    for key in ('instance_id','dossier_id','operation_id','plan_id'):
        identifier(value[key])
    hash_value(value['plan_digest']); text(value['reason'],2000)
    if value['decision'] not in ('APPROVE_EFFECT','REQUEST_CHANGES'):
        raise ContractError('explicit effect decision required')
    n=value['expected_decision_revision']
    if type(n) is not int or not 0<=n<8:
        raise ContractError('finite effect revision required')
    if n==0:
        if value['previous_decision_id'] is not None:
            raise ContractError('first effect decision has no predecessor')
    else:
        identifier(value['previous_decision_id'])
    return load_json(canonical(value)),digest(canonical(value))
