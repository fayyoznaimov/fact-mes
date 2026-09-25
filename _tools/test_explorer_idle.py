"""Разбор простоев и обход смены видят станок, простоявший всю смену: FACT
пишет его простой по причинам (25.09, смена A: J10 — «прочее» 457 мин и 23 мин
без питания), а раньше строки с работой ≤ 5 мин отбрасывались."""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_app"))
import ingest
import reports
import storage

J14 = ("shift 2026.09.25.0,mac_name J14,style 350,cloth 70135J156360,seisan 182.3 105.5 115.3 1,"
       "run_tm 367.617,stop_ttm 112.383,stop_ct 9 7 4 0 0 55 0 0 14 0 0 0 3,"
       "stop_tm 22.500 18.250 2.333 0 0 50.567 0 0 15.300 0 0 0 3.433,stop_wtm 0 0 0 0 0 0 0 0 0 0 0 0 0")
J10 = ("shift 2026.09.25.0,mac_name J10,style 650,cloth 200100TC%20390,seisan 0.0 0.0 0.0 0,"
       "run_tm 0.000,stop_ttm 456.950,stop_ct 0 0 0 0 0 0 0 0 0 0 0 0 0,"
       "stop_tm 0 0 0 0 0 0 0 0 0 23.033 456.950 0 0,stop_wtm 0 0 0 0 0 0 0 0 0 0 0 0 0")

D2 = ("shift 2026.09.25.0,mac_name D2,style Towel,cloth 70140D152500,seisan 0.0 0.2 0.2 0,"
      "run_tm 0.000,stop_ttm 290.383,stop_ct 0 0 0 0 0 0 0 0 0 0 0 0 0,"
      "stop_tm 0 0 0 0 0 0 290.383 0 0 0 0 0 0,stop_wtm 0 0 0 0 0 0 0 0 0 0 0 0 0")


class ExplorerIdleTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.old = storage.FACT_DB
        storage.FACT_DB = os.path.join(self.dir.name, "fact.db")
        db = sqlite3.connect(storage.FACT_DB)
        db.executescript(ingest.SHIFT_SCHEMA)
        rows = ingest.shift_rows("2026.09.25.0", "\n".join((J14, J10, D2)))
        db.executemany("INSERT INTO shift_full VALUES (%s)" % ",".join("?" * len(rows[0])), rows)
        db.commit()
        db.close()

    def tearDown(self):
        storage.FACT_DB = self.old
        self.dir.cleanup()

    def test_explorer_counts_idle_loom(self):
        d = reports.explorer({"from": "2026.09.25", "to": "2026.09.25"})
        looms = {r["loom"]: r for r in d["by_loom"]}
        self.assertIn("J10", looms)
        self.assertEqual((looms["J10"]["eff"], looms["J10"]["idle_shifts"]), (0, 1))
        self.assertEqual((looms["J10"]["other_h"], looms["J10"]["power_h"]), (7.6, 0.4))
        self.assertEqual(d["totals"]["idle_shifts"], 2)
        self.assertEqual(d["totals"]["stop_h"], round((112.383 + 456.95 + 290.383) / 60))
        # Категория 6 FACT — сход навоя, не «прочее».
        self.assertEqual((looms["D2"]["warp_out_h"], looms["D2"]["other_h"]), (4.8, 0))
        self.assertEqual(d["causes"]["Сход навоя"], 4.8)
        self.assertEqual(d["causes"]["Прочее"], round((456.95 + 3.433) / 60, 1))

    def test_walk_shows_idle_loom(self):
        rows = {r["loom"]: r for r in reports.walk("2026.09.25", "A")["rows"]}
        self.assertTrue(rows["J10"]["idle"])
        self.assertEqual((rows["J10"]["main"], rows["J10"]["main_min"]), ("прочее", 457))
        self.assertFalse(rows["J14"]["idle"])
        self.assertEqual((rows["D2"]["main"], rows["D2"]["main_min"]), ("сход навоя", 290))

    def test_payroll_rows_still_skip_idle(self):
        self.assertEqual([r["loom"] for r in reports.shift_rows("2026.09.25", "A")], ["J14"])


if __name__ == "__main__":
    unittest.main()
