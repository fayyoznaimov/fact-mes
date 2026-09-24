"""Обороты в производственном отчёте — скорость станка из снимков FACT.

Самое частое Rpm, пока станок работает, за сутки отчёта 07:00 — 07:00.
Остановленный станок и снимки вне суток не учитываются; без снимков — пусто."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zlib
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_excel_report as mer

TZ = timezone(timedelta(hours=5))


def blob(looms):
    return zlib.compress(json.dumps(looms).encode())


class RunningSpeedTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.dir.name, "shop.db")
        self.old = mer.SHOP_DB
        mer.SHOP_DB = self.db
        db = sqlite3.connect(self.db)
        db.execute("CREATE TABLE machine_sample (snapshot TEXT PRIMARY KEY, at INTEGER NOT NULL,"
                   " received_at TEXT NOT NULL, data BLOB NOT NULL)")
        start = datetime(2026, 9, 23, 7, 0, tzinfo=TZ)
        rows = []
        for m in range(0, 24 * 60, 10):           # раз в 10 минут, сутки отчёта
            at = start + timedelta(minutes=m)
            j7 = {"running": True, "rpm": 530 if m % 60 else 528}   # разгон — редкое значение
            d3 = {"running": False, "rpm": 0}
            rows.append((str(m), int(at.timestamp()), "", blob({"J7": j7, "D3": d3})))
        # до начала суток отчёта — не считается
        early = int((start - timedelta(hours=1)).timestamp())
        rows.append(("early", early, "", blob({"J7": {"running": True, "rpm": 400}})))
        db.executemany("INSERT INTO machine_sample VALUES (?,?,?,?)", rows)
        db.commit()
        db.close()

    def tearDown(self):
        mer.SHOP_DB = self.old
        self.dir.cleanup()

    def test_most_common_running_rpm(self):
        speed = mer.running_speed("2026.09.23", stride=1)
        self.assertEqual(speed, {"J7": 530})      # D3 стоял — скорости нет

    def test_no_archive(self):
        os.remove(self.db)
        self.assertEqual(mer.running_speed("2026.09.23"), {})


if __name__ == "__main__":
    unittest.main()
