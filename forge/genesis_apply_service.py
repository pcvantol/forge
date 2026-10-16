"""Explicit effect coordination over original owning Forge and EP HTTP services."""
from contextlib import contextmanager
import sqlite3
from urllib.parse import urlsplit, parse_qs
from .approved_worklist import identifier
from .ep_inspection_peer import PeerError
from .genesis_apply_contract import CONTRACT, apply_request, ep_request
from .genesis_apply_journal import GenesisDispatchJournal
from .genesis_apply_pairing import GenesisApplyPairings
from .genesis_apply_peer import exchange, receipt
from .genesis_bootstrap_contract import BootstrapConflict
from .genesis_bootstrap_grant import GenesisBootstrapGrant
from .genesis_bootstrap_service import GenesisBootstrapService
from .project_bootstrap.schema import canonical, load_json, ContractError
from .project_bootstrap.service import digest

BASE = '/v1/genesis-apply'


class GenesisApplyService:
    def __init__(self, grant):
        self.grant = grant
        self.journal = GenesisDispatchJournal(grant)
        self.pairings = GenesisApplyPairings(grant)
        self.bootstrap = GenesisBootstrapService(GenesisBootstrapGrant(grant.root, grant.instance_id))

    def source(self, principal, request, *, effect):
        if request['instance_id'] != self.grant.instance_id or request['dossier_id'] not in principal.dossier_ids:
            raise PermissionError('foreign Genesis apply instance or dossier')
        view = self.bootstrap.view(principal, self.bootstrap.store(), request['plan_id'])
        plan = view['plan']
        decisions = [d for d in view['effect_history'] if d['decision_id'] == request['decision_id']]
        if (plan['plan_digest'] != request['plan_digest'] or len(decisions) != 1
                or decisions[0]['decision_digest'] != request['decision_digest']):
            raise BootstrapConflict('GENESIS_EXACT_ORIGINAL_DECISION_REQUIRED')
        if effect and (not view['effect_decision_currently_applicable'] or view['effect_history'][-1] != decisions[0]):
            raise BootstrapConflict('GENESIS_CURRENT_EFFECT_DECISION_REQUIRED')
        original, _, _ = self.bootstrap.source(principal, request['dossier_id'], plan['source_subject']['plan_id'])
        request_ep, _ = ep_request(original, plan, decisions[0], request['operation_id'])
        return view, request_ep

    def current(self, authorization, audience, request, permission, expected=None):
        principal = self.grant.authorize(authorization, audience=audience, dossier_id=request['dossier_id'], permission=permission)
        view, request_ep = self.source(principal, request, effect=permission != 'READ')
        if permission != 'READ':
            self.grant.authorize(authorization, audience=audience, dossier_id=request['dossier_id'], permission=permission, plan=view['plan'])
        pairing = self.pairings.pair(request['pairing_id'], expected['pairing_digest'] if expected else None)
        plan = view['plan']
        expected_pair = {'plan_id':plan['plan_id'], 'plan_digest':plan['plan_digest'], 'decision_id':request['decision_id'],
                         'decision_digest':request['decision_digest'], 'placement_ref':plan['target']['placement_ref'],
                         'target_ref':plan['target']['target_ref'], 'request_digest':digest(canonical(request_ep)),
                         'input_digest':plan['source_subject']['input_digest']}
        if (any(pairing[k] != v for k, v in expected_pair.items())
                or pairing['binding']['instance_id'] != plan['target']['ep_instance_id']
                or pairing['binding']['operation_id'] != request['operation_id']):
            raise PermissionError('original EP grant/plan binding differs')
        if expected is not None and permission != 'READ' and principal.grant_id != expected['grant_id']:
            raise PermissionError('original Genesis effect grant required')
        if expected is not None and (principal.principal_id != expected['principal_id'] or principal.audience != expected['audience']
                                    or request != expected['request'] or request_ep != expected['ep_request']):
            raise PermissionError('original Genesis intent scope differs')
        return principal, view, pairing, request_ep

    @staticmethod
    def response(principal, row, view):
        observed = row['observation']['response'] if row['observation'] else None
        return {'contract_version':CONTRACT, 'instance_id':principal.instance_id, 'principal_id':principal.principal_id,
                'audience':principal.audience, 'dossier_id':row['request']['dossier_id'], 'operation_id':row['request']['operation_id'],
                'original_request':row['request'], 'original_request_digest':row['request_digest'],
                'ep_request_digest':row['ep_request_digest'], 'pairing_digest':row['pairing_digest'],
                'effect_decision_currently_applicable':view['effect_decision_currently_applicable'],
                'state':observed['state'] if observed else ('EFFECT_UNCERTAIN' if row['attempts'] else 'NOT_REQUESTED'),
                'original_ep_operation':observed, 'explicit_attempts':len(row['attempts']),
                'project_readiness':'NOT_ASSESSED', 'mission':'NOT_REQUESTED'}

    def _observe(self, authorization, audience, request, original, pairing, request_ep, raw, claim):
        documents = self._documents(request)
        observed = receipt(raw, pairing, request_ep, documents)
        with self.grant.boundary():
            principal, view, _, _ = self.current(authorization, audience, request, 'READ', original)
            row = self.journal.observe(request['operation_id'], claim, observed)
            return self.response(principal, row, view)

    def _documents(self, request):
        # Always sealed owning storage; never caller-provided approved documents.
        row = self.bootstrap.store()['records'].get(request['plan_id'])
        if row is None or row['kind'] != 'PLAN': raise RuntimeError('owning original plan unavailable')
        return row['document']['documents']

    def send(self, authorization, audience, request, original, pairing, method, *, permission='READ', claim=None, body=None, resume=False):
        def current_before_send(deadline):
            with self.grant.boundary(deadline):
                self.current(authorization, audience, request, permission, original)
                row = self.journal.store()['records'][request['operation_id']]
                if claim is not None and (not row['attempts'] or row['attempts'][-1]['claim'] != claim):
                    raise BootstrapConflict('GENESIS_LATE_SEND_FENCED')
        return exchange(pairing, method, body=body, resume=resume, before_send=current_before_send)

    def submit(self, authorization, audience, value):
        request, _ = apply_request(value)
        with self.grant.boundary():
            principal, view, pairing, request_ep = self.current(authorization, audience, request, 'REQUEST_APPLY')
            original, _ = self.journal.prepare(request, principal, pairing['pairing_digest'], request_ep)
        # Verify current peer authority and first recover the original operation.
        # No own grant or SQLite lock spans this wait.
        try:
            raw = self.send(authorization, audience, request, original, pairing, 'GET')
        except PeerError as error:
            if error.code != 'EP_GENESIS_HTTP_404': raise
            if original['attempts']:
                with self.grant.boundary():
                    principal, view, _, _ = self.current(authorization, audience, request, 'READ', original)
                    row = self.journal.store()['records'][request['operation_id']]
                    # Missing peer evidence must not publish an old COMPLETE.
                    if row['observation'] is not None: raise PeerError('EP_GENESIS_ORIGINAL_OPERATION_UNAVAILABLE', 424)
                    return self.response(principal, row, view)
            with self.grant.boundary():
                self.current(authorization, audience, request, 'REQUEST_APPLY', original)
                claim, send = self.journal.claim(request['operation_id'], attempt_id=request['operation_id'])
            if not send: return self.read(authorization, audience, request['dossier_id'], request['operation_id'])
            raw = self.send(authorization, audience, request, original, pairing, 'POST', permission='REQUEST_APPLY', claim=claim, body=request_ep)
        else:
            claim = original['attempts'][-1]['claim'] if original['attempts'] else None
        return self._observe(authorization, audience, request, original, pairing, request_ep, raw, claim)

    def original(self, authorization, audience, dossier, operation):
        identifier(dossier); identifier(operation)
        principal = self.grant.authorize(authorization, audience=audience, dossier_id=dossier)
        row = self.journal.store()['records'].get(operation)
        if row is None: raise FileNotFoundError('original Genesis intent unavailable')
        if row['request']['dossier_id'] != dossier or row['principal_id'] != principal.principal_id or row['audience'] != principal.audience:
            raise PermissionError('foreign original Genesis intent')
        return row

    def read(self, authorization, audience, dossier, operation):
        with self.grant.boundary():
            original = self.original(authorization, audience, dossier, operation)
            _, _, pairing, request_ep = self.current(authorization, audience, original['request'], 'READ', original)
        raw = self.send(authorization, audience, original['request'], original, pairing, 'GET')
        claim = original['attempts'][-1]['claim'] if original['attempts'] else None
        return self._observe(authorization, audience, original['request'], original, pairing, request_ep, raw, claim)

    def resume(self, authorization, audience, operation, value):
        fields = {'contract_version', 'instance_id', 'dossier_id', 'operation_id', 'attempt_id', 'original_request_digest'}
        if not isinstance(value, dict) or set(value) != fields or value['contract_version'] != CONTRACT or value['operation_id'] != operation or value['instance_id'] != self.grant.instance_id:
            raise ContractError('closed original explicit Genesis resume required')
        identifier(value['attempt_id'])
        with self.grant.boundary():
            original = self.original(authorization, audience, value['dossier_id'], operation)
            if original['request_digest'] != value['original_request_digest']:
                raise BootstrapConflict('GENESIS_ORIGINAL_INTENT_CONFLICT')
            _, view, pairing, request_ep = self.current(authorization, audience, original['request'], 'RESUME', original)
        # Explicit resume still requires a currently accessible original admission.
        raw = self.send(authorization, audience, original['request'], original, pairing, 'GET')
        observed = receipt(raw, pairing, request_ep, view['plan']['documents'])
        if observed['state'] == 'COMPLETE':
            return self.read(authorization, audience, value['dossier_id'], operation)
        with self.grant.boundary():
            self.current(authorization, audience, original['request'], 'RESUME', original)
            claim, send = self.journal.claim(operation, attempt_id=value['attempt_id'], resume=True)
        if send: raw = self.send(authorization, audience, original['request'], original, pairing, 'POST', permission='RESUME', claim=claim, resume=True)
        return self._observe(authorization, audience, original['request'], original, pairing, request_ep, raw, claim)

    def handle(self, method, target, authorization, audience, body=None):
        try:
            if not isinstance(audience, str): raise PermissionError('explicit consumer audience required')
            parsed = urlsplit(target); path = parsed.path
            if method == 'POST' and path == BASE+'/operations' and not parsed.query:
                return 200, self.submit(authorization, audience, body)
            pieces = path.removeprefix(BASE+'/operations/').split('/')
            if path.startswith(BASE+'/operations/') and method == 'GET' and len(pieces) == 1:
                query = parse_qs(parsed.query, strict_parsing=True)
                if set(query) != {'dossier_id'} or len(query['dossier_id']) != 1: raise ContractError('exact dossier query required')
                return 200, self.read(authorization, audience, query['dossier_id'][0], pieces[0])
            if path.startswith(BASE+'/operations/') and method == 'POST' and len(pieces) == 2 and pieces[1] == 'resume' and not parsed.query:
                return 200, self.resume(authorization, audience, pieces[0], body)
            raise ContractError('unsupported Genesis apply route')
        except PermissionError: status, code = 403, 'GENESIS_APPLY_SCOPE_DENIED'
        except BootstrapConflict as error: status, code = 409, error.code
        except FileNotFoundError: status, code = 503, 'GENESIS_APPLY_ORIGINAL_UNAVAILABLE'
        except PeerError as error: status, code = error.status, error.code
        except (RuntimeError, OSError, sqlite3.Error): status, code = 503, 'GENESIS_APPLY_STORAGE_UNAVAILABLE'
        except (ValueError, KeyError, TypeError, RecursionError): status, code = 400, 'GENESIS_APPLY_INVALID'
        return status, {'contract_version':CONTRACT, 'error':{'code':code}}


@contextmanager
def publication(grant, authorization, audience, body, *, deadline=None):
    service = GenesisApplyService(grant)
    with grant.boundary(deadline):
        original = service.original(authorization, audience, body['dossier_id'], body['operation_id'])
        _, _, pairing, request_ep = service.current(authorization, audience, original['request'], 'READ', original)
    # Recheck actual EP grant before each protected chunk, without own locks.
    try:
        raw = exchange(pairing, 'GET', deadline=deadline)
        receipt(raw, pairing, request_ep, service._documents(original['request']))
    except (PeerError, ValueError, KeyError, TypeError) as error:
        raise PermissionError('current original Genesis peer publication denied') from error
    with grant.boundary(deadline):
        principal, view, _, _ = service.current(authorization, audience, original['request'], 'READ', original)
        now = service.journal.store()['records'][body['operation_id']]
        if body != service.response(principal, now, view):
            raise PermissionError('Genesis publication scope/epoch changed')
        yield
