"""Интервалы состояний станка по снимкам FACT — на последовательностях,
которые FACT отдал 25.09 (16:29:03 и 16:30:03)."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_app"))
import loomstate
import storage

T1, T2 = 1790335743, 1790335803


def st(state, sec, style="Towel"):
    running = state == "Run"
    return {"state": state, "state_sec": sec, "running": running,
            "cause": "Run" if running else state, "style": style}


def snap(t, looms):
    return {"source": "fact", "fact_time": t, "looms": looms}


class LoomStateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.old = storage.SHOP_DB
        storage.SHOP_DB = os.path.join(self.dir.name, "shop.db")
        storage.shop().close()
        loomstate._READY.clear()
        loomstate.catch_up()                 # пустой архив — сразу готово

    def tearDown(self):
        storage.SHOP_DB = self.old
        loomstate._READY.clear()
        self.dir.cleanup()

    def rows(self, loom):
        db = sqlite3.connect(storage.SHOP_DB)
        try:
            return db.execute("SELECT cause, start, start_exact, seen_to FROM loom_state "
                              "WHERE loom=? ORDER BY start", (loom,)).fetchall()
        finally:
            db.close()

    def test_real_minute(self):
        loomstate.record(snap(T1, {"D1": st("Run", 172), "D10": st("Run", 14), "D6": st("Weft", 58),
                                   "D2": st("Power_off", 0, ""), "J10": st("Other", 96730)}))
        loomstate.record(snap(T2, {"D1": st("Run", 232), "D10": st("Run", 9), "D6": st("Run", 52),
                                   "D2": st("Power_off", 0, ""), "J10": st("Other", 96790)}))
        # Одна работа с 16:26:11 — счётчик сходится в обоих снимках.
        self.assertEqual(self.rows("D1"), [("Run", T1 - 172, 1, T2)])
        # «Работа 14 с», затем «работа 9 с»: между снимками был останов — две работы.
        self.assertEqual(self.rows("D10"), [("Run", T1 - 14, 1, T1), ("Run", T2 - 9, 1, T2)])
        self.assertEqual(self.rows("D6"), [("Weft", T1 - 58, 1, T1), ("Run", T2 - 52, 1, T2)])
        # Обесточен: счётчика у FACT нет — начало по первому снимку, не точное.
        self.assertEqual(self.rows("D2"), [("Power_off", T1, 0, T2)])
        # J10 стоит с 24.09 13:36 — тикет открыт в 13:36:55.
        self.assertEqual(self.rows("J10"), [("Other", T1 - 96730, 1, T2)])

    def test_same_snapshot_after_restart_is_skipped(self):
        s = snap(T1, {"D1": st("Run", 172)})
        loomstate.record(s)
        loomstate.record(s)
        loomstate.record(snap(T1 - 60, {"D1": st("Run", 112)}))
        self.assertEqual(self.rows("D1"), [("Run", T1 - 172, 1, T1)])

    def test_gap_bridged_only_by_counter(self):
        gap = 12 * 3600
        loomstate.record(snap(T1, {"J4": st("Other", 47149), "D5": st("Run", 708)}))
        loomstate.record(snap(T1 + gap, {"J4": st("Other", 47149 + gap), "D5": st("Run", 300)}))
        self.assertEqual(self.rows("J4"), [("Other", T1 - 47149, 1, T1 + gap)])
        self.assertEqual(len(self.rows("D5")), 2)          # за 12 часов работа прерывалась

    def test_catch_up_from_archive(self):
        db = storage.shop()
        for t, looms in ((T1, {"D1": st("Run", 172)}), (T2, {"D1": st("Run", 232)})):
            db.execute("INSERT INTO machine_sample VALUES (?,?,?,?)",
                       (str(t), t, "", zlib.compress(json.dumps(looms).encode())))
        db.commit()
        db.close()
        loomstate._READY.clear()
        loomstate.record(snap(T2 + 60, {"D1": st("Run", 292)}))   # до догонки — не пишем
        self.assertEqual(self.rows("D1"), [])
        self.assertEqual(loomstate.catch_up(batch=1), 2)
        loomstate.record(snap(T2 + 60, {"D1": st("Run", 292)}))
        self.assertEqual(self.rows("D1"), [("Run", T1 - 172, 1, T2 + 60)])
        got = loomstate.intervals(T1, T2)["D1"]
        self.assertEqual((got[0]["start"], got[0]["end"], got[0]["exact"]), (T1 - 172, T2 + 60, True))

    def test_current_for_power_off(self):
        loomstate.record(snap(T1, {"D2": st("Power_off", 0, ""), "D1": st("Run", 172)}))
        loomstate.record(snap(T2, {"D2": st("Power_off", 0, ""), "D1": st("Weft", 20)}))
        cur = loomstate.current(["D2"])
        self.assertEqual(list(cur), ["D2"])
        self.assertEqual((cur["D2"]["cause"], cur["D2"]["start"], cur["D2"]["exact"]), ("Power_off", T1, False))
        self.assertEqual(loomstate.current()["D1"]["cause"], "Weft")


if __name__ == "__main__":
    unittest.main()
