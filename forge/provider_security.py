"""Reference-only security configuration for future planning providers.

This module deliberately cannot invoke a provider or retain secret material.
"""
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import uuid
from .operator_identity import InstallationOperatorService, OperatorContext
from .runtime.database import _timestamp
from .secure_store import (
    MacOSKeychainSecureStoreAdapter,
    SecretReference,
    SecretState,
    SecureStorePort,
)

@dataclass(frozen=True)
class ProviderSecurityHealth:
    state: str
    ready: bool
    reference_fingerprint: str | None


class ProviderAuthenticationMode(str, Enum):
    """The only credential ownership modes accepted by planning providers."""

    SECRET_REFERENCE = "SECRET_REFERENCE"
    EXTERNAL_AUTHENTICATED_SESSION = "EXTERNAL_AUTHENTICATED_SESSION"


CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE = "CODEX_CLI_CHATGPT_SESSION"
CODEX_CLI_CHATGPT_SESSION_TYPE = "CODEX_CLI_CHATGPT_SESSION"


@dataclass(frozen=True)
class PlanningProviderInvocationPolicy:
    """Redacted G011 policy view consumed by a bounded provider adapter only."""
    provider_id: str
    model: str | None
    secret_reference: SecretReference | None
    timeout_seconds: int
    input_token_bound: int
    context_token_bound: int
    output_token_bound: int
    version: int
    authentication_mode: ProviderAuthenticationMode = ProviderAuthenticationMode.SECRET_REFERENCE
    provider_type: str = "OPENAI_RESPONSES"
    external_session_type: str | None = None
    executable_path: str | None = None
    adapter_version: str | None = None
    profile: str | None = None

class PlanningProviderSecurityService:
    """Runtime-DB-only config authority; all returned views are redacted."""
    def __init__(self, database, store: SecureStorePort, operator_service: InstallationOperatorService):
        self.db, self.store, self.operator_service = database, store, operator_service
    @staticmethod
    def _invocation_parameters(model, timeout_seconds, input_token_bound, context_token_bound, output_token_bound, *, model_required=True):
        values = (model, timeout_seconds, input_token_bound, context_token_bound, output_token_bound)
        if all(value is None for value in values):
            return None
        if ((model_required and (not isinstance(model, str) or not model))
                or (not model_required and model is not None and (not isinstance(model, str) or not model))
                or not all(isinstance(value, int) and value > 0 for value in values[1:])
                or input_token_bound > context_token_bound
                or input_token_bound + output_token_bound > context_token_bound):
            raise ValueError('complete bounded invocation parameters are required')
        return values

    def configure(self, *, configuration_id, provider_id, reference=None, operator_context: OperatorContext, expected_version=0, enabled=True,
                  model=None, timeout_seconds=None, input_token_bound=None, context_token_bound=None, output_token_bound=None,
                  authentication_mode=ProviderAuthenticationMode.SECRET_REFERENCE, provider_type="OPENAI_RESPONSES",
                  external_session_type=None, executable_path=None, adapter_version=None, profile=None):
        if not self.operator_service.authorize(operator_context):
            raise PermissionError('trusted named operator context is required')
        try:
            authentication_mode=ProviderAuthenticationMode(authentication_mode)
        except ValueError as error:
            raise ValueError('unsupported planning provider authentication mode') from error
        if authentication_mode is ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION:
            return self._configure_external_session(
                configuration_id=configuration_id, provider_id=provider_id, reference=reference,
                operator_context=operator_context, expected_version=expected_version, enabled=enabled,
                model=model, timeout_seconds=timeout_seconds, input_token_bound=input_token_bound,
                context_token_bound=context_token_bound, output_token_bound=output_token_bound,
                provider_type=provider_type, external_session_type=external_session_type,
                executable_path=executable_path, adapter_version=adapter_version, profile=profile,
            )
        if provider_type != "OPENAI_RESPONSES" or external_session_type is not None or executable_path is not None or adapter_version is not None or profile is not None:
            raise ValueError('secret-reference providers cannot declare external-session fields')
        if not isinstance(reference, SecretReference): raise TypeError('typed secret reference is required')
        reference=SecretReference(reference.scheme, reference.identifier)
        parameters=self._invocation_parameters(model, timeout_seconds, input_token_bound, context_token_bound, output_token_bound)
        occurred_at = _timestamp()
        operator_id = sha256(operator_context.generated_uid.encode()).hexdigest()[:16]
        if self.db._connection.execute('SELECT 1 FROM planning_provider_external_session_config WHERE provider_id=?',(provider_id,)).fetchone():
            raise ValueError('provider id is already configured for an external authenticated session')
        row=self.db._connection.execute('SELECT * FROM planning_provider_security_config WHERE provider_id=?',(provider_id,)).fetchone()
        actual=0 if row is None else row['version']
        if actual != expected_version: raise ValueError('stale provider security configuration write')
        new=actual+1
        with self.db._connection:
            permits=self.db._connection.execute("SELECT permit_id,state FROM planning_provider_generation_permits WHERE provider_id=? AND state IN ('PENDING','TRANSPORT_COMMITTED')",(provider_id,)).fetchall()
            if any(item['state']=='TRANSPORT_COMMITTED' for item in permits):
                raise PermissionError('G011 generation transport is committed; configuration mutation is denied')
            for item in permits:
                self.db._connection.execute("UPDATE planning_provider_generation_permits SET state='INVALIDATED',updated_at=? WHERE permit_id=?",(occurred_at,item['permit_id']))
            fields = parameters or (None if row is None else row['model'], None if row is None else row['timeout_seconds'], None if row is None else row['input_token_bound'], None if row is None else row['context_token_bound'], None if row is None else row['output_token_bound'])
            if row is None: self.db._connection.execute('INSERT INTO planning_provider_security_config (configuration_id,provider_id,secret_reference,enabled,operator_id,version,created_at,updated_at,model,timeout_seconds,input_token_bound,context_token_bound,output_token_bound) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(configuration_id,provider_id,reference.serialized,int(enabled),operator_id,new,occurred_at,occurred_at,*fields))
            else: self.db._connection.execute('UPDATE planning_provider_security_config SET secret_reference=?,enabled=?,operator_id=?,version=?,updated_at=?,model=?,timeout_seconds=?,input_token_bound=?,context_token_bound=?,output_token_bound=? WHERE provider_id=?',(reference.serialized,int(enabled),operator_id,new,occurred_at,*fields,provider_id))
            audit={'configuration_id':configuration_id,'operator_id':operator_id,'operation':'configured','version':new,'secret_reference_changed':True,'invocation_parameters_configured':parameters is not None,'result':'accepted'}
            self.db._connection.execute('INSERT INTO planning_provider_security_audit VALUES (?,?,?,?,?,?)',(f'{configuration_id}:{new}',configuration_id,operator_id,'configured',occurred_at,json.dumps(audit,sort_keys=True)))
        return self.inspect(provider_id)

    def _configure_external_session(self, *, configuration_id, provider_id, reference, operator_context, expected_version,
                                    enabled, model, timeout_seconds, input_token_bound, context_token_bound,
                                    output_token_bound, provider_type, external_session_type, executable_path,
                                    adapter_version, profile):
        """Persist only the typed, non-secret Codex-session policy.

        This deliberately has its own table.  The established secret-reference
        schema remains byte-for-byte compatible and a session can never be
        represented by a fake Keychain reference.
        """
        if reference is not None:
            raise ValueError('external authenticated sessions cannot carry a secret reference')
        if (provider_type != CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE
                or external_session_type != CODEX_CLI_CHATGPT_SESSION_TYPE
                or not isinstance(adapter_version, str) or not adapter_version
                or not isinstance(executable_path, str) or not executable_path
                or not executable_path.startswith('/') or '\\x00' in executable_path
                or profile is not None and (not isinstance(profile, str) or not profile or '\\x00' in profile)):
            raise ValueError('typed Codex external-session configuration is required')
        parameters=self._invocation_parameters(model, timeout_seconds, input_token_bound, context_token_bound,
                                               output_token_bound, model_required=False)
        if parameters is None:
            raise ValueError('complete bounded invocation parameters are required')
        occurred_at = _timestamp()
        operator_id = sha256(operator_context.generated_uid.encode()).hexdigest()[:16]
        if self.db._connection.execute('SELECT 1 FROM planning_provider_security_config WHERE provider_id=?',(provider_id,)).fetchone():
            raise ValueError('provider id is already configured for a secret reference')
        row=self.db._connection.execute('SELECT * FROM planning_provider_external_session_config WHERE provider_id=?',(provider_id,)).fetchone()
        actual=0 if row is None else row['version']
        if actual != expected_version:
            raise ValueError('stale provider security configuration write')
        new=actual+1
        with self.db._connection:
            permits=self.db._connection.execute("SELECT permit_id,state FROM planning_provider_generation_permits WHERE provider_id=? AND state IN ('PENDING','TRANSPORT_COMMITTED')",(provider_id,)).fetchall()
            if any(item['state']=='TRANSPORT_COMMITTED' for item in permits):
                raise PermissionError('G011 generation transport is committed; configuration mutation is denied')
            for item in permits:
                self.db._connection.execute("UPDATE planning_provider_generation_permits SET state='INVALIDATED',updated_at=? WHERE permit_id=?",(occurred_at,item['permit_id']))
            if row is None:
                self.db._connection.execute(
                    'INSERT INTO planning_provider_external_session_config (configuration_id,provider_id,provider_type,authentication_mode,external_session_type,executable_path,adapter_version,profile,enabled,operator_id,version,created_at,updated_at,model,timeout_seconds,input_token_bound,context_token_bound,output_token_bound) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (configuration_id,provider_id,provider_type,ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION.value,
                     external_session_type,executable_path,adapter_version,profile,int(enabled),operator_id,new,occurred_at,occurred_at,*parameters))
            else:
                self.db._connection.execute(
                    'UPDATE planning_provider_external_session_config SET provider_type=?,authentication_mode=?,external_session_type=?,executable_path=?,adapter_version=?,profile=?,enabled=?,operator_id=?,version=?,updated_at=?,model=?,timeout_seconds=?,input_token_bound=?,context_token_bound=?,output_token_bound=? WHERE provider_id=?',
                    (provider_type,ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION.value,external_session_type,
                     executable_path,adapter_version,profile,int(enabled),operator_id,new,occurred_at,*parameters,provider_id))
            audit={'configuration_id':configuration_id,'operator_id':operator_id,'operation':'configured',
                   'version':new,'authentication_mode':ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION.value,
                   'provider_type':provider_type,'external_session_type':external_session_type,
                   'adapter_version':adapter_version,'profile':profile,'result':'accepted'}
            self.db._connection.execute('INSERT INTO planning_provider_external_session_audit VALUES (?,?,?,?,?,?)',
                                        (f'{configuration_id}:{new}',configuration_id,operator_id,'configured',occurred_at,json.dumps(audit,sort_keys=True)))
        return self.inspect(provider_id)

    def inspect(self, provider_id):
        row=self.db._connection.execute('SELECT * FROM planning_provider_security_config WHERE provider_id=?',(provider_id,)).fetchone()
        if row is None:
            session=self.db._connection.execute('SELECT * FROM planning_provider_external_session_config WHERE provider_id=?',(provider_id,)).fetchone()
            if session is None: return {'state':'NOT_CONFIGURED','ready':False}
            parameters=self._invocation_parameters(session['model'], session['timeout_seconds'], session['input_token_bound'], session['context_token_bound'], session['output_token_bound'], model_required=False)
            result={'configuration_id':session['configuration_id'],'provider_id':provider_id,'enabled':bool(session['enabled']),
                    'version':session['version'],'operator_id':session['operator_id'],
                    'authentication_mode':session['authentication_mode'],'provider_type':session['provider_type'],
                    'external_session_type':session['external_session_type'],'executable_path':session['executable_path'],
                    'adapter_version':session['adapter_version'],'profile':session['profile'], 'state':'UNVERIFIED','ready':False}
            if parameters: result.update({'model':parameters[0],'timeout_seconds':parameters[1],'input_token_bound':parameters[2],
                                          'context_token_bound':parameters[3],'output_token_bound':parameters[4]})
            return result
        parameters=self._invocation_parameters(row['model'], row['timeout_seconds'], row['input_token_bound'], row['context_token_bound'], row['output_token_bound'])
        state=self.store.status(SecretReference.parse(row['secret_reference'])) if row['enabled'] and parameters else SecretState.MISSING
        result={'configuration_id':row['configuration_id'],'provider_id':provider_id,'enabled':bool(row['enabled']),'version':row['version'],'operator_id':row['operator_id'],'authentication_mode':ProviderAuthenticationMode.SECRET_REFERENCE.value,'provider_type':'OPENAI_RESPONSES','state':'READY' if state is SecretState.RESOLVABLE else state.value,'ready':state is SecretState.RESOLVABLE and bool(row['enabled']) and parameters is not None,'secret_reference':'[REDACTED]'}
        if parameters: result.update({'model':parameters[0],'timeout_seconds':parameters[1],'input_token_bound':parameters[2],'context_token_bound':parameters[3],'output_token_bound':parameters[4]})
        return result

    def invocation_policy(self, provider_id: str) -> PlanningProviderInvocationPolicy:
        """Load the sole supported adapter policy view from canonical G011 state.

        This intentionally does not interrogate the secure store. Adapter
        request construction and deterministic bounds validation must complete
        before the separate transport-time secret resolution.
        """
        row=self.db._connection.execute('SELECT * FROM planning_provider_security_config WHERE provider_id=?',(provider_id,)).fetchone()
        if row is None:
            session=self.db._connection.execute('SELECT * FROM planning_provider_external_session_config WHERE provider_id=?',(provider_id,)).fetchone()
            if session is None:
                raise PermissionError('planning provider is not configured')
            parameters=self._invocation_parameters(session['model'], session['timeout_seconds'], session['input_token_bound'], session['context_token_bound'], session['output_token_bound'], model_required=False)
            if (not session['enabled'] or parameters is None
                    or session['authentication_mode'] != ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION.value
                    or session['provider_type'] != CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE
                    or session['external_session_type'] != CODEX_CLI_CHATGPT_SESSION_TYPE):
                raise PermissionError('external session provider policy is not enabled and complete')
            return PlanningProviderInvocationPolicy(provider_id, parameters[0], None, parameters[1], parameters[2], parameters[3], parameters[4], session['version'], ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION, session['provider_type'], session['external_session_type'], session['executable_path'], session['adapter_version'], session['profile'])
        parameters=self._invocation_parameters(row['model'], row['timeout_seconds'], row['input_token_bound'], row['context_token_bound'], row['output_token_bound'])
        if not row['enabled'] or parameters is None:
            raise PermissionError('planning provider policy is not enabled and complete')
        return PlanningProviderInvocationPolicy(provider_id, parameters[0], SecretReference.parse(row['secret_reference']), parameters[1], parameters[2], parameters[3], parameters[4], row['version'])

    @staticmethod
    def _same_policy(left, right):
        return left == right

    def _acquire_generation_permit(self, expected_policy, policy_digest, request_digest):
        """Create a one-attempt, non-secret G011 guard owned by RuntimeDatabase."""
        if not isinstance(expected_policy, PlanningProviderInvocationPolicy) or not all(isinstance(value,str) and value.startswith('sha256:') for value in (policy_digest,request_digest)):
            raise PermissionError('canonical G011 transport binding is required')
        now=_timestamp(); permit_id=str(uuid.uuid4()); connection=self.db._connection
        connection.execute('BEGIN IMMEDIATE')
        try:
            actual=self.invocation_policy(expected_policy.provider_id)
            if not self._same_policy(actual,expected_policy): raise PermissionError('canonical G011 policy changed before generation permit')
            connection.execute("INSERT INTO planning_provider_generation_permits VALUES (?,?,?,?,?,?,?,?)",(permit_id,actual.provider_id,actual.version,policy_digest,request_digest,'PENDING',now,now))
            connection.commit()
        except Exception:
            connection.rollback(); raise
        return permit_id

    def _commit_generation_transport(self, permit_id, expected_policy, policy_digest, request_digest):
        """Atomically verify the permit and block G011 writes until transport ends."""
        connection=self.db._connection; now=_timestamp()
        connection.execute('BEGIN IMMEDIATE')
        try:
            row=connection.execute('SELECT * FROM planning_provider_generation_permits WHERE permit_id=?',(permit_id,)).fetchone()
            actual=self.invocation_policy(expected_policy.provider_id)
            if (row is None or row['state']!='PENDING' or row['policy_version']!=expected_policy.version
                    or row['policy_digest']!=policy_digest or row['request_digest']!=request_digest
                    or not self._same_policy(actual,expected_policy)):
                raise PermissionError('canonical G011 generation permit is invalid')
            connection.execute("UPDATE planning_provider_generation_permits SET state='TRANSPORT_COMMITTED',updated_at=? WHERE permit_id=?",(now,permit_id))
            connection.commit()
        except Exception:
            connection.rollback(); raise

    def _release_generation_permit(self, permit_id):
        with self.db._connection:
            self.db._connection.execute('DELETE FROM planning_provider_generation_permits WHERE permit_id=?',(permit_id,))
