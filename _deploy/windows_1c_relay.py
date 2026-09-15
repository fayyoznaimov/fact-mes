"""Сохранение старого URL 1С после переноса MES на Linux.

Передаёт только /api/v1/1c, включая исходный Authorization. GET остальных
страниц направляет браузер в Linux. Ни базы, ни Toyota здесь не читаются.
Пароли, ключи, тела запросов и query string в журнал не записываются.
"""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit

MAX_BODY = 5 * 1024 * 1024
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length"}
LOG = logging.getLogger("mes-relay")


class Relay(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def reply(self, status, message, location=None):
        payload = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if location:
            self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def forward(self):
        if not self.path.startswith("/") or self.path.startswith("//"):
            return self.reply(400, "Invalid request path")
        path = urlsplit(self.path).path
        if path != "/api/v1/1c":
            if self.command == "GET":
                return self.reply(307, "MES moved to Linux", self.server.target + self.path)
            return self.reply(410, "MES moved to " + self.server.target + "; reload the application")
        lengths = self.headers.get_all("Content-Length") or []
        if self.headers.get("Transfer-Encoding") or len(lengths) > 1:
            return self.reply(400, "Use a single Content-Length without Transfer-Encoding")
        raw = lengths[0].strip() if lengths else "0"
        if not raw.isascii() or not raw.isdigit():
            return self.reply(400, "Invalid Content-Length")
        if len(raw) > 10:
            return self.reply(413, "Payload too large")
        length = int(raw)
        if length > MAX_BODY:
            return self.reply(413, "Payload too large")
        self.connection.settimeout(60)
        connection = http.client.HTTPConnection(self.server.upstream.hostname,
                                               self.server.upstream.port or 80, timeout=180)
        started_response = False
        try:
            body = self.rfile.read(length) if length else b""
            if len(body) != length:
                return self.reply(400, "Incomplete request body")
            excluded = HOP | {v.strip().lower() for v in self.headers.get("Connection", "").split(",")}
            headers = {k: v for k, v in self.headers.items() if k.lower() not in excluded}
            headers["Content-Length"] = str(length)
            headers["Connection"] = "close"
            connection.request(self.command, self.path, body, headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            started_response = True
            self.wfile.write(payload)
            LOG.info("1C %s status=%s bytes=%s", self.command, response.status, length)
        except (OSError, http.client.HTTPException) as exc:
            LOG.error("Upstream connection error: %s", type(exc).__name__)
            if not started_response:
                self.reply(502, "MES upstream is temporarily unavailable")
        finally:
            self.close_connection = True
            connection.close()


class RelayServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, address, target):
        self.target = target.rstrip("/")
        self.upstream = urlsplit(self.target)
        if self.upstream.scheme != "http" or not self.upstream.hostname or self.upstream.path:
            raise ValueError("Target must be an HTTP origin without a path")
        super().__init__(address, Relay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="172.0.30.107")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--target", default="http://172.0.30.4:8780")
    parser.add_argument("--log", required=True)
    args = parser.parse_args()
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(args.log, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.info("Relay starting: %s:%s -> %s", args.listen, args.port, args.target)
    RelayServer((args.listen, args.port), args.target).serve_forever()
