"""Bounded, signed read checkpoints; no storage or authority is created here."""
import base64
import hashlib
import hmac
import json

CONTRACT = 'forge-workset-activity/v1'
MAX_EVENTS = 128
PAGE_SIZE = 16
MAX_CURSOR = 32768
MAX_PAGE_BYTES = 32768


class ActivityResync(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def checkpoint(key, context, manifest, seen, complete):
    value = {'contract_version': CONTRACT, 'context': context, 'manifest': manifest,
             'seen': seen, 'complete': complete, 'page_size': PAGE_SIZE}
    raw = canonical(value)
    encoded = base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
    result = encoded + '.' + hmac.new(key, raw, hashlib.sha256).hexdigest()
    if len(result) > MAX_CURSOR:
        raise ValueError('activity cursor capacity exceeded')
    return result


def resume(key, cursor, context):
    try:
        if type(cursor) is not str or not 1 <= len(cursor) <= MAX_CURSOR:
            raise ValueError('cursor bound')
        encoded, signature = cursor.split('.')
        raw = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True)
        if not hmac.compare_digest(signature, hmac.new(key, raw, hashlib.sha256).hexdigest()):
            raise ValueError('cursor signature')
        value = json.loads(raw)
        if (canonical(value) != raw or set(value) != {'contract_version', 'context', 'manifest', 'seen', 'complete', 'page_size'}
                or value['contract_version'] != CONTRACT or value['context'] != context
                or value['page_size'] != PAGE_SIZE or type(value['page_size']) is not int
                or type(value['complete']) is not bool or type(value['seen']) is not dict
                or len(value['seen']) > MAX_EVENTS or not _hex(value['manifest'])
                or any(not _hex(k) or not _hex(v) for k, v in value['seen'].items())):
            raise ValueError('closed cursor')
        return value
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ActivityResync('RESYNC_REQUIRED') from None


def _hex(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def page(key, context, events, cursor=None, *, source_snapshot=None):
    if len(events) > MAX_EVENTS or len({e['event_id'] for e in events}) != len(events):
        raise ValueError('bounded unique activity identities required')
    manifest = {e['event_id']: hashlib.sha256(canonical(e)).hexdigest() for e in events}
    watermark = source_snapshot or hashlib.sha256(canonical(manifest)).hexdigest()
    seen = {}
    if cursor is not None:
        old = resume(key, cursor, context)
        seen = old['seen']
        if (not old['complete'] and old['manifest'] != watermark
                or any(manifest.get(k) != v for k, v in seen.items())):
            raise ActivityResync('RESYNC_REQUIRED')
    pending = [e for e in events if e['event_id'] not in seen]
    selected = pending[:PAGE_SIZE]
    if len(canonical(selected)) > MAX_PAGE_BYTES:
        raise ValueError('activity page byte bound')
    seen = {**seen, **{e['event_id']: manifest[e['event_id']] for e in selected}}
    complete = len(selected) == len(pending)
    return {'events': selected, 'cursor': checkpoint(key, context, watermark, seen, complete),
            'has_more': not complete, 'source_watermark': watermark}
