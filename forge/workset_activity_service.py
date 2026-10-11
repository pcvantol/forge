"""Scoped HTTP history/current read; only explicit setup may provision authority."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from .approved_worklist import identifier, projection
from .workset_activity_cursor import CONTRACT, PAGE_SIZE, MAX_EVENTS, MAX_CURSOR, MAX_PAGE_BYTES, page, ActivityResync
from .workset_activity_grant import cursor_key
from .workset_activity_projection import collect, SOURCE_TYPES, ActivityUnavailable, MAX_SCAN_BYTES, public_label

BASE = '/v1/approved-workset-activity'


class WorksetActivityService:
    def __init__(self, root, grant):
        self.root, self.grant = Path(root), grant

    def capability(self, token):
        principal = self.grant.authorize(token, permission='READ')
        supported = True
        try:
            cursor_key(self.root)
        except (OSError, ValueError):
            supported = False
        self.grant.authorize(token, permission='READ')
        return {'contract_version': CONTRACT, 'supported': supported,
                'permissions': ['READ'], 'worksets': list(principal.worksets),
                'scope': {k: getattr(principal, k) for k in ('instance_id', 'project_id', 'repository_id')},
                'source_types': SOURCE_TYPES, 'page_size': PAGE_SIZE, 'maximum_events': MAX_EVENTS,
                'maximum_page_bytes': MAX_PAGE_BYTES, 'maximum_cursor_bytes': MAX_CURSOR,
                'maximum_scan_bytes': MAX_SCAN_BYTES, 'expires_at': principal.expires_at,
                'read_only': True, 'reorder_authorized_by_this_contract': False,
                'release_authorized_by_this_contract': False, 'accept_authorized_by_this_contract': False}

    def _collect(self, principal, workset_id):
        try:
            return collect(self.root, principal, workset_id)
        except ActivityUnavailable:
            raise
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            raise ActivityUnavailable('HISTORY_SOURCE_INVALID') from None

    def read(self, token, workset_id, *, cursor=None, event_id=None):
        principal = self.grant.authorize(token, workset_id, 'READ')
        key = cursor_key(self.root)
        events, context, stamp, coverage = self._collect(principal, workset_id)
        current = projection(self.root, principal.instance_id, workset_id, principal.principal_id, include_order=True)
        for item in current['items']:
            item['title'] = public_label(item['title'])[:160]
        # Existing projection owns current conditions. A second bounded snapshot
        # prevents presenting those conditions against a different source history.
        _, final_context, final_stamp, _ = self._collect(principal, workset_id)
        if context != final_context or stamp != final_stamp:
            raise ActivityResync('RESYNC_REQUIRED')
        self.grant.authorize(token, workset_id, 'READ')
        if event_id is not None:
            found = next((event for event in events if event['event_id'] == event_id), None)
            if found is None:
                return 404, {'contract_version': CONTRACT, 'error': {'code': 'EVENT_UNAVAILABLE'}}
            return 200, {'contract_version': CONTRACT, 'workset_id': workset_id, 'event': found,
                         'coverage': coverage, 'read_only': True}
        result = page(key, context, events, cursor, source_snapshot=stamp)
        response = {'contract_version': CONTRACT, 'workset_id': workset_id, **result,
                    'coverage': coverage, 'current': current,
                    'read_only': True, 'additional_model_calls': 0, 'execution_started': False}
        if len(json.dumps(response, ensure_ascii=True).encode()) > MAX_PAGE_BYTES:
            raise ActivityUnavailable('HISTORY_PARTIAL_CAPACITY')
        return 200, response

    def handle(self, method, target, token):
        try:
            parsed = urlsplit(target)
            if method != 'GET' or parsed.query or parsed.fragment or len(target) > MAX_CURSOR + 512:
                raise ValueError('closed activity read target required')
            if parsed.path == BASE:
                return 200, self.capability(token)
            if not parsed.path.startswith(BASE + '/'):
                return 404, {'contract_version': CONTRACT, 'error': {'code': 'ACTIVITY_ROUTE_MISSING'}}
            parts = parsed.path[len(BASE) + 1:].split('/')
            if len(parts) not in (2, 3):
                raise ValueError('closed activity route')
            workset_id = identifier(parts[0])
            if parts[1] == 'pages':
                return self.read(token, workset_id, cursor=parts[2] if len(parts) == 3 else None)
            if parts[1] == 'events' and len(parts) == 3:
                if len(parts[2]) != 64 or any(c not in '0123456789abcdef' for c in parts[2]):
                    raise ValueError('event identity')
                return self.read(token, workset_id, event_id=parts[2])
            raise ValueError('closed activity route')
        except PermissionError:
            return 403, {'contract_version': CONTRACT, 'error': {'code': 'ACTIVITY_SCOPE_DENIED'}}
        except ActivityResync:
            return 409, {'contract_version': CONTRACT, 'error': {'code': 'RESYNC_REQUIRED'},
                         'completeness': 'PARTIAL', 'read_only': True}
        except ActivityUnavailable as error:
            code = str(error) if str(error) in {'RESYNC_REQUIRED', 'HISTORY_PARTIAL_CAPACITY',
                                               'HISTORY_SOURCE_INVALID', 'HISTORY_SOURCE_UNAVAILABLE'} else 'HISTORY_SOURCE_UNAVAILABLE'
            return 409 if code == 'RESYNC_REQUIRED' else 503, {
                'contract_version': CONTRACT, 'error': {'code': code}, 'completeness': 'PARTIAL', 'read_only': True}
        except (OSError, KeyError, TypeError, RuntimeError):
            return 503, {'contract_version': CONTRACT, 'error': {'code': 'ACTIVITY_UNAVAILABLE'},
                         'completeness': 'PARTIAL', 'read_only': True}
        except ValueError:
            return 400, {'contract_version': CONTRACT, 'error': {'code': 'ACTIVITY_REQUEST_INVALID'}, 'read_only': True}
