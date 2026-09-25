"""Связь со станком — по журналу опроса FACT (opestate/collect_log*.txt), а не
догадкой: POWER_OFF — обесточен, System ERROR — нет связи, SUCCEED с нулевыми
флагами — «прочее». Зависший сбор FACT распознаётся, сообщение уходит один раз."""
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_app"))
import collector
import livestate
import storage

LOG_DONE = """[2026/09/25 02:55:26] **** START DATA COLLECTING ****
[2026/09/25 02:55:29] J10 (192.168.1.40) ---> POWER_OFF
[2026/09/25 02:55:29] D1 (192.168.1.11) ---> System ERROR
[2026/09/25 02:55:30] D3 (192.168.1.13) ---> SUCCEED
[2026/09/25 02:55:30] **** END DATA COLLECTING ****
[2026/09/25 02:55:31] COMPLETED ALL PROPERLY
"""
LOG_STUCK = """[2026/09/25 02:56:24] **** START DATA COLLECTING ****
[2026/09/25 02:56:24] D1 (192.168.1.11) ---> System ERROR
"""
LOOMS = {"J10": "192.168.1.40", "D1": "192.168.1.11", "D3": "192.168.1.13"}


def write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_mirror(root, current_log):
    d = "factdata/opestate/255832814384"
    write(root, d + "/list_data.txt", "".join(
        "%s,%s,Towel,%s,600,0,0,0,0,0,0,0,0,0,0,0,0\n" % (ip, name, "Other" if name != "J10" else "Run")
        for name, ip in LOOMS.items()))
    write(root, d + "/layout.txt", "".join("1,1,0,0,%s,JAT,%s\n" % (ip, name) for name, ip in LOOMS.items()))
    for name, ip in LOOMS.items():
        write(root, d + "/loom/%s.txt" % livestate.loom_file(ip),
              "0\n%d\n(State)\nStop=1\nWeft=0\nManual=0\nPower_off=0\n" % int(time.time()))
    write(root, "factdata/opestate/collect_log.txt", current_log)
    write(root, "factdata/opestate/collect_log1.txt", LOG_DONE)


class FactLinkTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.old = storage.LIVE_FILE
        storage.LIVE_FILE = os.path.join(self.dir.name, "live.json")

    def tearDown(self):
        storage.LIVE_FILE = self.old
        self.dir.cleanup()

    def collector(self, current_log):
        make_mirror(self.dir.name, current_log)
        return collector.Collector(livestate.MirrorSource(os.path.join(self.dir.name)))

    def test_causes_from_fact_log(self):
        c = self.collector(LOG_DONE)
        c.live_once(force=True)
        looms = livestate.load(storage.LIVE_FILE)["looms"]
        self.assertEqual((looms["J10"]["cause"], looms["J10"]["running"]), ("Power_off", False))
        self.assertEqual(looms["D1"]["cause"], "No_link")
        self.assertEqual(looms["D3"]["cause"], "Other")       # на связи, флаги нулевые — «прочее», не «обесточен»
        self.assertEqual(looms["D3"]["fact_link"], "SUCCEED")

    def test_loom_clock_skew(self):
        # 25.09 12:00:00 по FACT (UTC+5), часы станка — 11:45:21: отстают на 14 мин 39 с.
        fact = 1790319600
        text = "0\n%d\n(State)\nSys_time=2026 9 25 5 11 45 21 \nStop=1\n" % fact
        self.assertEqual(livestate.parse_loom(text)["clock_skew_sec"], -879)
        self.assertIsNone(livestate.parse_loom("0\n%d\n(State)\nStop=1\n" % fact)["clock_skew_sec"])

    def test_parse_log(self):
        done = livestate.parse_collect_log(LOG_DONE)
        self.assertTrue(done["completed"])
        self.assertEqual(done["started"], "2026/09/25 02:55:26")
        stuck = livestate.parse_collect_log(LOG_STUCK)
        self.assertFalse(stuck["completed"])
        self.assertIsNone(stuck["finished"])

    def test_stuck_collection_told_once(self):
        c = self.collector(LOG_STUCK)
        c.live_once(force=True)                  # снимок есть, текущий опрос висит
        c.src.kind = "fact"                      # сообщаем только о живом источнике
        told = []
        with patch.object(c, "_tell", side_effect=told.append):
            c.snap_at = time.time() - 1000       # снимков нет 16 минут
            c.collect_checked = 0
            c._watch_stuck()
            c.collect_checked = 0
            c._watch_stuck()                     # второй раз не пишем
        self.assertEqual(len(told), 1)
        self.assertIn("02:56", told[0])
        self.assertIn("перезапустите", told[0])
        self.assertFalse(c.status["fact_collect"]["completed"])


if __name__ == "__main__":
    unittest.main()
