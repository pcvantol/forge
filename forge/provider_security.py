"""Reference-only security configuration for future planning providers.

This module deliberately cannot invoke a provider or retain secret material.
"""
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Protocol, Callable
import json
import re
import subprocess
from urllib.parse import urlparse, parse_qsl, urlencode
from .operator_identity import InstallationOperatorService, OperatorContext
from .runtime.database import _timestamp

class SecretState(str, Enum):
    RESOLVABLE='RESOLVABLE'; MISSING='MISSING'; REVOKED='REVOKED'; ROTATED_INVALID='ROTATED_INVALID'; STORE_UNAVAILABLE='STORE_UNAVAILABLE'; INVALID_REFERENCE='INVALID_REFERENCE'; ACCESS_DENIED='ACCESS_DENIED'

@dataclass(frozen=True)
class SecretReference:
    scheme: str
    identifier: str
    def __post_init__(self):
        self.validate()
        object.__setattr__(self, 'identifier', self._canonical_identifier())
    def validate(self):
        try:
            if self.scheme != 'keychain' or not isinstance(self.identifier,str) or not self.identifier or len(self.identifier) > 512:
                raise ValueError
            if any(ord(char) < 32 for char in self.identifier) or '%' in self.identifier:
                raise ValueError
            parsed=urlparse(self.identifier)
            if parsed.scheme or parsed.username or parsed.password or parsed.port or parsed.fragment or not parsed.netloc:
                raise ValueError
            parts=parsed.path.split('/')
            if len(parts) != 2 or not parts[1] or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}',parsed.netloc) or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}',parts[1]):
                raise ValueError
            query=parse_qsl(parsed.query,keep_blank_values=True,strict_parsing=True)
            if len(query) != len({key for key,_ in query}) or any(key not in {'namespace','version'} or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}',value) for key,value in query):
                raise ValueError
        except (UnicodeError, ValueError):
            raise ValueError('invalid secret reference') from None
    def _canonical_identifier(self):
        parsed=urlparse(self.identifier)
        query=dict(parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True))
        suffix=urlencode([(key, query[key]) for key in ('namespace','version') if key in query])
        return f'//{parsed.netloc}/{parsed.path[1:]}' + (f'?{suffix}' if suffix else '')
    @property
    def fingerprint(self): return 'sha256:' + sha256(self.serialized.encode()).hexdigest()
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
        reference.validate()
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

@dataclass(frozen=True)
class PlanningProviderInvocationPolicy:
    """Redacted G011 policy view consumed by a bounded provider adapter only."""
    provider_id: str
    model: str
    secret_reference: SecretReference
    timeout_seconds: int
    input_token_bound: int
    context_token_bound: int
    output_token_bound: int
    version: int

class PlanningProviderSecurityService:
    """Runtime-DB-only config authority; all returned views are redacted."""
    def __init__(self, database, store: SecureStorePort, operator_service: InstallationOperatorService):
        self.db, self.store, self.operator_service = database, store, operator_service
    @staticmethod
    def _invocation_parameters(model, timeout_seconds, input_token_bound, context_token_bound, output_token_bound):
        values = (model, timeout_seconds, input_token_bound, context_token_bound, output_token_bound)
        if all(value is None for value in values):
            return None
        if (not isinstance(model, str) or not model
                or not all(isinstance(value, int) and value > 0 for value in values[1:])
                or input_token_bound > context_token_bound
                or input_token_bound + output_token_bound > context_token_bound):
            raise ValueError('complete bounded invocation parameters are required')
        return values

    def configure(self, *, configuration_id, provider_id, reference, operator_context: OperatorContext, expected_version=0, enabled=True,
                  model=None, timeout_seconds=None, input_token_bound=None, context_token_bound=None, output_token_bound=None):
        if not self.operator_service.authorize(operator_context):
            raise PermissionError('trusted named operator context is required')
        if not isinstance(reference, SecretReference): raise TypeError('typed secret reference is required')
        reference=SecretReference(reference.scheme, reference.identifier)
        parameters=self._invocation_parameters(model, timeout_seconds, input_token_bound, context_token_bound, output_token_bound)
        occurred_at = _timestamp()
        operator_id = sha256(operator_context.generated_uid.encode()).hexdigest()[:16]
        row=self.db._connection.execute('SELECT * FROM planning_provider_security_config WHERE provider_id=?',(provider_id,)).fetchone()
        actual=0 if row is None else row['version']
        if actual != expected_version: raise ValueError('stale provider security configuration write')
        new=actual+1
        with self.db._connection:
            fields = parameters or (None if row is None else row['model'], None if row is None else row['timeout_seconds'], None if row is None else row['input_token_bound'], None if row is None else row['context_token_bound'], None if row is None else row['output_token_bound'])
            if row is None: self.db._connection.execute('INSERT INTO planning_provider_security_config (configuration_id,provider_id,secret_reference,enabled,operator_id,version,created_at,updated_at,model,timeout_seconds,input_token_bound,context_token_bound,output_token_bound) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(configuration_id,provider_id,reference.serialized,int(enabled),operator_id,new,occurred_at,occurred_at,*fields))
            else: self.db._connection.execute('UPDATE planning_provider_security_config SET secret_reference=?,enabled=?,operator_id=?,version=?,updated_at=?,model=?,timeout_seconds=?,input_token_bound=?,context_token_bound=?,output_token_bound=? WHERE provider_id=?',(reference.serialized,int(enabled),operator_id,new,occurred_at,*fields,provider_id))
            audit={'configuration_id':configuration_id,'operator_id':operator_id,'operation':'configured','version':new,'secret_reference_changed':True,'invocation_parameters_configured':parameters is not None,'result':'accepted'}
            self.db._connection.execute('INSERT INTO planning_provider_security_audit VALUES (?,?,?,?,?,?)',(f'{configuration_id}:{new}',configuration_id,operator_id,'configured',occurred_at,json.dumps(audit,sort_keys=True)))
        return self.inspect(provider_id)
    def inspect(self, provider_id):
        row=self.db._connection.execute('SELECT * FROM planning_provider_security_config WHERE provider_id=?',(provider_id,)).fetchone()
        if row is None: return {'state':'NOT_CONFIGURED','ready':False}
        parameters=self._invocation_parameters(row['model'], row['timeout_seconds'], row['input_token_bound'], row['context_token_bound'], row['output_token_bound'])
        state=self.store.status(SecretReference.parse(row['secret_reference'])) if row['enabled'] and parameters else SecretState.MISSING
        result={'configuration_id':row['configuration_id'],'provider_id':provider_id,'enabled':bool(row['enabled']),'version':row['version'],'operator_id':row['operator_id'],'state':'READY' if state is SecretState.RESOLVABLE else state.value,'ready':state is SecretState.RESOLVABLE and bool(row['enabled']) and parameters is not None,'secret_reference':'[REDACTED]'}
        if parameters: result.update({'model':parameters[0],'timeout_seconds':parameters[1],'input_token_bound':parameters[2],'context_token_bound':parameters[3],'output_token_bound':parameters[4]})
        return result

    def invocation_policy(self, provider_id: str) -> PlanningProviderInvocationPolicy:
        """Return the sole supported adapter policy view from canonical G011 state.

        The typed secret reference is required only to resolve the secret at
        transport time.  No secret material is returned or retained here.
        """
        row=self.db._connection.execute('SELECT * FROM planning_provider_security_config WHERE provider_id=?',(provider_id,)).fetchone()
        if row is None:
            raise PermissionError('planning provider is not configured')
        parameters=self._invocation_parameters(row['model'], row['timeout_seconds'], row['input_token_bound'], row['context_token_bound'], row['output_token_bound'])
        state=self.store.status(SecretReference.parse(row['secret_reference'])) if row['enabled'] and parameters else SecretState.MISSING
        if not row['enabled'] or parameters is None or state is not SecretState.RESOLVABLE:
            raise PermissionError('planning provider policy is not ready')
        return PlanningProviderInvocationPolicy(provider_id, parameters[0], SecretReference.parse(row['secret_reference']), parameters[1], parameters[2], parameters[3], parameters[4], row['version'])
