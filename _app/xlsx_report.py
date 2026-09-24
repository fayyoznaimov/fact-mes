"""Переносимый XLSX-отчёт: stdlib, без COM Excel и без изменения шаблона XLSB.

Лист TOYOTA повторяет раскладку ручного отчёта цеха («New Production Report»):
шапка с итогами в строках 1–3, заголовки групп в 4-й, колонок в 5-й, станки с 6-й;
колонки A…AK как в шаблоне, AL — номер станка, AM:AP — ручные отметки
(абразия, программа дизайна), AR:AZ — среднее время устранения останова.
Итоги записаны формулами шаблона вместе с посчитанным значением, поэтому числа
видны и там, где формулы не пересчитываются. Строки — inlineStr, поэтому
названия не становятся формулами.
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

FIRST = 6                      # первая строка станков, как в шаблоне

# Колонки листа: (буква, ключ строки make_excel_report.build, заголовок строки 5).
# Ключ None — колонка считается формулой или заполняется в цеху руками.
COLUMNS = [
    ("A", "sr", "Sr#"), ("B", "size", "Size cm"), ("C", "rpm", "RPM"), ("D", "ppt", "PPT"),
    ("E", "weight", "P Pc. Wt Kg"), ("F", "panels", "# of panels"), ("G", None, "100% Prod. Kg"),
    ("H", "design", "MODEL (DIZAYN)"), ("I", "gsm", "GSM"), ("J", "pile_count", "Pile Count (vors)"),
    ("K", "ground_count", "Ground Count (karenoy)"), ("L", "loto", "LOTO"),
    ("M", "weft1", "WEFT (UTOG)"), ("N", "weft2", "WEFT (UTOG)"), ("O", "weft3", "WEFT (UTOG)"),
    ("P", "weft4", "WEFT (UTOG)"), ("Q", "loom", "L#"),
    ("R", "eff_a", "A"), ("S", "eff_b", "B"), ("T", "eff_c", "C"), ("U", None, "Total"),
    ("V", "pile_a", "A"), ("W", "pile_b", "B"), ("X", "pile_c", "C"), ("Y", None, "Total"),
    ("Z", "weft_a", "A"), ("AA", "weft_b", "B"), ("AB", "weft_c", "C"), ("AC", None, "Total"),
    ("AD", "ground_a", "A"), ("AE", "ground_b", "B"), ("AF", "ground_c", "C"), ("AG", None, "Total"),
    ("AH", "other_a", "A"), ("AI", "other_b", "B"), ("AJ", "other_c", "C"), ("AK", "other_total", "Total"),
    ("AL", "loom", "L#"), ("AM", None, "ABR P (vors)"), ("AN", None, "ABR G (karinoy)"),
    ("AO", None, ""), ("AP", None, "Design (program)"),
]
MEND_COL = 44                  # AR: устранение ворса A/B/C, утка A/B/C, основы A/B/C
MEND_TITLES = ["Vors A", "Vors B", "Vors C", "Utog A", "Utog B", "Utog C",
               "Karenoy A", "Karenoy B", "Karenoy C"]
GROUPS = (("R", "Efficiency"), ("V", "Pile (Vors)"), ("Z", "Weft (Utog)"),
          ("AD", "Ground (Karenoy)"), ("AH", "Other Stops"), ("AM", "ABRAZES"))
WIDTHS = {"A": 5, "B": 9, "C": 6, "D": 7, "E": 7, "F": 6, "G": 9, "H": 13, "I": 6, "J": 8,
          "K": 9, "L": 14, "M": 10, "N": 10, "O": 10, "P": 10, "Q": 5, "AL": 5, "AM": 8,
          "AN": 8, "AO": 8, "AP": 30}

# Стили (порядок в cellXfs ниже).
S_TEXT, S_HEAD, S_CELL, S_INT, S_DEC1, S_DEC3, S_LABEL, S_TOT1, S_TOT0 = range(9)


def column_name(number):
    out = ""
    while number:
        number, rem = divmod(number - 1, 26)
        out = chr(65 + rem) + out
    return out


def column_number(name):
    n = 0
    for ch in name:
        n = n * 26 + ord(ch) - 64
    return n


def element(parent, name, attrs=None):
    return ET.SubElement(parent, "{" + NS + "}" + name, attrs or {})


def clean(value):
    # XML 1.0 не допускает управляющие символы, встречающиеся в импорте.
    return "".join(x for x in str(value) if x in "\t\n\r" or 32 <= ord(x) <= 0xD7FF
                   or 0xE000 <= ord(x) <= 0xFFFD or 0x10000 <= ord(x) <= 0x10FFFF)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def cell(row, ref, value, style=0, formula=None):
    """Ячейка со значением; с формулой — значение пишется как посчитанный результат."""
    if value is None and formula is None:
        if style:
            element(row, "c", {"r": ref, "s": str(style)})
        return
    c = element(row, "c", {"r": ref, "s": str(style)})
    if formula is not None:
        element(c, "f").text = formula
        if number(value):
            element(c, "v").text = repr(float(value)) if isinstance(value, float) else str(value)
        else:
            c.set("t", "str")
            element(c, "v").text = clean("" if value is None else value)
    elif number(value):
        element(c, "v").text = repr(float(value)) if isinstance(value, float) else str(value)
    else:
        c.set("t", "inlineStr")
        text = element(element(c, "is"), "t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
        text.text = clean(value)


def num(value):
    """Число из значения строки отчёта; пусто и текст — None."""
    if number(value):
        return value
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def avg(values):
    vals = [v for v in values if number(v)]
    return sum(vals) / len(vals) if vals else None


def write_report(day, rows, path):
    last = FIRST + max(len(rows), 1) - 1
    last_col = column_name(MEND_COL + len(MEND_TITLES) - 1)
    sheet = ET.Element("{" + NS + "}worksheet")
    element(sheet, "dimension", {"ref": "A1:%s%d" % (last_col, last)})
    view = element(element(sheet, "sheetViews"), "sheetView", {"workbookViewId": "0", "zoomScale": "85"})
    element(view, "pane", {"ySplit": str(FIRST - 1), "topLeftCell": "A%d" % FIRST,
                           "activePane": "bottomLeft", "state": "frozen"})
    cols = element(sheet, "cols")
    for n in range(1, MEND_COL + len(MEND_TITLES)):
        name = column_name(n)
        width = WIDTHS.get(name, 11 if n >= MEND_COL else 6)
        element(cols, "col", {"min": str(n), "max": str(n), "width": str(width), "customWidth": "1"})
    data = element(sheet, "sheetData")

    # --- значения по станкам (для посчитанных итогов) ---
    calc = []
    for r in rows:
        c, e, f, d = (num(r.get(k)) for k in ("rpm", "weight", "panels", "ppt"))
        eff = [num(r.get("eff_" + s)) for s in "abc"]
        calc.append({
            "loom": str(r.get("loom") or ""),
            "rpm": c,
            "G": f * e * (c * 24 * 60 / d) if (c and e and f and d) else None,
            "U": avg(eff),
            **{k + "_" + s: num(r.get(k + "_" + s)) or 0
               for k in ("pile", "weft", "ground", "other") for s in "abc"},
            **{"eff_" + s: eff[i] for i, s in enumerate("abc")},
        })
    for x in calc:
        for k in ("pile", "weft", "ground", "other"):
            x[k + "_total"] = sum(x[k + "_" + s] for s in "abc")

    # --- шапка: строки 1–3 ---
    prod100 = sum(x["G"] or 0 for x in calc)
    achieved = sum(num(r.get("achieved")) or 0 for r in rows)
    rng = lambda col: "%s%d:%s%d" % (col, FIRST, col, last)
    summary_cols = [("R", "eff_a"), ("S", "eff_b"), ("T", "eff_c"), ("U", "U")] + [
        (col, key) for col, key, _ in COLUMNS[21:37] if key or col in ("Y", "AC", "AG")]
    totals_key = {"Y": "pile_total", "AC": "weft_total", "AG": "ground_total"}
    heads = {1: ("All Total", None), 2: ("Dobby Total", "D"), 3: ("Jacquard Total", "J")}
    for n in (1, 2, 3):
        row = element(data, "row", {"r": str(n)})
        if n == 1:
            cell(row, "C1", "Avg. RPM", S_LABEL)
        if n == 3:
            cell(row, "C3", avg([x["rpm"] for x in calc]), S_TOT0, "IFERROR(AVERAGE(%s),\"\")" % rng("C"))
        cell(row, "E%d" % n, ("100% Production", "Achieved Production", "Production Efficiency")[n - 1], S_LABEL)
        if n == 1:
            cell(row, "J1", prod100, S_TOT1, "SUM(%s)" % rng("G"))
        elif n == 2:
            cell(row, "J2", round(achieved, 1), S_TOT1)
        else:
            cell(row, "J3", achieved / prod100 * 100 if prod100 else "", S_TOT1, "IFERROR(J2/J1*100,\"\")")
        title, prefix = heads[n]
        cell(row, "O%d" % n, title, S_LABEL)
        group = [x for x in calc if prefix is None or x["loom"].upper().startswith(prefix)]
        for col, key in summary_cols:
            key = totals_key.get(col, key)
            ref = "%s%d" % (col, n)
            if col == "U":
                # Итог КПД в шаблоне — среднее трёх смен этой же строки.
                value = avg([avg([x["eff_" + s] for x in group]) for s in "abc"])
                cell(row, ref, "" if value is None else value, S_TOT1,
                     "IFERROR(AVERAGE(R{0}:T{0}),\"\")".format(n))
            elif col in ("R", "S", "T"):
                value = avg([x[key] for x in group])
                f = ("IFERROR(AVERAGE(%s),\"\")" % rng(col) if prefix is None else
                     "IFERROR(AVERAGEIF(%s,\"%s*\",%s),\"\")" % (rng("Q"), prefix, rng(col)))
                cell(row, ref, "" if value is None else value, S_TOT1, f)
            else:
                value = sum(x[key] for x in group)
                f = ("SUM(%s)" % rng(col) if prefix is None else
                     "SUMIF(%s,\"%s*\",%s)" % (rng("Q"), prefix, rng(col)))
                cell(row, ref, value, S_TOT0, f)

    # --- строка 4: группы колонок и дата отчёта ---
    row = element(data, "row", {"r": "4"})
    p = day.split(".")
    for col, title in GROUPS:
        cell(row, col + "4", title, S_HEAD)
    cell(row, "AP4", "%s,%s,%s" % (p[2], p[1], p[0]) if len(p) == 3 else day, S_HEAD)
    for i in range(0, len(MEND_TITLES), 3):
        cell(row, column_name(MEND_COL + i) + "4", "Mending time, sek", S_HEAD)

    # --- строка 5: заголовки колонок ---
    row = element(data, "row", {"r": "5", "ht": "45", "customHeight": "1"})
    for col, _, title in COLUMNS:
        cell(row, col + "5", title or None, S_HEAD)
    for i, title in enumerate(MEND_TITLES):
        cell(row, column_name(MEND_COL + i) + "5", title, S_HEAD)

    # --- станки ---
    for i, (r, x) in enumerate(zip(rows, calc)):
        n = FIRST + i
        row = element(data, "row", {"r": str(n)})
        formulas = {
            "G": ("F{0}*E{0}*(C{0}*24*60/D{0})".format(n), x["G"], S_DEC1),
            "U": ("IFERROR(AVERAGE(R{0}:T{0}),\"\")".format(n), "" if x["U"] is None else x["U"], S_DEC1),
            "Y": ("X{0}+W{0}+V{0}".format(n), x["pile_total"], S_INT),
            "AC": ("AB{0}+AA{0}+Z{0}".format(n), x["weft_total"], S_INT),
            "AG": ("AF{0}+AE{0}+AD{0}".format(n), x["ground_total"], S_INT),
        }
        for col, key, _ in COLUMNS:
            ref = "%s%d" % (col, n)
            if col in formulas:
                f, value, style = formulas[col]
                if col == "G" and value is None:
                    cell(row, ref, None, S_CELL)        # нет PPT/веса — пусто, а не #DIV/0!
                else:
                    cell(row, ref, value, style, f)
                continue
            value = r.get(key) if key else None
            if value == "":
                value = None
            style = S_DEC3 if col == "E" else S_INT if number(value) else S_CELL
            cell(row, ref, value, style)
        mend = r.get("mending") or {}
        for j, kind in enumerate(("vors", "utog", "karenoy")):
            vals = mend.get(kind) or []
            for s in range(3):
                v = vals[s] if s < len(vals) else None
                cell(row, column_name(MEND_COL + j * 3 + s) + str(n),
                     None if v in ("", None) else v, S_INT)

    element(sheet, "autoFilter", {"ref": "A5:AP%d" % last})
    element(sheet, "pageMargins", {"left": "0.2", "right": "0.2", "top": "0.4", "bottom": "0.4", "header": "0.2", "footer": "0.2"})
    element(sheet, "pageSetup", {"orientation": "landscape", "paperSize": "8", "fitToHeight": "0"})

    workbook = ET.Element("{" + NS + "}workbook")
    element(element(workbook, "sheets"), "sheet", {"name": "TOYOTA", "sheetId": "1", "{" + REL + "}id": "rId1"})
    element(workbook, "calcPr", {"calcId": "191029", "fullCalcOnLoad": "1"})
    content_types = '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
      <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
      <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    relationships = 'http://schemas.openxmlformats.org/package/2006/relationships'
    thin = '<left style="thin"><color rgb="FF808080"/></left><right style="thin"><color rgb="FF808080"/></right><top style="thin"><color rgb="FF808080"/></top><bottom style="thin"><color rgb="FF808080"/></bottom><diagonal/>'
    styles = '''<styleSheet xmlns="%s">
      <numFmts count="2"><numFmt numFmtId="164" formatCode="0.0"/><numFmt numFmtId="165" formatCode="0.000"/></numFmts>
      <fonts count="2"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="10"/><name val="Arial"/></font></fonts>
      <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill></fills>
      <borders count="2"><border/><border>%s</border></borders>
      <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
      <cellXfs count="9">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
        <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
        <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
        <xf numFmtId="1" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
        <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
        <xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
        <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
        <xf numFmtId="164" fontId="1" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
        <xf numFmtId="1" fontId="1" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
      </cellXfs>
      <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''' % (NS, thin)
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
