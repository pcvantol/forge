"""Closed consumer contracts for explicit Business Mission end acceptance."""
from __future__ import annotations

import json
from typing import Any

from .advisory_contract import text
from .advisory_candidate_contract import hash_reference
from .approved_worklist import identifier

CONTRACT = 'forge-mission-final-acceptance/v1'
PERMISSIONS = ('READ', 'ACCEPT')
REQUEST_FIELDS = frozenset({
    'contract_version', 'operation_id', 'instance_id', 'project_id',
    'repository_id', 'mission_id', 'package_digest', 'reason', 'confirm',
})


def acceptance_request(value: object) -> dict[str, Any]:
    """Confirm the exact server-derived package; never accept caller authority."""
    if (not isinstance(value, dict) or set(value) != REQUEST_FIELDS
            or value['contract_version'] != CONTRACT or value['confirm'] is not True):
        raise ValueError('closed explicit Mission final-acceptance request required')
    for field in ('operation_id', 'instance_id', 'project_id', 'repository_id', 'mission_id'):
        identifier(value[field])
    hash_reference(value['package_digest'])
    text(value['reason'], 1000)
    return json.loads(json.dumps(value, sort_keys=True))


def grant_bounds(permissions: object, missions: object, maximum_acceptances: object) -> None:
    """An explicit finite READ/ACCEPT grant has unique exact Mission subjects."""
    if (not isinstance(permissions, (list, tuple)) or not permissions
            or any(not isinstance(p, str) or p not in PERMISSIONS for p in permissions)
            or len(set(permissions)) != len(permissions) or 'READ' not in permissions):
        raise ValueError('separate explicit final-acceptance permissions required')
    if (not isinstance(missions, (list, tuple)) or not 1 <= len(missions) <= 16
            or type(maximum_acceptances) is not int or not 1 <= maximum_acceptances <= 16):
        raise ValueError('finite typed final-acceptance scope and allowance required')
    seen = set()
    for mission in missions:
        if not isinstance(mission, dict) or set(mission) != {'mission_id', 'subject_revision'}:
            raise ValueError('exact Mission subject scope required')
        identifier(mission['mission_id'])
        text(mission['subject_revision'], 512)
        if mission['mission_id'] in seen:
            raise ValueError('duplicate final-acceptance Mission scope')
        seen.add(mission['mission_id'])
