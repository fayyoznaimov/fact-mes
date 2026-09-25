"""История MES: только временные SQLite, без сети и рабочего сервера."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '_app'))
import storage
import productionlog as history
import loomsetup
import machinehistory


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'shop.db')
        self.config = patch.object(storage, 'SHOP_DB', self.path)
        self.config.start()
        self.db = storage.shop()
        self.db.execute("INSERT INTO operator(id,code,name) VALUES(1,'47','First'),(2,'48','Second')")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.config.stop()
        self.temp.cleanup()

    def assignment(self, operator, at):
        with patch.object(history, 'now', return_value=at):
            db = storage.shop()
            db.execute("DELETE FROM assignment WHERE day='2026.09.16' AND shift='A'")
            db.execute("INSERT INTO assignment VALUES('2026.09.16','A','J1',?)", (operator,))
            db.commit()
            db.close()

    def test_assignment_periods_and_late_correction(self):
        self.assignment(1,'2026-09-16T06:00:00+05:00')
        self.assignment(2,'2026-09-16T10:00:00+05:00')
        self.assignment(2,'2026-09-16T11:00:00+05:00')
        self.assignment(1,'2026-09-17T10:00:00+05:00')
        result = history.assignment_periods('2026.09.16','A')
        self.assertEqual(len(result['periods']),2)
        self.assertEqual(result['periods'][0]['start'],'2026-09-16T07:00:00+05:00')
        self.assertEqual(result['periods'][0]['end'],result['periods'][1]['start'])
        self.assertEqual(result['periods'][1]['operator']['operator_name'],'Second')
        self.assertEqual(len(result['corrections']),1)
        self.db.execute("UPDATE operator SET name='Renamed' WHERE id=2")
        self.db.commit()
        self.assertEqual(history.assignment_periods('2026.09.16','A')['periods'][1]['operator']['operator_name'],'Second')

    def test_atomic_audit_and_immutable_document(self):
        n = self.db.execute('SELECT COUNT(*) FROM production_event').fetchone()[0]
        self.db.execute("INSERT INTO assignment VALUES('2026.09.16','A','J1',1)")
        self.db.rollback()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM production_event').fetchone()[0],n)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM production_event")
        self.db.rollback()
        self.db.execute("INSERT INTO setup_document(loom,valid_from,created_at,author,snapshot_json) VALUES ('J1','2026-09-16','now','user','{}')")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE setup_document SET author='other'")
        self.db.rollback()

    def test_repeated_setup_keeps_ppt_and_plan_snapshot(self):
        self.db.execute("INSERT INTO loom_plan(loom,day,order_no,product,design,client,gsm,size) VALUES('J1','2026.09.16','1661','Towel','J301','6',420,'70x140')")
        self.db.commit()
        def fact():
            db=sqlite3.connect(':memory:')
            db.execute('CREATE TABLE shift_full(day TEXT)')
            return db
        with patch.object(loomsetup,'fact',side_effect=fact), patch('reports.rebuild_daily_reports',return_value=[]):
            loomsetup.save(['J1'],'2026.09.16',{'ppt':3000},'master608','2026-09-16T07:00:00+05:00')
            self.db.execute("UPDATE loom_plan SET client='99'")
            self.db.commit()
            loomsetup.save(['J1'],'2026.09.16',{'ppt':4000},'master608','2026-09-16T12:00:00+05:00')
        docs=loomsetup.documents('J1')
        self.assertEqual(len(docs),2)
        self.assertEqual(docs[1]['snapshot']['values']['ppt'],3000)
        self.assertEqual(docs[1]['snapshot']['plan']['client'],'6')
        self.assertEqual(docs[0]['snapshot']['values']['ppt'],4000)
        with self.assertRaises(ValueError):
            loomsetup.save(['J1'],'2026.09.16',{'ppt':3000},'user','2026-09-17T07:00:00+05:00')
        self.assertEqual(len(loomsetup.documents()),2)

    def test_archive_and_gaps(self):
        import loomstate
        def machine(seconds):return dict(running=True,state='Run',cause='Run',state_sec=seconds)
        # 1060 → 1120: счётчик начался заново (5 с) — между снимками был останов.
        for at,seconds in [(1000,10),(1060,70),(1120,5),(1400,285)]:
            history.archive_sample(dict(source='fact',dir=str(at),fact_time=at,looms={'J1':machine(seconds)}))
        history.archive_sample(dict(source='mirror'))
        self.assertEqual(len(history.sample_archive(1000,1500)),4)
        loomstate._READY.clear()
        self.assertEqual(loomstate.catch_up(),4)
        states=loomstate.intervals(1000,1500)['J1']
        self.assertEqual([(x['start'],x['end']) for x in states],[(990,1060),(1115,1400)])
        row=dict(loom='J1',segments=[dict(start=1000,end=1500,kind='unknown')],totals={})
        machinehistory.add_observations(row,states,1000,1500,1500)
        self.assertEqual(row['totals']['observed_run'],60+285)
        self.assertEqual(row['totals']['unknown'],55+100)
        self.assertEqual(sum(row['totals'].values()),500)

    def test_ticket_creation_closure_actor_and_counter_noise(self):
        import tickets
        db=tickets.db()
        token=history.ACTOR.set('master608')
        try:
            tid=db.execute("INSERT INTO ticket(loom,started_at,opened_by) VALUES('J1','2026-09-16T07:00:00+05:00','master608')").lastrowid
            db.execute('UPDATE ticket SET duration_sec=60 WHERE id=?',(tid,))
            db.execute("UPDATE ticket SET ended_at='2026-09-16T08:00:00+05:00' WHERE id=?",(tid,))
            db.commit()
        finally:
            db.close();history.ACTOR.reset(token)
        events=history.events('ticket',record_id=tid)
        self.assertEqual([e['action'] for e in events],['UPDATE','INSERT'])
        self.assertEqual(events[0]['actor'],'master608')
        self.assertIsNone(events[0]['before']['ended_at'])
        self.assertIsNotNone(events[0]['after']['ended_at'])

    def test_yarn_analysis_excludes_mixed_and_incomplete_shifts(self):
        snap=dict(values={},resolved=dict(pile_yarn='16 RING',pile_lot='LOT1',gsm=420,panels=2),plan=dict(design='J301'))
        for loom,valid in [('J1','2026-09-01T07:00:00+05:00'),('J2','2026-09-01T07:00:00+05:00'),('J2','2026-09-01T10:00:00+05:00'),('J3','2026-09-01T07:00:00+05:00')]:
            self.db.execute('INSERT INTO setup_document(loom,valid_from,created_at,author,snapshot_json) VALUES(?,?,?,?,?)',(loom,valid,valid,'test',json.dumps(snap)))
        self.db.commit()
        def fact():
            db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
            db.execute('CREATE TABLE shift_full(day TEXT,letter TEXT,loom TEXT,run_min REAL,stop_min REAL,picks REAL,pieces INTEGER,top_ct INTEGER)')
            db.executemany("INSERT INTO shift_full VALUES('2026.09.01','A',?,?,?,?,?,?)",[('J1',400,80,200000,100,10),('J2',400,80,200000,100,10),('J3',100,80,50000,20,2),('J4',400,80,200000,100,10)])
            return db
        with patch.object(loomsetup,'fact',side_effect=fact):result=loomsetup.yarn_analysis('2026-09-01','2026-09-01')
        self.assertEqual(result['included_shifts'],1)
        self.assertEqual(result['excluded']['mixed_setup'],1)
        self.assertEqual(result['excluded']['incomplete'],1)
        self.assertEqual(result['excluded']['no_document'],1)
        self.assertEqual(result['groups'][0]['rpm'],500)
        self.assertEqual(result['groups'][0]['towels'],200)


if __name__ == '__main__':unittest.main()
