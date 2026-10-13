"""Authenticated finite private HTTP dossiers above the unchanged R50/R51 services."""
from hashlib import sha256
import json
from urllib.parse import urlsplit, parse_qs
from .approved_worklist import identifier
from .project_bootstrap.schema import canonical, load_json, ContractError
from .project_bootstrap.service import render, digest, safe_path, check_input as check_basis
from .project_adoption.service import payload as adoption_payload, check_input as check_adoption
from .project_proposal_grant import CONTRACT, KINDS
from .project_proposal_storage import write
from .workspace_review_grant import _locked

MAX_REQUEST = 262144
MAX_RESULT = 1048576
MAX_ARTIFACTS = 64


def plan_identity(principal, dossier, operation):
    return 'proposal-' + digest(canonical([principal.instance_id,principal.principal_id,principal.audience,dossier,operation]))[:32]


def result(kind, value):
    files = render(value) if kind == KINDS[0] else adoption_payload(value)
    if len(files) > MAX_ARTIFACTS or any(len(raw) > 131072 for raw in files.values()): raise ContractError('finite artifact limit')
    artifacts = [{'path':name,'mode':0o644,'sha256':digest(raw),'content':raw.decode('utf-8')} for name,raw in sorted(files.items())]
    summary = ('Portable project basis proposal; no project registered.\n' + '\n'.join(x['path'] + ' sha256:' + x['sha256'] for x in artifacts)) if kind == KINDS[0] else files['README.md'].decode('utf-8')
    value = {'state':'PROPOSED_NOT_APPROVED','original_contract_version':kind,'input_digest':digest(canonical(value)),
             'summary':summary,'artifacts':artifacts,'result_digest':digest(canonical(artifacts)),'observations':'SUPPLIED_UNVERIFIED','repository_quality':'NOT_ASSESSED'}
    if len(canonical(value)) > MAX_RESULT: raise ContractError('finite result limit')
    return value


class InvalidRequest(ValueError):
    pass


class ProjectProposalService:
    def __init__(self, grant): self.grant = grant

    def _record(self, store, plan_id):
        record = store['records'].get(plan_id)
        if record is None: return None
        fields = {'plan_id','instance_id','principal_id','audience','dossier_id','operation_id','proposal_kind','request_digest','input','result','record_digest','integrity_tag'}
        if not isinstance(record,dict) or set(record) != fields: raise ValueError('proposal record invalid')
        original = {k:v for k,v in record.items() if k not in {'record_digest','integrity_tag'}}
        if record['record_digest'] != digest(canonical(original)) or record['plan_id'] != plan_id or record['proposal_kind'] not in KINDS:
            raise ValueError('proposal record integrity failed')
        import secrets
        signed = {k:v for k,v in record.items() if k != 'integrity_tag'}
        if not secrets.compare_digest(record['integrity_tag'], self.grant.integrity(signed)): raise ValueError('frozen proposal integrity failed')
        request = {'contract_version':CONTRACT, **{k:record[k] for k in ['instance_id','dossier_id','operation_id','proposal_kind','input']}}
        if record['request_digest'] != digest(canonical(request)) or len(canonical(request)) > MAX_REQUEST: raise ValueError('original request binding invalid')
        for k in ['instance_id','principal_id','audience','dossier_id','operation_id']: identifier(record[k])
        (check_basis if record['proposal_kind'] == KINDS[0] else check_adoption)(record['input'])
        binding = [record[k] for k in ['instance_id','principal_id','audience','dossier_id','operation_id']]
        if plan_id != 'proposal-' + digest(canonical(binding))[:32]: raise ValueError('proposal identity invalid')
        r = record['result']
        if not isinstance(r,dict) or set(r) != {'state','original_contract_version','input_digest','summary','artifacts','result_digest','observations','repository_quality'} or r['state'] != 'PROPOSED_NOT_APPROVED' or r['original_contract_version'] != record['proposal_kind'] or r['input_digest'] != digest(canonical(record['input'])) or r['result_digest'] != digest(canonical(r['artifacts'])):
            raise ValueError('proposal result binding invalid')
        if r['observations'] != 'SUPPLIED_UNVERIFIED' or r['repository_quality'] != 'NOT_ASSESSED' or not isinstance(r['summary'],str) or not isinstance(r['artifacts'],list) or not 1 <= len(r['artifacts']) <= MAX_ARTIFACTS: raise ValueError('proposal semantics invalid')
        paths = []
        for artifact in r['artifacts']:
            if not isinstance(artifact,dict) or set(artifact) != {'path','mode','sha256','content'} or artifact['sha256'] != digest(artifact['content'].encode('utf-8')) or artifact['mode'] != 0o644:
                raise ValueError('proposal artifact corrupt')
            safe_path(artifact['path']); paths.append(artifact['path'])
            if len(artifact['content'].encode('utf-8')) > 131072: raise ValueError('proposal artifact limit')
        if paths != sorted(set(paths)): raise ValueError('proposal inventory invalid')
        if len(canonical(r)) > MAX_RESULT: raise ValueError('proposal record exceeds limit')
        return record

    def scoped(self, principal, dossier, record):
        if record['instance_id'] != principal.instance_id or record['principal_id'] != principal.principal_id or record['audience'] != principal.audience or record['dossier_id'] != dossier or record['proposal_kind'] not in principal.kinds:
            raise PermissionError('proposal scope denied')

    def response(self, principal, dossier, record):
        self.scoped(principal,dossier,record)
        return {'contract_version':CONTRACT,'instance_id':record['instance_id'],'principal_id':record['principal_id'],
                'audience':record['audience'],'dossier_id':dossier,'operation_id':record['operation_id'],'plan_id':record['plan_id'],
                'proposal_kind':record['proposal_kind'],'request_digest':record['request_digest'],'record_digest':record['record_digest'],
                'result':record['result'],'read_only_result':True,'approval':'NOT_PERFORMED','registration':'NOT_PERFORMED'}

    def handle(self, method, target, authorization, audience, body=None):
        try:
            if not isinstance(audience,str): raise PermissionError('explicit audience required')
            principal = self.grant.authorize(authorization,audience=audience)
            parsed = urlsplit(target)
            if parsed.fragment or '%' in target or '\\' in target or '//' in parsed.path: raise InvalidRequest('invalid proposal target')
            parts = parsed.path.split('/'); query = parse_qs(parsed.query,strict_parsing=True)
            if any(len(values) != 1 for values in query.values()): raise InvalidRequest('duplicate query')
            if method == 'GET' and parsed.path == '/v1/onboarding/capability':
                if query or body: raise InvalidRequest('capability has no input')
                with self.grant.boundary():
                    principal = self.grant.authorize(authorization,audience=audience); self.grant._store()
                    return 200,{'contract_version':CONTRACT,'capability_id':'PROJECT_PROPOSAL_PREPARE_READ_V1','support':'SUPPORTED_PROPOSAL_ONLY',
                        'instance_id':principal.instance_id,'principal_id':principal.principal_id,'audience':principal.audience,
                        'dossier_ids':list(principal.dossier_ids),'permissions':list(principal.permissions),'proposal_kinds':list(principal.kinds),
                        'limits':{'request_bytes':MAX_REQUEST,'result_bytes':MAX_RESULT,'artifacts':MAX_ARTIFACTS,'records_per_dossier':principal.maximum_records,'global_records':64,'store_bytes':16777216},
                        'operations':['GET /v1/onboarding/capability',*(['POST /v1/onboarding/plans'] if 'PREPARE' in principal.permissions else []),'GET /v1/onboarding/plans/{plan_id}?dossier_id={dossier_id}','GET /v1/onboarding/intents/{operation_id}?dossier_id={dossier_id}'],
                        'decisions':False,'apply':False,'project_registration':False}
            if method == 'POST' and parsed.path == '/v1/onboarding/plans':
                if query or not isinstance(body,dict) or set(body) != {'contract_version','instance_id','dossier_id','operation_id','proposal_kind','input'} or body['contract_version'] != CONTRACT or len(canonical(body)) > MAX_REQUEST:
                    raise InvalidRequest('closed finite proposal request required')
                dossier = identifier(body['dossier_id']); operation = identifier(body['operation_id']); kind = body['proposal_kind']
                principal = self.grant.authorize(authorization,audience=audience,dossier_id=dossier,permission='PREPARE',kind=kind)
                if body['instance_id'] != principal.instance_id: raise PermissionError('foreign instance')
                plan_id = plan_identity(principal,dossier,operation); request_digest = digest(canonical(body))
                with self.grant.boundary():
                    principal = self.grant.authorize(authorization,audience=audience,dossier_id=dossier,permission='PREPARE',kind=kind)
                    store = self.grant._store(); prior = self._record(store,plan_id)
                    if prior is not None:
                        if prior['request_digest'] != request_digest: return 409,{'contract_version':CONTRACT,'error':{'code':'PROPOSAL_IDEMPOTENCY_CONFLICT'}}
                        return 200,self.response(principal,dossier,prior)
                computed = result(kind,body['input'])  # No authority/storage lock held during rendering.
                record = {'plan_id':plan_id,'instance_id':principal.instance_id,'principal_id':principal.principal_id,'audience':audience,
                          'dossier_id':dossier,'operation_id':operation,'proposal_kind':kind,'request_digest':request_digest,'input':body['input'],'result':computed}
                record['record_digest'] = digest(canonical(record))
                record['integrity_tag'] = self.grant.integrity(record)
                with self.grant.boundary():
                    principal = self.grant.authorize(authorization,audience=audience,dossier_id=dossier,permission='PREPARE',kind=kind)
                    store = self.grant._store(); prior = self._record(store,plan_id)
                    if prior is not None:
                        if prior['request_digest'] != request_digest: return 409,{'contract_version':CONTRACT,'error':{'code':'PROPOSAL_IDEMPOTENCY_CONFLICT'}}
                        return 200,self.response(principal,dossier,prior)
                    owner = store['dossiers'].get(dossier)
                    if owner is None or owner['principal_id'] != principal.principal_id or owner['audience'] != audience: raise PermissionError('dossier owner mismatch')
                    count = sum(r.get('dossier_id') == dossier for r in store['records'].values())
                    if len(store['records']) >= 64 or count >= min(owner['maximum_records'],principal.maximum_records): return 409,{'contract_version':CONTRACT,'error':{'code':'PROPOSAL_CAPACITY_EXHAUSTED'}}
                    store['records'][plan_id] = record; write(self.grant.store,store)
                    return 200,self.response(principal,dossier,record)
            if method == 'GET' and len(parts) == 5 and parts[:3] == ['','v1','onboarding'] and parts[3] in {'plans','intents'}:
                if set(query) != {'dossier_id'} or body: raise InvalidRequest('exact dossier query required')
                dossier = identifier(query['dossier_id'][0]); reference = identifier(parts[4])
                principal = self.grant.authorize(authorization,audience=audience,dossier_id=dossier)
                plan_id = reference if parts[3] == 'plans' else plan_identity(principal,dossier,reference)
                with self.grant.boundary():
                    principal = self.grant.authorize(authorization,audience=audience,dossier_id=dossier)
                    record = self._record(self.grant._store(),plan_id)
                    if record is None: return 404,{'contract_version':CONTRACT,'error':{'code':'PROPOSAL_NOT_FOUND'}}
                    return 200,self.response(principal,dossier,record)
            return 404,{'contract_version':CONTRACT,'error':{'code':'PROPOSAL_ROUTE_UNSUPPORTED'}}
        except InvalidRequest:
            return 400,{'contract_version':CONTRACT,'error':{'code':'PROPOSAL_REQUEST_INVALID'}}
        except PermissionError:
            return 403,{'contract_version':CONTRACT,'error':{'code':'PROPOSAL_SCOPE_DENIED'}}
        except ContractError:
            return 422,{'contract_version':CONTRACT,'error':{'code':'PROPOSAL_INPUT_UNSUPPORTED'}}
        except (OSError,KeyError,TypeError,ValueError):
            return 503,{'contract_version':CONTRACT,'error':{'code':'PROPOSAL_UNAVAILABLE_OR_INVALID'}}
