"""HTTP-раздача React: временные файлы, loopback; рабочие БД не открываются."""
import http.client
import logging
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_app"))
import frontend
import logs
with patch.object(logs, "get", lambda name: logging.getLogger("frontend_test." + name)):
    import web


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fact_frontend_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p = patch.object(frontend, "DIST", self.root)
        p.start()
        self.addCleanup(p.stop)
        (self.root / "assets").mkdir()
        (self.root / ".vite").mkdir()
        (self.root / ".vite/manifest.json").write_text('{"index.html":{"file":"assets/main-123.js"}}')
        (self.root / "index.html").write_text('<html><script src="/next/assets/main-123.js"></script></html>')
        (self.root / "assets/main-123.js").write_text('console.log("test")')
        self.server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            c.request("GET", path)
            r = c.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            c.close()

    def test_index_and_assets_have_correct_mime_and_security_headers(self):
        for path, mime in (("/next/", "text/html"), ("/next/assets/main-123.js", "text/javascript")):
            code, headers, body = self.request(path)
            self.assertEqual(code, 200)
            self.assertTrue(headers["Content-Type"].startswith(mime))
            self.assertEqual(headers["Cache-Control"], "no-cache")
            self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
            self.assertTrue(body)
            if mime == "text/html":
                self.assertTrue(body.startswith(frontend.SHELL.read_bytes()))
                self.assertIn(b'id="rep-table"', body)
                self.assertIn(b'id="ls-dlg"', body)
                self.assertIn(b'/next/assets/main-123.js', body)

    def test_traversal_and_unknown_files_are_rejected(self):
        for path in ("/next/../web.py", "/next/%2e%2e/web.py", "/next/assets/../../web.py",
                     "/next/assets%5c..%5cweb.py", "/next/package.json", "/next/assets/missing.js"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_missing_build_is_explicit_and_legacy_page_still_works(self):
        (self.root / "index.html").unlink()
        self.assertEqual(self.request("/next/")[0], 503)
        self.assertEqual(self.request("/")[0], 200)

    def test_canonical_path_redirect(self):
        code, headers, _ = self.request("/next")
        self.assertEqual((code, headers["Location"]), (308, "/next/"))


if __name__ == "__main__":
    unittest.main()
