"""Планирование: заказ — станок — успеваем или нет.

Как это работает в цехе: заказ приходит из 1С, внутри заказа изделие с
дизайном, заказ ставится на станок. Дальше ничего вводить не надо — станок сам
считает ряды, а мы знаем, сколько полотенец в ряду и сколько пиков в изделии,
поэтому факт и прогноз считаются из счётчиков.

    план     сколько полотенец заказано и к какому дню;
    факт     ряды со счётчика станка × панели, с того дня, как заказ поставили;
    темп     полотенец в сутки — по последним рабочим дням этого станка;
    прогноз  когда закончим при нынешнем темпе, и успеваем ли к сроку.

Чтобы факт засчитался заказу, станок должен ткать именно это изделие. Код
ткани на станке набирают руками («3050X7360»), а артикул живёт в 1С
(«3060  D152 320»), поэтому изделие узнаём тремя путями по очереди:

    код ткани совпал с артикулом (без учёта пробелов и регистра);
    код ткани связан с артикулом в таблице связки (один раз, дальше само);
    код ткани пустой или «Undefined» — берём артикул, который мастер
    поставил на станок на дашборде.

Пиков на изделие берём в таком порядке: введённое руками или пришедшее из 1С,
затем техкарта 1С, затем расчёт по счётчикам. Расчёт — запасной вариант,
потому что под одним кодом ткани в цехе идут разные изделия.
"""
import re
from datetime import datetime, timedelta

import metrics
from storage import fact, shop

RATE_DAYS = 7           # по скольким последним дням считаем темп станка


def norm_code(code):
    """«70140%20Hotel%20» и «70140 HOTEL» — один и тот же артикул для сравнения."""
    return re.sub(r"[^a-z0-9]", "", (code or "").replace("%20", " ").lower())


def norm_day(value):
    """Дата в виде 2026.10.01 из того, что пришлёт человек или 1С:
    2026-10-01, 2026.10.01, 01.10.2026, 2026-10-01T00:00:00. Пусто — None."""
    v = str(value or "").strip()
    if not v:
        return None
    v = v[:10]
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y.%m.%d")
        except ValueError:
            continue
    raise ValueError("не понял дату «%s»: нужна вида 2026.10.01" % value)


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _loom_key(loom):
    m = re.match(r"^([A-Za-z]+)(\d+)$", loom or "")
    return (m.group(1), int(m.group(2))) if m else (loom or "", 0)


# --- пиков на изделие ---------------------------------------------------------

def ppt_sources():
    """Все известные значения PPT: ручные и из 1С, плюс техкарты."""
    db = shop()
    manual = {r["key"]: {"ppt": r["ppt"], "panels": r["panels"],
                         "source": r["source"] or "вручную"}
              for r in db.execute("SELECT key, ppt, panels, source FROM ppt_manual")}
    card = {r["product_code"]: {"ppt": r["ppt"], "panels": r["panels"], "source": "техкарта 1С"}
            for r in db.execute("SELECT product_code, ppt, panels FROM tech_card"
                                " WHERE ppt IS NOT NULL")}
    db.close()
    return manual, card


def set_ppt(key, ppt, panels=None, source="вручную", who=""):
    ppt = float(ppt)
    if not metrics.PPT_MIN <= ppt <= metrics.PPT_MAX:
        raise ValueError("пиков на изделие должно быть от %d до %d"
                         % (metrics.PPT_MIN, metrics.PPT_MAX))
    db = shop()
    db.execute("INSERT OR REPLACE INTO ppt_manual (key, ppt, panels, source, set_by, set_at)"
               " VALUES (?,?,?,?,?,?)",
               (key.strip(), ppt, int(panels) if panels else None, source, who, _now_iso()))
    db.commit()
    db.close()


def ppt_for(cloth="", product_code="", sources=None):
    """Пиков на изделие и откуда это значение взято. sources — готовый
    ppt_sources(), когда PPT нужен сразу для сотен заказов."""
    manual, card = sources or ppt_sources()
    for key in (product_code, cloth):
        if key and key in manual:
            m = manual[key]
            return m["ppt"], m["panels"], m["source"]
    if product_code and product_code in card:
        c = card[product_code]
        return c["ppt"], c["panels"], c["source"]
    derived = metrics.ppt_by_cloth().get(cloth or "")
    if derived:
        return (derived["ppt"], None,
                "счётчики станка" + ("" if derived["trusted"] else ", ненадёжно"))
    return None, None, "неизвестно"


# --- связка кода ткани с артикулом 1С ----------------------------------------

def cloth_map():
    db = shop()
    rows = {r["cloth_norm"]: dict(r) for r in db.execute("SELECT * FROM cloth_map")}
    db.close()
    return rows


def set_cloth_map(cloth_code, product_code, who=""):
    """Связать код ткани на станке с артикулом 1С; пустой артикул — снять связь."""
    key = norm_code(cloth_code)
    if not key:
        raise ValueError("пустой код ткани")
    db = shop()
    if (product_code or "").strip():
        db.execute("INSERT OR REPLACE INTO cloth_map (cloth_norm, cloth_code, product_code,"
                   " set_by, set_at) VALUES (?,?,?,?,?)",
                   (key, cloth_code.strip(), product_code.strip(), who, _now_iso()))
    else:
        db.execute("DELETE FROM cloth_map WHERE cloth_norm=?", (key,))
    db.commit()
    db.close()


def _card_codes():
    db = shop()
    codes = {r["product_code"] for r in db.execute("SELECT product_code FROM tech_card")}
    codes |= {r["product_code"] for r in db.execute("SELECT product_code FROM plan_order")}
    db.close()
    return codes


def unmapped_cloths(days=14):
    """Коды ткани, которые шли на станках, но не опознаются как артикул 1С.

    «Undefined» сюда не попадает: у него нет одного изделия — артикул таких
    станков ставит мастер на дашборде.
    """
    mapped = cloth_map()
    known = {norm_code(p) for p in _card_codes()}
    with fact() as db:
        last = db.execute("SELECT MAX(day) d FROM shift_full").fetchone()["d"]
        if not last:
            return []
        since = (datetime.strptime(last, "%Y.%m.%d") - timedelta(days=days)).strftime("%Y.%m.%d")
        rows = db.execute(
            "SELECT cloth, GROUP_CONCAT(DISTINCT loom) names, SUM(pieces) pc, MAX(day) last"
            " FROM shift_full WHERE day >= ? AND cloth IS NOT NULL AND cloth <> ''"
            " AND run_min > 5 GROUP BY cloth ORDER BY pc DESC", (since,)).fetchall()
    # «70140HOTEL500» и «70140 Hotel 500» — один код, набранный по-разному:
    # показываем одной строкой с самым частым написанием.
    groups = {}
    for r in rows:
        k = norm_code(r["cloth"])
        if not k or k in mapped or k in known or k == "undefined":
            continue
        g = groups.setdefault(k, {"cloth": r["cloth"], "variants": 0, "looms": set(),
                                  "rows": 0, "last_day": ""})
        g["variants"] += 1
        g["looms"] |= set(filter(None, (r["names"] or "").split(",")))
        g["rows"] += int(r["pc"] or 0)
        g["last_day"] = max(g["last_day"], r["last"] or "")
    out = [{**g, "looms": sorted(g["looms"], key=_loom_key)} for g in groups.values()]
    out.sort(key=lambda g: -g["rows"])
    return out


def cloth_map_list():
    return sorted(cloth_map().values(), key=lambda r: r["cloth_code"])


# --- заказы -------------------------------------------------------------------

def products():
    """Что можно поставить в план: артикулы из техкарт 1С и коды ткани со станков."""
    out = set(_card_codes())
    with fact() as db:
        for r in db.execute(
                "SELECT DISTINCT cloth FROM shift_full WHERE cloth IS NOT NULL AND cloth <> ''"
                " AND day >= (SELECT MAX(day) FROM shift_full) ORDER BY cloth"):
            out.add(r["cloth"])
    return sorted(out)


_UPSERT_ORDER = (
    "INSERT INTO plan_order (order_no, product_code, qty_towels, due_day, source, note)"
    " VALUES (?,?,?,?,?,?)"
    " ON CONFLICT(order_no, product_code) DO UPDATE SET"
    " qty_towels=excluded.qty_towels,"
    " due_day=COALESCE(excluded.due_day, plan_order.due_day),"
    " source=excluded.source,"
    " note=CASE WHEN excluded.note <> '' THEN excluded.note ELSE plan_order.note END")


def _order_row(order_no, product_code, qty_towels, due_day, source, note):
    order_no, product_code = str(order_no or "").strip(), (product_code or "").strip()
    if not order_no or not product_code:
        raise ValueError("нужны номер заказа и изделие")
    qty = int(float(qty_towels))
    if qty <= 0:
        raise ValueError("количество должно быть больше нуля")
    return (order_no, product_code, qty, norm_day(due_day), source, (note or "").strip()[:300])


def add_order(order_no, product_code, qty_towels, due_day=None, source="вручную", note=""):
    """Завести заказ или обновить тот же (номер + изделие).

    Обновление, а не замена строки: при замене у заказа менялся бы номер в базе,
    и станки, поставленные на него руками, терялись бы при каждом обмене с 1С.
    """
    row = _order_row(order_no, product_code, qty_towels, due_day, source, note)
    order_no, product_code = row[0], row[1]
    db = shop()
    db.execute(_UPSERT_ORDER, row)
    db.commit()
    row = db.execute("SELECT id FROM plan_order WHERE order_no=? AND product_code=?",
                     (order_no, product_code)).fetchone()
    db.close()
    return row["id"] if row else None


def assign_loom(order_id, loom, from_day=None, qty_towels=None, keep_existing=False):
    """Поставить заказ на станок. keep_existing — не трогать станок, который уже
    стоит на заказе: повторный обмен с 1С не должен сдвигать день начала."""
    from_day = norm_day(from_day) or datetime.now().strftime("%Y.%m.%d")
    loom = (loom or "").strip().upper()
    if not loom:
        raise ValueError("не указан станок")
    db = shop()
    db.execute(("INSERT OR IGNORE" if keep_existing else "INSERT OR REPLACE") +
               " INTO plan_loom (order_id, loom, from_day, qty_towels) VALUES (?,?,?,?)",
               (order_id, loom, from_day, int(qty_towels) if qty_towels else None))
    db.commit()
    db.close()


def drop_loom(order_id, loom):
    db = shop()
    db.execute("DELETE FROM plan_loom WHERE order_id=? AND loom=?", (order_id, loom))
    db.commit()
    db.close()


def close_order(order_id, closed=True):
    db = shop()
    db.execute("UPDATE plan_order SET closed=? WHERE id=?", (1 if closed else 0, order_id))
    db.commit()
    db.close()


def import_from_1c():
    """Заводит заказы по техкартам 1С: изделие, количество и срок.

    Станки 1С называет списком «где изделие можно делать» — на один станок
    претендует много изделий, поэтому на станки их не ставим: какой станок в
    какой день делает заказ, говорит план цеха (loomplan.py)."""
    db = shop()
    cards = [dict(r) for r in db.execute(
        "SELECT product_code, order_number, total_quantity, due_day FROM tech_card"
        " WHERE total_quantity > 0")]
    by_product = {}
    for r in db.execute("SELECT product_code, loom FROM tech_card_loom"):
        by_product.setdefault(r["product_code"], []).append(r["loom"])
    db.close()
    if not cards:
        return {"error": "техкарт из 1С нет: загрузите их или подключите 1С", "orders": 0, "looms": 0}

    # Заказ начинают считать с последнего дня, по которому есть данные станков,
    # а не с сегодняшнего: иначе факт будет нулевым, пока не выгрузят новую смену.
    with fact() as f:
        last = f.execute("SELECT MAX(day) d FROM shift_full").fetchone()["d"]
    start = last or datetime.now().strftime("%Y.%m.%d")

    # Все заказы — одной транзакцией: по соединению на заказ приём конверта 1С
    # с 400 изделиями занимал 2–5 секунд.
    rows = [_order_row(c["order_number"] or "б/н", c["product_code"], int(c["total_quantity"]),
                       c.get("due_day"), "1С", "") for c in cards]
    db = shop()
    try:
        db.executemany(_UPSERT_ORDER, rows)
        db.commit()
    finally:
        db.close()
    made = len(rows)
    return {"orders": made, "looms": 0, "from_day": start,
            "candidates": sum(len(v) for v in by_product.values())}


# --- факт и прогноз -----------------------------------------------------------

def _articles(loom):
    """История артикулов на станке, которые ставил мастер: [(с какого дня, артикул)]."""
    db = shop()
    rows = [(r["from_day"], r["product_code"]) for r in db.execute(
        "SELECT from_day, product_code FROM loom_article WHERE loom=? ORDER BY from_day", (loom,))]
    db.close()
    return rows


def _article_on(arts, day):
    cur = None
    for d, p in arts:
        if d > day:
            break
        cur = p
    return cur


def _loom_progress(loom, from_day, product_code, cmap, arts, panels, days=RATE_DAYS):
    """Сколько станок сделал по этому изделию и с каким темпом.

    Считаем только те дни, когда на станке шёл заказанный артикул: иначе в факт
    заказа попадёт всё подряд, что станок ткал за это время.
    """
    want = norm_code(product_code)
    with fact() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT day, cloth, SUM(pieces) pc FROM shift_full"
            " WHERE loom=? AND day >= ? AND run_min > 5 GROUP BY day, cloth ORDER BY day",
            (loom, from_day))]
    by_day = {}
    for r in rows:
        c = norm_code(r["cloth"])
        ok = c == want or cmap.get(c) == want
        if not ok and c in ("", "undefined"):
            ok = norm_code(_article_on(arts, r["day"])) == want
        if not ok:
            continue
        by_day[r["day"]] = by_day.get(r["day"], 0) + (r["pc"] or 0) * panels.get(r["cloth"] or "", 1)
    done = sum(by_day.values())
    recent = [by_day[d] for d in sorted(by_day)[-days:]]
    rate = round(sum(recent) / len(recent)) if recent else 0
    return int(done), rate, bool(by_day)


def orders(include_closed=False):
    """Заказы с фактом, темпом и прогнозом срока."""
    db = shop()
    rows = [dict(r) for r in db.execute(
        "SELECT * FROM plan_order" + ("" if include_closed else " WHERE closed=0") +
        " ORDER BY (due_day IS NULL), due_day, order_no")]
    links = {}
    for r in db.execute("SELECT * FROM plan_loom"):
        links.setdefault(r["order_id"], []).append(dict(r))
    db.close()

    cmap_full = cloth_map()
    cmap = {k: norm_code(v["product_code"]) for k, v in cmap_full.items()}
    panels = metrics.panels_by_cloth()
    arts_cache = {}
    today = datetime.now().date()
    import loomplan
    plan_stats = loomplan.order_stats()["stats"]
    ppt_src = ppt_sources()             # один раз на все заказы, а не по запросу на заказ
    per_order = {}
    for o in rows:
        per_order[str(o["order_no"])] = per_order.get(str(o["order_no"]), 0) + 1
    out = []
    for o in rows:
        st = plan_stats.get(str(o["order_no"]))
        if st:
            # В заказе 1С несколько изделий — у каждой строки свой прогресс: клетки
            # плана, где стоит именно это изделие. Изделие одно — весь заказ.
            if per_order[str(o["order_no"])] > 1:
                st = st["by_product"].get(o["product_code"]) or EMPTY_PLAN_STATS
            out.append(_order_by_plan(o, st, ppt_src))
            continue
        ls = links.get(o["id"], [])
        done, rate, matched_any = 0, 0, False
        looms = []
        for l in ls:
            if l["loom"] not in arts_cache:
                arts_cache[l["loom"]] = _articles(l["loom"])
            d, r, matched = _loom_progress(l["loom"], l["from_day"], o["product_code"],
                                           cmap, arts_cache[l["loom"]], panels)
            done += d
            rate += r
            matched_any = matched_any or matched
            looms.append({"loom": l["loom"], "from_day": l["from_day"],
                          "done": d, "rate": r, "share": l["qty_towels"],
                          "matched": matched})
        left = max(0, o["qty_towels"] - done)
        days_left = (left / rate) if rate else None
        eta = (today + timedelta(days=days_left)).strftime("%Y.%m.%d") if days_left else None

        late = None
        if eta and o["due_day"]:
            try:
                due = datetime.strptime(o["due_day"], "%Y.%m.%d").date()
                late = (datetime.strptime(eta, "%Y.%m.%d").date() - due).days
            except ValueError:
                late = None

        # Код ткани, связанный с изделием, даёт расчёт PPT по счётчикам.
        want = norm_code(o["product_code"])
        cloth = next((v["cloth_code"] for v in cmap_full.values()
                      if norm_code(v["product_code"]) == want), None)
        ppt, _, src = ppt_for(cloth=cloth or o["product_code"], product_code=o["product_code"],
                              sources=ppt_src)
        out.append({**o, "looms": sorted(looms, key=lambda x: _loom_key(x["loom"])),
                    "done": done, "left": left, "matched": matched_any,
                    "percent": round(100.0 * done / o["qty_towels"], 1) if o["qty_towels"] else 0,
                    "rate_per_day": rate,
                    "days_left": round(days_left, 1) if days_left else None,
                    "eta": eta, "late_days": late,
                    "on_time": (late is not None and late <= 0),
                    "ppt": ppt, "ppt_source": src, "cloth_code": cloth, "plan": None})
    return out


EMPTY_PLAN_STATS = {"looms": [], "future": [], "first_day": None, "last_day": None, "cells": 0,
                    "done": 0, "expected": 0, "rate_now": 0}


def _order_by_plan(o, st, ppt_src=None):
    """Заказ, который есть в плане цеха: факт — полотенца станков в дни плана,
    прогноз — идём по будущим дням плана с нынешним темпом станков."""
    qty = o["qty_towels"] or 0
    cum, eta = st["done"], None
    if qty and cum >= qty:
        eta = max((l["to_day"] for l in st["looms"] if l["done"]), default=None)
    else:
        for day, r in st["future"]:
            cum += r
            if qty and cum >= qty:
                eta = day
                break
    late = None
    if eta and o["due_day"]:
        try:
            late = (datetime.strptime(eta, "%Y.%m.%d") - datetime.strptime(o["due_day"], "%Y.%m.%d")).days
        except ValueError:
            late = None
    rate = st["rate_now"]           # темп станков, которые ещё стоят на заказе по плану
    ppt, _, src = ppt_for(cloth=o["product_code"], product_code=o["product_code"], sources=ppt_src)
    left = max(0, qty - st["done"])
    return {**o, "looms": [{"loom": l["loom"], "from_day": l["from_day"], "to_day": l["to_day"],
                            "done": l["done"], "rate": l["rate"], "share": None, "matched": True,
                            "days": l["days"]} for l in st["looms"]],
            "done": st["done"], "left": left, "matched": True,
            "percent": round(100.0 * st["done"] / qty, 1) if qty else 0,
            "rate_per_day": round(rate), "days_left": round(left / rate, 1) if rate and left else None,
            "eta": eta, "late_days": late, "on_time": late is not None and late <= 0,
            "ppt": ppt, "ppt_source": src, "cloth_code": None,
            "plan": {"first_day": st["first_day"], "last_day": st["last_day"], "cells": st["cells"],
                     "expected": st["expected"], "shortfall": max(0, qty - st["expected"]) if qty else 0}}


def plan_only_orders():
    """Заказы, которые стоят в плане цеха, а из 1С ещё не пришли."""
    import loomplan
    stats = loomplan.order_stats()["stats"]
    db = shop()
    known = {str(r["order_no"]) for r in db.execute("SELECT order_no FROM plan_order")}
    db.close()
    return [{"order_no": o, "looms": [l["loom"] for l in s["looms"]], "first_day": s["first_day"],
             "last_day": s["last_day"], "done": s["done"]}
            for o, s in sorted(stats.items()) if o not in known]
