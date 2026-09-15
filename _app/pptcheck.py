"""Сверка PPT: сколько пиков на ряд задано в 1С и сколько даёт станок.

У станка два независимых счётчика — пики и ряды (штуки Toyota); их отношение —
фактический PPT того, что станок ткал. В 1С у изделия задан weftPerOneRow.
Сравниваем по каждому станку и дню, где в плане стоит изделие с техкартой 1С:

    в пределах 5 %                          норма;
    код ткани на станке не совпадает с планом, за день было несколько кодов
    или день выбивается из обычного для этого изделия — станок ткал другое
    изделие: поправить план или код ткани на станке;
    так же на нескольких днях при совпадающем коде ткани — неверный PPT в 1С.

Полотенца считаются по рядам, поэтому неверный PPT в 1С их количество не
искажает, а вес (кг в производственном отчёте) и прогноз времени — искажает.

Там же — выполнение нормы 1С. Секунды на ряд из 1С (secondsPerRow) = PPT × 60 ÷
375, а 375 = 500 об/мин × 75 %: эффективность 75 % в секундах уже заложена.
Выполнение нормы = ряды × секунды на ряд ÷ время смен; 100 % — станок выдал
ровно норму.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median

import cache
from storage import fact, shop

THRESHOLD = 5.0        # %: расхождение больше — отмечаем
MIN_ROWS = 50          # меньше рядов за день — изделие меняли, сравнивать не с чем
MIN_DAYS = 3           # вывод «PPT в 1С неверный» — не меньше чем по трём станко-дням

VERDICTS = {"ok": "норма", "other": "станок ткал другое изделие",
            "ppt": "проверьте PPT в 1С", "diff": "расхождение"}


def default_period(days=14):
    to = datetime.now().strftime("%Y.%m.%d")
    frm = (datetime.now() - timedelta(days=days - 1)).strftime("%Y.%m.%d")
    return frm, to


def check(date_from, date_to):
    """{"days": по станкам и дням, "products": по изделиям}. Держим две минуты."""
    return cache.get(("ppt_check", date_from, date_to), 120, lambda: _check(date_from, date_to))


def loom_days(date_from, date_to, context_days=13):
    """Станко-дни за период. Вывод «проверьте PPT в 1С» опирается на соседние
    дни, поэтому считаем с запасом в две недели назад и отдаём только период."""
    ctx = (datetime.strptime(date_from, "%Y.%m.%d") - timedelta(days=context_days)).strftime("%Y.%m.%d")
    return [d for d in check(ctx, date_to)["days"] if date_from <= d["day"] <= date_to]


def _check(date_from, date_to):
    import dashboard
    db = shop()
    plan = [dict(r) for r in db.execute(
        "SELECT p.loom, p.day, p.order_no, p.product_code, p.product, p.size, p.design, p.gsm,"
        " t.ppt, t.seconds_per_row sec FROM loom_plan p JOIN tech_card t"
        " ON t.order_number = p.order_no AND t.product_code = p.product_code"
        " WHERE p.day BETWEEN ? AND ? AND t.ppt > 0", (date_from, date_to))]
    db.close()
    if not plan:
        return {"days": [], "products": [], "threshold": THRESHOLD}

    counters = {}
    with fact() as f:
        for r in f.execute(
                "SELECT loom, day, cloth, SUM(picks) picks, SUM(pieces) rows, SUM(run_min) run,"
                " SUM(stop_min) stop, SUM(rpm * run_min) rpm_w FROM shift_full"
                " WHERE day BETWEEN ? AND ? AND run_min > 5 GROUP BY loom, day, cloth",
                (date_from, date_to)):
            a = counters.setdefault((r["loom"], r["day"]), {"picks": 0.0, "rows": 0.0, "run": 0.0,
                                                           "stop": 0.0, "rpm_w": 0.0, "cloths": {}})
            a["picks"] += r["picks"] or 0
            a["rows"] += r["rows"] or 0
            a["run"] += r["run"] or 0
            a["stop"] += r["stop"] or 0
            a["rpm_w"] += r["rpm_w"] or 0
            c = r["cloth"] or ""
            a["cloths"][c] = a["cloths"].get(c, 0) + (r["rows"] or 0)

    days = []
    for p in plan:
        a = counters.get((p["loom"], p["day"]))
        if not a or a["rows"] < MIN_ROWS:
            continue
        ppt = a["picks"] / a["rows"]
        main = max(a["cloths"].items(), key=lambda kv: kv[1])[0]
        cal = (a["run"] + a["stop"]) * 60           # секунд в сменах
        sec = p["sec"] or None
        days.append({
            "sec_1c": round(sec) if sec else None,
            "norm_pct": round(100.0 * a["rows"] * sec / cal, 1) if sec and cal else None,
            "rpm": round(a["rpm_w"] / a["run"]) if a["run"] else None,
            "time_eff": round(100.0 * a["run"] / (a["run"] + a["stop"]), 1) if cal else None,
            "loom": p["loom"], "day": p["day"], "order_no": p["order_no"],
            "product_code": p["product_code"], "product": p["product"],
            "ppt_1c": round(p["ppt"]), "ppt_fact": round(ppt),
            "dev": round(100.0 * (ppt - p["ppt"]) / p["ppt"], 1), "rows": int(a["rows"]),
            "cloth": main, "mixed": sum(1 for n in a["cloths"].values() if n >= 20) > 1,
            "cloth_mismatch": bool(dashboard.plan_mismatch(p, main))})

    # По изделию — только «чистые» дни: код ткани совпадает с планом и изделие одно.
    groups = defaultdict(list)
    for d in days:
        groups[(d["product_code"], d["ppt_1c"])].append(d)
    products = []
    med = {}
    for (code, ppt_1c), grp in groups.items():
        clean = [d for d in grp if not d["mixed"] and not d["cloth_mismatch"]]
        m = median(d["ppt_fact"] for d in clean) if clean else None
        med[(code, ppt_1c)] = m
        dev = round(100.0 * (m - ppt_1c) / ppt_1c, 1) if m else None
        if len(clean) < MIN_DAYS:
            verdict = "мало данных" if (dev is None or abs(dev) > THRESHOLD) else "совпадает"
        else:
            verdict = "совпадает" if abs(dev) <= THRESHOLD else "проверьте PPT в 1С"
        vals = [d["ppt_fact"] for d in clean]
        norms = [d["norm_pct"] for d in grp if d["norm_pct"] is not None]
        products.append({
            "norm_pct": round(median(norms), 1) if norms else None,
            "sec_1c": grp[0]["sec_1c"],
            "product_code": code, "ppt_1c": ppt_1c, "ppt_fact": round(m) if m else None,
            "dev": dev, "days": len(grp), "clean_days": len(clean),
            "spread": round(100.0 * (max(vals) - min(vals)) / m, 1) if len(vals) > 1 and m else None,
            "orders": sorted({d["order_no"] for d in grp}),
            "looms": sorted({d["loom"] for d in grp}), "verdict": verdict})
    products.sort(key=lambda x: (x["verdict"] != "проверьте PPT в 1С", -abs(x["dev"] or 0)))
    wrong_1c = {(x["product_code"], x["ppt_1c"]) for x in products if x["verdict"] == "проверьте PPT в 1С"}

    for d in days:
        m = med.get((d["product_code"], d["ppt_1c"]))
        if abs(d["dev"]) <= THRESHOLD:
            d["verdict"] = "ok"
            d["text"] = "норма (%+.1f%%)" % d["dev"]
        elif d["mixed"] or d["cloth_mismatch"] or (m and abs(d["ppt_fact"] - m) * 100.0 / m > THRESHOLD):
            d["verdict"] = "other"
            why = ("за день на станке было несколько кодов ткани" if d["mixed"]
                   else "код ткани на станке «%s» не совпадает с планом" % d["cloth"] if d["cloth_mismatch"]
                   else "PPT дня не такой, как обычно у этого изделия")
            d["text"] = "по счётчикам %d, в 1С %d (%+.1f%%) — станок ткал другое изделие: %s" % (
                d["ppt_fact"], d["ppt_1c"], d["dev"], why)
        elif (d["product_code"], d["ppt_1c"]) in wrong_1c:
            d["verdict"] = "ppt"
            d["text"] = "по счётчикам %d, в 1С %d (%+.1f%%) — так же на других днях: проверьте PPT в 1С" % (
                d["ppt_fact"], d["ppt_1c"], d["dev"])
        else:
            d["verdict"] = "diff"
            d["text"] = "по счётчикам %d, в 1С %d (%+.1f%%)" % (d["ppt_fact"], d["ppt_1c"], d["dev"])
    days.sort(key=lambda d: (d["day"], d["loom"]))
    return {"days": days, "products": products, "threshold": THRESHOLD, "min_rows": MIN_ROWS}
