"""Explicit private EP pairing and finite adoption PREPARE/READ authority."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
import json
import secrets
import unicodedata
from .approved_worklist import identifier, timestamp
from .project_bootstrap.schema import canonical, ContractError
from .project_proposal_grant import ProjectProposalGrant, operator_binding
from .workspace_review_grant import _private_bytes, _write_private, _new_token
from .project_proposal_storage import read, write
from .ep_inspection_contract import CONTRACT, KIND, EP_REVISION, EP_TREE, EP_SCHEMA_SHA256
from .ep_inspection_peer import original, endpoint
from .project_adoption.service import document_path


@dataclass(frozen=True)
class InspectionPrincipal:
    grant_id: str
    principal_id: str
    instance_id: str
    audience: str
    dossier_ids: tuple
    permissions: tuple
    pairing_id: str
    pairing_digest: str
    maximum_records: int
    operator_binding: str


def check_pairing(config):
    if not isinstance(config, dict) or set(config) != {'pairing_id','endpoint','binding','snapshot_digest','producer_revision','producer_tree','producer_schema_sha256'}:
        raise ContractError('closed explicit qualified producer pairing required')
    identifier(config['pairing_id'])
    endpoint(config['endpoint'])
    for key, expected in [('producer_revision', EP_REVISION), ('producer_tree', EP_TREE), ('producer_schema_sha256', EP_SCHEMA_SHA256)]:
        if config[key] != expected:
            raise ContractError('unsupported qualified producer pin')
    if not isinstance(config['snapshot_digest'], str) or len(config['snapshot_digest']) != 64 or any(c not in '0123456789abcdef' for c in config['snapshot_digest']):
        raise ContractError('original selected snapshot digest required')
    binding = config['binding']
    keys = {'instance_id','host_id','consumer_id','principal','audience','source_ref','operation_id','paths','content_paths'}
    if not isinstance(binding, dict) or set(binding) != keys:
        raise ContractError('closed EP source/operation/transfer binding required')
    for key in keys-{'paths','content_paths'}:
        identifier(binding[key])
    for key in ('paths','content_paths'):
        paths = binding[key]
        if not isinstance(paths, list) or len(paths) > 16 or len(set(paths)) != len(paths):
            raise ContractError('finite explicit EP path selection required')
        for path in paths:
            document_path(path)
            if path != unicodedata.normalize('NFC', path):
                raise ContractError('noncanonical EP path')
        if len({p.casefold() for p in paths}) != len(paths):
            raise ContractError('EP selection path alias')
    if not set(binding['content_paths']) <= set(binding['paths']):
        raise ContractError('content consent exceeds selection')
    return config


class InspectionAdoptionGrant(ProjectProposalGrant):
    contract = CONTRACT

    def __init__(self, root, instance_id):
        super().__init__(root, instance_id)
        self.path = self.root/'credentials'/'inspection-adoption'/'grants.json'
        self.store = self.root/'onboarding'/'inspection-adoption'/'store.json'
        self.witness = self.store.parent/'initialized.json'
        self.pairs = self.path.parent/'pairings.json'

    def initialize(self):
        existed = self.witness.exists() or self.witness.is_symlink()
        super().initialize()
        with self.boundary():
            if existed:
                self._pair_records()
            else:
                self._save_pairs({}, create=True)

    def _pair_records(self):
        value = read(self.pairs, 131072)
        if not isinstance(value, dict) or set(value) != {'records','integrity'} or not isinstance(value['records'], dict) or len(value['records']) > 16:
            raise ContractError('finite private pairings required')
        if not secrets.compare_digest(value['integrity'], self.integrity(value['records'])):
            raise ContractError('private pairing integrity failed')
        return value['records']

    def _save_pairs(self, records, *, create=False):
        write(self.pairs, {'records':records,'integrity':self.integrity(records)}, create=create)

    def bind(self, config, credential_file):
        config = check_pairing(json.loads(canonical(config)))
        credential = _private_bytes(Path(credential_file)).decode('ascii').strip()
        if not 1 <= len(credential) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in credential):
            raise ContractError('private existing EP bearer required')
        record = {'config':config,'credential':credential,'state':'ACTIVE'}
        record['pairing_digest'] = self.integrity({'config':config,'credential_sha256':sha256(credential.encode()).hexdigest()})
        original({**config,'credential':credential})  # Owner verifies original before binding; no own lock spans GET.
        with self.boundary():
            self._store()
            records = self._pair_records()
            if config['pairing_id'] in records or len(records) >= 16:
                raise ContractError('pairing identity immutable or capacity exhausted')
            records[config['pairing_id']] = record
            self._save_pairs(records)
        return {'pairing_id':config['pairing_id'],'pairing_digest':record['pairing_digest'],'state':'EXPLICIT_ORIGINAL_BOUND'}

    def pair(self, pairing_id, expected_digest=None):
        record = self._pair_records().get(pairing_id)
        if record is None or record.get('state') != 'ACTIVE':
            raise PermissionError('pairing inactive')
        check_pairing(record['config'])
        if expected_digest is not None and not secrets.compare_digest(record['pairing_digest'], expected_digest):
            raise PermissionError('pairing binding changed')
        return {**record['config'],'credential':record['credential'],'pairing_digest':record['pairing_digest']}

    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():
            return []
        value = json.loads(_private_bytes(self.path))
        if not isinstance(value, dict) or set(value) != {'contract_version','instance_id','records'} or value['contract_version'] != CONTRACT or value['instance_id'] != self.instance_id or not isinstance(value['records'], list) or len(value['records']) > 32:
            raise ContractError('finite inspection-adoption grants required')
        seen = set()
        for record in value['records']:
            if not isinstance(record, dict) or set(record) != set(InspectionPrincipal.__dataclass_fields__) | {'token_digest','state','expires_at'}:
                raise ContractError('closed inspection-adoption grant required')
            for key in ('grant_id','principal_id','instance_id','audience','pairing_id'):
                identifier(record[key])
            self._bounds(record['dossier_ids'], record['permissions'], record['maximum_records'])
            timestamp(record['expires_at'])
            if record['instance_id'] != self.instance_id or record['state'] not in ('ACTIVE','REVOKED') or record['grant_id'] in seen:
                raise ContractError('grant identity/state invalid')
            for key in ('token_digest','operator_binding','pairing_digest'):
                if not isinstance(record[key], str) or len(record[key]) != 64 or any(c not in '0123456789abcdef' for c in record[key]):
                    raise ContractError('grant digest invalid')
            seen.add(record['grant_id'])
        return value['records']

    @staticmethod
    def _bounds(dossiers, permissions, maximum):
        if not isinstance(dossiers, (tuple,list)) or not 1 <= len(dossiers) <= 8 or len(set(dossiers)) != len(dossiers):
            raise ContractError('finite dossier scope required')
        for dossier in dossiers:
            identifier(dossier)
        if not isinstance(permissions, (tuple,list)) or 'READ' not in permissions or set(permissions)-{'READ','PREPARE'} or len(set(permissions)) != len(permissions) or type(maximum) is not int or not 1 <= maximum <= 8:
            raise ContractError('finite explicit prepare/read scope required')

    def save_records(self, records):
        _write_private(self.path, canonical({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records}))

    def issue(self, *, principal_id, audience, dossier_ids, permissions, pairing_id, maximum_records, expires_at, token_path):
        identifier(principal_id)
        identifier(audience)
        self._bounds(dossier_ids, permissions, maximum_records)
        if not datetime.now(UTC) < timestamp(expires_at) <= datetime.now(UTC)+timedelta(days=30):
            raise ContractError('finite expiry required')
        token_path = Path(token_path)
        if token_path.resolve().is_relative_to(self.store.parent.resolve()) or token_path.resolve().is_relative_to(self.path.parent.resolve()):
            raise ContractError('token storage collision')
        with self.boundary():
            pairing = self.pair(pairing_id)
            rows = self._records(True)
            if len(rows) >= 32:
                raise ContractError('grant capacity exhausted')
            store = self._store()
            for dossier in dossier_ids:
                owner = {'principal_id':principal_id,'audience':audience,'maximum_records':maximum_records}
                if dossier in store['dossiers'] and store['dossiers'][dossier] != owner:
                    raise PermissionError('dossier owner immutable')
                store['dossiers'][dossier] = owner
            if len(store['dossiers']) > 32:
                raise ContractError('dossier capacity exhausted')
            self.save_store(store)
            token = secrets.token_urlsafe(48)
            record = {'grant_id':'inspection-'+secrets.token_hex(16),'principal_id':principal_id,'instance_id':self.instance_id,
                      'audience':audience,'dossier_ids':sorted(dossier_ids),'permissions':sorted(permissions),
                      'pairing_id':pairing_id,'pairing_digest':pairing['pairing_digest'],'maximum_records':maximum_records,
                      'operator_binding':operator_binding(self.root,self.instance_id),'token_digest':sha256(token.encode()).hexdigest(),
                      'state':'ACTIVE','expires_at':expires_at}
            _new_token(token_path, token)
            try:
                self.save_records([*rows,record])
            except BaseException:
                token_path.unlink(missing_ok=True)
                raise
        return {key:value for key,value in record.items() if key not in ('token_digest','operator_binding')}

    def authorize(self, authorization, *, audience=None, dossier_id=None, permission='READ', pairing_id=None):
        if not isinstance(authorization, str) or not authorization.startswith('Bearer '):
            raise PermissionError('inspection-adoption credential required')
        token = authorization[7:]
        if not 1 <= len(token) <= 256:
            raise PermissionError('finite bearer required')
        rows = [r for r in self._records() if secrets.compare_digest(r['token_digest'],sha256(token.encode()).hexdigest())]
        if len(rows) != 1:
            raise PermissionError('inspection-adoption credential required')
        row = rows[0]
        if row['state'] != 'ACTIVE' or timestamp(row['expires_at']) <= datetime.now(UTC) or row['operator_binding'] != operator_binding(self.root,self.instance_id):
            raise PermissionError('current authority changed')
        if (audience is not None and audience != row['audience']) or (dossier_id is not None and dossier_id not in row['dossier_ids']) or permission not in row['permissions'] or (pairing_id is not None and pairing_id != row['pairing_id']):
            raise PermissionError('explicit inspection-adoption scope denied')
        self.pair(row['pairing_id'],row['pairing_digest'])
        return InspectionPrincipal(*(tuple(row[k]) if k in ('dossier_ids','permissions') else row[k] for k in InspectionPrincipal.__dataclass_fields__))

    def revoke_pair(self, pairing_id):
        with self.boundary():
            records = self._pair_records()
            if pairing_id not in records:
                raise ContractError('unknown pairing')
            records[pairing_id]['state'] = 'REVOKED'
            self._save_pairs(records)
        return {'pairing_id':pairing_id,'state':'REVOKED'}

    def publication(self, authorization, audience, body, *, deadline=None):
        from .ep_inspection_service import publication
        return publication(self,authorization,audience,body,deadline=deadline)
