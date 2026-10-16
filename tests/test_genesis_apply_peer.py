"""Causal transport boundary tests; fake sockets are not installed EP evidence."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from forge.genesis_apply_peer import exchange
from forge.ep_inspection_peer import PeerError
from forge.project_bootstrap.schema import canonical
from forge.project_bootstrap.service import digest


class GenesisPeerDeadlineTests(TestCase):
    def setUp(self):
        self.clock = 0
        self.request = {'operation_id':'original'}
        self.pairing = {'endpoint':'http://127.0.0.1:8765', 'credential':'synthetic-private',
            'request_digest':digest(canonical(self.request)), 'binding':{'operation_id':'original',
            'instance_id':'ep-test','host_id':'a'*64,'consumer_id':'forge','principal':'owner'}}
        self.connection = MagicMock(); self.response = MagicMock(status=200)
        self.connection.getresponse.return_value = self.response
        self.response.read.side_effect = [b'{}\n',b'']
        self.factory = patch('forge.genesis_apply_peer.http.client.HTTPConnection', return_value=self.connection)
        self.factory.start(); self.addCleanup(self.factory.stop)
        self.time = patch('forge.genesis_apply_peer.time.monotonic', side_effect=lambda:self.clock)
        self.time.start(); self.addCleanup(self.time.stop)
        self.timer = patch('forge.genesis_apply_peer.Timer'); self.timer.start(); self.addCleanup(self.timer.stop)

    def test_late_connect_does_not_send_effect(self):
        self.connection.connect.side_effect = lambda:setattr(self,'clock',31)
        with self.assertRaisesRegex(PeerError,'DEADLINE_EXCEEDED'):
            exchange(self.pairing,'POST',body=self.request,before_send=lambda _:None)
        self.connection.request.assert_not_called()
        self.connection.close.assert_called_once()

    def test_late_complete_response_is_not_success_even_if_watchdog_has_not_run(self):
        def read(_):
            self.clock = 31
            return b'{}\n' if self.response.read.call_count == 1 else b''
        self.response.read.side_effect = read
        with self.assertRaisesRegex(PeerError,'DEADLINE_EXCEEDED'):
            exchange(self.pairing,'GET')
        self.connection.request.assert_called_once()

    def test_current_authority_failure_after_connect_sends_no_post(self):
        def revoked(_): raise PermissionError('current grant revoked')
        with self.assertRaises(PermissionError):
            exchange(self.pairing,'POST',body=self.request,before_send=revoked)
        self.connection.connect.assert_called_once(); self.connection.request.assert_not_called()
        self.connection.close.assert_called_once()

    def test_post_without_current_authority_callback_or_rebound_request_is_refused(self):
        with self.assertRaises(ValueError): exchange(self.pairing,'POST',body=self.request)
        with self.assertRaises(ValueError): exchange(self.pairing,'POST',body={'operation_id':'other'},before_send=lambda _:None)
        self.connection.request.assert_not_called()

    def test_http_refusal_is_typed_and_never_redirected_or_retried(self):
        self.response.status = 302
        with self.assertRaisesRegex(PeerError,'HTTP_302'):
            exchange(self.pairing,'GET')
        self.connection.request.assert_called_once()

    def test_one_explicit_resume_uses_original_path_no_new_body(self):
        result = exchange(self.pairing,'POST',resume=True,before_send=lambda _:None)
        self.assertEqual(result,b'{}\n')
        args, kwargs = self.connection.request.call_args
        self.assertEqual(args,('POST','/v1/bootstrap/genesis/operations/original/resume'))
        self.assertIsNone(kwargs['body'])
        self.assertEqual(kwargs['headers']['EP-Audience'],'genesis-bootstrap')
        self.assertEqual(self.connection.request.call_count,1)

    def test_actual_http_resume_obeys_owning_zero_length_body_guard(self):
        from http.server import BaseHTTPRequestHandler,HTTPServer
        from threading import Thread
        observed={}
        class StrictSyntheticResume(BaseHTTPRequestHandler):
            def do_POST(self):
                observed.update(path=self.path,length=self.headers.get('Content-Length'))
                raw=b'{"synthetic_original":true}\n'
                self.send_response(200 if observed['length']=='0' else 400)
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*args):pass
        server=HTTPServer(('127.0.0.1',0),StrictSyntheticResume)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            pairing={**self.pairing,'endpoint':'http://127.0.0.1:'+str(server.server_port)}
            # Use actual stdlib connection/clock, not the fixture transport mocks.
            self.factory.stop();self.time.stop();self.timer.stop()
            raw=exchange(pairing,'POST',resume=True,before_send=lambda _:None)
            self.assertEqual(raw,b'{"synthetic_original":true}\n')
            self.assertEqual(observed,{'path':'/v1/bootstrap/genesis/operations/original/resume','length':'0'})
        finally:
            server.shutdown();thread.join(3);server.server_close()
