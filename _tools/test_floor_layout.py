"""Расстановка по цеху: места станков — из layout.txt FACT в последнем снимке."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_app"))
import web


class FloorLayoutTests(unittest.TestCase):
    def test_rows_and_columns_from_snapshot(self):
        snap = {"looms": {"J1": {"row": 3, "col": 2}, "D1": {"row": 3, "col": 8}, "X": {"row": None, "col": 1}}}
        with patch.object(web.livestate, "load", return_value=snap):
            self.assertEqual(web.floor_layout(), {"J1": [3, 2], "D1": [3, 8]})

    def test_no_snapshot(self):
        with patch.object(web.livestate, "load", return_value=None):
            self.assertEqual(web.floor_layout(), {})


if __name__ == "__main__":
    unittest.main()
