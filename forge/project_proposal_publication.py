"""Revalidate each bounded nonblocking send; never hold authority while a client waits."""
import json
import select
import socket
import sqlite3
import time


def publish(handler, grant, authorization, audience, response, payload):
    headers = ('HTTP/1.0 '+str(response.status)+' OK\r\n' + ''.join(k+': '+v+'\r\n' for k,v in response.headers.items()) + 'Content-Length: '+str(len(payload))+'\r\nConnection: close\r\n\r\n').encode('ascii')
    data = headers + payload; offset = 0; deadline = time.monotonic()+5
    handler.close_connection = True
    try:
        while offset < len(data):
            if time.monotonic() >= deadline: raise TimeoutError('bounded publication deadline')
            if not select.select([], [handler.connection], [], min(0.1,max(0,deadline-time.monotonic())))[1]: continue
            try:
                with grant.publication(authorization,audience,response.body):
                    sent = handler.connection.send(data[offset:offset+65536],socket.MSG_DONTWAIT)
            except BlockingIOError: continue
            if sent <= 0: raise ConnectionError('publication interrupted')
            offset += sent
    except PermissionError:
        if offset == 0:
            body=json.dumps({'error':{'code':'PROPOSAL_PUBLICATION_DENIED'}}).encode()
            handler.send_response(403);handler.send_header('Content-Type','application/json');handler.send_header('Content-Length',str(len(body)));handler.send_header('Cache-Control','no-store');handler.end_headers();handler.wfile.write(body)
        # Already sent bytes cannot be withdrawn; incomplete JSON is never a new success.
    except (OSError,ValueError,TypeError,RuntimeError,sqlite3.Error):
        return
