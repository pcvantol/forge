"""Reference-only security configuration for future planning providers.

This module deliberately cannot invoke a provider or retain secret material.
"""
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Protocol
import json

class SecretState(str, Enum):
    RESOLVABLE='RESOLVABLE'; MISSING='MISSING'; REVOKED='REVOKED'; ROTATED_INVALID='ROTATED_INVALID'; STORE_UNAVAILABLE='STORE_UNAVAILABLE'; INVALID_REFERENCE='INVALID_REFERENCE'

@dataclass(frozen=True)
class SecretReference:
    scheme: str
    identifier: str
    def __post_init__(self):
        if not self.scheme or not self.identifier or any(x in self.identifier.lower() for x in ('token=', 'bearer ', 'sk-', 'api_key')):
            raise ValueError('secret reference must be opaque and non-secret-bearing')
    @property
    def fingerprint(self): return 'sha256:' + sha256(f'{self.scheme}:{self.identifier}'.encode()).hexdigest()
    @property
    def serialized(self): return f'{self.scheme}:{self.identifier}'
    @classmethod
    def parse(cls, value):
        scheme, identifier = value.split(':', 1)
        return cls(scheme, identifier)

class SecureStorePort(Protocol):
    def status(self, reference: SecretReference) -> SecretState: ...

@dataclass(frozen=True)
class ProviderSecurityHealth:
    state: str
    ready: bool
    reference_fingerprint: str | None

class PlanningProviderSecurityService:
    """Runtime-DB-only config authority; all returned views are redacted."""
    def __init__(self, database, store: SecureStorePort): self.db, self.store = database, store
    def configure(self, *, configuration_id, provider_id, reference, operator_id, expected_version=0, enabled=True, occurred_at):
        if not operator_id: raise PermissionError('named operator is required')
        if not isinstance(reference, SecretReference): raise TypeError('typed secret reference is required')
        row=self.db._connection.execute('SELECT version FROM planning_provider_security_config WHERE provider_id=?',(provider_id,)).fetchone()
        actual=0 if row is None else row['version']
        if actual != expected_version: raise ValueError('stale provider security configuration write')
        new=actual+1
        with self.db._connection:
            if row is None: self.db._connection.execute('INSERT INTO planning_provider_security_config VALUES (?,?,?,?,?,?,?,?)',(configuration_id,provider_id,reference.serialized,int(enabled),operator_id,new,occurred_at,occurred_at))
            else: self.db._connection.execute('UPDATE planning_provider_security_config SET secret_reference=?,enabled=?,operator_id=?,version=?,updated_at=? WHERE provider_id=?',(reference.serialized,int(enabled),operator_id,new,occurred_at,provider_id))
            audit={'configuration_id':configuration_id,'operator_id':operator_id,'operation':'configured','version':new,'secret_reference_changed':True,'result':'accepted'}
            self.db._connection.execute('INSERT INTO planning_provider_security_audit VALUES (?,?,?,?,?,?)',(f'{configuration_id}:{new}',configuration_id,operator_id,'configured',occurred_at,json.dumps(audit,sort_keys=True)))
        return self.inspect(provider_id)
    def inspect(self, provider_id):
        row=self.db._connection.execute('SELECT * FROM planning_provider_security_config WHERE provider_id=?',(provider_id,)).fetchone()
        if row is None: return {'state':'NOT_CONFIGURED','ready':False}
        state=self.store.status(SecretReference.parse(row['secret_reference'])) if row['enabled'] else SecretState.MISSING
        return {'configuration_id':row['configuration_id'],'provider_id':provider_id,'enabled':bool(row['enabled']),'version':row['version'],'operator_id':row['operator_id'],'state':'READY' if state is SecretState.RESOLVABLE else state.value,'ready':state is SecretState.RESOLVABLE and bool(row['enabled']),'secret_reference':'[REDACTED]'}
