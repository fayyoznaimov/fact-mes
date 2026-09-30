"""Локальный просмотр React на синтетических данных, без FACT и рабочих БД.

python _tools/react_sandbox.py
Открыть http://127.0.0.1:8791/preview-login (только временная тестовая сессия).
Это отдельная песочница нового экрана, не замена полного e2e_test.py.
"""
from contextlib import contextmanager, ExitStack, closing
import logging
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_app"))
import storage
import logs
with patch.object(logs, "get", lambda name: logging.getLogger("react_sandbox." + name)), \
        patch.object(storage, "config", return_value={}):
    import web
import auth
import cache
import ingest
import make_excel_report
import metrics
import pptcheck
import reports
import xlsx_report
import fact_api


@contextmanager
def sandbox(port=8791):
    with tempfile.TemporaryDirectory(prefix="fact_react_sandbox_") as directory, ExitStack() as stack:
        root = Path(directory)
        for obj, name, value in ((storage, "SHOP_DB", str(root / "shop.db")),
                                 (storage, "FACT_DB", str(root / "fact.db")),
                                 (reports, "REPORTS_DIR", str(root / "reports")),
                                 (auth, "DB_PATH", str(root / "shop.db"))):
            stack.enter_context(patch.object(obj, name, value))
        # Дополнительные сверки по архиву FACT здесь отсутствуют. Сам дневной отчёт,
        # разбор простоев, сессии и проверка прав проходят через реальные модули.
        stack.enter_context(patch.object(metrics, "ppt_by_cloth", return_value={}))
        stack.enter_context(patch.object(pptcheck, "loom_days", return_value=[]))
        stack.enter_context(patch.object(make_excel_report, "DB", str(root / "fact.db")))
        stack.enter_context(patch.object(make_excel_report, "SHOP_DB", str(root / "shop.db")))
        stack.enter_context(patch.object(make_excel_report, "MIRROR", str(root / "mirror")))
        stack.enter_context(patch.object(make_excel_report, "loom_ppt", return_value={}))
        stack.enter_context(patch.object(fact_api, "get_shift", return_value=[]))
        cache.clear()
        (root / "reports").mkdir()
        with closing(storage.shop()) as db:
            db.execute("INSERT INTO yarn(name,key,kind) VALUES('20/2','20/2','pile')")
            op1 = db.execute("INSERT INTO operator(code,name,role) VALUES('O1','Иванова','operator')").lastrowid
            db.execute("INSERT INTO operator(code,name,role) VALUES('M1','Петрова','master')")
            db.executemany("INSERT INTO assignment(day,shift,loom,operator_id) VALUES(?,?,?,?)",
                           [("2026.09.25", "A", "D1", op1), ("2026.09.25", "A", "D2", op1)])
            db.execute("INSERT INTO shift_master(day,shift,operator_id) VALUES('2026.09.25','A',"
                       "(SELECT id FROM operator WHERE code='M1'))")
            db.commit()
        auth.create_user("preview", "Тестовый мастер", "admin", "local-preview-only", must_change=False)
        token = auth.login("preview", "local-preview-only")
        with closing(sqlite3.connect(storage.FACT_DB)) as db:
            db.executescript(ingest.SHIFT_SCHEMA)
            db.executescript(make_excel_report.SCHEMA)
            # Старый расчёт отчёта читает компактный shift_loom; источник тот же,
            # синтетический shift_full. Пересчёт после заправки выполняется реально.
            db.execute("CREATE VIEW shift_loom AS SELECT *, top_ct AS warp_top_ct, "
                       "picks / 1000.0 AS product_kpick FROM shift_full")
            for day in ("2026.09.25", "2026.09.24"):
                for i, loom in enumerate(("D1", "D2", "D3", "D4", "J1", "J2", "J3", "J14")):
                    db.execute("INSERT INTO report_daily(day,loom,sr,design,rpm,ppt,weight_kg,panels,"
                               "prod100_kg,achieved_kg,eff_total,picks,pile_total,weft_total,ground_total,other_total)"
                               " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (day, loom, i + 1, "D327" if i < 4 else "J156", 480 + i * 5,
                                None if i == 5 else 3200, .25, 2, None if i == 5 else 120,
                                None if i == 5 else 82 + i * 3, 72 + i, 280000 + i * 1000,
                                3 + i, 10 + i, 2, 4))
                    text = (f"shift {day}.0,mac_name {loom},style DEMO,cloth 70135J156360,"
                            "seisan 182.3 105.5 115.3 1,run_tm 360,stop_ttm 120,"
                            "stop_ct 9 7 4 0 0 2 0 0 0 0 0 0 1,"
                            "stop_tm 30 20 10 0 0 50 0 0 0 0 0 0 10,stop_wtm 0 0 0 0 0 0 0 0 0 0 0 0 0")
                    rows = ingest.shift_rows(day + ".0", text)
                    db.executemany("INSERT INTO shift_full VALUES (%s)" % ",".join("?" * len(rows[0])), rows)
            db.commit()

        def export_fixture(day):
            if day not in ("2026.09.25", "2026.09.24"):
                raise ValueError("Нет тестового отчёта за этот день")
            with storage.fact() as db:
                rows = [dict(r) for r in db.execute("SELECT * FROM report_daily WHERE day=?", (day,))]
            for r in rows:
                r.update(weight=r["weight_kg"], achieved=r["achieved_kg"])
            xlsx_report.write_report(day, rows, reports.excel_path(day))
            return {"ok": True}

        stack.enter_context(patch.object(reports, "export_excel", side_effect=export_fixture))

        class PreviewHandler(web.Handler):
            def do_GET(self):
                if self.path == "/preview-login":
                    return self._send(302, b"", "text/plain", {"Location": "/next/#report",
                        "Set-Cookie": f"sid={token}; Path=/; HttpOnly; SameSite=Lax", "Cache-Control": "no-store"})
                path = self.path.split("?", 1)[0]
                if path.startswith("/api/") and path not in ("/api/me", "/api/report_days", "/api/report", "/api/explorer", "/api/excel",
                    "/api/shifts", "/api/operators", "/api/settings", "/api/rates", "/api/reasons", "/api/yarns",
                    "/api/report_period", "/api/documents", "/api/documents/get", "/api/documents/verify", "/api/salary",
                    "/api/shift_doc", "/api/shift_docs", "/api/assignment_periods"):
                    return self._send(403, {"error": "В песочнице доступны только отчёт и простои"})
                return super().do_GET()

            def do_POST(self):
                if self.path not in ("/api/export_excel", "/api/documents/preview", "/api/documents/post",
                    "/api/assign_one", "/api/assign_copy", "/api/shift_doc", "/api/shift_doc/confirm", "/api/shift_doc/fill"):
                    self.close_connection = True
                    return self._send(403, {"error": "Запись в этой песочнице отключена"})
                return super().do_POST()

        server = web.ThreadingHTTPServer(("127.0.0.1", port), PreviewHandler)
        try:
            yield server, token
        finally:
            server.server_close()
            cache.clear()


if __name__ == "__main__":
    with sandbox() as (server, _):
        print("Synthetic preview: http://127.0.0.1:8791/preview-login", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
