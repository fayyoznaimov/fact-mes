"""Проверка переносимой выгрузки: 80 станков, числа, итоги и безопасные строки."""
from pathlib import Path
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_app"))
from xlsx_report import NS, write_report


class PortableReportTests(unittest.TestCase):
    def test_eighty_looms_and_safe_values(self):
        rows = [{"sr": i, "loom": "D" + str(i), "design": '=HYPERLINK("x") & <дизайн>',
                 "prod100": 120.5, "achieved": 90.25, "weight": 0.176,
                 "eff_total": 75.0, "mending": {"vors": [10, 20, 30]}} for i in range(1, 81)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.xlsx"
            write_report("2026.09.15", rows, path)
            with ZipFile(path) as z:
                self.assertIsNone(z.testzip())
                for name in z.namelist():
                    ET.fromstring(z.read(name))
                root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
                ns = {"s": NS}
                cells = {c.attrib["r"]: c for c in root.findall(".//s:c", ns)}
                self.assertEqual(cells["B85"].find("s:is/s:t", ns).text, "D80")
                self.assertEqual(cells["C6"].attrib["t"], "inlineStr")
                self.assertEqual(cells["C6"].find("s:is/s:t", ns).text, rows[0]["design"])
                self.assertFalse(root.findall(".//s:f", ns))
                self.assertEqual(float(cells["E2"].find("s:v", ns).text), 120.5 * 80)
                self.assertEqual(float(cells["E3"].find("s:v", ns).text), 90.25 * 80)
                self.assertEqual(float(cells["J6"].find("s:v", ns).text), 0.176)
                self.assertTrue(root.find("s:autoFilter", ns).attrib["ref"].endswith("85"))


if __name__ == "__main__":
    unittest.main()
