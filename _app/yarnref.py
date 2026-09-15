"""Справочник пряжи из 1С: номенклатура вида «ПРЯЖА» — одна строка на пряжу и лот.

В 1С каждая партия пряжи — своя номенклатура: «16/1 Ring Иштихан Суровый Ворс
630 Лот №41». Здесь из неё берётся:
  пряжа        — колонка «Yarn» («16/1 Ring» -> «16/1 RING»), нет её — из названия;
  вид          — «Тип основа пряжи»: Ворс -> ворс, Основа -> грунт, Уток -> уток;
  лот          — колонка «Лот» (нет — из названия, после «Лот №»);
  поставщик, цвет, крутка, состав, вес мешка, бобин в мешке — как есть.

Пока API нет, справочник присылают файлом из 1С (табличный документ .mxl) —
`import_mxl`. Потом та же `load_items` примет JSON от 1С.
"""
import re
from datetime import datetime

import yarns
from storage import shop

KIND = {"ВОРС": "pile", "ОСНОВА": "ground", "ГРУНТ": "ground", "УТОК": "weft"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS yarn_lot (
    code TEXT PRIMARY KEY,           -- код номенклатуры 1С
    name TEXT NOT NULL,              -- полное название в 1С
    yarn TEXT,                       -- пряжа в справочном написании: «16/1 RING»
    kind TEXT,                       -- pile / ground / weft — «Тип основа пряжи»
    lot TEXT,
    supplier TEXT, color TEXT, twist TEXT, composition TEXT,
    bag_kg REAL, bobbins INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    loaded_by TEXT, loaded_at TEXT
);
CREATE INDEX IF NOT EXISTS yarn_lot_yarn ON yarn_lot(yarn);
"""

# Заголовок колонки в выгрузке 1С -> поле.
COLUMNS = {"Наименование": "name", "Код": "code", "Вид номенклатуры": "type", "Yarn": "yarn",
           "Поставщик": "supplier", "Цвет пряжи": "color", "Тип основа пряжи": "kind",
           "Крученость": "twist", "Состав пряжи": "composition", "Лот": "lot",
           "Вес мешка": "bag_kg", "Количество бобин в мешке": "bobbins"}

_CELL = re.compile(r'\{16,\d+,\s*\{1,(?:0|1,\s*\{"#","((?:[^"]|"")*)"\}\s*)\},\d+\}\s*,?((?:\s*\d+\s*,)*)')


def parse_mxl(data):
    """Табличный документ 1С (.mxl, текстовый) -> [{заголовок: значение}].

    Ячейки идут подряд; после каждой — номер следующей колонки или четвёрка
    «строка, 0, ячеек, колонка», когда начинается новая строка."""
    text = data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
    first = text.find("{16,")
    if first < 0:
        raise ValueError("это не табличный документ 1С")
    lead = [int(x) for x in re.findall(r"\d+", text[max(0, first - 40):first])[-4:]]
    row, col = (lead[0], lead[-1]) if len(lead) == 4 else (0, 0)
    rows = {}
    for m in _CELL.finditer(text, first):
        if m.group(1) is not None:
            rows.setdefault(row, {})[col] = m.group(1).replace('""', '"').strip()
        ints = [int(x) for x in re.findall(r"\d+", m.group(2) or "")]
        if len(ints) == 1:
            col = ints[0]
        elif len(ints) >= 4:
            row, col = ints[-4], ints[-1]
    if not rows:
        return []
    head = rows.pop(min(rows))
    return [{head[c]: v for c, v in r.items() if c in head} for _, r in sorted(rows.items())]


def _num(s):
    try:
        return float(str(s).replace(" ", "").replace("\xa0", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def item_from_row(r):
    """Строка выгрузки -> позиция справочника; не пряжа — None."""
    f = {COLUMNS[k]: v for k, v in r.items() if k in COLUMNS}
    if (f.get("type") or "").upper() != "ПРЯЖА" or not f.get("code"):
        return None
    from integration import parse_component
    name_yarn, name_lot = parse_component(f.get("name"))
    yarn = yarns.canon(f.get("yarn")) if f.get("yarn") else name_yarn
    return {"code": re.sub(r"\s+", "", f["code"]), "name": f.get("name") or "", "yarn": yarn or None,
            "kind": KIND.get((f.get("kind") or "").strip().upper()),
            "lot": (f.get("lot") or name_lot or "").strip() or None,
            "supplier": f.get("supplier") or None, "color": f.get("color") or None,
            "twist": f.get("twist") or None, "composition": f.get("composition") or None,
            "bag_kg": _num(f.get("bag_kg")), "bobbins": int(_num(f.get("bobbins")) or 0) or None}


def load_items(items, who="1С"):
    """Записать позиции (по коду 1С: есть — обновить) и дополнить справочник пряжи:
    новая пряжа добавляется с видом, у пряжи без вида вид проставляется."""
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    items = [i for i in items if i and i.get("code")]
    db = shop()
    try:
        db.executescript(SCHEMA)
        before = {r[0] for r in db.execute("SELECT code FROM yarn_lot")}
        db.executemany(
            "INSERT OR REPLACE INTO yarn_lot (code, name, yarn, kind, lot, supplier, color, twist,"
            " composition, bag_kg, bobbins, active, loaded_by, loaded_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            [(i["code"], i["name"], i["yarn"], i["kind"], i["lot"], i["supplier"], i["color"],
              i["twist"], i["composition"], i["bag_kg"], i["bobbins"], who, now) for i in items])
        # Справочник пряжи: вид — самый частый у её партий.
        kinds = {}
        for i in items:
            if i["yarn"]:
                kinds.setdefault(i["yarn"], {}).setdefault(i["kind"] or "", 0)
                kinds[i["yarn"]][i["kind"] or ""] += 1
        added, kinded = [], []
        for name, ks in kinds.items():
            kind = max((k for k in ks if k), key=lambda k: ks[k], default="")
            cur = db.execute("SELECT id, kind, active FROM yarn WHERE key=?", (yarns.key(name),)).fetchone()
            if not cur:
                db.execute("INSERT INTO yarn (name, key, kind) VALUES (?,?,?)", (name, yarns.key(name), kind))
                added.append(name)
            else:
                if kind and not cur["kind"]:
                    db.execute("UPDATE yarn SET kind=? WHERE id=?", (kind, cur["id"]))
                    kinded.append(name)
                if not cur["active"]:
                    db.execute("UPDATE yarn SET active=1 WHERE id=?", (cur["id"],))
        db.commit()
    finally:
        db.close()
    codes = {i["code"] for i in items}
    return {"items": len(items), "new": len(codes - before), "updated": len(codes & before),
            "yarns_added": sorted(added), "kind_set": sorted(kinded),
            "no_kind": sorted({i["name"] for i in items if not i["kind"]})}


def import_mxl(data, who="файл 1С"):
    rows = parse_mxl(data)
    items = [i for i in (item_from_row(r) for r in rows) if i]
    if not items:
        raise ValueError("в файле нет номенклатуры вида «ПРЯЖА»")
    res = load_items(items, who)
    res["rows"] = len(rows)
    return res


def lots_by_yarn():
    """{пряжа: [{lot, supplier, kind}]} — партии из справочника 1С."""
    db = shop()
    try:
        db.executescript(SCHEMA)
        out = {}
        for r in db.execute("SELECT yarn, lot, supplier, kind FROM yarn_lot"
                            " WHERE active=1 AND yarn IS NOT NULL AND lot IS NOT NULL"
                            " ORDER BY yarn, CAST(code AS INTEGER) DESC"):
            out.setdefault(r["yarn"], []).append({"lot": r["lot"], "supplier": r["supplier"], "kind": r["kind"]})
        return out
    finally:
        db.close()
