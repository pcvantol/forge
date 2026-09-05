"""Reference-only security configuration for future planning providers.

This module deliberately cannot invoke a provider or retain secret material.
"""
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Protocol, Callable
import json
import subprocess
from urllib.parse import urlparse, parse_qsl
from .operator_identity import InstallationOperatorService, OperatorContext
from .runtime.database import _timestamp

class SecretState(str, Enum):
    RESOLVABLE='RESOLVABLE'; MISSING='MISSING'; REVOKED='REVOKED'; ROTATED_INVALID='ROTATED_INVALID'; STORE_UNAVAILABLE='STORE_UNAVAILABLE'; INVALID_REFERENCE='INVALID_REFERENCE'; ACCESS_DENIED='ACCESS_DENIED'

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

class MacOSKeychainSecureStoreAdapter:
    """Explicit-reference-only adapter; it never enumerates Keychain items."""
    executable = '/usr/bin/security'
    def __init__(self, runner: Callable[..., object] = subprocess.run, timeout: float = 5.0):
        self._runner, self._timeout = runner, timeout
    @staticmethod
    def _parts(reference: SecretReference):
        if reference.scheme != 'keychain': raise ValueError('unexpected secure-store scheme')
        parsed=urlparse(reference.identifier)
        if parsed.scheme or not parsed.netloc: raise ValueError('invalid keychain reference')
        path=[parsed.netloc, *[item for item in parsed.path.split('/') if item]]
        query=parse_qsl(parsed.query, keep_blank_values=True)
        if len(path) != 2 or not all(path) or len(query) != len(set(query)) or any(k not in {'namespace','version'} or not v for k,v in query):
            raise ValueError('invalid keychain reference')
        return path[0], path[1]
    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]:
        try: service, account = self._parts(reference)
        except ValueError: return SecretState.INVALID_REFERENCE, None
        try:
            result=self._runner([self.executable, 'find-generic-password', '-s', service, '-a', account, '-w'], capture_output=True, text=True, timeout=self._timeout, check=False)
        except (OSError, subprocess.TimeoutExpired): return SecretState.STORE_UNAVAILABLE, None
        if result.returncode == 0: return SecretState.RESOLVABLE, result.stdout.rstrip('\n')
        error=(result.stderr or '').lower()
        if 'could not be found' in error or 'item not found' in error: return SecretState.MISSING, None
        if 'not allowed' in error or 'user interaction is not allowed' in error: return SecretState.ACCESS_DENIED, None
        return SecretState.STORE_UNAVAILABLE, None
    def status(self, reference): return self.resolve(reference)[0]

@dataclass(frozen=True)
class ProviderSecurityHealth:
    state: str
    ready: bool
    reference_fingerprint: str | None

class PlanningProviderSecurityService:
    """Runtime-DB-only config authority; all returned views are redacted."""
    def __init__(self, database, store: SecureStorePort, operator_service: InstallationOperatorService):
        self.db, self.store, self.operator_service = database, store, operator_service
    def configure(self, *, configuration_id, provider_id, reference, operator_context: OperatorContext, expected_version=0, enabled=True):
        if not self.operator_service.authorize(operator_context):
            raise PermissionError('trusted named operator context is required')
        if not isinstance(reference, SecretReference): raise TypeError('typed secret reference is required')
        occurred_at = _timestamp()
        operator_id = sha256(operator_context.generated_uid.encode()).hexdigest()[:16]
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
