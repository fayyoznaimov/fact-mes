"""Проверка передачи JSON и ключа 1С только на временных loopback-серверах."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_deploy"))
from windows_1c_relay import RelayServer


class Echo(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        self.server.seen = (self.path, body, self.headers.get('Authorization'))
        self.send_response(202)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', '11')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *args):
        pass


class RelayTests(unittest.TestCase):
    def test_routes_and_payload(self):
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Echo)
        relay = RelayServer(('127.0.0.1', 0), 'http://127.0.0.1:%d' % upstream.server_port)
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (upstream, relay)]
        for thread in threads:
            thread.start()
        try:
            for method, path, body, headers, expected in [
                ('POST', '/api/v1/1c?source=test', b'{"order":1708}', {'Authorization':'Bearer synthetic-test'}, 202),
                ('GET', '/#plan', None, {}, 307),
                ('POST', '/api/users', b'{}', {}, 410),
                ('POST', '/api/v1/1c', b'', {'Content-Length':'-1'}, 400),
                ('POST', '/api/v1/1c', b'', {'Content-Length':'99999999'}, 413),
            ]:
                with self.subTest(method=method, path=path, expected=expected):
                    conn = http.client.HTTPConnection('127.0.0.1', relay.server_port, timeout=5)
                    conn.request(method, path, body, headers)
                    response = conn.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                    conn.close()
            self.assertEqual(upstream.seen, ('/api/v1/1c?source=test', b'{"order":1708}', 'Bearer synthetic-test'))
        finally:
            for server in (relay, upstream):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(5)


if __name__ == '__main__':
    unittest.main()
