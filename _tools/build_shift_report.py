"""Собирает ежедневный производственный отчёт (лист TOYOTA) из данных Toyota FACT.

Показатели берутся из FACT, заправочные данные артикула — из справочника
artikul_ref.json (собран из вашего отчёта, дополняется вручную).

    python build_shift_report.py 2026.09.11
    python build_shift_report.py 2026.09.11 --db fact.db --out report_11.09.csv
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import urllib.request
from collections import defaultdict

FACT = "http://172.0.30.9"
HERE = os.path.dirname(os.path.abspath(__file__))

# Допустимые размеры полотна (см) — по ним разбираем слипшееся число в поле cloth.
SIZES = [220, 200, 180, 160, 150, 140, 135, 130, 100, 90, 85, 80, 70, 60, 50, 40, 35, 30]

# Колонки отчёта в порядке листа TOYOTA.
HEADERS = ["Sr#", "Size cm", "RPM", "PPT", "P Pc. Wt Kg", "# of panels", "100% Prod. Kg",
           "MODEL (DIZAYN)", "GSM", "Pile Count (vors)", "Ground Count (karenoy)", "LOTO",
           "WEFT (UTOG) 1", "WEFT (UTOG) 2", "WEFT (UTOG) 3", "WEFT (UTOG) 4", "L#",
           "Effic A", "Effic B", "Effic C", "Effic Total",
           "Pile A", "Pile B", "Pile C", "Pile Total",
           "Weft A", "Weft B", "Weft C", "Weft Total",
           "Ground A", "Ground B", "Ground C", "Ground Total",
           "Other A", "Other B", "Other C", "Other Total",
           "Achieved Kg", "Артикул найден"]


def parse_cloth(cloth):
    """'70140D272600' -> (70, 'D-272', 600). Возвращает (размер_см, дизайн, плотность)."""
    s = (cloth or "").replace("%20", "").replace(" ", "").upper()
    if not s:
        return None, None, None

    size = None
    m = re.match(r"^(\d+)", s)
    if m:
        digits = m.group(1)
        for a in SIZES:                       # первая часть пары размеров
            sa = str(a)
            if digits.startswith(sa):
                rest = digits[len(sa):]
                if any(rest.startswith(str(b)) for b in SIZES) or rest == "":
                    size = a
                    break
        if size is None:
            size = int(digits[:2])

    tail = s[m.end():] if m else s            # то, что после размеров
    tail = tail.lstrip("X")
    design = gsm = None
    d = re.match(r"^([A-Z]{1,2})-?(\d{3})", tail)
    if d:
        design = f"{d.group(1)}-{d.group(2)}"
        rest = tail[d.end():]
    else:                                     # HOTEL500, Waffle D269, TC …
        w = re.match(r"^([A-Z]+)", tail)
        if w:
            design = w.group(1)
            rest = tail[w.end():]
            d2 = re.match(r"^-?([A-Z]{1,2})-?(\d{3})", rest)
            if d2:                            # WaffleD269
                design = f"{d2.group(1)}-{d2.group(2)}"
                rest = rest[d2.end():]
        else:
            rest = tail
    g = re.match(r"^(\d{3})", rest or "")
    if g:
        gsm = int(g.group(1))
    return size, design, gsm


def fact_meta(shift):
    """Артикул и ткань по станкам за смену — прямо из FACT."""
    out = {}
    url = f"{FACT}/factdata/shift-shift/{shift}.txt"
    with urllib.request.urlopen(url, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    for line in text.splitlines():
        d = {}
        for field in line.split(","):
            p = field.strip().split(" ", 1)
            if len(p) == 2:
                d[p[0]] = p[1]
        if "mac_name" in d:
            out[d["mac_name"]] = d
    return out


def load_shifts(day, db_path):
    """Показатели по сменам A/B/C: из локальной базы, иначе прямо из FACT."""
    per_loom = defaultdict(dict)
    db = sqlite3.connect(db_path) if os.path.exists(db_path) else None
    if db:
        db.row_factory = sqlite3.Row
    for idx, letter in enumerate("ABC"):
        shift = f"{day}.{idx}"
        rows = []
        if db:
            rows = [dict(r) for r in db.execute("SELECT * FROM shift_loom WHERE shift=?", (shift,))]
        if not rows:
            sys.path.insert(0, HERE)
            import fact_api
            try:
                rows = fact_api.get_shift(shift)
            except Exception as e:
                print(f"  смена {shift}: нет данных ({e})")
                continue
        for r in rows:
            per_loom[r["loom"]][letter] = r
    if db:
        db.close()
    return per_loom


def build(day, db_path, out_path):
    meta = {}
    for idx in range(3):
        try:
            meta.update(fact_meta(f"{day}.{idx}"))
        except Exception:
            pass
    ref = json.load(open(os.path.join(HERE, "artikul_ref.json"), encoding="utf-8"))
    per_loom = load_shifts(day, db_path)
    if not per_loom:
        sys.exit(f"Нет данных за {day}")

    rows, missing = [], []
    for loom, shifts in per_loom.items():
        cloth = (meta.get(loom) or {}).get("cloth", "")
        size, design, gsm = parse_cloth(cloth)
        # Сначала ищем по фактическому коду ткани из FACT, потом по паре «дизайн + размер»:
        # дизайн в отчёте ставят по плану, и он расходится с тем, что реально на станке.
        key_cloth = "CLOTH|" + re.sub(r"[^A-Z0-9]", "", cloth.replace("%20", "").upper())
        art = ref.get(key_cloth) or ref.get(f"{design}|{size}") or {}
        if not art:
            missing.append((loom, cloth, design, size))

        g = lambda letter, key: (shifts[letter][key] if letter in shifts else 0)
        eff = [round(g(l, "effic_pct")) for l in "ABC"]
        pile = [g(l, "warp_top_ct") for l in "ABC"]
        weft = [g(l, "weft_ct") for l in "ABC"]
        grnd = [g(l, "warp_ct") for l in "ABC"]
        other = [g(l, "unselect_ct") for l in "ABC"]
        picks = sum(g(l, "product_kpick") for l in "ABC") * 1000
        rpms = [g(l, "rpm") for l in "ABC" if g(l, "rpm")]
        rpm = round(sum(rpms) / len(rpms)) if rpms else 0

        ppt, weight, panels = art.get("ppt"), art.get("weight_kg"), art.get("panels")
        prod100 = achieved = None
        if ppt and weight and panels:
            prod100 = panels * weight * (rpm * 24 * 60 / ppt)
            achieved = panels * weight * (picks / ppt)

        rows.append([
            None, f"{size} CM" if size else "", rpm, ppt, weight, panels,
            round(prod100, 1) if prod100 else None,
            # Плотность из кода ткани берём, только если она правдоподобна (200–900 г/м²):
            # у части кодов хвост после дизайна — не плотность, а служебные цифры.
            # Дизайн: из кода ткани, а если он там нестандартный — из справочника.
            design or art.get("design_report") or "",
            (gsm if gsm and 200 <= gsm <= 900 else None) or art.get("gsm") or "",
            art.get("pile_count", ""), art.get("ground_count", ""), art.get("loto", ""),
            *(art.get("weft") or ["", "", "", ""]), loom,
            *eff, round(sum(eff) / 3, 1),
            *pile, sum(pile), *weft, sum(weft), *grnd, sum(grnd), *other, sum(other),
            round(achieved, 1) if achieved else None,
            "да" if art else "НЕТ — дополните справочник",
        ])

    rows.sort(key=lambda r: r[28], reverse=True)          # как в вашем отчёте: по обрывам утка
    for i, r in enumerate(rows, 1):
        r[0] = i

    def block(name, keep):
        sel = [r for r in rows if keep(r[16])]
        if not sel:
            return []
        col = lambda i: [r[i] for r in sel if isinstance(r[i], (int, float))]
        avg = lambda i: round(sum(col(i)) / len(col(i)), 1) if col(i) else ""
        tot = lambda i: sum(col(i))
        return [name, "", avg(2), "", "", "", round(tot(6), 1), "", "", "", "", "",
                "", "", "", "", f"{len(sel)} станков",
                avg(17), avg(18), avg(19), avg(20),
                tot(21), tot(22), tot(23), tot(24), tot(25), tot(26), tot(27), tot(28),
                tot(29), tot(30), tot(31), tot(32), tot(33), tot(34), tot(35), tot(36),
                round(tot(37), 1), ""]

    totals = [block("ALL TOTAL", lambda l: True),
              block("DOBBY (D) TOTAL", lambda l: l.startswith("D")),
              block("JACQUARD (J) TOTAL", lambda l: l.startswith("J"))]

    prod100_all = sum(r[6] for r in rows if isinstance(r[6], (int, float)))
    achieved_all = sum(r[37] for r in rows if isinstance(r[37], (int, float)))
    with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow([f"Производственный отчёт за {day}", "", "источник: Toyota FACT"])
        w.writerow(["100% Production, кг", round(prod100_all, 1),
                    "Achieved Production, кг", round(achieved_all, 1),
                    "Production Efficiency, %",
                    round(100 * achieved_all / prod100_all, 1) if prod100_all else ""])
        w.writerow([])
        w.writerow(HEADERS)
        w.writerows(rows)
        w.writerow([])
        for t in totals:
            if t:
                w.writerow(t)

    print(f"Готово: {out_path}")
    print(f"  станков: {len(rows)}   100% {round(prod100_all)} кг   факт {round(achieved_all)} кг   "
          f"КПД производства {round(100*achieved_all/prod100_all,1) if prod100_all else '—'}%")
    if missing:
        print(f"  нет в справочнике артикулов: {len(missing)}")
        for loom, cloth, design, size in missing:
            print(f"    {loom:5} cloth={cloth:24} -> дизайн {design}, размер {size}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("day", help="дата в формате 2026.09.11")
    ap.add_argument("--db", default=os.path.join(HERE, "fact.db"))
    ap.add_argument("--out")
    a = ap.parse_args()
    build(a.day, a.db, a.out or os.path.join(HERE, f"report_{a.day}.csv"))
