"""Отчёты по данным станков: смена, день, разбор простоев, обход цеха.

Читает только базу станков `fact.db`, которую собирают скрипты из зеркала FACT.
Формулы восстановлены из макроса Toyota: КПД = работа / (работа + простой),
время устранения обрыва = время останова − ожидание оператора, среднее время
одного останова = время / количество.
"""
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

import cache
import loomsetup
import metrics
import tickets
from storage import REPORTS_DIR, SHIFT_LETTERS, TOOLS_DIR, fact


def shift_rows(day, letter):
    """Строки по станкам за смену: выработка, КПД, обрывы, ожидание оператора."""
    with fact() as db:
        return [dict(r) for r in db.execute(
            "SELECT loom, style, rpm, effic_pct, run_min, stop_min, picks, meters, pieces,"
            " weft_ct, weft_fix_min, weft_mttr_sec, top_ct, top_fix_min, top_mttr_sec,"
            " warp_ct, warp_fix_min, warp_mttr_sec, manual_ct, manual_min, wait_total_min"
            " FROM shift_full WHERE day=? AND letter=? AND run_min > 5 ORDER BY loom",
            (day, letter))]


def available_shifts(limit=120):
    with fact() as db:
        return [(r["day"], r["letter"]) for r in db.execute(
            "SELECT DISTINCT day, letter FROM shift_full ORDER BY day DESC, letter DESC LIMIT ?",
            (limit,))]


def latest_day():
    with fact() as db:
        r = db.execute("SELECT MAX(day) d FROM shift_full").fetchone()
    return r["d"] if r else ""


def loom_day_stats(day, letter=""):
    """Обрывы и простой по ним, по каждому станку за день или смену.

    Для доски в цехе: сколько раз рвалось (уток, основа, ворс), сколько минут
    из-за этого стоял станок и сколько из них он просто ждал оператора.
    """
    sql = ("SELECT loom,"
           " SUM(weft_ct) weft_ct, SUM(weft_stop_min) weft_min, SUM(weft_wait_min) weft_wait,"
           " SUM(warp_ct) warp_ct, SUM(warp_stop_min) warp_min, SUM(warp_wait_min) warp_wait,"
           " SUM(top_ct) top_ct, SUM(top_stop_min) top_min, SUM(top_wait_min) top_wait,"
           " SUM(manual_ct) manual_ct, SUM(manual_min) manual_min,"
           " SUM(stop_min) stop_min, SUM(run_min) run_min, SUM(picks) picks"
           " FROM shift_full WHERE day=? AND run_min > 5")
    args = [day]
    if letter:
        sql += " AND letter=?"
        args.append(letter)
    sql += " GROUP BY loom"

    out, tot = {}, {"weft_ct": 0, "warp_ct": 0, "top_ct": 0, "manual_ct": 0,
                    "weft_min": 0, "warp_min": 0, "top_min": 0, "manual_min": 0,
                    "wait_min": 0, "stop_min": 0}
    with fact() as db:
        for r in db.execute(sql, args):
            run, stop = r["run_min"] or 0, r["stop_min"] or 0
            wait = (r["weft_wait"] or 0) + (r["warp_wait"] or 0) + (r["top_wait"] or 0)
            row = {
                "weft_ct": int(r["weft_ct"] or 0), "weft_min": round(r["weft_min"] or 0),
                "warp_ct": int(r["warp_ct"] or 0), "warp_min": round(r["warp_min"] or 0),
                "top_ct": int(r["top_ct"] or 0), "top_min": round(r["top_min"] or 0),
                "manual_ct": int(r["manual_ct"] or 0), "manual_min": round(r["manual_min"] or 0),
                "wait_min": round(wait), "stop_min": round(stop),
                "breaks_min": round((r["weft_min"] or 0) + (r["warp_min"] or 0) + (r["top_min"] or 0)),
                "effic": round(100 * run / (run + stop), 1) if (run + stop) else 0,
                "kpicks": round((r["picks"] or 0) / 1000, 1),
            }
            out[r["loom"]] = row
            for k in tot:
                tot[k] += row.get(k, 0)
    tot["breaks_min"] = tot["weft_min"] + tot["warp_min"] + tot["top_min"]
    tot["breaks_ct"] = tot["weft_ct"] + tot["warp_ct"] + tot["top_ct"]
    return out, tot


def report_days():
    """Дни с отчётом — только те, когда цех работал: воскресенье (выходной по
    расписанию) и праздники дают 40 строк с нулями и выглядят как день простоя."""
    with fact() as db:
        return [r[0] for r in db.execute(
            "SELECT day FROM report_daily GROUP BY day HAVING SUM(COALESCE(picks, 0)) > 0"
            " ORDER BY day DESC")]


PERIOD_MAX_DAYS = 366


def report_period(date_from, date_to):
    """Производственный отчёт за любой период: итоги по станкам.

    Время работы, пики и ряды — из смен Toyota (shift_full), изделие, панели и
    килограммы — из дневного отчёта (report_daily) каждого дня: заправка за
    период могла меняться, поэтому полотенца считаются по дням."""
    try:
        first = datetime.strptime(date_from or "", "%Y.%m.%d")
        last = datetime.strptime(date_to or "", "%Y.%m.%d")
    except ValueError:
        raise ValueError("период: нужны даты вида 2026.09.01") from None
    if first > last:
        raise ValueError("начало периода позже конца")
    if (last - first).days + 1 > PERIOD_MAX_DAYS:
        raise ValueError("период — не больше %d дней" % PERIOD_MAX_DAYS)
    looms = {}
    with fact() as db:
        daily = {(r["day"], r["loom"]): dict(r) for r in db.execute(
            "SELECT day, loom, design, gsm, panels, achieved_kg, pile_total, weft_total, ground_total,"
            " other_total FROM report_daily WHERE day BETWEEN ? AND ?", (date_from, date_to))}
        shifts = db.execute(
            "SELECT day, loom, COUNT(*) shifts, SUM(run_min) run_min, SUM(stop_min) stop_min, SUM(picks) picks,"
            " SUM(pieces) pieces, SUM(top_ct) top_ct, SUM(weft_ct) weft_ct, SUM(warp_ct) warp_ct"
            " FROM shift_full WHERE day BETWEEN ? AND ? GROUP BY day, loom", (date_from, date_to)).fetchall()
        days = [r[0] for r in db.execute("SELECT DISTINCT day FROM shift_full WHERE day BETWEEN ? AND ?",
                                         (date_from, date_to))]
    for s in shifts:
        d = daily.get((s["day"], s["loom"])) or {}
        a = looms.setdefault(s["loom"], dict(loom=s["loom"], days=0, shifts=0, run_min=0.0, stop_min=0.0,
                                             picks=0.0, rows=0, towels=0, towels_known=True, kg=0.0,
                                             pile=0, weft=0, ground=0, other=0, designs=[], gsm=[]))
        a["days"] += 1
        a["shifts"] += s["shifts"]
        for k in ("run_min", "stop_min", "picks"):
            a[k] += s[k] or 0
        a["rows"] += int(s["pieces"] or 0)
        if d.get("panels"):
            a["towels"] += int((s["pieces"] or 0) * d["panels"])
        elif s["pieces"]:
            a["towels_known"] = False
        a["kg"] += d.get("achieved_kg") or 0
        a["pile"] += d.get("pile_total") if d.get("pile_total") is not None else (s["top_ct"] or 0)
        a["weft"] += d.get("weft_total") if d.get("weft_total") is not None else (s["weft_ct"] or 0)
        a["ground"] += d.get("ground_total") if d.get("ground_total") is not None else (s["warp_ct"] or 0)
        a["other"] += d.get("other_total") or 0
        if d.get("design") and d["design"] not in a["designs"]:
            a["designs"].append(d["design"])
        if d.get("gsm") and d["gsm"] not in a["gsm"]:
            a["gsm"].append(d["gsm"])
    rows = []
    for a in sorted(looms.values(), key=lambda x: loomsetup._loom_key(x["loom"])):
        total = a["run_min"] + a["stop_min"]
        a.update(effic=round(100 * a["run_min"] / total, 1) if total else None,
                 run_min=round(a["run_min"]), stop_min=round(a["stop_min"]), picks=round(a["picks"]),
                 kg=round(a["kg"], 1))
        rows.append(a)
    run = sum(r["run_min"] for r in rows)
    stop = sum(r["stop_min"] for r in rows)
    totals = dict(looms=len(rows), days=len(days), run_min=run, stop_min=stop,
                  effic=round(100 * run / (run + stop), 1) if run + stop else None,
                  picks=sum(r["picks"] for r in rows), rows=sum(r["rows"] for r in rows),
                  towels=sum(r["towels"] for r in rows), kg=round(sum(r["kg"] for r in rows), 1),
                  pile=sum(r["pile"] for r in rows), weft=sum(r["weft"] for r in rows),
                  ground=sum(r["ground"] for r in rows), other=sum(r["other"] for r in rows))
    missing = sorted({s["day"] for s in shifts} - {d for d, _ in daily})
    return {"from": date_from, "to": date_to, "rows": rows, "totals": totals, "days": sorted(days),
            "days_without_report": missing}


def all_days():
    with fact() as db:
        return [r[0] for r in db.execute(
            "SELECT DISTINCT day FROM shift_full ORDER BY day")]


def report_day(day):
    """Строки отчёта за день плюс среднее время одного останова по сменам (сек)."""
    return cache.get(("report_day", day), 120, lambda: _report_day(day))


def _report_day(day):
    with fact() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM report_daily WHERE day=? ORDER BY sr", (day,))]
        mend = {}
        for r in db.execute(
                "SELECT loom, letter, top_ct, top_stop_min, weft_ct, weft_stop_min,"
                " warp_ct, warp_stop_min FROM shift_full WHERE day=?", (day,)):
            slot = {"A": 0, "B": 1, "C": 2}.get(r["letter"])
            if slot is None:
                continue
            d = mend.setdefault(r["loom"], {})
            for name, ct, tm in (("vors", r["top_ct"], r["top_stop_min"]),
                                 ("utog", r["weft_ct"], r["weft_stop_min"]),
                                 ("karenoy", r["warp_ct"], r["warp_stop_min"])):
                d[f"mend_{name}_{'abc'[slot]}"] = round(tm * 60 / ct) if ct else None
    # PPT из счётчиков станка рядом с тем, что стоит в отчёте: расхождение
    # больше 5 % означает либо ошибку в карте, либо путаницу в коде ткани.
    ppt = metrics.ppt_by_cloth()
    # Точнее — пики ÷ ряды этого станка за этот день (сверка с изделием по плану).
    import pptcheck
    daily = {d["loom"]: d for d in pptcheck.loom_days(day, day)}
    # Заправка, введённая вручную: лоты пряжи и отметка, что и кем введено.
    setups = loomsetup.effective(day)
    for row in rows:
        row.update(mend.get(row["loom"], {}))
        row["setup"] = setups.get(row["loom"])
        d = daily.get(row["loom"])
        # Выполнение нормы 1С: ряды × секунды на ряд (в них заложено 75 %) ÷ время смен.
        row["norm_pct"] = d["norm_pct"] if d else None
        if d and row.get("ppt"):
            row["ppt_fact"], row["ppt_spread"] = d["ppt_fact"], None
            row["ppt_gap"] = round(100.0 * (d["ppt_fact"] - row["ppt"]) / row["ppt"], 1)
            row["ppt_note"] = None if d["verdict"] == "ok" else d["text"].split(" — ", 1)[-1]
            continue
        p = ppt.get(row.get("cloth") or "")
        row["ppt_fact"] = p["ppt"] if p else None
        row["ppt_spread"] = p["spread"] if p else None
        # Расхождение показываем только там, где счётчикам можно верить:
        # если под одним кодом ткани шли разные изделия, сравнивать не с чем.
        row["ppt_gap"] = (round(100.0 * (p["ppt"] - row["ppt"]) / row["ppt"], 1)
                          if p and p.get("trusted") and row.get("ppt") else None)
    return rows


def explorer(q):
    """Разбор простоев: фильтры по периоду, сменам, группе станков и станкам.

    Считается тремя запросами GROUP BY: тащить тысячи строк в Python и складывать
    их там на порядок медленнее, а при 80 станках разница станет решающей.
    """
    where = ["day BETWEEN ? AND ?", "run_min > 5"]
    args = [q.get("from", "0000"), q.get("to", "9999")]
    letters = [c for c in (q.get("shifts") or "ABC") if c in SHIFT_LETTERS]
    where.append("letter IN (%s)" % ",".join("?" * len(letters)))
    args += letters
    group = q.get("group", "all")
    if group in ("D", "J"):
        where.append("loom LIKE ?")
        args.append(group + "%")
    looms = [l for l in (q.get("looms") or "").split(",") if l]
    if looms:
        where.append("loom IN (%s)" % ",".join("?" * len(looms)))
        args += looms
    cond = " AND ".join(where)

    with fact() as db:
        tot = db.execute(
            "SELECT SUM(run_min) run, SUM(stop_min) stop, SUM(picks) picks, COUNT(*) n,"
            " SUM(weft_stop_min) weft, SUM(manual_min) manual, SUM(warp_stop_min) warp,"
            " SUM(top_stop_min) top, SUM(power_min) power, SUM(other_min) other"
            " FROM shift_full WHERE " + cond, args).fetchone()
        days = db.execute(
            "SELECT day, SUM(run_min) run, SUM(stop_min) stop, SUM(manual_min) manual"
            " FROM shift_full WHERE " + cond + " GROUP BY day ORDER BY day", args).fetchall()
        looms_rows = db.execute(
            "SELECT loom, SUM(run_min) run, SUM(stop_min) stop, SUM(picks) picks,"
            " SUM(weft_ct) weft_ct, SUM(warp_ct) warp_ct, SUM(top_ct) top_ct,"
            " SUM(manual_ct) manual_ct, SUM(manual_min) manual_min,"
            " SUM(wait_total_min) wait, COUNT(*) shifts"
            " FROM shift_full WHERE " + cond + " GROUP BY loom", args).fetchall()

    run = tot["run"] or 0.0
    stop = tot["stop"] or 0.0
    cal = run + stop
    causes = {"Уток": tot["weft"] or 0, "Ручные остановы": tot["manual"] or 0,
              "Основа": tot["warp"] or 0, "Верхний навой": tot["top"] or 0,
              "Питание выключено": tot["power"] or 0, "Прочее": tot["other"] or 0}

    looms_out = []
    for r in looms_rows:
        c = (r["run"] or 0) + (r["stop"] or 0)
        kp = (r["picks"] or 0) / 1000.0 or 1
        looms_out.append({
            "loom": r["loom"], "eff": round(100 * (r["run"] or 0) / c, 1) if c else 0,
            "kpicks": round((r["picks"] or 0) / 1000, 1),
            "weft_ct": int(r["weft_ct"] or 0), "weft_cmpx": round(100 * (r["weft_ct"] or 0) / kp, 1),
            "warp_ct": int(r["warp_ct"] or 0), "top_ct": int(r["top_ct"] or 0),
            "manual_ct": int(r["manual_ct"] or 0), "manual_h": round((r["manual_min"] or 0) / 60, 1),
            "wait_h": round((r["wait"] or 0) / 60, 1), "shifts": int(r["shifts"] or 0),
        })
    looms_out.sort(key=lambda x: x["eff"])

    return {
        "totals": {"eff": round(100 * run / cal, 1) if cal else 0,
                   "run_h": round(run / 60), "stop_h": round(stop / 60),
                   "mpicks": round((tot["picks"] or 0) / 1e6, 2), "rows": tot["n"] or 0},
        "causes": {k: round(v / 60, 1) for k, v in causes.items() if v > 0},
        "by_day": [{"day": r["day"],
                    "eff": round(100 * (r["run"] or 0) / ((r["run"] or 0) + (r["stop"] or 0)), 1)
                           if ((r["run"] or 0) + (r["stop"] or 0)) else 0,
                    "manual_h": round((r["manual"] or 0) / 60, 1)} for r in days],
        "by_loom": looms_out,
    }


def walk(day, letter):
    """Обход цеха: станки с наибольшими потерями за смену и причина простоя."""
    rows = shift_rows(day, letter)
    out = []
    for r in rows:
        parts = [("уток", r["weft_fix_min"]), ("ворс", r["top_fix_min"]),
                 ("основа", r["warp_fix_min"]), ("ручные", r["manual_min"]),
                 ("ожидание оператора", r["wait_total_min"])]
        parts = [p for p in parts if p[1] and p[1] > 0]
        parts.sort(key=lambda p: -p[1])
        out.append({
            "loom": r["loom"], "style": r["style"] or "—",
            "eff": r["effic_pct"], "stop_min": round(r["stop_min"]),
            "weft_ct": r["weft_ct"], "top_ct": r["top_ct"], "warp_ct": r["warp_ct"],
            "manual_ct": r["manual_ct"], "wait_min": round(r["wait_total_min"]),
            "main": parts[0][0] if parts else "—",
            "main_min": round(parts[0][1]) if parts else 0,
        })
    out.sort(key=lambda x: -x["stop_min"])
    return {"day": day, "shift": letter, "rows": out}


def shift_summary(day, letter):
    """Короткая сводка по смене — то, что имеет смысл прочитать с телефона.

    Если смена ещё не загружена из FACT (зеркало не обновляли), возвращает
    `loaded: False` — врать нулями хуже, чем честно сказать, что данных нет.
    """
    with fact() as db:
        t = db.execute(
            "SELECT COUNT(*) looms, SUM(run_min) run, SUM(stop_min) stop, SUM(picks) picks,"
            " SUM(weft_stop_min) weft, SUM(warp_stop_min) warp, SUM(top_stop_min) top,"
            " SUM(manual_min) manual, SUM(power_min) power, SUM(other_min) other,"
            " SUM(weft_ct) weft_ct, SUM(warp_ct) warp_ct, SUM(top_ct) top_ct,"
            " SUM(manual_ct) manual_ct, SUM(wait_total_min) wait"
            " FROM shift_full WHERE day=? AND letter=? AND run_min > 5",
            (day, letter)).fetchone()
        worst = db.execute(
            "SELECT loom, style, effic_pct, stop_min, manual_min, weft_ct, warp_ct, top_ct"
            " FROM shift_full WHERE day=? AND letter=? AND run_min > 5"
            " ORDER BY stop_min DESC LIMIT 5", (day, letter)).fetchall()

    if not t or not t["looms"]:
        return {"day": day, "shift": letter, "loaded": False}

    run, stop = t["run"] or 0.0, t["stop"] or 0.0
    cal = run + stop
    causes = {"уток": t["weft"] or 0, "основа": t["warp"] or 0, "ворс": t["top"] or 0,
              "ручные остановы": t["manual"] or 0, "обесточен": t["power"] or 0,
              "прочее": t["other"] or 0}
    return {
        "day": day, "shift": letter, "loaded": True,
        "looms": t["looms"],
        "effic": round(100 * run / cal, 1) if cal else 0,
        "kpicks": round((t["picks"] or 0) / 1000),
        "stop_h": round(stop / 60, 1),
        "wait_h": round((t["wait"] or 0) / 60, 1),
        "stops": {"уток": int(t["weft_ct"] or 0), "основа": int(t["warp_ct"] or 0),
                  "ворс": int(t["top_ct"] or 0), "ручные": int(t["manual_ct"] or 0)},
        "causes_h": {k: round(v / 60, 1) for k, v in sorted(causes.items(), key=lambda x: -x[1])
                     if v > 0},
        "worst": [{"loom": r["loom"], "style": r["style"] or "—", "eff": r["effic_pct"],
                   "stop_min": round(r["stop_min"]), "manual_min": round(r["manual_min"] or 0)}
                  for r in worst],
    }


def day_summary(day):
    """Итог за сутки: три смены вместе и каждая по отдельности.

    Отправляется утром, когда смена C закончилась и сутки закрыты.
    """
    with fact() as db:
        t = db.execute(
            "SELECT COUNT(DISTINCT loom) looms, SUM(run_min) run, SUM(stop_min) stop,"
            " SUM(picks) picks, SUM(weft_stop_min) weft, SUM(warp_stop_min) warp,"
            " SUM(top_stop_min) top, SUM(manual_min) manual, SUM(power_min) power,"
            " SUM(other_min) other, SUM(weft_ct) weft_ct, SUM(warp_ct) warp_ct,"
            " SUM(top_ct) top_ct, SUM(manual_ct) manual_ct, SUM(wait_total_min) wait"
            " FROM shift_full WHERE day=? AND run_min > 5", (day,)).fetchone()
        by_shift = db.execute(
            "SELECT letter, SUM(run_min) run, SUM(stop_min) stop, SUM(picks) picks"
            " FROM shift_full WHERE day=? AND run_min > 5 GROUP BY letter ORDER BY letter",
            (day,)).fetchall()
        worst = db.execute(
            "SELECT loom, SUM(stop_min) stop_min, SUM(manual_min) manual_min,"
            " 100.0*SUM(run_min)/(SUM(run_min)+SUM(stop_min)) eff"
            " FROM shift_full WHERE day=? AND run_min > 5 GROUP BY loom"
            " ORDER BY stop_min DESC LIMIT 5", (day,)).fetchall()

    if not t or not t["looms"]:
        return {"day": day, "loaded": False}

    run, stop = t["run"] or 0.0, t["stop"] or 0.0
    cal = run + stop
    causes = {"уток": t["weft"] or 0, "основа": t["warp"] or 0, "ворс": t["top"] or 0,
              "ручные остановы": t["manual"] or 0, "обесточен": t["power"] or 0,
              "прочее": t["other"] or 0}
    return {
        "day": day, "loaded": True, "looms": t["looms"],
        "effic": round(100 * run / cal, 1) if cal else 0,
        "kpicks": round((t["picks"] or 0) / 1000),
        "stop_h": round(stop / 60, 1), "wait_h": round((t["wait"] or 0) / 60, 1),
        "stops": {"уток": int(t["weft_ct"] or 0), "основа": int(t["warp_ct"] or 0),
                  "ворс": int(t["top_ct"] or 0), "ручные": int(t["manual_ct"] or 0)},
        "causes_h": {k: round(v / 60, 1) for k, v in sorted(causes.items(), key=lambda x: -x[1])
                     if v > 0},
        "by_shift": [{"shift": r["letter"],
                      "effic": round(100 * (r["run"] or 0) / ((r["run"] or 0) + (r["stop"] or 0)), 1)
                               if ((r["run"] or 0) + (r["stop"] or 0)) else 0,
                      "kpicks": round((r["picks"] or 0) / 1000)} for r in by_shift],
        "worst": [{"loom": r["loom"], "eff": round(r["eff"], 1),
                   "stop_min": round(r["stop_min"]), "manual_min": round(r["manual_min"] or 0)}
                  for r in worst],
    }


# --- сводка ручных остановов, как «Manual Stoppages Summary» в LDS -------------

# Категории остановов в итогах смены FACT (stop_ct / stop_tm, 13 штук) идут в
# порядке колонок шаблона Toyota shiftreport.xlsm; сверено с журналом остановов
# за три недели по совпадению счётчиков:
#   0 ворс  1 основа  2 ложная кромка  5 уток  6 конец навоя (WARP_OUT)
#   7 съём ткани (DOFF)  8 ручной (MANUAL)  9 питание выключено  10 прочие (OTHER)
IDX_WARP_OUT, IDX_DOFF, IDX_MANUAL, IDX_POWER, IDX_OTHER = 6, 7, 8, 9, 10

# Длинные остановы, которые станок называет сам: в LDS это «Knotting» и съём.
LDS_MACHINE = {"warp_out": "Конец навоя", "doffing": "Съём ткани"}
LDS_NAMES = {**{c["id"]: c["reason"] for c in tickets.CATEGORIES}, **LDS_MACHINE,
             "unexplained": "Без причины", "power": "Обесточен"}
LDS_ORDER = [c["id"] for c in tickets.CATEGORIES] + ["warp_out", "doffing", "unexplained", "power"]
SHIFT_HOURS = (("A", 7, 15), ("B", 15, 23), ("C", 23, 31))


def _arr(raw, cast):
    out = []
    for x in (raw or "").split():
        try:
            out.append(cast(float(x)))
        except ValueError:
            out.append(cast(0))
    return (out + [cast(0)] * 13)[:13]


def shift_parts(start_iso, dur_sec):
    """Раскладывает простой по сменам: [(производственный день, смена, минут)].

    Тикет на останов, который тянулся через пересменку или через выходной,
    делится между сменами — так же, как FACT делит своё время простоя.
    Ночная смена C (23:00–07:00) относится к дню, в который началась.
    """
    try:
        start = datetime.fromisoformat(start_iso).replace(tzinfo=None)
    except (TypeError, ValueError):
        return []
    end = start + timedelta(seconds=min(max(0, dur_sec or 0), 60 * 86400))
    out = []
    d = start.date() - timedelta(days=1)
    while True:
        base = datetime(d.year, d.month, d.day)
        if base + timedelta(hours=7) >= end:
            break
        for letter, a, b in SHIFT_HOURS:
            lo, hi = max(start, base + timedelta(hours=a)), min(end, base + timedelta(hours=b))
            if hi > lo:
                out.append((d.strftime("%Y.%m.%d"), letter, (hi - lo).total_seconds() / 60))
        d += timedelta(days=1)
    return out


def _loom_order(k):
    m = re.match(r"^([A-Za-z]+)(\d+)$", k or "")
    return (m.group(1), int(m.group(2))) if m else (k or "", 0)


def lds_manual(date_from, date_to, group="day"):
    """Сводка ручных остановов (подробности — в _lds_manual); ответ держим две минуты."""
    return cache.get(("lds", date_from, date_to, group), 120,
                     lambda: _lds_manual(date_from, date_to, group))


def _lds_manual(date_from, date_to, group="day"):
    """Сводка ручных остановов — наш вариант «Manual Stoppages Summary» из LDS.

    Строка — производственный день (или смена, или станок). Колонки:

        Shed Eff    работа ÷ (весь парк × календарное время смен) — сюда
                    входят и станки, простоявшие без работы всю смену;
        Time Eff    работа ÷ (работа + простой) работавших станков — наш КПД;
        Tot. Stop   длинные остановы ÷ то же время работавших станков;
        Prod Eff    Time Eff + Tot. Stop — КПД, если бы длинных остановов не
                    было и остались одни обрывы. В LDS именно так: 48,1 + 44,0 = 92,1.

    Длинные остановы берутся из итогов смены FACT, где время уже поделено по
    сменам: ручной останов и «прочее» (станок стоит молча), конец навоя, съём
    ткани. Тикет с причиной забирает своё время из молчаливых и кладёт в свою
    колонку (электрика, ТОиР, заправка…). Что осталось — «без причины»: это
    мерило дисциплины. В LDS его закрывают RFID-карты мастеров, у нас — тикеты.

    Обесточенный станок FACT простоем не считает, поэтому колонка «Обесточен»
    справочная и в Tot. Stop не входит.
    """
    keyf = {"day": lambda d, l, lo: d, "shift": lambda d, l, lo: l,
            "loom": lambda d, l, lo: lo}[group]
    with fact() as db:
        rows = db.execute(
            "SELECT day, letter, loom, run_min, stop_min, stop_ct_raw, stop_tm_raw"
            " FROM shift_full WHERE day BETWEEN ? AND ?", (date_from, date_to)).fetchall()
    try:
        lo = (datetime.strptime(date_from, "%Y.%m.%d") - timedelta(days=3)).strftime("%Y-%m-%d")
        hi = (datetime.strptime(date_to, "%Y.%m.%d") + timedelta(days=2)).strftime("%Y-%m-%d")
    except ValueError:
        lo, hi = "0000", "9999"
    conn = tickets.db()
    trows = conn.execute(
        "SELECT loom, started_at, duration_sec, fact_cause, category_id FROM ticket"
        " WHERE category_id IS NOT NULL AND started_at >= ? AND started_at < ?",
        (lo, hi)).fetchall()
    conn.close()

    acc, working, all_shifts, installed = {}, set(), set(), set()
    # Смена, в которую не работал ни один станок (выходной, праздник), в отчёт
    # не попадает — как в LDS, где воскресенья в сводке нет.
    worked = {(r["day"], r["letter"]) for r in rows if (r["run_min"] or 0) > 5}
    rows = [r for r in rows if (r["day"], r["letter"]) in worked]

    def row(k):
        return acc.setdefault(k, {"key": k, "looms": set(), "run_w": 0.0, "cal_w": 0.0,
                                  "run_all": 0.0, "shifts": set(), "silent": [0, 0.0],
                                  "tk": [], "tk_power": 0.0, "cats": {}})

    def add(a, cid, n, m):
        v = a["cats"].setdefault(cid, [0, 0.0])
        v[0] += n
        v[1] += m

    for r in rows:
        a = row(keyf(r["day"], r["letter"], r["loom"]))
        run = r["run_min"] or 0
        a["run_all"] += run
        a["shifts"].add((r["day"], r["letter"]))
        all_shifts.add((r["day"], r["letter"]))
        installed.add(r["loom"])
        if run <= 5:
            continue
        ct, tm = _arr(r["stop_ct_raw"], int), _arr(r["stop_tm_raw"], float)
        working.add((r["day"], r["letter"], r["loom"]))
        a["looms"].add(r["loom"])
        a["run_w"] += run
        a["cal_w"] += run + (r["stop_min"] or 0)
        a["silent"][0] += ct[IDX_MANUAL] + ct[IDX_OTHER]
        a["silent"][1] += tm[IDX_MANUAL] + tm[IDX_OTHER]
        for cid, i in (("warp_out", IDX_WARP_OUT), ("doffing", IDX_DOFF), ("power", IDX_POWER)):
            if ct[i] or tm[i]:
                add(a, cid, ct[i], tm[i])

    # Тикет делится по сменам, через которые тянулся простой, и попадает туда,
    # где станок в эту смену работал.
    for t in trows:
        _, src = tickets.resolve_reason(t["fact_cause"] or "Unknown", t["category_id"])
        if src != "тикет":
            continue
        first = True
        for day, letter, m in shift_parts(t["started_at"], t["duration_sec"]):
            if (day, letter, t["loom"]) not in working:
                continue
            a = acc[keyf(day, letter, t["loom"])]
            if t["fact_cause"] == "Power_off":
                a["tk_power"] += m
            else:
                a["tk"].append((t["category_id"], 1 if first else 0, m))
            first = False

    # Тикет не может объяснить больше, чем FACT насчитал молчаливых остановов
    # за смену: лишнее (тикет забыли закрыть) срезаем пропорционально.
    for a in acc.values():
        n, m = a["silent"]
        tk_m = sum(x[2] for x in a["tk"])
        k = min(1.0, m / tk_m) if tk_m else 1.0
        for cid, cnt, mins in a["tk"]:
            add(a, cid, cnt, mins * k)
        tn = sum(x[1] for x in a["tk"])
        if n or m:
            a["cats"]["unexplained"] = [max(0, n - tn), max(0.0, m - tk_m * k)]

    def finish(a, shed_den):
        cal = a["cal_w"]
        cats = a["cats"]
        stop_min = sum(v[1] for c, v in cats.items() if c != "power")
        te = 100 * a["run_w"] / cal if cal else 0
        sp = 100 * stop_min / cal if cal else 0
        un = cats.get("unexplained", [0, 0.0])[1]
        out = {cid: {"n": n, "min": round(m), "avg_sec": round(m * 60 / n) if n else None,
                     "pct": round(100 * m / cal, 2) if cal else 0}
               for cid, (n, m) in cats.items()}
        if "power" in out:
            out["power"]["ticketed_min"] = round(min(a["tk_power"], cats["power"][1]))
        looms = a["looms"]
        return {"key": a["key"], "looms": len(looms) if isinstance(looms, set) else looms,
                "shed_eff": round(100 * a["run_all"] / shed_den, 1) if shed_den else None,
                "time_eff": round(te, 1), "stop_pct": round(sp, 1),
                "prod_eff": round(min(100.0, te + sp), 1), "stop_min": round(stop_min),
                "explained_pct": round(100 * (stop_min - un) / stop_min, 1) if stop_min else None,
                "cats": out}

    n_inst = len(installed)
    rows_out = []
    for key in sorted(acc, key=_loom_order if group == "loom" else (lambda x: x)):
        a = acc[key]
        den = (len(all_shifts) if group == "loom" else n_inst * len(a["shifts"])) * 480
        rows_out.append(finish(a, den))

    tot = {"key": "итого", "looms": n_inst, "cats": {},
           "tk_power": sum(a["tk_power"] for a in acc.values()),
           **{f: sum(a[f] for a in acc.values()) for f in ("run_w", "cal_w", "run_all")}}
    for a in acc.values():
        for cid, (n, m) in a["cats"].items():
            v = tot["cats"].setdefault(cid, [0, 0.0])
            v[0] += n
            v[1] += m
    present = {cid for a in acc.values() for cid in a["cats"]} | {"unexplained"}
    return {
        "from": date_from, "to": date_to, "group": group,
        "installed": n_inst, "days": len({d for d, _ in all_shifts}), "shifts": len(all_shifts),
        "columns": [{"id": cid, "name": LDS_NAMES[cid],
                     "kind": ("machine" if cid in LDS_MACHINE else
                              "none" if cid == "unexplained" else
                              "power" if cid == "power" else "ticket")}
                    for cid in LDS_ORDER if cid in present],
        "rows": rows_out,
        "totals": finish(tot, n_inst * len(all_shifts) * 480),
    }


def rebuild_daily_reports(days):
    """Производственный отчёт (лист TOYOTA) заново за эти дни — после новых смен
    или после ручного ввода заправки. Расчёт — в _tools/make_excel_report.py."""
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)
    import fact_api
    import make_excel_report as mer
    # Смены отчёт берёт из shift_loom, которую ведёт сборщик. Если смены ещё
    # нет (идёт день), старый код шёл за ней в FACT по сети — здесь не ходим.
    fact_api.get_shift = lambda shift: []
    done = []
    for day in days:
        try:
            mer.save_db(day, mer.build(day))
            done.append(day)
        except SystemExit:
            continue                # за этот день смен ещё нет
    cache.clear()
    return done


def excel_path(day):
    return os.path.join(REPORTS_DIR, f"Production Report {day.replace('.', '-')}.xlsx")


def export_excel(day):
    """Собирает Excel-отчёт за день теми же скриптами, что и из командной строки."""
    if os.name != "nt":
        # COM Excel доступен только на Windows. На Linux создаём самостоятельный
        # XLSX из тех же рассчитанных данных, не меняя исходный шаблон XLSB.
        if TOOLS_DIR not in sys.path:
            sys.path.insert(0, TOOLS_DIR)
        import make_excel_report as mer
        from xlsx_report import write_report
        rows = mer.build(day)
        mer.save_db(day, rows)
        path = excel_path(day)
        write_report(day, rows, path)
        return {"ok": True, "step": "xlsx", "path": path,
                "log": "Отчёт XLSX: %d станков; формат Linux без шаблона Excel" % len(rows)}
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r1 = subprocess.run([sys.executable, "make_excel_report.py", day], cwd=TOOLS_DIR,
                        capture_output=True, text=True, encoding="utf-8", env=env, timeout=600)
    if r1.returncode:
        return {"ok": False, "step": "расчёт", "log": (r1.stdout or "") + (r1.stderr or "")}
    # Папку вывода передаём явно: у скрипта своя по умолчанию, и копия приложения
    # (проверка, песочница) писала бы файл в папку рабочего приложения.
    os.makedirs(REPORTS_DIR, exist_ok=True)
    r2 = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File",
                         os.path.join(TOOLS_DIR, "fill_template.ps1"), "-Day", day,
                         "-OutDir", REPORTS_DIR],
                        cwd=TOOLS_DIR, capture_output=True, text=True, encoding="utf-8", timeout=900)
    path = excel_path(day)
    return {"ok": os.path.exists(path), "step": "шаблон", "path": path,
            "log": ((r2.stdout or "") + (r2.stderr or ""))[-1500:]}
