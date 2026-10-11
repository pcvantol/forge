"""Observe the existing real A/C/B producer chain without replacing its effects."""
from contextlib import redirect_stdout
from importlib.util import spec_from_file_location, module_from_spec
from io import StringIO
from pathlib import Path
from datetime import UTC, datetime, timedelta
import json
import sys
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]
spec = spec_from_file_location('actual_workset_order_chain', SOURCE / 'scripts/qualification/qualify_workset_order_chain.py')
chain = module_from_spec(spec); spec.loader.exec_module(chain)


def flow(root):
    sys.path.insert(0, str(SOURCE / 'tests'))
    from test_mission_concept_readiness import driver
    from forge.workset_activity_grant import main as setup
    from forge.workset_activity_service import BASE
    root = Path(root); ready, _ = driver.cases(); observations = []; checkpoint = None
    key = None; initialized = False; known = {}
    @patch.object(chain.utils.composition.MacOSGeneratedUIDIdentityAdapter, 'resolve', return_value=chain.utils.fixture.IDENTITY)
    def observe(phase, record, _external_os):
        nonlocal key, initialized, checkpoint
        key = record['workset']['definition']['workset_id']
        if not initialized:
            with redirect_stdout(StringIO()) as output:
                code = setup(['--data-root', str(root / 'runtime'), 'issue',
                    '--workset-id', key,
                    '--expires-at', (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
                    '--token-file', str(root / 'activity.private')])
            assert code == 0, output.getvalue(); initialized = True
        with ready.qual.http(root) as port:
            pages = []; seen = set()
            before_provider = (root / 'provider-requests.private.jsonl').read_bytes()
            while True:
                target = BASE + '/' + key + '/pages' + ('/' + checkpoint if checkpoint else '')
                status, page = ready.call(port, root / 'activity.private', 'GET', target)
                assert status == 200, page
                again_status, replay = ready.call(port, root / 'activity.private', 'GET', target)
                assert again_status == 200 and replay['events'] == page['events'] and replay['cursor'] == page['cursor']
                for event in page['events']:
                    assert event['event_id'] not in seen
                    seen.add(event['event_id']); known[event['event_id']] = event
                pages.append(page); checkpoint = page['cursor']
                if not page['has_more']:
                    break
            assert (root / 'provider-requests.private.jsonl').read_bytes() == before_provider
            observations.append({'phase': phase, 'events': [e for p in pages for e in p['events']],
                                 'current': pages[-1]['current'], 'coverage': pages[-1]['coverage']})
    result = chain.flow(root, observe=observe)
    facts = {e['fact'] for e in known.values()}
    assert {'ACTIVATION_CLAIMED', 'ORDER_APPLIED', 'EP_EXECUTION_RESULT',
            'HUMAN_FINAL_ACCEPTANCE_RECORDED', 'MISSION_TRANSITION', 'FORGE_SUBMISSION_SENT', 'EP_SUBMISSION_RECEIPT_RECEIVED'}.issubset(facts), facts
    assert any('FINAL_ACCEPTANCE_REQUIRED' in item['blocking_reasons'] for o in observations for item in o['current']['items'])
    assert sum(e['fact'] == 'ACTIVATION_CLAIMED' for e in known.values()) == 3
    assert sum(e['fact'] == 'HUMAN_FINAL_ACCEPTANCE_RECORDED' for e in known.values()) == 3
    assert result[-1]['governance_decisions'] == 18
    return {'canonical_decisions': result[-1]['governance_decisions'], 'records': result, 'activity_observations': observations, 'unique_activity_events': len(known),
            'read_only_activity': True}
