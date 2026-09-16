"""Связь учётной записи с мастером; только временная база."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import provision_shift_masters as provision
import auth
import storage
import people


class ShiftMasterTest(unittest.TestCase):
    def test_identity_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'shop.db')
            with patch.object(auth, 'DB_PATH', path), patch.object(storage, 'SHOP_DB', path):
                record = provision.provision([dict(login='master608', name='Test Master', code='608')])[0]
                token = auth.login(record['login'], record['password'])
                user = auth.user_by_token(token)
                self.assertEqual(user['role'], 'master')
                self.assertEqual(user['must_change'], 1)
                self.assertIn('cards', user['sections'])
                self.assertNotIn('dash', user['sections'])
                self.assertIn('plan', user['sections'])
                self.assertTrue(auth.can(user, 'assign'))
                self.assertTrue(auth.can(user, 'tickets'))
                for action in ('users', 'people', 'settings', 'plan_edit', 'setup_edit'):
                    self.assertFalse(auth.can(user, action))
                with patch.object(people, 'ensure_shift_docs'), patch.object(people, 'get_shift_doc'):
                    conn = storage.shop()
                    conn.execute("INSERT INTO shift_doc(day,shift) VALUES ('2026.09.16','A')")
                    conn.commit()
                    conn.close()
                    people.save_shift_doc('2026.09.16', 'A', {'foreman_id': 999}, 'master608')
                conn = storage.shop()
                self.assertIsNone(conn.execute('SELECT foreman_id FROM shift_doc').fetchone()[0])
                self.assertEqual(conn.execute('SELECT operator_id FROM shift_master').fetchone()[0], user['employee_id'])
                conn.close()
                with patch.object(people, 'get_shift_doc'):
                    people.confirm_shift_doc('2026.09.16', 'A', 'master608')
                with self.assertRaises(ValueError):
                    provision.provision([dict(login='master608', name='Duplicate', code='608')])
                self.assertIsNotNone(auth.login(record['login'], record['password']))


if __name__ == '__main__':
    unittest.main()
