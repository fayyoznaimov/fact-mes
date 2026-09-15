"""Переносимый XLSX-отчёт: stdlib, без COM Excel и без изменения шаблона XLSB.

Числа берём из make_excel_report.build, включая уже рассчитанные итоги.
Строки записываются как inlineStr, поэтому названия не становятся формулами.
"""
import math
import os
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", NS)

COLUMNS = [
    ("sr", "№"), ("loom", "Станок"), ("design", "Дизайн"), ("client", "Клиент"),
    ("size", "Размер"), ("gsm", "GSM"), ("rpm", "Об/мин"), ("ppt", "Пиков на ряд"),
    ("panels", "Панелей"), ("weight", "Вес полотенца, кг"),
    ("prod100", "Выработка 100%, кг"), ("achieved", "Факт, кг"), ("picks", "Пиков"),
    ("pile_count", "Пряжа ворса"), ("ground_count", "Пряжа грунта"), ("loto", "Лоты"),
    ("weft1", "Уток"), ("weft2", "Кромка"), ("weft3", "Бордюр"), ("weft4", "Бордюр полиэстер"),
] + [("eff_" + s.lower(), "КПД " + s + ", %") for s in ("A", "B", "C", "TOTAL")] + [
    (kind + "_" + s.lower(), title + " " + s)
    for kind, title in (("pile", "Обрывы ворса"), ("weft", "Обрывы утка"),
                        ("ground", "Обрывы основы"), ("other", "Прочие остановы"))
    for s in ("A", "B", "C", "TOTAL")
] + [(kind + "_mend_" + str(i), title + " " + shift + ", с")
     for kind, title in (("vors", "Устранение ворса"), ("utog", "Устранение утка"),
                         ("karenoy", "Устранение основы"))
     for i, shift in enumerate("ABC")]


def column_name(number):
    out = ""
    while number:
        number, rem = divmod(number - 1, 26)
        out = chr(65 + rem) + out
    return out


def element(parent, name, attrs=None):
    return ET.SubElement(parent, "{" + NS + "}" + name, attrs or {})


def cell(row, ref, value, style=0):
    if value is None:
        return
    c = element(row, "c", {"r": ref, "s": str(style)})
    if isinstance(value, (int, float)) and math.isfinite(value):
        element(c, "v").text = str(value)
    else:
        c.set("t", "inlineStr")
        text = element(element(c, "is"), "t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
        # XML 1.0 не допускает управляющие символы, встречающиеся в импорте.
        text.text = "".join(x for x in str(value) if x in "\t\n\r" or 32 <= ord(x) <= 0xD7FF
                            or 0xE000 <= ord(x) <= 0xFFFD or 0x10000 <= ord(x) <= 0x10FFFF)


def write_report(day, rows, path):
    sheet = ET.Element("{" + NS + "}worksheet")
    last_col = column_name(len(COLUMNS))
    element(sheet, "dimension", {"ref": "A1:%s%d" % (last_col, len(rows) + 5)})
    view = element(element(sheet, "sheetViews"), "sheetView", {"workbookViewId": "0"})
    element(view, "pane", {"xSplit": "2", "ySplit": "5", "topLeftCell": "C6",
                           "activePane": "bottomRight", "state": "frozen"})
    cols = element(sheet, "cols")
    for n, (key, _) in enumerate(COLUMNS, 1):
        width = 7 if key in ("sr", "loom") else 24 if key in ("loto", "design") else 16
        element(cols, "col", {"min": str(n), "max": str(n), "width": str(width), "customWidth": "1"})
    data = element(sheet, "sheetData")
    for n, label, value in ((1, "Производственный отчёт", day),
                            (2, "Выработка 100%, кг", sum(r.get("prod100") or 0 for r in rows)),
                            (3, "Фактическая выработка, кг", sum(r.get("achieved") or 0 for r in rows))):
        row = element(data, "row", {"r": str(n)})
        cell(row, "A" + str(n), label, 1)
        cell(row, "E" + str(n), value, 2 if n > 1 else 0)
    header = element(data, "row", {"r": "5", "ht": "44", "customHeight": "1"})
    for n, (_, title) in enumerate(COLUMNS, 1):
        cell(header, column_name(n) + "5", title, 1)
    for number, record in enumerate(rows, 6):
        row = element(data, "row", {"r": str(number)})
        for n, (key, _) in enumerate(COLUMNS, 1):
            if "_mend_" in key:
                kind, index = key.split("_mend_")
                values = (record.get("mending") or {}).get(kind) or []
                value = values[int(index)] if len(values) > int(index) else None
            else:
                value = record.get(key)
            cell(row, column_name(n) + str(number), value, 2 if isinstance(value, float) else 0)
    element(sheet, "autoFilter", {"ref": "A5:%s%d" % (last_col, max(5, len(rows) + 5))})
    element(sheet, "pageMargins", {"left": "0.3", "right": "0.3", "top": "0.5", "bottom": "0.5", "header": "0.2", "footer": "0.2"})
    element(sheet, "pageSetup", {"orientation": "landscape", "paperSize": "8"})
    workbook = ET.Element("{" + NS + "}workbook")
    element(element(workbook, "sheets"), "sheet", {"name": "TOYOTA", "sheetId": "1", "{" + REL + "}id": "rId1"})
    content_types = '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
      <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
      <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    relationships = 'http://schemas.openxmlformats.org/package/2006/relationships'
    styles = '''<styleSheet xmlns="%s"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
      <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFDCE8FA"/><bgColor indexed="64"/></patternFill></fill></fills>
      <borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
      <cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="2" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>
      <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''' % NS
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".report-", suffix=".xlsx", dir=target.parent)
    os.close(fd)
    try:
        with ZipFile(tmp, "w", ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types)
            z.writestr("_rels/.rels", '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/officeDocument" Target="xl/workbook.xml"/></Relationships>' % (relationships, REL))
            z.writestr("xl/workbook.xml", ET.tostring(workbook, encoding="utf-8", xml_declaration=True))
            z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="%s/styles" Target="styles.xml"/></Relationships>' % (relationships, REL, REL))
            z.writestr("xl/styles.xml", styles)
            z.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet, encoding="utf-8", xml_declaration=True))
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return str(target)
