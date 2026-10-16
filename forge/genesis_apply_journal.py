"""Bounded durable dispatch intents; EP remains the owner of effect truth.

Callers hold the owning grant boundary and recheck authority. A persisted send
claim is never cleared, including after timeout or a lost response. Recovery
therefore reads the original EP operation instead of issuing another create.
"""
import secrets
from .approved_worklist import identifier
from .genesis_apply_contract import apply_request
from .genesis_bootstrap_contract import BootstrapConflict
from .project_bootstrap.schema import canonical, load_json
from .project_bootstrap.service import digest


class GenesisDispatchJournal:
    def __init__(self, grant):
        self.grant = grant

    def store(self):
        try:
            value = self.grant._store()
            for key, row in value['records'].items():
                fields = {'request', 'request_digest', 'principal_id', 'audience', 'grant_id',
                          'pairing_digest', 'ep_request', 'ep_request_digest', 'attempts', 'observation'}
                if not isinstance(row, dict) or set(row) != fields:
                    raise ValueError('closed dispatch intent required')
                request, request_digest = apply_request(row['request'])
                if key != request['operation_id'] or request_digest != row['request_digest']:
                    raise ValueError('original dispatch identity differs')
                for name in ('principal_id', 'audience', 'grant_id'):
                    identifier(row[name])
                from .proposal_content_contract import hash_value
                hash_value(row['pairing_digest'])
                if (digest(canonical(row['ep_request'])) != row['ep_request_digest']
                        or row['ep_request']['operation_id'] != key):
                    raise ValueError('frozen EP request differs')
                attempts = row['attempts']
                if not isinstance(attempts, list) or len(attempts) > 16:
                    raise ValueError('finite explicit dispatch attempts required')
                seen = set()
                for index, attempt in enumerate(attempts):
                    if (not isinstance(attempt, dict) or set(attempt) != {'attempt_id', 'claim', 'kind'}
                            or attempt['kind'] != ('CREATE' if index == 0 else 'RESUME')
                            or attempt['attempt_id'] in seen):
                        raise ValueError('append-only original dispatch attempts required')
                    identifier(attempt['attempt_id']); identifier(attempt['claim'])
                    seen.add(attempt['attempt_id'])
                observation = row['observation']
                if observation is not None and (not isinstance(observation, dict)
                        or set(observation) != {'claim', 'response', 'response_digest'}
                        or observation['claim'] not in ({a['claim'] for a in attempts} if attempts else {None})
                        or digest(canonical(observation['response'])) != observation['response_digest']):
                    raise ValueError('bound original observation required')
            return value
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise RuntimeError('initialized Genesis dispatch storage unavailable') from error

    def prepare(self, request, principal, pairing_digest, ep_request):
        request, h = apply_request(request)
        store = self.store(); key = request['operation_id']
        existing = store['records'].get(key)
        proposed = {'request': request, 'request_digest': h, 'principal_id': principal.principal_id,
                    'audience': principal.audience, 'grant_id': principal.grant_id,
                    'pairing_digest': pairing_digest, 'ep_request': ep_request,
                    'ep_request_digest': digest(canonical(ep_request)), 'attempts': [], 'observation': None}
        if existing is not None:
            if {k: v for k, v in existing.items() if k not in ('attempts', 'observation')} != {
                    k: v for k, v in proposed.items() if k not in ('attempts', 'observation')}:
                raise BootstrapConflict('GENESIS_ORIGINAL_INTENT_CONFLICT')
            return load_json(canonical(existing)), False
        if any(row['request']['plan_id'] == request['plan_id'] for row in store['records'].values()):
            raise BootstrapConflict('GENESIS_PLAN_ALREADY_HAS_ORIGINAL_INTENT')
        if len(store['records']) >= 64:
            raise BootstrapConflict('GENESIS_INTENT_CAPACITY_EXCEEDED')
        store['records'][key] = proposed
        self.grant.save_store(store)
        return load_json(canonical(proposed)), True

    def claim(self, operation_id, *, attempt_id, resume=False):
        identifier(operation_id); identifier(attempt_id)
        store = self.store(); row = store['records'][operation_id]
        found = next((a for a in row['attempts'] if a['attempt_id'] == attempt_id), None)
        if found is not None:
            if found['kind'] != ('RESUME' if resume else 'CREATE'):
                raise BootstrapConflict('GENESIS_ATTEMPT_KIND_CONFLICT')
            return found['claim'], False
        if not resume and row['attempts']:
            # Even a prior uncertain send is permanently claimed. Never retry POST.
            return row['attempts'][0]['claim'], False
        if resume and not row['attempts']:
            raise BootstrapConflict('GENESIS_ORIGINAL_ADMISSION_REQUIRED')
        if len(row['attempts']) >= 16:
            raise BootstrapConflict('GENESIS_ATTEMPT_CAPACITY_EXCEEDED')
        claim = 'dispatch-'+secrets.token_hex(16)
        row['attempts'].append({'attempt_id': attempt_id, 'kind': 'RESUME' if resume else 'CREATE', 'claim': claim})
        self.grant.save_store(store)
        return claim, True

    def observe(self, operation_id, claim, response):
        store = self.store(); row = store['records'][identifier(operation_id)]
        # Caller separately validates the closed producer response and current
        # authority. An older in-flight response cannot replace a newer attempt.
        if (row['attempts'][-1]['claim'] if row['attempts'] else None) != claim:
            raise BootstrapConflict('GENESIS_LATE_RESPONSE_FENCED')
        prior = row['observation']
        if prior is not None and 'source_updated_at' in response and 'source_updated_at' in prior['response']:
            from .approved_worklist import timestamp
            if timestamp(response['source_updated_at']) < timestamp(prior['response']['source_updated_at']):
                raise BootstrapConflict('GENESIS_OLDER_OBSERVATION_FENCED')
        row['observation'] = {'claim': claim, 'response': response, 'response_digest': digest(canonical(response))}
        self.grant.save_store(store)
        return load_json(canonical(row))
