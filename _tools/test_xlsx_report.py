"""Проверка переносимой выгрузки: раскладка листа TOYOTA как в ручном отчёте,
80 станков, итоги формулами с посчитанными значениями и безопасные строки."""
from pathlib import Path
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_app"))
from xlsx_report import NS, write_report


def value(c, ns):
    v = c.find("s:v", ns)
    if v is not None:
        return v.text
    return c.find("s:is/s:t", ns).text


class PortableReportTests(unittest.TestCase):
    def test_template_layout(self):
        rows = [{"sr": i, "loom": ("J" if i <= 40 else "D") + str(i), "size": "70 CM",
                 "rpm": 500, "ppt": 2500, "weight": 0.4, "panels": 3,
                 "design": '=HYPERLINK("x") & <дизайн>', "achieved": 90.25,
                 "eff_a": 80, "eff_b": 70, "eff_c": None,
                 "weft_a": 10, "weft_b": 20, "weft_c": 30, "other_total": 3,
                 "mending": {"vors": [10, 20, 30]}} for i in range(1, 81)]
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
            # заголовки как в шаблоне
            self.assertEqual(value(cells["A5"], ns), "Sr#")
            self.assertEqual(value(cells["H5"], ns), "MODEL (DIZAYN)")
            self.assertEqual(value(cells["Q5"], ns), "L#")
            self.assertEqual(value(cells["AP4"], ns), "15,09,2026")
            # строки станков с 6-й, дизайн — текст, а не формула
            self.assertEqual(value(cells["Q85"], ns), "D80")
            self.assertEqual(cells["H6"].attrib["t"], "inlineStr")
            self.assertEqual(value(cells["H6"], ns), rows[0]["design"])
            # формулы шаблона с посчитанным значением
            g = 3 * 0.4 * (500 * 24 * 60 / 2500)
            self.assertEqual(cells["G6"].find("s:f", ns).text, "F6*E6*(C6*24*60/D6)")
            self.assertAlmostEqual(float(value(cells["G6"], ns)), g)
            self.assertAlmostEqual(float(value(cells["U6"], ns)), 75.0)
            self.assertEqual(float(value(cells["AC6"], ns)), 60)
            self.assertAlmostEqual(float(value(cells["J1"], ns)), g * 80)
            self.assertAlmostEqual(float(value(cells["J2"], ns)), 90.25 * 80)
            self.assertEqual(float(value(cells["AC2"], ns)), 60 * 40)     # Dobby — D
            self.assertIn("SUMIF(Q6:Q85,\"J*\"", cells["AC3"].find("s:f", ns).text)
            self.assertEqual(float(value(cells["AR6"], ns)), 10)
            self.assertTrue(root.find("s:autoFilter", ns).attrib["ref"].endswith("85"))


if __name__ == "__main__":
    unittest.main()
