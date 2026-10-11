"""Read checkpoints reject mixed snapshots and retain late identities."""
import hashlib
import unittest
from forge.workset_activity_cursor import page, ActivityResync, PAGE_SIZE


def event(n):
    return {'event_id': hashlib.sha256(str(n).encode()).hexdigest(), 'sequence': n}


class ActivityCursorTests(unittest.TestCase):
    def test_fixed_pages_replay_and_complete_continuation_with_late_fact(self):
        key = b'private-fixture-cursor-key'; context = {'workset': 'abc', 'generation': 1}
        events = [event(i) for i in range(PAGE_SIZE + 2)]
        first = page(key, context, events)
        second = page(key, context, events, first['cursor'])
        self.assertEqual(second, page(key, context, events, first['cursor']))
        self.assertFalse(second['has_more'])
        self.assertEqual(second['events'], events[PAGE_SIZE:])
        late = event(-1)
        self.assertEqual(page(key, context, [late] + events, second['cursor'])['events'], [late])
        self.assertEqual(page(key, context, events, second['cursor'])['events'], [])

    def test_context_snapshot_tamper_and_known_fact_change_require_resync(self):
        key = b'private-fixture-cursor-key'; context = {'workset': 'abc', 'generation': 1}
        events = [event(i) for i in range(PAGE_SIZE + 2)]
        first = page(key, context, events)
        for changed_context, changed_events, cursor in (
                ({'workset': 'foreign', 'generation': 1}, events, first['cursor']),
                ({'workset': 'abc', 'generation': 2}, events, first['cursor']),
                (context, events + [event(99)], first['cursor']),
                (context, events, first['cursor'][:-1] + 'x')):
            with self.subTest(context=changed_context):
                with self.assertRaises(ActivityResync):
                    page(key, changed_context, changed_events, cursor)
        done = page(key, context, events, first['cursor'])
        with self.assertRaises(ActivityResync):
            page(key, context, [{**events[0], 'sequence': 999}] + events[1:], done['cursor'])
        with self.assertRaises(ActivityResync):
            page(key, context, events[1:], done['cursor'])
