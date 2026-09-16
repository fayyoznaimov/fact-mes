"""Документы учёта: проверка, подтверждение, неизменяемость. Только временные базы."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '_app'))
import storage
import productionlog
import documents
import doc_kinds
import loomsetup
import payroll


def rows_for(day, letter):
    if day == '2026.09.02':
        return []
    return [dict(loom='J1', style='S', rpm=500, effic_pct=90, run_min=400, stop_min=80, picks=100000,
                 meters=0, pieces=0, weft_ct=1, weft_fix_min=0, weft_mttr_sec=0, top_ct=0, top_fix_min=0,
                 top_mttr_sec=0, warp_ct=0, warp_fix_min=0, warp_mttr_sec=0, manual_ct=0, manual_min=0,
                 wait_total_min=0),
            dict(loom='J2', style='S', rpm=500, effic_pct=90, run_min=400, stop_min=80, picks=50000,
                 meters=0, pieces=0, weft_ct=0, weft_fix_min=0, weft_mttr_sec=0, top_ct=0, top_fix_min=0,
                 top_mttr_sec=0, warp_ct=0, warp_fix_min=0, warp_mttr_sec=0, manual_ct=0, manual_min=0,
                 wait_total_min=0)]


class DocumentsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'shop.db')
        self.patches = [patch.object(storage, 'SHOP_DB', self.path),
                        patch.object(loomsetup, 'rebuild', return_value=[]),
                        patch.object(payroll, 'shift_rows', side_effect=rows_for),
                        patch.object(doc_kinds, '_today', return_value='2026.09.16')]
        for p in self.patches:
            p.start()
        self.db = storage.shop()
        self.db.execute("INSERT INTO operator(id,code,name) VALUES(1,'47','First')")
        self.db.execute("INSERT INTO yarn(name,key,kind) VALUES('16/1 RING','16/1RING','pile')")
        self.db.execute("INSERT INTO assignment VALUES('2026.09.01','A','J1',1)")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def post(self, kind, payload, who='master'):
        checked = documents.preview(kind, payload)
        self.assertEqual(checked['errors'], [], checked)
        return documents.post(kind, payload, checked['checksum'], who)

    def test_setup_preview_shows_changes_and_post_is_immutable(self):
        payload = {'from_day': '2026.09.15', 'rows': [{'loom': 'j1', 'values': {'ppt': '3000', 'pile_yarn': '16/1 ring'}}]}
        checked = documents.preview('setup', payload)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM loom_setup').fetchone()[0], 0,
                         'проверка ничего не пишет')
        fields = {c['field']: c for c in checked['changes']}
        self.assertEqual(fields['ppt']['after'], 3000)
        self.assertEqual(fields['pile_yarn']['after'], '16/1 RING')
        self.assertTrue(any('без лота' in w for w in checked['warnings']))
        self.assertTrue(any('пересобран' in w for w in checked['warnings']))
        r = documents.post('setup', payload, checked['checksum'], 'master608')
        self.assertTrue(r['number'].startswith('ЗАП-'))
        setup = self.db.execute('SELECT * FROM loom_setup').fetchone()
        self.assertEqual((setup['loom'], setup['ppt'], setup['set_by']), ('J1', 3000, 'master608'))
        sd = self.db.execute('SELECT doc_id FROM setup_document').fetchone()
        self.assertEqual(sd['doc_id'], r['id'])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE doc SET title='x' WHERE id=?", (r['id'],))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('DELETE FROM doc')
        self.db.rollback()
        with self.assertRaises(ValueError):
            documents.cancel(r['id'], 'ошибка', 'admin')
        again = documents.preview('setup', payload)
        self.assertIn('изменений нет', ' '.join(again['errors']))
        doc = documents.get(r['id'])
        self.assertEqual(doc['history'][0]['actor'], 'master608')
        self.assertEqual(doc['created_by'], 'master608')

    def test_stale_confirmation_is_rejected(self):
        payload = {'from_day': '2026.09.15', 'rows': [{'loom': 'J1', 'values': {'ppt': '3000'}}]}
        first = documents.preview('setup', payload)
        self.post('setup', {'from_day': '2026.09.15', 'rows': [{'loom': 'J1', 'values': {'ppt': '2500'}}]}, 'other')
        with self.assertRaises(documents.Stale):
            documents.post('setup', payload, first['checksum'], 'master')
        with self.assertRaises(ValueError):
            documents.post('setup', payload, '', 'master')
        self.assertEqual(self.db.execute('SELECT ppt FROM loom_setup').fetchone()[0], 2500)

    def test_errors_block_posting(self):
        payload = {'from_day': '2026.09.15', 'rows': [{'loom': 'J1', 'values': {'ppt': 'abc'}},
                                                       {'loom': 'J2', 'values': {'pile_yarn': 'нет такой'}}]}
        checked = documents.preview('setup', payload)
        self.assertEqual(len(checked['errors']), 2)
        self.assertFalse(checked['can_post'])
        with self.assertRaises(ValueError):
            documents.post('setup', payload, checked['checksum'], 'master')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM doc').fetchone()[0], 0)

    def test_rate_is_effective_dated_and_cancel_restores(self):
        self.assertEqual(storage.rate_for(self.db, '2026.09.10'), (287.0, 'kpick'))
        r = self.post('rate', {'valid_from': '2026.09.10', 'rate': '300', 'unit': 'kpick'}, 'admin')
        self.assertEqual(storage.rate_for(self.db, '2026.09.09'), (287.0, 'kpick'))
        self.assertEqual(storage.rate_for(self.db, '2026.09.10'), (300.0, 'kpick'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('DELETE FROM rate_period')
        self.db.rollback()
        with self.assertRaises(ValueError):
            documents.cancel(r['id'], '', 'admin')
        documents.cancel(r['id'], 'ошибка в дате', 'admin')
        self.assertEqual(storage.rate_for(self.db, '2026.09.10'), (287.0, 'kpick'))
        d = documents.get(r['id'])
        self.assertEqual((d['status'], d['cancelled_by'], d['cancel_reason']), ('cancelled', 'admin', 'ошибка в дате'))
        with self.assertRaises(ValueError):
            storage.save_settings({'rate': '999'}, 'admin')
        storage.save_settings({'rate': '287', 'andon_warn_min': '3'}, 'admin')
        event = self.db.execute("SELECT actor, before_json, after_json FROM production_event WHERE entity='setting'"
                                " AND action='UPDATE' ORDER BY id DESC").fetchone()
        self.assertEqual(event['actor'], 'admin')
        self.assertEqual(json.loads(event['after_json'])['value'], '3')

    def test_payroll_frozen_and_uses_rate_per_day(self):
        self.post('rate', {'valid_from': '2026.09.03', 'rate': '300', 'unit': 'kpick'}, 'admin')
        payload = {'from': '2026.09.01', 'to': '2026.09.03'}
        checked = documents.preview('payroll', payload)
        self.assertEqual(checked['errors'], [])
        first = [s for s in checked['result']['shifts'] if s['day'] == '2026.09.01' and s['shift'] == 'A'][0]
        self.assertEqual((first['rate'], first['operators'][0]['salary']), (287.0, round(100000 * 287 / 1000)))
        self.assertTrue(any('без оператора' in w for w in checked['warnings']))
        self.assertTrue(any('разные ставки' in w for w in checked['warnings']))
        self.assertTrue(any('нет выработки' in w for w in checked['warnings']))
        r = documents.post('payroll', payload, checked['checksum'], 'admin')
        # Пересекающаяся ведомость не проводится; замена — проводится и отменяет прежнюю.
        self.assertTrue(any('пересекается' in e for e in documents.preview('payroll', {'from': '2026.09.03', 'to': '2026.09.03'})['errors']))
        self.db.execute("INSERT INTO assignment VALUES('2026.09.01','A','J2',1)")
        self.db.commit()
        self.assertFalse(documents.verify(r['id'])['same'])
        replace = dict(payload, supersedes_id=r['id'])
        checked = documents.preview('payroll', replace)
        self.assertEqual(checked['errors'], [])
        self.assertEqual(checked['changes'][0]['before'] + round(50000 * 287 / 1000), checked['changes'][0]['after'])
        r2 = documents.post('payroll', replace, checked['checksum'], 'admin')
        self.assertEqual(documents.get(r['id'])['status'], 'cancelled')
        self.assertEqual(documents.get(r['id'])['replaced_by'][0]['id'], r2['id'])
        self.assertEqual([d['number'] for d in documents.list_docs(['payroll'], '2026.09.02', '2026.09.02', 'posted')],
                         [r2['number']])

    def test_unfinished_shift_is_error(self):
        checked = documents.preview('payroll', {'from': '2999.01.01', 'to': '2999.01.01'})
        self.assertTrue(any('не закончились' in e for e in checked['errors']))

    def test_audit_covers_reference_books_without_secrets(self):
        import auth
        with patch.object(auth, 'DB_PATH', self.path), patch.object(auth, '_audited', False):
            auth.create_user('ivan', 'Иван', 'master', 'secret123', must_change=False)
            conn = auth.db()
            conn.execute("UPDATE app_user SET last_login='now' WHERE login='ivan'")
            conn.execute("UPDATE app_user SET pwd_hash='x' WHERE login='ivan'")
            conn.commit()
            conn.close()
        events = self.db.execute("SELECT action, after_json FROM production_event WHERE entity='app_user'"
                                 " AND action<>'BASELINE' ORDER BY id").fetchall()
        self.assertEqual([e['action'] for e in events], ['INSERT', 'UPDATE'])
        for e in events:
            self.assertNotIn('pwd_hash', e['after_json'])
        self.assertTrue(json.loads(events[1]['after_json'])['secret_changed'])
        self.db.execute("INSERT INTO cloth_map(cloth_norm,cloth_code,product_code) VALUES('a','A','P')")
        self.db.execute("INSERT INTO yarn_lot(code,name) VALUES('1','Пряжа')")
        self.db.execute("INSERT INTO onec_message(received_at,ok,payload) VALUES('now',1,'{}')")
        self.db.commit()
        entities = {r[0] for r in self.db.execute("SELECT entity FROM production_event WHERE action='INSERT'")}
        self.assertTrue({'cloth_map', 'yarn_lot'} <= entities)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('DELETE FROM onec_message')
        self.db.rollback()

    def test_trigger_follows_new_column(self):
        self.db.execute('ALTER TABLE cloth_map ADD COLUMN note TEXT')
        productionlog.install(self.db)
        before = self.db.execute("SELECT sql FROM sqlite_master WHERE name='pl_cloth_map_INSERT'").fetchone()[0]
        self.assertIn('note', before)
        productionlog.install(self.db)      # повторная установка ничего не пересоздаёт
        self.assertEqual(before, self.db.execute("SELECT sql FROM sqlite_master WHERE name='pl_cloth_map_INSERT'").fetchone()[0])


if __name__ == '__main__':
    unittest.main()
