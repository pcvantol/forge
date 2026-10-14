"""Durable private concept turns over the existing provider, no project mutation."""
from urllib.parse import urlsplit, parse_qs
from hashlib import sha256
import json
import sqlite3
from .concept_advisory_contract import CONTRACT, request, result, digest, LANGUAGES, FIELDS
from .concept_advisory_provider import ConceptAdvisoryProvider
from .advisory_contract import AdvisoryConflict
from .advisory_provider import AdvisoryNotStarted, AdvisoryProviderUnavailable
from .worklist_control import control_runtime
from .planner.codex_cli_session import _policy_digest


def provider_profile(root, provider_id):
    with control_runtime(root) as runtime:
        provider = ConceptAdvisoryProvider(runtime, provider_id)
        policy = provider.configuration.current_policy()
        if not policy.provider_home or not policy.provider_config_home or policy.instance_id != runtime.database.runtime_identity.runtime_id:
            raise PermissionError('instance-owned provider context required')
        profile = {'provider_id': policy.provider_id, 'model': policy.model or 'SESSION_CONFIGURED_NOT_REPORTED', 'profile': policy.profile,
                   'policy_digest': _policy_digest(policy), 'input_token_bound': policy.input_token_bound,
                   'context_token_bound': policy.context_token_bound, 'output_token_bound': policy.output_token_bound,
                   'timeout_seconds': policy.timeout_seconds,
                   'data_transfer': ['explicit_briefing', 'user_message', 'accepted_prior_turns'],
                   'receiver': 'INSTANCE_CONFIGURED_EXTERNAL_SESSION', 'tools': False}
        return {**profile, 'transfer_policy_digest': digest(profile)}


class ConceptAdvisoryService:
    def __init__(self, grant):
        self.grant = grant

    def _load(self):
        store = self.grant._store()
        for key, turn in store['records'].items():
            if not isinstance(turn, dict) or set(turn) != {'request', 'request_digest', 'principal_id', 'audience', 'session_id', 'invocation_id', 'context', 'provider', 'status', 'outcome', 'reserved_tokens', 'revision', 'integrity'}:
                raise ValueError('retained concept turn invalid')
            r, h = request(turn['request'])
            if h != turn['request_digest'] or key != self._key(turn['principal_id'], turn['audience'], r):
                raise ValueError('retained concept source invalid')
            original = {k: v for k, v in turn.items() if k != 'integrity'}
            if turn['integrity'] != self.grant.integrity(original) or turn['status'] not in ('PENDING', 'COMPLETE', 'FAILED', 'UNCERTAIN'):
                raise ValueError('retained concept integrity invalid')
            if type(turn['reserved_tokens']) is not int or turn['reserved_tokens'] < 1 or type(turn['revision']) is not int or turn['revision'] < 1:
                raise ValueError('retained concept consumption invalid')
            if turn['status'] == 'COMPLETE':
                if turn['outcome'] is None or turn['outcome']['output'] is None or digest(result(turn['outcome']['output'], turn)) != turn['outcome']['result_digest']:
                    raise ValueError('retained concept result invalid')
        return store

    @staticmethod
    def _key(principal, audience, r):
        return sha256(json.dumps([r['instance_id'], principal, audience, r['dossier_id'], r['operation_id']], separators=(',', ':')).encode()).hexdigest()

    def _save(self, store, key, turn):
        original = {k: v for k, v in turn.items() if k != 'integrity'}
        store['records'][key] = {**original, 'integrity': self.grant.integrity(original)}
        if len(json.dumps(store).encode()) > 1048576:
            raise AdvisoryConflict('CONCEPT_STORAGE_CAPACITY')
        self.grant.save_store(store)

    def _envelope(self, principal, turn=None, **extra):
        return {'contract_version': CONTRACT, 'instance_id': principal.instance_id,
                'principal_id': principal.principal_id, 'audience': principal.audience,
                **({'dossier_id': turn['request']['dossier_id'], 'conversation_id': turn['request']['conversation_id'], 'original_turn': turn} if turn else {}), **extra}

    def capability(self, authorization, audience):
        p = self.grant.authorize(authorization, audience=audience)
        with self.grant.boundary():
            self.grant.authorize(authorization, audience=audience); self._load()
        profile = provider_profile(self.grant.root, p.provider_id)
        return self._envelope(p, supported_languages=list(LANGUAGES), briefing_fields=list(FIELDS),
                              dossier_ids=list(p.dossier_ids), conversation_ids=list(p.conversation_ids),
                              permissions=list(p.permissions), maximum_turns=p.maximum_turns, maximum_tokens=p.maximum_tokens,
                              provider=profile, transfer_authorized=p.transfer_policy_digest == profile['transfer_policy_digest'],
                              generation_on_read=False, approval=False, apply=False, retention='PRIVATE_NO_AUTOMATIC_DELETE')

    def submit(self, authorization, audience, document):
        r, h = request(document)
        p = self.grant.authorize(authorization, audience=audience, dossier_id=r['dossier_id'], conversation_id=r['conversation_id'], permission='ADVISE')
        if r['instance_id'] != p.instance_id:
            raise PermissionError('foreign concept instance')
        profile = provider_profile(self.grant.root, p.provider_id)
        if r['transfer_policy_digest'] != p.transfer_policy_digest or p.transfer_policy_digest != profile['transfer_policy_digest']:
            raise PermissionError('current explicit transfer permission required')
        key = self._key(p.principal_id, p.audience, r)
        with control_runtime(self.grant.root) as runtime:
            provider = ConceptAdvisoryProvider(runtime, p.provider_id)
            with self.grant.boundary():
                p = self.grant.authorize(authorization, audience=audience, dossier_id=r['dossier_id'], conversation_id=r['conversation_id'], permission='ADVISE')
                store = self._load(); old = store['records'].get(key)
                if old is not None:
                    if old['request_digest'] != h:
                        raise AdvisoryConflict('OPERATION_CONTENT_CONFLICT')
                    return self._envelope(p, old, recorded=False)
                owned = [t for t in store['records'].values() if t['principal_id'] == p.principal_id and t['audience'] == p.audience]
                if any(t['status'] in ('PENDING', 'UNCERTAIN') for t in store['records'].values()):
                    raise AdvisoryConflict('INVOCATION_UNRESOLVED')
                history_turns = [t for t in owned if t['request']['dossier_id'] == r['dossier_id'] and t['request']['conversation_id'] == r['conversation_id']]
                if any(t['request']['turn_id'] == r['turn_id'] for t in history_turns):
                    raise AdvisoryConflict('TURN_ID_REUSED')
                revision = len(history_turns)
                if revision != r['expected_revision']:
                    raise AdvisoryConflict('CONVERSATION_STALE')
                if history_turns:
                    previous = max(history_turns, key=lambda t: t['revision'])['request']['briefing']
                    if previous['concept_id'] != r['briefing']['concept_id'] or previous['revision'] > r['briefing']['revision'] or (previous['revision'] == r['briefing']['revision'] and previous != r['briefing']):
                        raise AdvisoryConflict('BRIEFING_STALE')
                if len(owned) >= p.maximum_turns or sum(t['reserved_tokens'] for t in owned) + profile['context_token_bound'] > p.maximum_tokens or len(store['records']) >= 64:
                    raise AdvisoryConflict('CONCEPT_QUOTA_EXHAUSTED')
                history = [{'turn_id': t['request']['turn_id'], 'request': t['request'], 'output': t['outcome']['output']} for t in sorted(history_turns, key=lambda t: t['revision']) if t['status'] == 'COMPLETE']
                refs = ['briefing:'+r['briefing_digest'], 'turn:'+r['turn_id']] + ['turn:'+t['turn_id'] for t in history]
                context = {'evidence_references': refs, 'source_qualification': 'SUPPLIED_UNVERIFIED', 'missing_information': 'UNKNOWN', 'governance': 'NO_APPROVAL'}
                turn = {'request': r, 'request_digest': h, 'principal_id': p.principal_id, 'audience': p.audience,
                        'session_id': 'concept-session-'+key[:32], 'invocation_id': 'concept-invocation-'+key[:32],
                        'context': context, 'provider': None, 'status': 'PENDING', 'outcome': None,
                        'reserved_tokens': profile['context_token_bound'], 'revision': revision+1}
                policy, _, generation_digest = provider.prepare(turn, history)
                turn['provider'] = {'provider_id': p.provider_id, 'policy_digest': _policy_digest(policy),
                                    'generation_digest': generation_digest, 'requested_model': policy.model,
                                    'requested_profile': policy.profile, 'input_token_bound': policy.input_token_bound,
                                    'output_token_bound': policy.output_token_bound, 'context_token_bound': policy.context_token_bound}
                self._save(store, key, turn)
            # No grant/authorization lock spans preflight, generation, or client wait.
            def authorize():
                with self.grant.boundary():
                    current = self.grant.authorize(authorization, audience=audience, dossier_id=r['dossier_id'], conversation_id=r['conversation_id'], permission='ADVISE')
                    self._load()
                    if current.transfer_policy_digest != r['transfer_policy_digest']:
                        raise PermissionError('transfer grant changed')
            def sink(outcome):
                with self.grant.boundary():
                    current_store = self._load(); turn['outcome'] = outcome
                    turn['status'] = 'COMPLETE' if outcome['output'] is not None else ('UNCERTAIN' if outcome['execution'] == 'MAY_HAVE_HAPPENED' else 'FAILED')
                    self._save(current_store, key, turn)
            try:
                provider.invoke(turn, history, authorize, sink)
            except AdvisoryNotStarted:
                with self.grant.boundary():
                    current_store = self._load(); turn['status'] = 'FAILED'; self._save(current_store, key, turn)
                raise
        self.grant.authorize(authorization, audience=audience, dossier_id=r['dossier_id'], conversation_id=r['conversation_id'])
        return self._envelope(p, self._load()['records'][key], recorded=True)

    def read(self, authorization, audience, dossier, conversation, operation=None):
        p = self.grant.authorize(authorization, audience=audience, dossier_id=dossier, conversation_id=conversation)
        with self.grant.boundary():
            self.grant.authorize(authorization, audience=audience, dossier_id=dossier, conversation_id=conversation)
            store = self._load()
            turns = [t for t in store['records'].values() if t['principal_id'] == p.principal_id and t['audience'] == audience and t['request']['dossier_id'] == dossier and t['request']['conversation_id'] == conversation]
            if operation is not None:
                turn = next((t for t in turns if t['request']['operation_id'] == operation), None)
                if turn is None:
                    raise FileNotFoundError('unknown concept turn')
                return self._envelope(p, turn, read_only=True)
            return self._envelope(p, dossier_id=dossier, conversation_id=conversation, turns=sorted(turns, key=lambda t: t['revision']), revision=len(turns), read_only=True)

    def handle(self, method, target, authorization, audience, body):
        try:
            if not audience:
                raise PermissionError('explicit audience required')
            path = urlsplit(target).path; query = parse_qs(urlsplit(target).query, strict_parsing=True)
            if path == '/v1/concept-advisory/capability' and method == 'GET' and not query:
                return 200, self.capability(authorization, audience)
            if path == '/v1/concept-advisory/turns' and method == 'POST' and not query:
                return 200, self.submit(authorization, audience, body)
            if method == 'GET' and set(query) == {'dossier_id', 'conversation_id'} and all(len(v) == 1 for v in query.values()):
                dossier = query['dossier_id'][0]; conversation = query['conversation_id'][0]
                if path == '/v1/concept-advisory/history':
                    return 200, self.read(authorization, audience, dossier, conversation)
                prefix = '/v1/concept-advisory/intents/'
                if path.startswith(prefix):
                    from .approved_worklist import identifier
                    operation = identifier(path[len(prefix):])
                    return 200, self.read(authorization, audience, dossier, conversation, operation)
            return 404, {'contract_version': CONTRACT, 'error': {'code': 'CONCEPT_ROUTE_UNSUPPORTED'}}
        except PermissionError:
            code, status = 'CONCEPT_SCOPE_DENIED', 403
        except AdvisoryConflict as error:
            code, status = error.code, 409
        except FileNotFoundError:
            code, status = 'CONCEPT_TURN_NOT_FOUND', 404
        except (AdvisoryProviderUnavailable, OSError, RuntimeError, sqlite3.Error):
            code, status = 'CONCEPT_STORAGE_OR_PROVIDER_UNAVAILABLE', 503
        except (ValueError, TypeError, KeyError):
            code, status = 'CONCEPT_REQUEST_INVALID', 400
        return status, {'contract_version': CONTRACT, 'error': {'code': code}}
