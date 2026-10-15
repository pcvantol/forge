"""One private durable proposal from an already selected original EP inspection."""
from contextlib import contextmanager
from hashlib import sha256
import secrets
import sqlite3
import time
from urllib.parse import urlsplit, parse_qs
from .approved_worklist import identifier
from .project_bootstrap.schema import canonical, ContractError
from .ep_inspection_contract import CONTRACT, KIND, EP_REVISION
from .ep_inspection_preview import check_input, result
from .ep_inspection_peer import original, PeerError

MAX_REQUEST = 262144


def plan_identity(principal, dossier, operation):
    return 'inspection-proposal-'+sha256(canonical([principal.instance_id,principal.principal_id,principal.audience,dossier,operation])).hexdigest()[:32]


class InspectionAdoptionService:
    def __init__(self, grant):
        self.grant = grant

    def _record(self, store, plan_id):
        record = store['records'].get(plan_id)
        if record is None:
            return None
        fields = {'plan_id','instance_id','principal_id','audience','dossier_id','operation_id','pairing_id','pairing_digest',
                  'request_digest','input','state','source','result','integrity_tag'}
        if not isinstance(record, dict) or set(record) != fields:
            raise ContractError('closed original adoption record required')
        unsigned = {k:v for k,v in record.items() if k != 'integrity_tag'}
        if not secrets.compare_digest(record['integrity_tag'],self.grant.integrity(unsigned)):
            raise ContractError('original proposal record integrity failed')
        if record['state'] not in ('PREPARING','PREPARED') or record['plan_id'] != plan_id:
            raise ContractError('original proposal state invalid')
        for key in ('instance_id','principal_id','audience','dossier_id','operation_id','pairing_id'):
            identifier(record[key])
        request = {'contract_version':CONTRACT,**{k:record[k] for k in ('instance_id','dossier_id','operation_id','pairing_id','input')}}
        if sha256(canonical(request)).hexdigest() != record['request_digest']:
            raise ContractError('original request binding invalid')
        check_input(record['input'])
        if record['state'] == 'PREPARING':
            if record['source'] is not None or record['result'] is not None:
                raise ContractError('pending original has uncommitted result')
        else:
            source, prepared = record['source'], record['result']
            if not isinstance(source, dict) or set(source) != {'response','response_digest','raw_response','raw_sha256'}:
                raise ContractError('original source capture invalid')
            if sha256(canonical(source['response'])).hexdigest() != source['response_digest'] or sha256(source['raw_response'].encode()).hexdigest() != source['raw_sha256']:
                raise ContractError('original source capture digest invalid')
            if not isinstance(prepared, dict) or prepared.get('state') != 'PROPOSED_NOT_APPROVED' or prepared.get('input_digest') != sha256(canonical(record['input'])).hexdigest() or prepared.get('result_digest') != sha256(canonical(prepared.get('artifacts'))).hexdigest() or prepared['source_binding']['snapshot_digest'] != source['response_digest']:
                raise ContractError('original result binding invalid')
            for artifact in prepared['artifacts']:
                if set(artifact) != {'path','mode','content','sha256'} or artifact['path'] not in ('README.md','proposal.json') or artifact['mode'] != 0o644 or sha256(artifact['content'].encode()).hexdigest() != artifact['sha256']:
                    raise ContractError('original result artifact invalid')
        return record

    def _authorize_record(self, principal, dossier, record):
        for key in ('instance_id','principal_id','audience','pairing_id','pairing_digest'):
            if record[key] != getattr(principal,key):
                raise PermissionError('original proposal scope denied')
        if record['dossier_id'] != dossier:
            raise PermissionError('original proposal dossier denied')

    def _response(self, principal, dossier, record):
        self._authorize_record(principal,dossier,record)
        return {'contract_version':CONTRACT,**{k:record[k] for k in ('instance_id','principal_id','audience','dossier_id','operation_id','plan_id','pairing_id','request_digest','state','result')},
                'proposal_kind':KIND,'original_intent':True,'approval':'NOT_PERFORMED','registration':'NOT_PERFORMED'}

    def _save(self, store, record):
        record['integrity_tag'] = self.grant.integrity({k:v for k,v in record.items() if k != 'integrity_tag'})
        store['records'][record['plan_id']] = record
        self.grant.save_store(store)

    def _peer(self, principal, deadline=None):
        pairing = self.grant.pair(principal.pairing_id,principal.pairing_digest)
        return pairing, *original(pairing,deadline=deadline)

    def _prepare(self, body, authorization, audience):
        if not isinstance(body,dict) or set(body) != {'contract_version','instance_id','dossier_id','operation_id','pairing_id','input'} or body['contract_version'] != CONTRACT or len(canonical(body)) > MAX_REQUEST:
            raise ContractError('closed finite prepare input required')
        value = check_input(body['input'])
        dossier, operation = identifier(body['dossier_id']), identifier(body['operation_id'])
        request_digest = sha256(canonical(body)).hexdigest()
        with self.grant.boundary():
            principal = self.grant.authorize(authorization,audience=audience,dossier_id=dossier,permission='PREPARE',pairing_id=body['pairing_id'])
            if body['instance_id'] != principal.instance_id:
                raise PermissionError('foreign Forge instance')
            store = self.grant._store()
            plan_id = plan_identity(principal,dossier,operation)
            record = self._record(store,plan_id)
            if record is not None:
                self._authorize_record(principal,dossier,record)
                if record['request_digest'] != request_digest:
                    return 409,{'contract_version':CONTRACT,'error':{'code':'INSPECTION_ADOPTION_IDEMPOTENCY_CONFLICT'}}
            else:
                owner = store['dossiers'].get(dossier)
                if owner is None or owner['principal_id'] != principal.principal_id or owner['audience'] != audience:
                    raise PermissionError('private dossier owner mismatch')
                if len(store['records']) >= 64 or sum(r['dossier_id'] == dossier for r in store['records'].values()) >= min(owner['maximum_records'],principal.maximum_records):
                    return 409,{'contract_version':CONTRACT,'error':{'code':'INSPECTION_ADOPTION_CAPACITY_EXHAUSTED'}}
                record = {'plan_id':plan_id,'instance_id':principal.instance_id,'principal_id':principal.principal_id,'audience':audience,
                          'dossier_id':dossier,'operation_id':operation,'pairing_id':principal.pairing_id,'pairing_digest':principal.pairing_digest,
                          'request_digest':request_digest,'input':value,'state':'PREPARING','source':None,'result':None}
                self._save(store,record)  # Durable original intent precedes transport; no second operation on recovery.
        pairing, raw, snapshot = self._peer(principal)
        computed = result(value,snapshot,pairing['binding']) if record['state'] != 'PREPARED' else None
        with self.grant.boundary():
            current = self.grant.authorize(authorization,audience=audience,dossier_id=dossier,permission='PREPARE',pairing_id=principal.pairing_id)
            if current != principal:
                raise PermissionError('late own authority changed')
            store = self.grant._store()
            record = self._record(store,plan_id)
            if record is None or record['request_digest'] != request_digest:
                raise ContractError('original durable intent unavailable or conflicting')
            self._authorize_record(current,dossier,record)
            if record['state'] != 'PREPARED':
                record['source'] = {'response':snapshot,'response_digest':sha256(canonical(snapshot)).hexdigest(),'raw_response':raw.decode('utf-8'),'raw_sha256':sha256(raw).hexdigest()}
                record.update(state='PREPARED',result=computed)
                self._save(store,record)
            return 200,self._response(current,dossier,record)

    def _read(self, reference, dossier, is_intent, authorization, audience):
        with self.grant.boundary():
            principal = self.grant.authorize(authorization,audience=audience,dossier_id=dossier)
            plan_id = plan_identity(principal,dossier,reference) if is_intent else reference
            record = self._record(self.grant._store(),plan_id)
            if record is not None:
                self._authorize_record(principal,dossier,record)
        self._peer(principal)  # Even missing/pending readback must not fabricate healthy peer availability.
        with self.grant.boundary():
            current = self.grant.authorize(authorization,audience=audience,dossier_id=dossier)
            if current != principal:
                raise PermissionError('late readback authority changed')
            record = self._record(self.grant._store(),plan_id)
            if record is None:
                return 404,{'contract_version':CONTRACT,'error':{'code':'INSPECTION_ADOPTION_NOT_FOUND'}}
            return (200 if record['state'] == 'PREPARED' else 202),self._response(current,dossier,record)

    def handle(self, method, target, authorization, audience, body=None):
        try:
            if not isinstance(audience,str):
                raise PermissionError('explicit audience required')
            self.grant.authorize(authorization,audience=audience)
            parsed = urlsplit(target)
            if parsed.fragment or '%' in target or '\\' in target or '//' in parsed.path:
                raise ContractError('invalid inspection-adoption target')
            query = parse_qs(parsed.query,strict_parsing=True)
            if any(len(v) != 1 for v in query.values()):
                raise ContractError('duplicate query')
            if method == 'POST' and parsed.path == '/v1/inspection-adoptions/plans' and not query:
                return self._prepare(body,authorization,audience)
            if method == 'GET' and parsed.path == '/v1/inspection-adoptions/capability' and not query and not body:
                with self.grant.boundary():
                    p = self.grant.authorize(authorization,audience=audience)
                    self.grant._store()
                    return 200,{'contract_version':CONTRACT,'instance_id':p.instance_id,'principal_id':p.principal_id,'audience':p.audience,
                                'permissions':list(p.permissions),'dossier_ids':list(p.dossier_ids),'pairing_id':p.pairing_id,'proposal_kind':KIND,
                                'producer_revision':EP_REVISION,'current_peer_access':'CHECKED_BY_ORIGINAL_GET_AT_PREPARE_AND_READ',
                                'limits':{'request_bytes':MAX_REQUEST,'result_bytes':1048576,'global_records':64,'per_dossier':p.maximum_records},'apply':False,'inspection_post':False}
            parts = parsed.path.split('/')
            if method == 'GET' and len(parts) == 5 and parts[:3] == ['','v1','inspection-adoptions'] and parts[3] in ('plans','intents') and set(query) == {'dossier_id'} and not body:
                return self._read(identifier(parts[4]),identifier(query['dossier_id'][0]),parts[3]=='intents',authorization,audience)
            raise ContractError('unsupported inspection-adoption target/input')
        except PermissionError:
            return 403,{'contract_version':CONTRACT,'error':{'code':'INSPECTION_ADOPTION_SCOPE_DENIED'}}
        except PeerError as error:
            return error.status,{'contract_version':CONTRACT,'error':{'code':error.code}}
        except ContractError:
            return 422,{'contract_version':CONTRACT,'error':{'code':'INSPECTION_ADOPTION_INVALID_OR_UNSUPPORTED'}}
        except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):
            return 503,{'contract_version':CONTRACT,'error':{'code':'INSPECTION_ADOPTION_UNAVAILABLE'}}


@contextmanager
def publication(grant, authorization, audience, body, deadline=None):
    with grant.boundary(deadline):
        p = grant.authorize(authorization,audience=audience,dossier_id=body.get('dossier_id'))
        grant._store()
    if 'plan_id' in body:
        try:
            InspectionAdoptionService(grant)._peer(p,deadline=deadline)
        except PeerError as error:
            raise PermissionError('current peer publication access denied') from error
    with grant.boundary(deadline):
        current = grant.authorize(authorization,audience=audience,dossier_id=body.get('dossier_id'))
        if current != p or body.get('instance_id') != p.instance_id or body.get('principal_id') != p.principal_id:
            raise PermissionError('late publication authority changed')
        if 'plan_id' in body:
            service = InspectionAdoptionService(grant)
            record = service._record(grant._store(),body['plan_id'])
            if record is None or service._response(current,body['dossier_id'],record) != body:
                raise PermissionError('publication original snapshot changed')
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('bounded publication deadline')
        yield
