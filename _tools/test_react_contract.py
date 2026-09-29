"""Реальный HTTP-контракт пилотного интерфейса: SQLite, сессия, отчёт, простои."""
from contextlib import ExitStack
import http.client
import io
import json
import threading
import unittest
import zipfile

from react_sandbox import sandbox
import auth


class ReactContractTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.server, self.token = self.stack.enter_context(sandbox(port=0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=3)

    def request(self, path, token=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Cookie"] = "sid=" + token
        try:
            c.request("POST" if body is not None else "GET", path,
                      json.dumps(body) if body is not None else None, headers)
            r = c.getresponse()
            data = r.read()
            return r.status, json.loads(data) if r.getheader("Content-Type", "").startswith("application/json") else data
        finally:
            c.close()

    def test_authenticated_report_retains_null_and_loom_filter_limits_causes(self):
        self.assertEqual(self.request("/api/report?day=2026.09.25")[0], 401)
        code, data = self.request("/api/report?day=2026.09.25", self.token)
        self.assertEqual(code, 200)
        self.assertEqual(len(data["rows"]), 8)
        self.assertIsNone(next(r for r in data["rows"] if r["loom"] == "J2")["achieved_kg"])
        code, data = self.request("/api/explorer?from=2026.09.25&to=2026.09.25&looms=J14", self.token)
        self.assertEqual(code, 200)
        self.assertEqual([r["loom"] for r in data["by_loom"]], ["J14"])
        self.assertGreater(data["causes"]["Уток"], 0)

    def test_report_permission_does_not_grant_downtime_or_export(self):
        auth.create_user("reporter", "Отчёт", "viewer", "test-password", access={"sections": ["report"], "permissions": []})
        token = auth.login("reporter", "test-password")
        self.assertEqual(self.request("/api/report?day=2026.09.25", token)[0], 200)
        self.assertEqual(self.request("/api/explorer?from=2026.09.25&to=2026.09.25", token)[0], 403)
        self.assertEqual(self.request("/api/export_excel", token, {"day": "2026.09.25"})[0], 403)

    def test_export_builds_only_a_synthetic_workbook_inside_sandbox(self):
        self.assertEqual(self.request("/api/export_excel", self.token, {"day": "2026.09.25"}), (200, {"ok": True}))
        code, data = self.request("/api/excel?day=2026.09.25", self.token)
        self.assertEqual(code, 200)
        with zipfile.ZipFile(io.BytesIO(data)) as book:
            self.assertIn("xl/worksheets/sheet1.xml", book.namelist())

    def test_setup_document_rebuilds_report_and_export_in_temporary_databases(self):
        payload = {"from_day": "2026.09.24", "effective_at": "2026-09-24T07:00:00+05:00",
                   "rows": [{"loom": "D1", "values": {"ppt": "3300", "weight_kg": "0,635",
                             "panels": "2", "design": "D327", "pile_yarn": "20/2", "pile_lot": "TEST"}}]}
        code, preview = self.request("/api/documents/preview", self.token, {"type": "setup", "payload": payload})
        self.assertEqual(code, 200, preview)
        self.assertEqual(preview["errors"], [], preview)
        code, posted = self.request("/api/documents/post", self.token,
                                    {"type": "setup", "payload": payload, "checksum": preview["checksum"], "comment": "Synthetic test"})
        self.assertEqual(code, 200, posted)
        self.assertFalse(posted.get("after", {}).get("after_error"), posted)
        self.assertEqual(posted["after"]["days"], ["2026.09.24", "2026.09.25"])
        code, report = self.request("/api/report?day=2026.09.24", self.token)
        self.assertEqual(code, 200)
        row = next(r for r in report["rows"] if r["loom"] == "D1")
        self.assertEqual(row["ppt"], 3300)
        self.assertEqual(row["weight_kg"], .635)
        self.assertEqual(row["setup"]["pile_lot"], "TEST")
        self.assertGreater(row["achieved_kg"], 0)
        self.assertEqual(self.request("/api/export_excel", self.token, {"day": "2026.09.24"})[0], 200)

    def test_report_only_user_cannot_preview_or_post_setup(self):
        auth.create_user("read_only", "Отчёт", "viewer", "test-password", access={"sections": ["report"], "permissions": []})
        token = auth.login("read_only", "test-password")
        body = {"type": "setup", "payload": {"from_day": "2026.09.24", "rows": []}}
        for path in ("/api/documents/preview", "/api/documents/post"):
            self.assertEqual(self.request(path, token, body)[0], 403)

    def test_period_approval_is_stored_and_can_be_verified(self):
        payload = {"from": "2026.09.24", "to": "2026.09.25"}
        code, preview = self.request("/api/documents/preview", self.token, {"type": "report", "payload": payload})
        self.assertEqual((code, preview["errors"]), (200, []))
        code, posted = self.request("/api/documents/post", self.token,
            {"type": "report", "payload": payload, "checksum": preview["checksum"], "comment": "React period test"})
        self.assertEqual(code, 200, posted)
        code, document = self.request("/api/documents/get?id=" + str(posted["id"]), self.token)
        self.assertEqual(code, 200)
        self.assertEqual(document["status"], "posted")
        self.assertEqual(document["result"]["totals"]["kg"], preview["result"]["totals"]["kg"])
        code, verified = self.request("/api/documents/verify?id=" + str(posted["id"]), self.token)
        self.assertEqual((code, verified["same"]), (200, True))


if __name__ == "__main__":
    unittest.main()
