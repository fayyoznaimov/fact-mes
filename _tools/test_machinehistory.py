"""Границы хронологии: только синтетические данные, без рабочих баз/FACT."""
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '_app'))
import ingest
import machinehistory as h
import storage
import tickets

DAY = date(2026, 9, 14)
START = h.stamp(DAY, 7 * 3600)
END = START + 28800


def event(start=7 * 3600 + 600, duration=60, **kw):
    return dict(day='2026.09.14', start_sec=start, dur_sec=duration,
                cause='Weft', code='21', shift='2026.09.14.0', style='Towel', resp_sec=None, **kw)


def shift(run=479, stop=1):
    return dict(day='2026.09.14', letter='A', shift='2026.09.14.0', run_min=run, stop_min=stop)


class Intervals(unittest.TestCase):
    def build(self, records, shifts=(), now=END+1):
        r = h.build_row('D1', records, shifts, START, END, now)
        self.assertEqual(sum(r['totals'].values()), 28800)
        self.assertEqual(r['segments'][0]['start'], START)
        self.assertEqual(r['segments'][-1]['end'], END)
        for a, b in zip(r['segments'], r['segments'][1:]):
            self.assertEqual(a['end'], b['start'])
        return r

    def test_empty_is_unknown(self):
        self.assertEqual(self.build([])['totals']['unknown'], 28800)

    def test_stops_do_not_imply_running(self):
        r = self.build([event()])
        self.assertEqual(r['totals']['stop'], 60)
        self.assertEqual(r['totals']['estimated_run'], 0)

    def test_closed_reconciled_shift(self):
        r = self.build([event()], [shift()])
        self.assertEqual(r['totals']['estimated_run'], 28740)
        self.assertEqual(r['totals']['unknown'], 0)

    def test_missing_stop_refuses_estimate(self):
        self.assertEqual(self.build([], [shift(470, 10)])['totals']['estimated_run'], 0)

    def test_partial_shift_refuses_estimate(self):
        self.assertEqual(self.build([event()], [shift(200, 1)])['totals']['estimated_run'], 0)

    def test_unfinished_shift_has_future(self):
        r = self.build([event()], [shift()], now=START+1000)
        self.assertEqual(r['totals']['future'], 27800)
        self.assertEqual(r['totals']['estimated_run'], 0)

    def test_overlap_not_counted_twice(self):
        r = self.build([event(duration=120), event(start=7*3600+660, duration=120)], [shift(477, 3)])
        self.assertEqual(r['totals']['stop'], 180)
        self.assertEqual(r['overlap_sec'], 60)
        self.assertEqual(r['totals']['estimated_run'], 0)

    def test_long_carry_over(self):
        e = event(start=0, duration=3*86400)
        e['day'] = '2026.09.12'
        self.assertEqual(self.build([e])['totals']['stop'], 28800)

    def test_boundaries_are_half_open(self):
        self.assertEqual(self.build([event(start=7*3600-60),event(start=15*3600)])['totals']['stop'], 0)

    def test_bad_record_refuses_estimate(self):
        r = self.build([event(start=None)], [shift(480, 0)])
        self.assertEqual(r['invalid_records'], 1)
        self.assertEqual(r['totals']['unknown'], 28800)

    def test_zero_stop_completed_shift_is_estimate(self):
        self.assertEqual(self.build([], [shift(480, 0)])['totals']['estimated_run'], 28800)


class Database(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fact_history_unit_')
        self.fact = os.path.join(self.tmp.name, 'fact.db')
        self.shop = os.path.join(self.tmp.name, 'shop.db')
        with closing(sqlite3.connect(self.fact)) as db, db:
            db.executescript(ingest.STOP_SCHEMA + ingest.SHIFT_SCHEMA)
            db.execute("INSERT INTO shift_full(day,loom,letter,shift,run_min,stop_min) VALUES "
                       "('2026.09.14','D1','A','2026.09.14.0',479,1)")
            db.execute("INSERT INTO stop_log(day,loom,start_sec,dur_sec,cause,code) VALUES "
                       "('2026.09.14','D1',25800,60,'Weft','21')")
        with closing(sqlite3.connect(self.shop)) as db, db:
            db.executescript(tickets.SCHEMA)
        self.fp = patch.object(storage, 'FACT_DB', self.fact)
        self.sp = patch.object(storage, 'SHOP_DB', self.shop)
        self.fp.start(); self.sp.start(); h._cached.cache_clear()

    def tearDown(self):
        self.fp.stop(); self.sp.stop(); h._cached.cache_clear(); self.tmp.cleanup()

    def test_calendar_clips_but_checks_full_shift(self):
        d = h.timeline('2026-09-14')
        self.assertEqual(len(d['rows']), 1)
        self.assertEqual(d['rows'][0]['totals']['estimated_run'], 28740)
        self.assertEqual(sum(d['rows'][0]['totals'].values()), 86400)

    def test_night_shift_continues_next_day(self):
        with closing(sqlite3.connect(self.fact)) as db, db:
            db.execute("INSERT INTO stop_log(day,loom,start_sec,dur_sec,cause,code) VALUES "
                       "('2026.09.15','D1',3600,120,'Warp','1')")
        d = h.timeline('2026-09-14', 'C')
        self.assertEqual(d['start'], h.stamp(DAY, 23*3600))
        self.assertEqual(d['rows'][0]['totals']['stop'], 120)

    def test_fetches_multi_day_stop(self):
        with closing(sqlite3.connect(self.fact)) as db, db:
            db.execute("INSERT INTO stop_log(day,loom,start_sec,dur_sec,cause,code) VALUES "
                       "('2026.09.10','D1',0,5*86400,'Manual','9')")
        self.assertEqual(h.timeline('2026-09-14')['rows'][0]['totals']['stop'], 86400)

    def test_naive_and_offset_tickets_separate_from_machine(self):
        with closing(sqlite3.connect(self.shop)) as db, db:
            db.execute("INSERT INTO ticket(loom,started_at,ended_at,category_id) VALUES "
                       "('D1','2026-09-14T00:01:00','2026-09-14T00:02:00','naladka')")
            db.execute("INSERT INTO ticket(loom,started_at,ended_at,category_id) VALUES "
                       "('D1','2026-09-13T19:03:00+00:00','2026-09-13T19:04:00+00:00','toir')")
        r = h.timeline('2026-09-14')['rows'][0]
        self.assertEqual(len(r['tickets']), 2)
        self.assertEqual(r['totals']['stop'], 60)
        self.assertEqual(sorted(t['start'] for t in r['tickets']), [h.stamp(DAY,60),h.stamp(DAY,180)])

    def test_bad_input(self):
        for args in [('bad',),('2026-09-14','bad'),('2026-09-14','day','bad/sql'),
                     ('2026-09-14','day','MISSING'),('1500-01-01',)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                h.timeline(*args)


if __name__ == '__main__':
    unittest.main()
