"""Эталонный день производственного отчёта (лист TOYOTA): все колонки строки
станка из сменных файлов FACT, минутных снимков и заправки — посчитаны руками.

Правка формулы, которая незаметно меняет число в Excel, ломает этот тест.
J14, смена A — настоящая строка FACT за 25.09; B и C — простые числа; J10 —
простоял весь день (как 25.09)."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zlib
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "_app"))
import ingest
import make_excel_report as mer
import storage

DAY = "2026.09.25"
TZ = timezone(timedelta(hours=5))
ZERO13 = " ".join(["0"] * 13)
SHIFTS = {
    0: ["shift 2026.09.25.0,mac_name J14,style 350,cloth 70135J156360,seisan 182.3 105.5 115.3 1,"
        "run_tm 367.617,stop_ttm 112.383,stop_ct 9 7 4 0 0 55 0 0 14 0 0 0 3,"
        "stop_tm 22.500 18.250 2.333 0 0 50.567 0 0 15.300 0 0 0 3.433,stop_wtm " + ZERO13,
        "shift 2026.09.25.0,mac_name J10,style 650,cloth 200100TC%20390,seisan 0.0 0.0 0.0 0,"
        "run_tm 0.000,stop_ttm 456.950,stop_ct " + ZERO13 + ","
        "stop_tm 0 0 0 0 0 0 0 0 0 23.033 456.950 0 0,stop_wtm " + ZERO13],
    1: ["shift 2026.09.25.1,mac_name J14,style 350,cloth 70135J156360,seisan 200.0 110.0 120.0 1,"
        "run_tm 400.000,stop_ttm 80.000,stop_ct 1 2 0 0 0 30 0 0 5 1 0 0 0,"
        "stop_tm 5 6 0 0 0 40 0 0 20 9 0 0 0,stop_wtm " + ZERO13],
    2: ["shift 2026.09.25.2,mac_name J14,style 350,cloth 70135J156360,seisan 1.0 0.5 0.5 0,"
        "run_tm 5.000,stop_ttm 475.000,stop_ct " + ZERO13 + ",stop_tm 0 0 0 0 0 0 0 0 0 0 475 0 0,"
        "stop_wtm " + ZERO13],
}


def blob(looms):
    return zlib.compress(json.dumps(looms).encode())


class GoldenDayTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = self.dir.name
        self.old = (mer.DB, mer.MIRROR, mer.SHOP_DB, storage.SHOP_DB, storage.FACT_DB)
        mer.DB = storage.FACT_DB = os.path.join(root, "fact.db")
        mer.SHOP_DB = storage.SHOP_DB = os.path.join(root, "shop.db")
        mer.MIRROR = os.path.join(root, "shift-shift")
        os.makedirs(mer.MIRROR)

        db = sqlite3.connect(mer.DB)
        db.executescript(ingest.SHIFT_SCHEMA + ingest.SHIFT_LOOM_SCHEMA)
        for i, lines in SHIFTS.items():
            text = "\n".join(lines)
            ingest.upsert_shift(db, "%s.%d" % (DAY, i), text)
            with open(os.path.join(mer.MIRROR, "%s.%d.txt" % (DAY, i)), "w", encoding="utf-8") as f:
                f.write(text)
        db.commit()
        db.close()

        shop = storage.shop()
        shop.execute("INSERT INTO loom_setup (loom, from_day, gsm, weight_kg, ppt, panels,"
                     " pile_yarn, pile_lot, weft1_yarn, set_by, set_at)"
                     " VALUES ('J14', '2026.09.20', 450, 0.5, 3000, 4, 'Ne 16/1', 'L1', 'Ne 20/1', 't', 't')")
        # Снимки FACT раз в 10 мин за сутки отчёта 07:00—07:00: J14 работает на 530.
        start = datetime(2026, 9, 25, 7, 0, tzinfo=TZ)
        rows = [("s%d" % m, int((start + timedelta(minutes=m)).timestamp()), "",
                 blob({"J14": {"running": True, "rpm": 530 if m % 60 else 520}, "J10": {"running": False, "rpm": 0}}))
                for m in range(0, 24 * 60, 10)]
        # КПД смены A по FACT — последний снимок в последние 10 минут смены.
        rows.append(("a-end", int(datetime(2026, 9, 25, 14, 55, tzinfo=TZ).timestamp()), "",
                     blob({"J14": {"running": True, "rpm": 530, "effic_shift": 76.4}})))
        shop.executemany("INSERT INTO machine_sample VALUES (?,?,?,?)", rows)
        shop.commit()
        shop.close()

    def tearDown(self):
        mer.DB, mer.MIRROR, mer.SHOP_DB, storage.SHOP_DB, storage.FACT_DB = self.old
        self.dir.cleanup()

    def test_golden_day(self):
        rows = mer.build(DAY)
        self.assertEqual([r["loom"] for r in rows], ["J14", "J10"])   # по обрывам утка, как в файле цеха
        j14, j10 = rows
        expect = {
            "sr": 2, "cloth": "70135J156360",
            # обороты — самое частое Rpm снимков, пока станок работает
            "rpm": 530, "rpm_src": "fact",
            "ppt": 3000, "weight": 0.5, "panels": 4, "gsm": 450, "ppt_est": None,
            "pile_count": "Ne 16/1", "loto": "В:L1", "weft1": "Ne 20/1", "weft2": "",
            # КПД: A — число FACT (76,4 → 76), B — расчёт по сменному файлу
            # 400 / (400 + 80) = 83,3 → 83; C — работа 5 мин, смена не в счёт.
            "eff_a": 76, "eff_b": 83, "eff_c": None, "eff_total": 79.5,
            # обрывы: ворс — категория 0, основа (грунт) — 1, уток — 5,
            # «прочие» — ручной (8) + без питания (9)
            "pile_a": 9, "pile_b": 1, "pile_c": 0, "pile_total": 10,
            "ground_a": 7, "ground_b": 2, "ground_c": 0, "ground_total": 9,
            "weft_a": 55, "weft_b": 30, "weft_c": 0, "weft_total": 85,
            "other_a": 14, "other_b": 6, "other_c": 0, "other_total": 20,
            # 100 %: панели × вес × обороты × 480 мин × 2 смены / PPT
            "prod100": round(4 * 0.5 * 530 * 480 * 2 / 3000, 1),
            "art_found": 1,
        }
        for k, v in expect.items():
            with self.subTest(column=k):
                self.assertEqual(j14[k], v)
        self.assertAlmostEqual(j14["picks"], (182.3 + 200.0 + 1.0) * 1000, places=3)
        # выработка: панели × вес × прокидки / PPT
        self.assertEqual(j14["achieved"], round(4 * 0.5 * 383300 / 3000, 1))
        # время одного останова, сек: минуты × 60 / число — ворс, уток, основа по сменам
        self.assertEqual(j14["mending"], {"vors": [150, 300, ""], "utog": [55, 80, ""],
                                          "karenoy": [156, 180, ""]})

        self.assertEqual((j10["sr"], j10["eff_a"], j10["eff_total"], j10["weft_total"],
                          j10["other_total"], j10["prod100"], j10["picks"], j10["art_found"]),
                         (1, None, 0, 0, 0, None, 0, 0))
        self.assertEqual(j10["rpm"], 0)            # не работал — скорости нет ни в снимках, ни в сменах


if __name__ == "__main__":
    unittest.main()
