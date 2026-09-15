"""Зарплата и KPI.

Зарплата за смену = сумма пиков по станкам оператора × ставка (по умолчанию
287 сум за 1000 пиков). Мастерица отвечает за всю смену целиком, оператор —
только за свои станки, поэтому показатели считаются по разному охвату.
"""
from collections import defaultdict

from reports import shift_rows
from storage import setting, shop


def money(picks, rate, unit):
    return picks * rate / 1000.0 if unit == "kpick" else picks * rate


def salary_for_shift(day, letter):
    """Зарплата и показатели по каждому оператору смены."""
    db = shop()
    rate = float(setting(db, "rate"))
    unit = setting(db, "rate_unit")

    assigns = {r["loom"]: r for r in db.execute(
        "SELECT a.loom, o.id, o.code, o.name FROM assignment a JOIN operator o ON o.id=a.operator_id"
        " WHERE a.day=? AND a.shift=?", (day, letter))}
    masters = [dict(r) for r in db.execute(
        "SELECT o.id, o.code, o.name FROM shift_master m JOIN operator o ON o.id=m.operator_id"
        " WHERE m.day=? AND m.shift=?", (day, letter))]
    db.close()

    rows = shift_rows(day, letter)
    by_op = defaultdict(lambda: {"looms": [], "picks": 0.0, "run": 0.0, "cal": 0.0,
                                 "weft": 0, "top": 0, "warp": 0, "wait": 0.0, "manual": 0})
    unassigned = []
    for r in rows:
        a = assigns.get(r["loom"])
        if not a:
            unassigned.append(r["loom"])
            continue
        acc = by_op[a["id"]]
        acc["code"], acc["name"] = a["code"], a["name"]
        acc["looms"].append(r["loom"])
        acc["picks"] += r["picks"] or 0
        acc["run"] += r["run_min"] or 0
        acc["cal"] += (r["run_min"] or 0) + (r["stop_min"] or 0)
        acc["weft"] += r["weft_ct"] or 0
        acc["top"] += r["top_ct"] or 0
        acc["warp"] += r["warp_ct"] or 0
        acc["wait"] += r["wait_total_min"] or 0
        acc["manual"] += r["manual_ct"] or 0

    out = []
    for op_id, a in by_op.items():
        kp = a["picks"] / 1000.0 or 1
        out.append({
            "operator_id": op_id, "code": a.get("code", ""), "name": a.get("name", ""),
            "looms": sorted(a["looms"]), "loom_count": len(a["looms"]),
            "picks": round(a["picks"]), "kpicks": round(a["picks"] / 1000, 1),
            "salary": round(money(a["picks"], rate, unit)),
            "effic": round(100 * a["run"] / a["cal"], 1) if a["cal"] else 0,
            "weft_ct": a["weft"], "top_ct": a["top"], "warp_ct": a["warp"],
            "weft_cmpx": round(100 * a["weft"] / kp, 1),
            "warp_cmpx": round(100 * (a["warp"] + a["top"]) / kp, 1),
            "wait_min": round(a["wait"]),
            "manual_ct": a["manual"],
        })
    out.sort(key=lambda x: -x["salary"])

    # Разбивка по станкам: её видно, даже когда операторов ещё не назначили —
    # иначе выработка смены висит в воздухе и кажется, что данных нет.
    loom_rows = []
    for r in rows:
        a = assigns.get(r["loom"])
        p = r["picks"] or 0
        loom_rows.append({
            "loom": r["loom"], "style": r["style"] or "—",
            "picks": round(p), "kpicks": round(p / 1000, 1),
            "salary": round(money(p, rate, unit)),
            "effic": r["effic_pct"],
            "weft_ct": r["weft_ct"] or 0, "warp_ct": (r["warp_ct"] or 0) + (r["top_ct"] or 0),
            "wait_min": round(r["wait_total_min"] or 0),
            "operator_id": a["id"] if a else None,
            "operator": a["name"] if a else None,
        })
    loom_rows.sort(key=lambda x: -x["picks"])

    total_picks = sum(r["picks"] or 0 for r in rows)
    unassigned_salary = sum(l["salary"] for l in loom_rows if not l["operator_id"])
    return {
        "day": day, "shift": letter, "rate": rate, "rate_unit": unit,
        "operators": out, "masters": masters,
        "unassigned_looms": unassigned,
        "looms": loom_rows,
        "totals": {
            "picks": round(total_picks), "kpicks": round(total_picks / 1000, 1),
            "salary": round(sum(o["salary"] for o in out)),
            "salary_all": round(money(total_picks, rate, unit)),
            "unassigned_salary": unassigned_salary,
            "looms": len(rows), "assigned": len(rows) - len(unassigned),
        },
    }


def kpi(date_from, date_to, role="operator"):
    """KPI за период: по операторам или по мастерицам."""
    db = shop()
    if role == "master":
        links = [dict(r) for r in db.execute(
            "SELECT m.day, m.shift, o.id, o.code, o.name FROM shift_master m"
            " JOIN operator o ON o.id=m.operator_id WHERE m.day BETWEEN ? AND ?", (date_from, date_to))]
        scope = None      # мастерица отвечает за всю смену
    else:
        links = [dict(r) for r in db.execute(
            "SELECT a.day, a.shift, a.loom, o.id, o.code, o.name FROM assignment a"
            " JOIN operator o ON o.id=a.operator_id WHERE a.day BETWEEN ? AND ?", (date_from, date_to))]
        scope = "loom"
    db.close()

    cache = {}

    def rows_for(day, letter):
        key = (day, letter)
        if key not in cache:
            cache[key] = shift_rows(day, letter)
        return cache[key]

    acc = defaultdict(lambda: {"picks": 0.0, "run": 0.0, "cal": 0.0, "weft": 0, "top": 0,
                               "warp": 0, "wait": 0.0, "manual": 0, "shifts": set(), "looms": set()})
    for l in links:
        rows = rows_for(l["day"], l["shift"])
        if scope == "loom":
            rows = [r for r in rows if r["loom"] == l["loom"]]
        a = acc[l["id"]]
        a["code"], a["name"] = l["code"], l["name"]
        a["shifts"].add((l["day"], l["shift"]))
        for r in rows:
            a["looms"].add(r["loom"])
            a["picks"] += r["picks"] or 0
            a["run"] += r["run_min"] or 0
            a["cal"] += (r["run_min"] or 0) + (r["stop_min"] or 0)
            a["weft"] += r["weft_ct"] or 0
            a["top"] += r["top_ct"] or 0
            a["warp"] += r["warp_ct"] or 0
            a["wait"] += r["wait_total_min"] or 0
            a["manual"] += r["manual_ct"] or 0

    out = []
    for op_id, a in acc.items():
        kp = a["picks"] / 1000.0 or 1
        out.append({
            "operator_id": op_id, "code": a.get("code", ""), "name": a.get("name", ""),
            "shifts": len(a["shifts"]), "looms": len(a["looms"]),
            "kpicks": round(a["picks"] / 1000, 1),
            "effic": round(100 * a["run"] / a["cal"], 1) if a["cal"] else 0,
            "weft_cmpx": round(100 * a["weft"] / kp, 1),
            "warp_cmpx": round(100 * (a["warp"] + a["top"]) / kp, 1),
            "wait_per_shift": round(a["wait"] / max(1, len(a["shifts"]))),
            "manual_per_shift": round(a["manual"] / max(1, len(a["shifts"])), 1),
        })
    out.sort(key=lambda x: -x["effic"])
    return {"role": role, "from": date_from, "to": date_to, "rows": out}
