"""Owning READ setup and measurement helpers, no positive records inserted."""
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
import json
import re

from forge.workset_activity_grant import main as grant_cli
from forge.workset_activity_service import BASE
from pathlib import Path
from jsonschema import Draft202012Validator
SCHEMA = Draft202012Validator(json.loads((Path(__file__).resolve().parents[1] / "forge/api/workset-activity-v1.json").read_text()))
from workset_order_fixture import counts


def setup(case):
    with redirect_stdout(StringIO()) as output:
        code = grant_cli(['--data-root', str(case['grant'].root), 'issue',
            '--workset-id', case['key'], '--expires-at', (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
            '--token-file', str(case['root'] / 'activity.private')])
    assert code == 0, output.getvalue()
    return json.loads(output.getvalue())


def call(case, suffix='/pages', token='activity.private', method='GET'):
    status, body = case['ready'].call(case['port'], case['root'] / token, method, BASE + '/' + case['key'] + suffix)
    if body.get('contract_version') == 'forge-workset-activity/v1':
        SCHEMA.validate(body)
    return status, body


def all_counts(case):
    result = counts(case); db = case['runtime'].database._connection
    result['all_runtime_tables'] = {}
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        name = row[0]
        assert re.fullmatch('[A-Za-z0-9_]+', name)
        result['all_runtime_tables'][name] = [tuple(r) for r in db.execute('SELECT * FROM ' + name)]
    return result
