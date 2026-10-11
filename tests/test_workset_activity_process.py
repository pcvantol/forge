"""Real cold readers and lost HTTP bodies; read authority never survives revocation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import socket
import subprocess
import unittest

from workset_order_fixture import order_case
from workset_activity_fixture import setup, call, all_counts
from test_workset_order_process import child
from forge.workspace_review_grant import _write_private
from forge.workset_activity_service import BASE


class ActivityProcessTests(unittest.TestCase):
    def test_cold_process_and_supported_cli_resume_same_checkpoint(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'cold') as case:
            setup(case); status, first = call(case); self.assertEqual(status, 200, first)
            packet = case['root'] / 'activity-page.private.json'; _write_private(packet, json.dumps(first).encode())
            before = all_counts(case)
            path = BASE + '/' + case['key'] + '/pages/' + first['cursor']
            for _ in range(2):
                result = subprocess.run(child(case['root'], 'activity', token='activity.private') +
                    ['--activity-path', path], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                value = json.loads(result.stdout)['output']; self.assertEqual(value['events'], [])
                self.assertEqual(value['cursor'], first['cursor'])
            result = subprocess.run(child(case['root'], 'activity-cli', token='activity.private') +
                ['--cursor-file', str(packet)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['events'], [])
            self.assertEqual(all_counts(case), before)

    def test_real_lost_http_body_and_repeat_read_preserve_every_runtime_table(self):
        with TemporaryDirectory() as tmp, order_case(Path(tmp) / 'lost') as case:
            setup(case); before = all_counts(case)
            token = (case['root'] / 'activity.private').read_text().strip()
            path = BASE + '/' + case['key'] + '/pages'
            with socket.create_connection(('127.0.0.1', case['port']), timeout=15) as stream:
                stream.sendall(('GET ' + path + ' HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer ' + token +
                                '\r\nConnection: close\r\n\r\n').encode())
                headers = b''
                while b'\r\n\r\n' not in headers:
                    piece = stream.recv(1); self.assertTrue(piece); headers += piece
                self.assertIn(b'200', headers.splitlines()[0])
            status, page = call(case); self.assertEqual(status, 200, page)
            status, again = call(case); self.assertEqual(status, 200, again)
            self.assertEqual(page['events'], again['events']); self.assertEqual(page['cursor'], again['cursor'])
            self.assertEqual(all_counts(case), before)
