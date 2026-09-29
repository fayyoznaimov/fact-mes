"""Читающее соединение FACT освобождает файл и сохраняет запрет записи."""
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_app"))
import storage


class StorageScopeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="fact_scope_test_")
        self.addCleanup(temp.cleanup)
        path = str(Path(temp.name) / "fact.db")
        with closing(sqlite3.connect(path)) as db:
            db.execute("CREATE TABLE sample(value INTEGER)")
        p = patch.object(storage, "FACT_DB", path)
        p.start()
        self.addCleanup(p.stop)

    def connection(self):
        db = storage.fact()
        self.addCleanup(db.close)
        return db

    def test_normal_exit_closes_connection(self):
        db = self.connection()
        with db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sample").fetchone()[0], 0)
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")

    def test_exception_is_propagated_and_connection_is_closed(self):
        db = self.connection()
        with self.assertRaisesRegex(ValueError, "report failed"):
            with db:
                raise ValueError("report failed")
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")

    def test_readonly_connection_cannot_write(self):
        with self.connection() as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("INSERT INTO sample VALUES(1)")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sample").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
