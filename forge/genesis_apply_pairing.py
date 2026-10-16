"""Owner-only finite pairing to an independently issued EP provisioning grant."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
import secrets
from .approved_worklist import identifier
from .ep_inspection_peer import endpoint
from .genesis_bootstrap_contract import finite_expiry
from .project_bootstrap.schema import canonical, load_json, ContractError
from .project_bootstrap.service import digest
from .project_proposal_storage import read, write
from .proposal_content_contract import hash_value
from .workspace_review_grant import _private_bytes


def check_pairing(config):
    from .genesis_apply_peer import QUALIFIED_PRODUCER
    fields = {'pairing_id', 'endpoint', 'binding', 'producer_revision', 'producer_tree', 'producer_schema_sha256',
              'producer_version', 'ep_grant_id', 'expires_at', 'plan_id', 'plan_digest', 'decision_id', 'decision_digest',
              'placement_ref', 'target_ref', 'request_digest', 'input_digest'}
    if not isinstance(config, dict) or set(config) != fields:
        raise ContractError('closed owner Genesis pairing required')
    if QUALIFIED_PRODUCER is None or any(config[k] != v for k, v in QUALIFIED_PRODUCER.items()):
        raise ContractError('qualified Genesis producer required')
    endpoint(config['endpoint'])
    for name in ('pairing_id', 'ep_grant_id', 'plan_id', 'decision_id', 'placement_ref', 'target_ref'):
        identifier(config[name])
    for name in ('plan_digest', 'decision_digest', 'request_digest', 'input_digest', 'producer_schema_sha256'):
        hash_value(config[name])
    finite_expiry(config['expires_at'])
    binding = config['binding']
    if not isinstance(binding, dict) or set(binding) != {'instance_id', 'host_id', 'consumer_id', 'principal', 'operation_id'}:
        raise ContractError('closed exact EP authorization headers required')
    for name, value in binding.items(): (hash_value if name == 'host_id' else identifier)(value)
    return config


class GenesisApplyPairings:
    def __init__(self, grant):
        self.grant = grant
        self.path = grant.path.parent/'pairings.json'

    def records(self):
        try:
            return self._records()
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise RuntimeError('initialized Genesis pairing storage unavailable') from error

    def _records(self):
        value = read(self.path, 131072)
        if (not isinstance(value, dict) or set(value) != {'records', 'integrity'}
                or not isinstance(value['records'], dict) or len(value['records']) > 16
                or not secrets.compare_digest(value['integrity'], self.grant.integrity(value['records']))):
            raise ContractError('sealed finite Genesis pairings required')
        for key, row in value['records'].items():
            if not isinstance(row, dict) or set(row) != {'config', 'credential', 'pairing_digest', 'state'}:
                raise ContractError('closed private Genesis pairing required')
            check_pairing(row['config'])
            if (key != row['config']['pairing_id'] or row['state'] not in ('ACTIVE', 'REVOKED')
                    or not isinstance(row['credential'], str) or not 1 <= len(row['credential']) <= 256
                    or any(ord(c) < 33 or ord(c) > 126 for c in row['credential'])
                    or row['pairing_digest'] != self.grant.integrity({'config':row['config'], 'credential_sha256':digest(row['credential'].encode())})):
                raise ContractError('original Genesis pairing binding invalid')
        return value['records']

    def save(self, records, *, create=False):
        write(self.path, {'records':records, 'integrity':self.grant.integrity(records)}, create=create)

    def bind(self, config, credential_file):
        config = check_pairing(load_json(canonical(config)))
        if not datetime.now(UTC) < finite_expiry(config['expires_at']) <= datetime.now(UTC)+timedelta(days=1):
            raise ContractError('finite existing EP grant expiry required')
        credential = _private_bytes(Path(credential_file)).decode('ascii').strip()
        if not 1 <= len(credential) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in credential):
            raise ContractError('separate private EP provisioning credential required')
        row = {'config':config, 'credential':credential, 'state':'ACTIVE',
               'pairing_digest':self.grant.integrity({'config':config, 'credential_sha256':digest(credential.encode())})}
        with self.grant.boundary():
            self.grant._store(); records = self.records()
            if config['pairing_id'] in records or len(records) >= 16:
                raise ContractError('Genesis pairing immutable or capacity exhausted')
            records[config['pairing_id']] = row; self.save(records)
        return {'pairing_id':config['pairing_id'], 'pairing_digest':row['pairing_digest'], 'state':'OWNER_CONFIGURED_NOT_EP_ADMITTED'}

    def pair(self, pairing_id, expected_digest=None):
        row = self.records().get(identifier(pairing_id))
        if row is None or row['state'] != 'ACTIVE' or finite_expiry(row['config']['expires_at']) <= datetime.now(UTC):
            raise PermissionError('Genesis peer grant inactive')
        if expected_digest is not None and not secrets.compare_digest(row['pairing_digest'], expected_digest):
            raise PermissionError('original Genesis pairing changed')
        return {**row['config'], 'credential':row['credential'], 'pairing_digest':row['pairing_digest']}

    def revoke(self, pairing_id):
        with self.grant.boundary():
            records = self.records(); row = records[identifier(pairing_id)]
            row['state'] = 'REVOKED'; self.save(records)
        return {'pairing_id':pairing_id, 'state':'REVOKED'}
