"""План цеха по станкам: какой заказ, изделие и ворс на каждом станке в каждый день.

План составляется во вкладке «План» (перетаскиванием заказов из 1С) или
загружается из Excel («TOYOTA - LOOM PLAN»): строка станка — изделие по дням,
под ней ворс и номер производственного заказа. Изделие записано так:

    70x140 J301/6 (420GSM)   размер 70×140, дизайн J301, клиент 6 (цифра после
                             косой), плотность 420 GSM

Заказ 1С — это набор изделий (размер × дизайн × GSM), у каждого своя техкарта:
PPT, вес, панели, пряжа. Поэтому клетка плана хранит не только номер заказа, но
и изделие (product_code техкарты). Изделие подбирается само по размеру, GSM и
дизайну клетки (pick = auto); если подходят несколько — не гадаем (ambiguous),
изделие выбирают руками (manual), и ручной выбор больше не трогается.

По плану:
    факт изделия = полотенца станка в дни плана (без связки кодов ткани);
    отчёт за день берёт PPT, вес, панели, GSM, пряжу и лот из техкарты изделия,
    которое стоит на станке по плану, — вводить руками не нужно.
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import cache
from storage import fact, shop

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
PRODUCT = re.compile(r"^(\d{2,3})\s*[xх×*]\s*(\d{2,3})\s+(.+?)\s*/\s*(\d+)\s*"
                     r"(?:\(\s*(\d*)\s*GSM\s*\))?", re.I)
SIZE = re.compile(r"(\d{2,3})\s*[*xх×X]\s*(\d{2,3})")
LOOM = re.compile(r"^[A-Z]{1,2}\d{1,3}$")
MAX_GRID_DAYS = 62
CELL_KEYS = ("product", "size", "design", "client", "gsm", "pile_yarn")


def _loom_key(loom):
    m = re.match(r"^([A-Za-z]+)(\d+)$", loom or "")
    return (m.group(1), int(m.group(2))) if m else (loom or "", 0)


def _xl_date(v):
    """Дата из ячейки: число Excel (46272) или текст 07.09.2026."""
    if re.fullmatch(r"\d{5}(\.\d+)?", v):
        d = date(1899, 12, 30) + timedelta(days=int(float(v)))
    else:
        try:
            d = datetime.strptime(v[:10], "%d.%m.%Y").date()
        except ValueError:
            return None
    return d.strftime("%Y.%m.%d") if 2020 <= d.year <= 2040 else None


def _cells(data):
    """{(строка, колонка): текст} первого листа xlsx — без сторонних библиотек."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("это не файл Excel (.xlsx)")
    names = z.namelist()
    ss = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si"):
            ss.append("".join(t.text or "" for t in si.iter(NS + "t")))
    sheets = sorted((n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                    key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
    if not sheets:
        raise ValueError("в файле нет листов")
    out = {}
    for c in ET.fromstring(z.read(sheets[0])).iter(NS + "c"):
        m = re.match(r"([A-Z]+)(\d+)", c.get("r") or "")
        if not m:
            continue
        col = 0
        for ch in m.group(1):
            col = col * 26 + ord(ch) - 64
        t, v = c.get("t"), c.find(NS + "v")
        if t == "s" and v is not None:
            val = ss[int(v.text)]
        elif t == "inlineStr":
            val = "".join(x.text or "" for x in c.iter(NS + "t"))
        else:
            val = v.text if v is not None else ""
        val = re.sub(r"\s+", " ", (val or "").strip())
        if val:
            out[(int(m.group(2)), col - 1)] = val
    return out


def _order(v):
    v = (v or "").strip()
    return v[:-2] if re.fullmatch(r"\d+\.0", v) else v


def parse(data):
    """Разбор файла плана: строка дат, строки станков, под ними «Ворс» и «ORDER #»."""
    cells = _cells(data)
    if not cells:
        raise ValueError("лист пустой")
    maxr = max(r for r, _ in cells)
    best = None
    for r in range(1, min(maxr, 20) + 1):
        ds = {c: d for (rr, c), v in cells.items() if rr == r for d in [_xl_date(v)] if d}
        if ds and (best is None or len(ds) > len(best[1])):
            best = (r, ds)
    if not best:
        raise ValueError("не нашёл строку с датами")
    hdr, dates = best

    def label_row(r, word):
        for rr in range(r + 1, r + 4):
            text = (cells.get((rr, 0), "") + " " + cells.get((rr, 1), "")).upper()
            if word in text:
                return rr
        return None

    rows = []
    for r in sorted(r for (r, c), v in cells.items() if c == 0 and r > hdr and LOOM.match(v.upper())):
        loom = cells[(r, 0)].upper()
        pile_r, order_r = label_row(r, "ВОРС"), label_row(r, "ORDER")
        for c, day in dates.items():
            text = cells.get((r, c), "")
            order = _order(cells.get((order_r, c), "")) if order_r else ""
            pile = cells.get((pile_r, c), "") if pile_r else ""
            if not (text or order):
                continue
            m = PRODUCT.match(text)
            row = {"loom": loom, "day": day, "order_no": order or None, "product": text or None,
                   "size": "%sx%s" % (m.group(1), m.group(2)) if m else None,
                   "design": m.group(3).strip() if m else None,
                   "client": m.group(4) if m else None,
                   "gsm": int(m.group(5)) if m and m.group(5) else None,
                   "pile_yarn": pile or None, "note": None}
            if text and not m:
                if re.fullmatch(r"[A-Za-z]{1,6}\d{2,4}", text):
                    row["design"] = text              # только дизайн: «D150»
                else:
                    row["note"] = text                # «Praborka 35 sm», «23 рулон берасиз»
            rows.append(row)
    return {"rows": rows, "days": sorted(set(dates.values()))}


def import_xlsx(data, who=""):
    """Загрузить план: дни из файла заменяются целиком, прошлые остаются."""
    p = parse(data)
    if not p["rows"]:
        raise ValueError("в файле не нашёл ни одного станка с планом")
    lo, hi = p["days"][0], p["days"][-1]
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    db = shop()
    try:
        db.execute("DELETE FROM loom_plan WHERE day BETWEEN ? AND ?", (lo, hi))
        db.executemany(
            "INSERT OR REPLACE INTO loom_plan (loom, day, order_no, product, size, design, client,"
            " gsm, pile_yarn, note, loaded_by, loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["loom"], r["day"], r["order_no"], r["product"], r["size"], r["design"], r["client"],
              r["gsm"], r["pile_yarn"], r["note"], who, now) for r in p["rows"]])
        db.commit()
    finally:
        db.close()
    picked = rematch(days=(lo, hi))
    rebuild_reports(lo, hi)
    notes = defaultdict(int)
    for r in p["rows"]:
        if r["note"]:
            notes[r["note"]] += 1
    return {"from": lo, "to": hi, "looms": len({r["loom"] for r in p["rows"]}),
            "cells": len(p["rows"]), "picked": picked,
            "orders": sorted({r["order_no"] for r in p["rows"] if r["order_no"]}),
            "notes": [n for n, _ in sorted(notes.items(), key=lambda x: -x[1])][:8]}


# --- изделие заказа в клетке ----------------------------------------------------

def _parse_product(text):
    """Поля клетки из текста изделия, как его пишут в плане."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:120]
    m = PRODUCT.match(text)
    if m:
        return {"product": text, "size": "%sx%s" % (m.group(1), m.group(2)),
                "design": m.group(3).strip(), "client": m.group(4),
                "gsm": int(m.group(5)) if m.group(5) else None}
    design = text if re.fullmatch(r"[A-Za-z]{1,6}\d{2,4}", text) else None
    return {"product": text or None, "size": None, "design": design, "client": None, "gsm": None}


def _size_key(text):
    """«30*50 D», «70x140» -> «30x50», «70x140»."""
    m = SIZE.search(text or "")
    return "%sx%s" % (m.group(1), m.group(2)) if m else None


def _loom_kind(size):
    """«30*50 D» -> «D»: 1С пишет после размера, на каких станках делают изделие."""
    m = re.search(r"\d\s*[*xх×X]\s*\d+\s*([A-Za-z])\b", size or "")
    return m.group(1).upper() if m else None


def _card_product(size, code):
    """Из техкарты 1С: «30*50 D», «3050  D324 450» -> («30x50», «D324»)."""
    design = re.sub(r"\s*\d{3,4}$", "", re.sub(r"^\d+\s*", "", (code or "").strip())).strip()
    return _size_key(size), design or None


def _norm_design(d):
    return re.sub(r"[\s\-_.]", "", str(d or "")).upper()


def _same_design(a, b):
    """«J401» и «J401-SH» — один дизайн: 1С дописывает к номеру дизайна суффикс.
    Сравниваем основу — буквы и номер; у дизайна без номера («Terry» и
    «TerryCloth») — начало названия."""
    a, b = _norm_design(a), _norm_design(b)
    if not a or not b:
        return False
    base = lambda s: (re.match(r"[A-Z]*\d+", s) or [None])[0]
    if base(a) and base(b):
        return base(a) == base(b)
    return a.startswith(b) or b.startswith(a)


def _cards_by_order(db):
    out = defaultdict(list)
    for r in db.execute("SELECT product_code, order_number, size, gsm FROM tech_card"
                        " WHERE order_number IS NOT NULL AND order_number <> ''"):
        size, design = _card_product(r["size"], r["product_code"])
        out[str(r["order_number"])].append({"product_code": r["product_code"], "size": size,
                                            "design": design, "gsm": r["gsm"],
                                            "kind": _loom_kind(r["size"])})
    return out


def match_card(cell, cands):
    """Какое изделие заказа стоит в клетке: (артикул, pick).

    Изделие у заказа одно — оно. Иначе среди изделий того же размера ищем по
    GSM и дизайну вместе, потом по GSM, потом по дизайну; из нескольких равных
    выбираем по типу станка (1С пишет «30*50 D»). Подходят несколько — не
    гадаем: ambiguous; не подходит ни одно (в заказе 1С нет такого размера,
    GSM и дизайна) — nomatch. В обоих случаях изделие выбирают руками."""
    if not cands:
        return None, None
    if len(cands) == 1:
        return cands[0]["product_code"], "auto"
    pool = [c for c in cands if c["size"] == cell.get("size")] if cell.get("size") else list(cands)
    if not pool:
        return None, "nomatch"
    want, gsm = cell.get("design"), cell.get("gsm")
    by_gsm = [c for c in pool if gsm and c["gsm"] and int(c["gsm"]) == int(gsm)]
    by_design = [c for c in pool if want and _same_design(c["design"], want)]
    groups = [[c for c in by_gsm if c in by_design], by_gsm, by_design]
    if not gsm and not want:
        groups.append(pool)
    m = re.match(r"[A-Za-z]+", cell.get("loom") or "")
    kind = m.group(0).upper() if m else None
    for grp in groups:
        if len(grp) > 1 and kind:
            grp = [c for c in grp if c["kind"] == kind] or grp
        if len(grp) == 1:
            return grp[0]["product_code"], "auto"
        if grp:
            return None, "ambiguous"
    return None, "nomatch"


def rematch(orders=None, days=None, cells=None):
    """Подобрать изделие 1С клеткам, где его не выбирали руками. orders — только
    эти заказы, days — (с, по), cells — [(станок, день)]. Возвращает счёт:
    сколько подобрано (auto), неоднозначно (ambiguous), без техкарт (none)."""
    db = shop()
    n = Counter()
    try:
        cards = _cards_by_order(db)
        sql = ("SELECT loom, day, order_no, size, design, gsm, product_code, pick FROM loom_plan"
               " WHERE order_no IS NOT NULL AND order_no <> '' AND COALESCE(pick, '') <> 'manual'")
        args = []
        if orders:
            sql += " AND order_no IN (%s)" % ",".join("?" * len(orders))
            args += [str(o) for o in orders]
        if days:
            sql += " AND day BETWEEN ? AND ?"
            args += list(days)
        rows = [dict(r) for r in db.execute(sql, args)]
        if cells is not None:
            want = set(cells)
            rows = [r for r in rows if (r["loom"], r["day"]) in want]
        for r in rows:
            pc, pick = match_card(r, cards.get(str(r["order_no"])))
            n[pick or "none"] += 1
            if (pc, pick) != (r["product_code"], r["pick"]):
                db.execute("UPDATE loom_plan SET product_code=?, pick=? WHERE loom=? AND day=?",
                           (pc, pick, r["loom"], r["day"]))
        db.commit()
    finally:
        db.close()
    cache.clear()
    return dict(n)


# --- заказы для палитры ---------------------------------------------------------

def catalog():
    """Заказы, которые можно ставить на станки: пришедшие из 1С (с изделиями) и уже
    стоящие в плане. Держим полминуты — палитра обновляется после каждой правки."""
    return cache.get(("plan_catalog",), 30, _catalog)


def _catalog():
    db = shop()
    plan = defaultdict(list)
    for r in db.execute("SELECT loom, day, order_no, product, size, design, client, gsm, pile_yarn,"
                        " product_code, pick FROM loom_plan"
                        " WHERE order_no IS NOT NULL AND order_no <> ''"):
        plan[str(r["order_no"])].append(dict(r))
    cards = defaultdict(list)
    for r in db.execute("SELECT * FROM tech_card WHERE order_number IS NOT NULL"
                        " AND order_number <> '' ORDER BY product_code"):
        cards[str(r["order_number"])].append(dict(r))
    yarn = defaultdict(dict)                 # (заказ, номенклатура) -> пряжа по местам
    for r in db.execute("SELECT order_number, product_code, slot, yarn_code, lot, grams"
                        " FROM tech_card_yarn"):
        yarn[(str(r["order_number"] or ""), r["product_code"])][r["slot"]] = {
            "yarn": r["yarn_code"], "lot": r["lot"], "grams": r["grams"]}
    orders = {str(r["order_no"]): dict(r) for r in db.execute(
        "SELECT order_no, SUM(qty_towels) qty, MIN(due_day) due_day, MIN(closed) closed"
        " FROM plan_order GROUP BY order_no")}
    db.close()
    stats = order_stats()["stats"]
    out = []
    for o in set(plan) | set(cards):
        cells, lines = plan.get(o, []), cards.get(o, [])
        e = {"order_no": o, "in_1c": bool(lines), "in_plan": bool(cells), "qty": None,
             "due_day": None, "closed": 0}
        top = Counter(tuple(c[k] for k in CELL_KEYS) for c in cells).most_common(1)
        e.update(zip(CELL_KEYS, top[0][0]) if top else ((k, None) for k in CELL_KEYS))
        clients = Counter(c["client"] for c in cells if c["client"]).most_common(1)
        e["client"] = e.get("client") or (clients[0][0] if clients else None)
        st = stats.get(o) or {}
        bp = st.get("by_product") or {}
        prods = []
        for card in lines:
            size, design = _card_product(card["size"], card["product_code"])
            ys = yarn.get((o, card["product_code"]), {})
            ps = bp.get(card["product_code"]) or {}
            prods.append({
                "product_code": card["product_code"], "size": size, "design": design,
                "gsm": card["gsm"], "qty": card["total_quantity"], "ppt": card["ppt"],
                "weight_kg": card["weight_kg"], "panels": card["panels"],
                "rolls": card["total_rolls"], "due_day": card["due_day"], "yarns": ys,
                "pile_yarn": (ys.get("vors") or {}).get("yarn"),
                "cells": ps.get("cells", 0), "done": ps.get("done", 0),
                "expected": ps.get("expected", 0),
                "looms": [l["loom"] for l in ps.get("looms", [])]})
        if lines:
            if len(lines) == 1:
                p = prods[0]
                for k in ("size", "design", "gsm", "pile_yarn"):
                    e[k] = e.get(k) or p[k]
            if not e.get("product"):
                e["product"] = (" ".join(x for x in (prods[0]["size"], prods[0]["design"]) if x)
                                if len(lines) == 1 else "изделий: %d" % len(lines))
            e["qty"] = sum(c["total_quantity"] or 0 for c in lines) or None
            e["due_day"] = min((c["due_day"] for c in lines if c["due_day"]), default=None)
            e["loaded_at"] = max((c["loaded_at"] or "" for c in lines), default=None)
        po = orders.get(o)
        if po:
            e["qty"] = e["qty"] or po["qty"]
            e["due_day"] = e["due_day"] or po["due_day"]
            e["closed"] = po["closed"] or 0
        e.update(products=prods, cells=len(cells),
                 unpicked=sum(1 for c in cells if lines and not c["product_code"]),
                 first_day=min((c["day"] for c in cells), default=None),
                 last_day=max((c["day"] for c in cells), default=None),
                 looms=sorted({c["loom"] for c in cells}, key=_loom_key),
                 done=st.get("done", 0), expected=st.get("expected", 0),
                 rate_now=st.get("rate_now", 0))
        out.append(e)
    out.sort(key=lambda e: (-int(e["order_no"]) if e["order_no"].isdigit() else 0, e["order_no"]))
    return out


def set_cells(changes, who=""):
    """Правка плана в приложении: [{loom, day, order_no, product_code?, note, product?}].

    product_code — изделие заказа, выбранное руками (перетащили изделие, выбрали
    в окне). Без него изделие подбирается само по размеру и GSM клетки. Пустые
    заказ и пометка — клетка очищается. product (текст как в плане) приходит,
    когда клетку переносят или копируют как есть. Каждая правка — в журнал."""
    if not isinstance(changes, list) or not changes:
        raise ValueError("изменений нет")
    if len(changes) > 3000:
        raise ValueError("за один раз — не больше 3000 клеток")
    cat = {e["order_no"]: e for e in _catalog()}
    # Изделие — пара (заказ, номенклатура): одна номенклатура бывает в разных заказах.
    lines = {(e["order_no"], p["product_code"]): (e, p) for e in cat.values() for p in e["products"]}
    owners = defaultdict(list)
    for o, p in lines:
        owners[p].append(o)
    db = shop()
    existing = {(r["loom"], r["day"]): dict(r) for r in db.execute(
        "SELECT loom, day, order_no, product, size, design, client, gsm, pile_yarn FROM loom_plan"
        " WHERE (loom, day) IN (%s)" % ",".join(["(?,?)"] * len(changes)),
        [x for ch in changes for x in (str(ch.get("loom") or "").strip().upper(),
                                       str(ch.get("day") or "").strip())])}
    db.close()
    rows = []
    for ch in changes:
        loom = str(ch.get("loom") or "").strip().upper()
        day = str(ch.get("day") or "").strip()
        if not LOOM.match(loom):
            raise ValueError("станок «%s» не опознан" % loom)
        try:
            datetime.strptime(day, "%Y.%m.%d")
        except ValueError:
            raise ValueError("день «%s»: нужна дата вида 2026.09.14" % day)
        order = _order(str(ch.get("order_no") or ""))
        pc = str(ch.get("product_code") or "").strip() or None
        note = re.sub(r"\s+", " ", str(ch.get("note") or "")).strip()[:120] or None
        if pc:
            if not order:
                if len(owners.get(pc, [])) != 1:
                    raise ValueError("изделие «%s» %s — укажите заказ" % (
                        pc, "есть в заказах %s" % ", ".join(owners[pc]) if owners.get(pc)
                        else "не найдено в заказах 1С"))
                order = owners[pc][0]
            if (order, pc) not in lines:
                raise ValueError("в заказе %s нет изделия «%s»" % (order, pc))
        cell = None
        if ch.get("product"):
            cell = _parse_product(ch["product"])
            cell["pile_yarn"] = ch.get("pile_yarn") or (cat.get(order) or {}).get("pile_yarn")
        elif pc:
            e, p = lines[(order, pc)]
            client = e.get("client")
            text = " ".join(x for x in (p["size"], (p["design"] or "") + ("/" + client if client else "")) if x)
            cell = {"product": text + (" (%s GSM)" % p["gsm"] if p["gsm"] else ""),
                    "size": p["size"], "design": p["design"], "client": client,
                    "gsm": p["gsm"], "pile_yarn": p["pile_yarn"]}
        elif order:
            e = cat.get(order)
            if not e:
                raise ValueError("заказа %s нет ни в 1С, ни в плане" % order)
            cell = {k: e.get(k) for k in CELL_KEYS}
            if len(e["products"]) > 1:
                # Изделий в заказе несколько, а какое — не сказали. Клетка, где уже
                # стоял этот заказ, сохраняет свой размер/GSM — по ним изделие и
                # подберётся. Пустая клетка остаётся «без изделия»: угадывать
                # самое частое изделие заказа — значит молча поставить не то.
                old = existing.get((loom, day)) or {}
                if str(old.get("order_no") or "") == order:
                    cell = {k: old.get(k) for k in CELL_KEYS}
                else:
                    cell = {k: None for k in CELL_KEYS}
                    cell["client"] = e.get("client")
        if cell is not None or order or note:
            pick = (ch.get("pick") if ch.get("pick") in ("auto", "manual") else "manual") if pc else None
            cell = dict(cell or {k: None for k in CELL_KEYS}, order_no=order or None, note=note,
                        product_code=pc, pick=pick)
        rows.append((loom, day, cell))

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    db = shop()
    try:
        for loom, day, cell in rows:
            old = db.execute("SELECT order_no, note FROM loom_plan WHERE loom=? AND day=?",
                             (loom, day)).fetchone()
            if cell is None:
                db.execute("DELETE FROM loom_plan WHERE loom=? AND day=?", (loom, day))
            else:
                db.execute(
                    "INSERT OR REPLACE INTO loom_plan (loom, day, order_no, product, size, design,"
                    " client, gsm, pile_yarn, note, product_code, pick, loaded_by, loaded_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (loom, day, cell["order_no"], cell["product"], cell["size"], cell["design"],
                     cell["client"], cell["gsm"], cell["pile_yarn"], cell["note"],
                     cell["product_code"], cell["pick"], who, now))
            db.execute("INSERT INTO loom_plan_log (at, who, loom, day, old_order, new_order,"
                       " old_note, new_note) VALUES (?,?,?,?,?,?,?,?)",
                       (now, who, loom, day, old["order_no"] if old else None,
                        cell and cell["order_no"], old["note"] if old else None,
                        cell and cell["note"]))
        db.commit()
    finally:
        db.close()
    auto = [(l, d) for l, d, c in rows if c and c["order_no"] and not c["product_code"]]
    picked = rematch(cells=auto) if auto else {}
    cache.clear()
    return {"ok": len(rows), "picked": picked,
            "report_days": _rebuild_days({d for _, d, _ in rows})}


# --- пересборка отчёта --------------------------------------------------------

def _rebuild_days(plan_days):
    """Пересобрать в фоне отчёт за те из этих дней, по которым уже есть смены."""
    if not plan_days:
        return []
    with fact() as f:
        days = sorted(r[0] for r in f.execute("SELECT DISTINCT day FROM shift_full WHERE day >= ?",
                                              (min(plan_days),)) if r[0] in plan_days)[-MAX_GRID_DAYS:]
    if days:
        import threading
        import reports
        threading.Thread(target=reports.rebuild_daily_reports, args=(days,), daemon=True,
                         name="plan-rebuild").start()
    return days


def rebuild_reports(date_from, date_to, orders=None):
    """Отчёт берёт PPT, вес, GSM и пряжу из техкарты изделия по плану, поэтому
    после нового плана или новой техкарты прошедшие дни плана пересобираются —
    в фоне, чтобы 1С и страница не ждали."""
    db = shop()
    sql = "SELECT DISTINCT day FROM loom_plan WHERE day BETWEEN ? AND ?"
    args = [date_from, date_to]
    if orders:
        sql += " AND order_no IN (%s)" % ",".join("?" * len(orders))
        args += [str(o) for o in orders]
    plan_days = {r[0] for r in db.execute(sql, args)}
    db.close()
    return _rebuild_days(plan_days)


# --- факт и сетка ---------------------------------------------------------------

def _fact_by_loom_day(date_from, date_to):
    """{(станок, день): {towels, run, stop, cloths}} — полотенца по счётчикам станка."""
    import metrics
    cloth_panels = metrics.panels_by_cloth()
    db = shop()
    plan = {(r["loom"], r["day"]): (str(r["order_no"] or ""), r["product_code"]) for r in db.execute(
        "SELECT loom, day, order_no, product_code FROM loom_plan WHERE day BETWEEN ? AND ?",
        (date_from, date_to))}
    card_panels, order_panels = {}, {}
    for r in db.execute("SELECT product_code, order_number, panels FROM tech_card"
                        " WHERE panels IS NOT NULL"):
        card_panels[(str(r["order_number"] or ""), r["product_code"])] = r["panels"]
        if r["order_number"]:
            order_panels.setdefault(str(r["order_number"]), set()).add(r["panels"])
    db.close()
    out = {}
    with fact() as f:
        for r in f.execute(
                "SELECT loom, day, cloth, SUM(pieces) pc, SUM(run_min) run, SUM(stop_min) stop"
                " FROM shift_full WHERE day BETWEEN ? AND ? AND run_min > 5"
                " GROUP BY loom, day, cloth", (date_from, date_to)):
            k = (r["loom"], r["day"])
            order, pc = plan.get(k, ("", None))
            # Панели — из техкарты изделия по плану; изделие не выбрано, но у всех
            # изделий заказа панелей одинаково — берём их; иначе — по коду ткани.
            same = order_panels.get(order) or set()
            pn = card_panels.get((order, pc)) or (next(iter(same)) if len(same) == 1 else None) \
                or cloth_panels.get(r["cloth"] or "", 1)
            a = out.setdefault(k, {"towels": 0.0, "rows": 0.0, "run": 0.0, "stop": 0.0,
                                   "cloths": set()})
            a["towels"] += (r["pc"] or 0) * pn
            a["rows"] += r["pc"] or 0
            a["run"] += r["run"] or 0
            a["stop"] += r["stop"] or 0
            if r["cloth"]:
                a["cloths"].add(r["cloth"])
    return out


def grid(date_from, date_to):
    """План по станкам за период и факт по тем же дням."""
    d0 = datetime.strptime(date_from, "%Y.%m.%d")
    cap = d0 + timedelta(days=MAX_GRID_DAYS - 1)
    try:
        d1 = min(datetime.strptime(date_to, "%Y.%m.%d"), cap)
    except (TypeError, ValueError):
        d1 = cap            # «по» не задано (или «9999») — весь допустимый период, а не 500
    days = [(d0 + timedelta(days=i)).strftime("%Y.%m.%d") for i in range((d1 - d0).days + 1)]
    db = shop()
    plan = [dict(r) for r in db.execute(
        "SELECT loom, day, order_no, product, size, design, client, gsm, pile_yarn, note,"
        " product_code, pick FROM loom_plan WHERE day BETWEEN ? AND ?", (days[0], days[-1]))]
    loaded = db.execute("SELECT MIN(day), MAX(day), MAX(loaded_at) FROM loom_plan").fetchone()
    # Секунды 1С на ряд изделия заказа: по ним — выполнение нормы (в них заложено 75 %).
    secs = {(str(r["order_number"] or ""), r["product_code"]): r["seconds_per_row"]
            for r in db.execute("SELECT order_number, product_code, seconds_per_row FROM tech_card"
                                " WHERE seconds_per_row > 0")}
    db.close()
    facts = _fact_by_loom_day(days[0], days[-1])
    # Все станки цеха, даже пустые: на пустой станок заказ и ставят.
    import people
    looms = {l: {} for l in people.all_looms()}
    for p in plan:
        looms.setdefault(p["loom"], {})[p["day"]] = p
    for (loom, day), a in facts.items():
        cell = looms.setdefault(loom, {}).setdefault(day, {"day": day})
        cal = a["run"] + a["stop"]
        sec = secs.get((str(cell.get("order_no") or ""), cell.get("product_code")))
        cell["fact"] = {"towels": int(a["towels"]), "eff": round(100 * a["run"] / cal, 1) if cal else 0,
                        "norm": round(100 * a["rows"] * sec / (cal * 60)) if sec and cal else None,
                        "cloth": ", ".join(sorted(a["cloths"]))}
    with fact() as f:
        last = f.execute("SELECT MAX(day) FROM shift_full").fetchone()[0]
    return {"days": days, "last_fact_day": last,
            "plan_from": loaded[0], "plan_to": loaded[1], "plan_loaded_at": loaded[2],
            "looms": [{"loom": l, "cells": looms[l]} for l in sorted(looms, key=_loom_key)]}


# --- прогресс заказов и изделий -------------------------------------------------

def order_stats():
    """По каждому заказу из плана и по каждому его изделию: станки, дни, сделано в
    прошедшие дни плана и сколько ждём к концу плана при нынешнем темпе станков.
    Держим минуту."""
    return cache.get(("order_stats",), 60, _order_stats)


def _new_stats(day):
    return {"looms": {}, "first_day": day, "last_day": day, "cells": 0, "done": 0.0,
            "future": defaultdict(float)}


def _add(s, c, towels, future, rate):
    s["cells"] += 1
    s["first_day"] = min(s["first_day"], c["day"])
    s["last_day"] = max(s["last_day"], c["day"])
    lm = s["looms"].setdefault(c["loom"], {"loom": c["loom"], "from_day": c["day"],
                                           "to_day": c["day"], "days": 0, "done": 0.0,
                                           "rate": round(rate)})
    lm["to_day"] = max(lm["to_day"], c["day"])
    lm["days"] += 1
    if future:
        s["future"][c["day"]] += rate
    else:
        s["done"] += towels
        lm["done"] += towels


def _finish(s, last):
    s["done"] = int(s["done"])
    s["left_cells"] = sum(1 for l in s["looms"].values() if l["to_day"] > last)
    s["expected"] = int(s["done"] + sum(s["future"].values()))
    s["rate_now"] = round(sum(l["rate"] for l in s["looms"].values() if l["to_day"] > last))
    s["future"] = sorted(s["future"].items())
    s["looms"] = sorted(({**l, "done": int(l["done"])} for l in s["looms"].values()),
                        key=lambda l: _loom_key(l["loom"]))
    return s


def _order_stats():
    db = shop()
    cells = [dict(r) for r in db.execute(
        "SELECT loom, day, order_no, product_code FROM loom_plan"
        " WHERE order_no IS NOT NULL AND order_no <> '' ORDER BY day")]
    db.close()
    if not cells:
        return {"stats": {}, "last_fact_day": None}
    with fact() as f:
        last = f.execute("SELECT MAX(day) FROM shift_full").fetchone()[0] or ""
    if not last:
        return {"stats": {}, "last_fact_day": None}
    week = (datetime.strptime(last, "%Y.%m.%d") - timedelta(days=10)).strftime("%Y.%m.%d")
    facts = _fact_by_loom_day(min(cells[0]["day"], week), last)

    # Темп станка: полотенец в сутки за последние 7 рабочих дней, с любым заказом.
    by_loom = defaultdict(list)
    for (loom, day), a in facts.items():
        by_loom[loom].append((day, a["towels"]))
    rate = {l: sum(t for _, t in sorted(v)[-7:]) / len(sorted(v)[-7:]) for l, v in by_loom.items()}

    stats = {}
    for c in cells:
        o = str(c["order_no"])
        s = stats.setdefault(o, dict(_new_stats(c["day"]), by_product={}))
        sub = s["by_product"].setdefault(c["product_code"] or "", _new_stats(c["day"]))
        future = c["day"] > last
        towels = 0 if future else (facts.get((c["loom"], c["day"])) or {}).get("towels", 0)
        for x in (s, sub):
            _add(x, c, towels, future, rate.get(c["loom"], 0))
    for s in stats.values():
        s["by_product"] = {k: _finish(v, last) for k, v in s["by_product"].items()}
        _finish(s, last)
    return {"stats": stats, "last_fact_day": last}
