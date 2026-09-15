"""Лист Working по техническому заданию: 1 строка = 1 станок = 1 дата.

Источники (раздел 2 ТЗ):
  FACT (TMS)  — эффективность по сменам, остановы Vors/Utog/Karenoy/Other
  1С (API)    — размер, PPT, панели, дизайн, плотность, пряжа с лотами
  приложение  — операторы и мастерицы по сменам, ручные остановы (тикеты)

    python build_working_report.py 2026.09.11
    python build_working_report.py 2026.09.11 --out working_11.csv
"""
import argparse
import csv
import io
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "fact.db")
SHOP_DB = os.path.join(os.path.dirname(HERE), "_app", "shop.db")

SHIFTS = ["A", "B", "C"]

# Блок Manual Stop (ТЗ разделы 10): категория -> сколько колонок
MANUAL_BLOCKS = [
    ("abr_p_vors", "ABR P (vors)", True),
    ("abr_p_karinoy", "ABR P (Karinoy)", True),
    ("pol_master", "Pol Master", True),
    ("designer", "Designer", True),
    ("electrical", "Electrical", True),
    ("beam_short", "Beam Short", False),      # без кодов операторов
    ("zapravka", "Zapravka (Article)", False),
]


def hhmm(minutes):
    """Время остановов в формате h:mm (ТЗ раздел 12)."""
    if not minutes:
        return "0:00"
    m = int(round(minutes))
    return f"{m // 60}:{m % 60:02d}"


def headers():
    h = ["Date", "Sr#", "Size (cm)", "RPM", "PPT", "P Pc. Wt Kg", "# of panels",
         "100% Prod. Kg", "MODEL DIZAYN", "GSM",
         "Vors", "Karenoy", "Utog 1", "Utog 2", "Utog 3", "Utog 4", "L#"]
    h += [f"Masterisa {s}" for s in SHIFTS] + [f"Operator {s}" for s in SHIFTS]
    h += [f"Efficiency {s}" for s in SHIFTS] + ["Efficiency Total"]
    for name in ("Vors", "Utog", "Karenoy"):
        for s in SHIFTS:
            h += [f"{name} count {s}", f"{name} stoppage time {s}", f"{name} mending {s}"]
        h += [f"{name} total time", f"{name} total count"]
    for s in SHIFTS:
        h += [f"Other Stops count {s}", f"Other Stops time {s}"]
    h += ["Other Stops total time", "Other Stops total count", "L# (manual)"]
    for _id, title, with_op in MANUAL_BLOCKS:
        for s in SHIFTS:
            h.append(f"{title} {s} time")
            if with_op:
                h.append(f"{title} {s} operator")
        h.append(f"{title} total time")
    return h


def tech_card_for(db, loom):
    """Техкарта станка — только если 1С привязала станок ровно к одному изделию."""
    codes = [r[0] for r in db.execute(
        "SELECT product_code FROM tech_card_loom WHERE loom=?", (loom,))]
    if len(codes) != 1:
        return None, len(codes)
    card = db.execute("SELECT * FROM tech_card WHERE product_code=?", (codes[0],)).fetchone()
    if not card:
        return None, len(codes)
    yarn = {r["slot"]: r["yarn_code"] for r in db.execute(
        "SELECT slot, yarn_code FROM tech_card_yarn WHERE product_code=?", (codes[0],))}
    return (dict(card), yarn), 1


def people(day):
    """Коды операторов и мастериц по сменам из базы приложения."""
    ops, masters = {}, {}
    if not os.path.exists(SHOP_DB):
        return ops, masters
    db = sqlite3.connect(SHOP_DB)
    db.row_factory = sqlite3.Row
    for r in db.execute(
            "SELECT a.shift, a.loom, o.code FROM assignment a JOIN operator o ON o.id=a.operator_id"
            " WHERE a.day=?", (day,)):
        ops[(r["loom"], r["shift"])] = r["code"]
    for r in db.execute(
            "SELECT m.shift, o.code FROM shift_master m JOIN operator o ON o.id=m.operator_id"
            " WHERE m.day=?", (day,)):
        masters.setdefault(r["shift"], []).append(r["code"])
    db.close()
    return ops, masters


def tickets(day):
    """Ручные остановы из тикетов: минуты и ответственный по сменам.

    Тикеты живут в цеховой базе приложения (прежняя служба stopwatch удалена)."""
    path = SHOP_DB
    out = {}
    if not os.path.exists(path):
        return out
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT loom, shift, category_id, SUM(duration_sec) sec,"
            " MAX(COALESCE(classified_by,'')) who FROM ticket"
            " WHERE substr(shift,1,10)=? AND category_id IS NOT NULL"
            " GROUP BY loom, shift, category_id", (day,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    for r in rows:
        letter = r["shift"][-1] if r["shift"] else ""
        out[(r["loom"], letter, r["category_id"])] = (r["sec"] / 60.0, r["who"])
    db.close()
    return out


def build(day, out_path):
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    shifts = {}
    for r in db.execute("SELECT * FROM shift_full WHERE day=?", (day,)):
        shifts.setdefault(r["loom"], {})[r["letter"]] = r
    if not shifts:
        raise SystemExit(f"Нет данных FACT за {day}")

    ops, masters = people(day)
    tk = tickets(day)
    # Техкарты 1С переехали в цеховую базу приложения.
    cards_db = sqlite3.connect(SHOP_DB)
    cards_db.row_factory = sqlite3.Row

    rows, ambiguous, no_card = [], [], []
    order = sorted(shifts, key=lambda l: (l[0], int(l[1:])))
    for sr, loom in enumerate(order, 1):
        sh = shifts[loom]
        card, n_codes = tech_card_for(cards_db, loom)
        if card is None:
            (ambiguous if n_codes > 1 else no_card).append(loom)
        info, yarn = card if card else ({}, {})

        g = lambda L, k: (sh[L][k] if L in sh else 0)
        worked = [L for L in SHIFTS if g(L, "run_min") > 5]
        run = sum(g(L, "run_min") for L in SHIFTS)
        cal = sum(g(L, "run_min") + g(L, "stop_min") for L in SHIFTS)
        rpms = [g(L, "rpm") for L in SHIFTS if g(L, "rpm")]
        rpm = round(sum(rpms) / len(rpms)) if rpms else 0
        ppt = info.get("ppt")
        weight = info.get("weight_kg")
        panels = info.get("panels")
        prod100 = round(panels * weight * (rpm * 24 * 60 / ppt), 1) if (ppt and weight and panels and rpm) else ""

        row = [day.replace(".", "."), sr, info.get("size_cm", ""), rpm, ppt or "",
               weight or "", panels or "", prod100, info.get("product_code", ""),
               info.get("gsm", ""),
               yarn.get("vors", ""), yarn.get("karenoy", ""), yarn.get("utog1", ""),
               yarn.get("utog2", ""), yarn.get("utog3", ""), yarn.get("utog4", ""), loom]
        row += [",".join(masters.get(s, [])) for s in SHIFTS]
        row += [ops.get((loom, s), "") for s in SHIFTS]
        row += [round(g(s, "effic_pct"), 1) if s in worked else "" for s in SHIFTS]
        row += [round(100 * run / cal, 1) if cal else ""]

        for ct_f, tm_f in (("top_ct", "top_stop_min"), ("weft_ct", "weft_stop_min"),
                           ("warp_ct", "warp_stop_min")):
            tot_c = tot_t = 0
            for s in SHIFTS:
                c, t = g(s, ct_f), g(s, tm_f)
                tot_c += c
                tot_t += t
                row += [c, hhmm(t), round(t * 60 / c) if c else 0]
            row += [hhmm(tot_t), tot_c]

        tot_c = tot_t = 0
        for s in SHIFTS:
            c, t = g(s, "other_ct"), g(s, "other_min")
            tot_c += c
            tot_t += t
            row += [c, hhmm(t)]
        row += [hhmm(tot_t), tot_c, loom]

        for cat_id, _title, with_op in MANUAL_BLOCKS:
            total = 0.0
            for s in SHIFTS:
                mins, who = tk.get((loom, s, cat_id), (0.0, ""))
                total += mins
                row.append(hhmm(mins))
                if with_op:
                    row.append(who)
            row.append(hhmm(total))
        rows.append(row)

    db.close()
    with io.open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(headers())
        w.writerows(rows)

    print(f"Готово: {out_path}")
    print(f"  станков: {len(rows)}, колонок: {len(headers())}")
    if ambiguous:
        print(f"\n  Изделие не определяется однозначно — 1С привязала станок к нескольким изделиям"
              f" ({len(ambiguous)}): {', '.join(ambiguous)}")
    if no_card:
        print(f"  Нет техкарты в 1С ({len(no_card)}): {', '.join(no_card)}")
    if not tk:
        print("  Ручные остановы пустые: служба тикетов ещё не набрала данных.")
    if not ops:
        print("  Операторы и мастерицы не заполнены: назначьте их в приложении на вкладке «Смена».")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("day", help="дата, например 2026.09.11")
    ap.add_argument("--out")
    a = ap.parse_args()
    build(a.day, a.out or os.path.join(HERE, f"working_{a.day}.csv"))
