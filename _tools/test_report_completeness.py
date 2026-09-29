"""Неполные отчёты: синтетические смены в временной SQLite, без сети и рабочих БД."""
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_app"))
import ingest
import make_excel_report
import reports
import storage

DAY = "2026.09.25"
NEXT = "2026.09.26"


class ReportCompletenessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="fact_report_test_")
        self.addCleanup(temp.cleanup)
        self.path = str(Path(temp.name) / "fact.db")
        p = patch.object(storage, "FACT_DB", self.path)
        p.start()
        self.addCleanup(p.stop)
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(ingest.SHIFT_SCHEMA)
            db.executescript(make_excel_report.SCHEMA)

    def shift(self, loom="J1", day=DAY, pieces=10, letter="A"):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO shift_full(shift,day,letter,loom,run_min,stop_min,picks,pieces)"
                       " VALUES(?,?,?,?,400,80,100000,?)",
                       (day + "." + str("ABC".index(letter)), day, letter, loom, pieces))
            db.commit()

    def daily(self, loom="J1", day=DAY, kg=10, panels=2):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO report_daily(day,loom,achieved_kg,panels) VALUES(?,?,?,?)",
                       (day, loom, kg, panels))
            db.commit()

    def report(self):
        return reports.report_period(DAY, NEXT)

    def test_missing_loom_is_detected_even_when_another_loom_has_daily_report(self):
        self.shift("J1")
        self.shift("J2")
        self.daily("J1")
        result = self.report()
        self.assertEqual(result["days_without_report"], [DAY])
        self.assertEqual(result["missing_reports"], [{"day": DAY, "loom": "J2"}])
        self.assertEqual(result["totals"]["kg"], 10)
        self.assertEqual(result["totals"]["quality"]["kg"]["status"], "partial")
        rows = {r["loom"]: r for r in result["rows"]}
        self.assertIsNone(rows["J2"]["kg"])

    def test_unavailable_production_is_not_zero(self):
        self.shift()
        self.daily(kg=None, panels=None)
        result = self.report()
        self.assertIsNone(result["totals"]["kg"])
        self.assertIsNone(result["totals"]["towels"])
        self.assertEqual(result["totals"]["quality"]["kg"]["status"], "unavailable")
        self.assertEqual(result["missing_reports"], [])
        self.assertEqual([(r["day"], r["loom"]) for r in result["uncalculated_kg"]], [(DAY, "J1")])

    def test_known_zero_remains_complete(self):
        self.shift(pieces=0)
        self.daily(kg=0)
        result = self.report()
        self.assertEqual(result["totals"]["kg"], 0)
        self.assertEqual(result["totals"]["towels"], 0)
        self.assertEqual(result["totals"]["quality"]["kg"]["status"], "complete")
        self.assertEqual(result["uncalculated_kg"], [])

    def test_partial_loom_retains_known_subtotal_with_day_coverage(self):
        self.shift()
        self.daily(kg=12.5)
        self.shift(day=NEXT)
        self.daily(day=NEXT, kg=None, panels=None)
        result = self.report()
        row = result["rows"][0]
        self.assertEqual((row["kg"], row["towels"]), (12.5, 20))
        self.assertEqual(row["quality"]["kg"],
                         {"status": "partial", "known": 1, "total": 2, "value": 12.5})
        self.assertFalse(row["towels_known"])

    def test_daily_kg_is_not_repeated_for_each_shift(self):
        self.shift()
        self.shift(letter="B", pieces=5)
        self.daily(kg=15)
        self.shift(day=NEXT, pieces=4)
        self.daily(day=NEXT, kg=7, panels=3)
        result = self.report()
        self.assertEqual((result["totals"]["kg"], result["totals"]["towels"]), (22, 42))
        self.assertEqual(result["totals"]["quality"]["kg"]["total"], 2)
        self.assertEqual(result["totals"]["quality"]["kg"]["status"], "complete")

    def test_idle_loom_with_zero_rows_does_not_require_panels_for_zero_towels(self):
        self.shift(pieces=0)
        self.daily(kg=None, panels=None)
        result = self.report()
        self.assertEqual(result["totals"]["towels"], 0)
        self.assertEqual(result["totals"]["quality"]["towels"]["status"], "complete")
        self.assertIsNone(result["totals"]["kg"])

    def test_empty_period_is_unavailable_not_a_measured_zero(self):
        result = self.report()
        self.assertEqual(result["rows"], [])
        self.assertIsNone(result["totals"]["kg"])
        self.assertEqual(result["totals"]["quality"]["kg"]["status"], "unavailable")

    def test_invalid_period_is_rejected(self):
        for start, end in ((NEXT, DAY), ("bad", DAY), (DAY, "2028.09.25")):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                reports.report_period(start, end)


if __name__ == "__main__":
    unittest.main()
