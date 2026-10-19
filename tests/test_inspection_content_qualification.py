"""Loss evidence detector must receive a full successful response before dropping it."""
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
import json
import unittest
import subprocess
import sys
from tempfile import TemporaryDirectory
from hashlib import sha256

spec=spec_from_file_location('r59_qualification',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_installed_inspection_content.py')
qualification=module_from_spec(spec);spec.loader.exec_module(qualification)

class CompleteSuccessLossTests(unittest.TestCase):
    def test_original_fault_output_retained_exactly_but_private_unexpected_output_rejected(self):
        detector="assert False, 'revoked-role-approval-detector'"
        red=subprocess.run([sys.executable,'-I','-c',detector],capture_output=True)
        green=subprocess.run([sys.executable,'-I','-c','pass'],capture_output=True)
        with TemporaryDirectory() as name:
            output=Path(name)
            args={'binding':{'source_revision':'synthetic-fixture'},'detector':detector,'original':b'original','mutation':b'mutation'}
            receipt=qualification.retain_fault(output,'RED',red,**args)
            retained=json.loads((output/receipt['file']).read_text())
            self.assertEqual(retained['original_stderr_text'].encode(),red.stderr)
            self.assertEqual(retained['original_stderr_sha256'],sha256(red.stderr).hexdigest())
            self.assertEqual(sha256((output/receipt['file']).read_bytes()).hexdigest(),receipt['sha256'])
            qualification.retain_fault(output,'GREEN',green,restored=True,**args)
            with self.assertRaises(RuntimeError):qualification.retain_fault(output,'RED',red,**args)
        for stdout,stderr in [(b'private',red.stderr),(b'',red.stderr+b'Bearer private\n'),(b'',b'OtherError\n')]:
            with TemporaryDirectory() as name:
                fake=subprocess.CompletedProcess([],1,stdout,stderr)
                with self.assertRaises(RuntimeError):qualification.retain_fault(Path(name),'RED',fake,**args)
                self.assertEqual(list(Path(name).iterdir()),[])

    def test_full_success_loss_and_incomplete_or_failed_response_rejected(self):
        class Peer(BaseHTTPRequestHandler):
            status=200
            truncated=False
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                raw=json.dumps({'original_decision':{'decision_id':'synthetic-decision','request':{'operation_id':'original'}}}).encode()
                self.send_response(self.status)
                self.send_header('Content-Length',str(len(raw)+(1 if self.truncated else 0)))
                self.end_headers();self.wfile.write(raw);self.close_connection=True
            def log_message(self,*_):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Peer)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            value=qualification.lose_complete_success(server.server_port,{}, {'operation_id':'original'})
            self.assertEqual(value['success_status'],200)
            self.assertEqual(value['received_bytes'],value['full_content_length'])
            self.assertEqual(value['decision_id'],'synthetic-decision')
            Peer.truncated=True
            with self.assertRaises(AssertionError):qualification.lose_complete_success(server.server_port,{}, {'operation_id':'original'})
            Peer.truncated=False;Peer.status=503
            with self.assertRaises(AssertionError):qualification.lose_complete_success(server.server_port,{}, {'operation_id':'original'})
        finally:server.shutdown();thread.join(3);server.server_close()
