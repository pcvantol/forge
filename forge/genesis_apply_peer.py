"""Finite Genesis HTTP transport; no proxy, redirects, retries or grant issuance."""
import http.client
from importlib.resources import files
import socket
from threading import Timer
import time
from .approved_worklist import identifier, timestamp
from .ep_inspection_contract import _schema
from .ep_inspection_peer import endpoint, PeerError
from .project_bootstrap.schema import canonical, load_json, ContractError
from .project_bootstrap.service import digest

MAX_RESPONSE = 524288
# Filled only from the separately qualified L2 exact-final-main handoff.
# A merged candidate and its local tests do not qualify a producer.
QUALIFIED_PRODUCER = None


def receipt(raw, pairing, request, documents):
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
        raise ContractError('finite original Genesis receipt required')
    schema_raw = files('forge').joinpath('api/ep-genesis-local-bootstrap-v1.schema.json').read_bytes()
    if digest(schema_raw) != pairing['producer_schema_sha256']:
        raise ContractError('qualified Genesis schema differs')
    schema = load_json(schema_raw)['oneOf'][0]
    value = load_json(raw)
    _schema(value, schema)
    def extra_bounds(item, rule):
        if type(item) is int and item > rule.get('maximum', item):
            raise ContractError('Genesis integer maximum exceeded')
        if type(item) is list:
            if rule.get('uniqueItems') and len({canonical(v) for v in item}) != len(item):
                raise ContractError('Genesis duplicate array item')
            for child in item: extra_bounds(child, rule['items'])
        elif type(item) is dict:
            for key, child in item.items(): extra_bounds(child, rule['properties'][key])
    extra_bounds(value, schema)
    binding = pairing['binding']
    expected = {'operation_id': request['operation_id'], 'request_digest': digest(canonical(request)),
                'effect_plan_binding': request['effect_plan_binding'], 'target_ref': request['target_ref'],
                'authorization_ref': pairing['ep_grant_id'], 'instance_id': binding['instance_id'], 'host_id': binding['host_id'],
                'bundle_digest': documents['ep_bundle_binding']['canonical_digest'],
                'manifest_digest': documents['manifest_digest'], 'input_digest': pairing['input_digest'],
                'producer_version': pairing['producer_version']}
    if any(value[key] != item for key, item in expected.items()):
        raise ContractError('original Genesis operation binding differs')
    if {k: v for k, v in value['identity'].items() if k != 'state'} != documents['identity']:
        raise ContractError('original Genesis identity differs')
    for name in ('source_updated_at', 'observed_at'):
        timestamp(value[name])
    if value['validator_sha256'] not in (None, documents['validation']['validator_sha256']):
        raise ContractError('original Genesis validator differs')
    if value['validation'] is not None and value['validation']['manifest_digest'] != documents['manifest_digest']:
        raise ContractError('original Genesis validation manifest differs')
    if value['state'] == 'COMPLETE' and (value['identity']['state'] != 'REGISTERED' or not value['commit'] or not value['tree']
            or value['validation'] is None or value['validator_sha256'] is None
            or set(value['completed_steps']) != set(schema['properties']['completed_steps']['items']['enum'])):
        raise ContractError('complete Genesis lacks committed registration evidence')
    return value


def exchange(pairing, method, *, body=None, resume=False, deadline=None, before_send=None):
    """One exact request. Lost responses remain uncertain; callers recover by GET."""
    if method == 'POST' and before_send is None:
        raise ContractError('current Forge authority callback required before effect send')
    if method not in ('GET', 'POST') or (method == 'GET' and (body is not None or resume)):
        raise ContractError('finite explicit Genesis transport required')
    host, port = endpoint(pairing['endpoint']); binding = pairing['binding']
    operation = identifier(binding['operation_id'])
    if method == 'POST' and not resume and (body is None or body['operation_id'] != operation
            or digest(canonical(body)) != pairing['request_digest']):
        raise ContractError('exact owner-bound Genesis request required')
    if resume and body is not None:
        raise ContractError('resume cannot replace the original request')
    timeout = min(30, deadline-time.monotonic()) if deadline is not None else 30
    if timeout <= 0: raise PeerError('EP_GENESIS_DEADLINE_EXCEEDED')
    headers = {'Authorization': 'Bearer '+pairing['credential'], 'EP-Bootstrap-Contract': '1.0',
               'EP-Instance-ID': binding['instance_id'], 'EP-Host-ID': binding['host_id'],
               'EP-Consumer-ID': binding['consumer_id'], 'EP-Principal': binding['principal'], 'EP-Audience': 'genesis-bootstrap'}
    path = '/v1/bootstrap/genesis/operations'
    if method == 'GET' or resume: path += '/'+operation+('/resume' if resume else '')
    # Owning EP resume explicitly forbids a request body (Content-Length0).
    payload = canonical(body) if body is not None else None
    if payload is not None: headers['Content-Type'] = 'application/json'
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    hard_deadline = time.monotonic()+timeout; watchdog = None
    try:
        connection.connect(); peer_socket = connection.sock
        def interrupt():
            try: peer_socket.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            peer_socket.close()
        watchdog = Timer(max(0, hard_deadline-time.monotonic()), interrupt); watchdog.daemon = True; watchdog.start()
        if time.monotonic() >= hard_deadline: raise PeerError('EP_GENESIS_DEADLINE_EXCEEDED')
        if before_send is not None: before_send(hard_deadline)
        if time.monotonic() >= hard_deadline: raise PeerError('EP_GENESIS_DEADLINE_EXCEEDED')
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise PeerError('EP_GENESIS_HTTP_'+str(response.status), 424)
        raw = response.read(MAX_RESPONSE+1)
        if len(raw) > MAX_RESPONSE or response.read(1): raise PeerError('EP_GENESIS_RESPONSE_LIMIT', 424)
        if time.monotonic() >= hard_deadline: raise PeerError('EP_GENESIS_DEADLINE_EXCEEDED')
        return raw
    except PermissionError:
        raise
    except (OSError, http.client.HTTPException) as error:
        raise PeerError('EP_GENESIS_TRANSPORT_UNCERTAIN') from error
    finally:
        if watchdog is not None: watchdog.cancel(); watchdog.join(0.2)
        connection.close()
