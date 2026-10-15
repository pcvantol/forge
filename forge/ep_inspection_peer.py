"""Finite owner-bound original EP GET; no proxy, redirect, POST or ambient auth."""
import http.client
import time
from urllib.parse import urlsplit
from hashlib import sha256
from .approved_worklist import identifier
from .project_bootstrap.schema import canonical, ContractError
from .ep_inspection_contract import observation, MAX_RESPONSE


class PeerError(RuntimeError):
    def __init__(self, code, status=503):
        super().__init__(code)
        self.code = code
        self.status = status


def endpoint(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment or not parsed.port:
        raise ContractError('first local EP profile requires explicit loopback origin')
    return parsed.hostname, parsed.port


def original(pairing, *, deadline=None):
    """Check current peer access to the original; network wait owns no Forge lock."""
    host, port = endpoint(pairing['endpoint'])
    binding = pairing['binding']
    operation = identifier(binding['operation_id'])
    timeout = min(10, deadline-time.monotonic()) if deadline is not None else 10
    if timeout <= 0:
        raise PeerError('EP_DEADLINE_EXCEEDED')
    headers = {'Authorization': 'Bearer '+pairing['credential'],
               'EP-Inspection-Contract': '1.0', 'EP-Instance-ID': binding['instance_id'],
               'EP-Host-ID': binding['host_id'], 'EP-Consumer-ID': binding['consumer_id'],
               'EP-Principal': binding['principal'], 'EP-Audience': binding['audience']}
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request('GET', '/v1/onboarding/inspections/'+operation, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            # Preserve denied/not-found/refused/unavailable distinctions; no cached success.
            raise PeerError('EP_HTTP_'+str(response.status), 424)
        raw = response.read(MAX_RESPONSE+1)
        if len(raw) > MAX_RESPONSE or response.read(1):
            raise PeerError('EP_RESPONSE_LIMIT_EXCEEDED', 424)
        value = observation(raw, binding)
        if sha256(canonical(value)).hexdigest() != pairing['snapshot_digest']:
            raise PeerError('EP_ORIGINAL_SNAPSHOT_MISMATCH', 424)
        return raw, value
    except (OSError, http.client.HTTPException) as error:
        raise PeerError('EP_TRANSPORT_UNAVAILABLE') from error
    except (ValueError, TypeError, KeyError) as error:
        raise PeerError('EP_CONTRACT_OR_SUBJECT_INVALID', 424) from error
    finally:
        connection.close()
