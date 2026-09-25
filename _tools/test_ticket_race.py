"""Один останов — один открытый тикет, даже когда монитор и сборщик заводят его
одновременно (разбор 15.09 воспроизвёл два тикета на один станок)."""
import os
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_app"))
import storage
import tickets


class TicketRaceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.old = (storage.SHOP_DB, tickets.state_now, tickets._migrated)
        storage.SHOP_DB = os.path.join(self.dir.name, "shop.db")
        tickets._migrated = False
        self.sec = iter(range(600, 100000, 7))       # у каждого вызова своё «начало» останова
        self.lock = threading.Lock()

        def state_now(max_age=20):
            with self.lock:
                sec = next(self.sec)
            return None, {"J1": {"running": False, "state_sec": sec, "state": "Stop",
                                 "cause": "Manual", "style": "S"}}
        tickets.state_now = state_now
        tickets.db().close()

    def tearDown(self):
        storage.SHOP_DB, tickets.state_now, tickets._migrated = self.old
        self.dir.cleanup()

    def open_count(self):
        db = sqlite3.connect(storage.SHOP_DB)
        try:
            return db.execute("SELECT COUNT(*) FROM ticket WHERE loom='J1' AND ended_at IS NULL").fetchone()[0]
        finally:
            db.close()

    def test_monitor_and_collector_at_once(self):
        start = threading.Barrier(20)
        errors = []

        def monitor():
            start.wait()
            try:
                tickets.open_ticket("J1", who="монитор")
            except Exception as e:           # noqa: BLE001 — собираем для проверки
                errors.append(e)

        def collector():
            start.wait()
            try:
                tickets.poll_once()
            except Exception as e:           # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=monitor if i % 2 else collector) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(self.open_count(), 1)

    def test_classify_does_not_overwrite_someone_elses_reason(self):
        tid = tickets.open_ticket("J1", who="монитор")
        cats = sorted(tickets.active_ids())
        a, b = cats[0], cats[1]
        tickets.classify(tid, a, "мастер1", was=None)             # видел «без причины» — ок
        with self.assertRaises(tickets.Conflict):
            tickets.classify(tid, b, "мастер2", was=None)          # тоже видел пустую — уже нет
        tickets.classify(tid, b, "мастер2", was=a)                  # видел выбор мастера1 — ок
        tickets.classify(tid, b, "мастер3", was=None)               # та же причина — не конфликт
        tickets.classify(tid, a, "api")                             # без was — как раньше

    def test_unique_open_index_exists(self):
        db = sqlite3.connect(storage.SHOP_DB)
        try:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")]
        finally:
            db.close()
        self.assertIn("ticket_one_open", names)


if __name__ == "__main__":
    unittest.main()
