"""Показатели, по которым видно, где цех теряет время.

Считаются по свёртке `stop_day` — пособытийные остановы из FACT, сложенные по
дню, станку, смене и причине, с гистограммой времени прихода оператора. Три
величины, которых нет в отчётах FACT:

    MTTR                время устранения одного останова по каждой причине;
    время реакции       от остановки станка до прихода оператора;
    обрывность на 100k  обрывы на сто тысяч пиков — сравнимо между станками,
                        в отличие от «обрывов за смену».

Раньше всё это считалось по сырым остановам: 30 дней — 217 тысяч строк и
2,4 секунды, вся история — 28 секунд. На 80 станках это стало бы минутой.
Свёртка читает тысячи строк вместо миллионов, медианы берутся из гистограммы.

Плюс пересчёт выработки в полотенца: счётчик Toyota считает ряды, а полотенец в
ряду столько, сколько панелей — без этого производительность занижена в разы.
"""
import time
from collections import defaultdict

import cache
from ingest import H, hist_add, hist_q
from storage import fact, shop

# Причины, которые станок называет сам. Остальное — ручные остановы и «прочее»,
# то есть то, подо что заведены тикеты.
CAUSE_RU = {
    "Weft": "Уток", "Warp": "Основа", "Warp_top": "Ворс",
    "False_selvage": "Ложная кромка", "Leno_L": "Перевивка (лев)",
    "Leno_R": "Перевивка (прав)", "Manual": "Ручной останов",
    "Power_off": "Обесточен", "Machine_failure": "Отказ станка",
    "Warp_out": "Конец навоя", "Cloth_doffing": "Съём ткани",
    "Cloth_mending": "Починка ткани", "Out_of_product": "Нет продукции",
    "Other": "Прочее",
}
BREAK_CAUSES = ("Weft", "Warp", "Warp_top")


def available_days():
    with fact() as db:
        return [r[0] for r in db.execute(
            "SELECT DISTINCT day FROM stop_day ORDER BY day DESC")]


def panels_by_cloth():
    """Сколько полотенец в ряду по каждому коду ткани.

    Берём из готовых отчётов: там число панелей проставлено людьми. Для кодов,
    которых там нет, считаем один — лучше занизить, чем выдумать.
    """
    return cache.get(("panels",), 300, _panels_by_cloth)


def _panels_by_cloth():
    out = {}
    with fact() as db:
        for r in db.execute(
                "SELECT cloth, panels, COUNT(*) n FROM report_daily"
                " WHERE panels IS NOT NULL AND cloth IS NOT NULL AND cloth <> ''"
                " GROUP BY cloth, panels ORDER BY cloth, n DESC"):
            out.setdefault(r["cloth"], int(r["panels"] or 1))
    return out


# Разумные границы длины изделия: полотенце короче 200 и длиннее 9000 пиков
# не бывает. За этими границами — не длина, а сбой счётчика.
PPT_MIN, PPT_MAX = 200, 9000
_ppt_cache = {"at": 0, "data": None}


def ppt_by_cloth(min_pieces=50, min_days=3, max_age=300):
    """Пиков на изделие по счётчикам станка — по каждому коду ткани.

    В FACT этого параметра нет: длину задаёт дизайн-файл жаккарда. Но станок
    считает и пики, и ряды, поэтому величина восстанавливается.

    Берём медиану по дням, а не отношение сумм. Если код ткани выставили
    посреди рулона, пики уже накоплены, а ряды ещё нет — отношение сумм даёт
    десятки тысяч (так у J22 выходило 41 407 вместо тысячи с небольшим).
    Медиана такие дни отбрасывает, а разброс показывает, можно ли верить:
    у чистых кодов он 1–2 %, у мусорных — десятки процентов.
    """
    now = time.time()
    if _ppt_cache["data"] is not None and now - _ppt_cache["at"] < max_age:
        return _ppt_cache["data"]

    per = defaultdict(list)
    with fact() as db:
        for r in db.execute(
                "SELECT cloth, day, SUM(picks) p, SUM(pieces) pc FROM shift_full"
                " WHERE pieces > 10 AND cloth IS NOT NULL AND cloth <> ''"
                " GROUP BY cloth, day"):
            v = (r["p"] or 0) / r["pc"]
            if PPT_MIN <= v <= PPT_MAX:
                per[r["cloth"]].append((v, int(r["pc"])))

    out = {}
    for cloth, vals in per.items():
        pieces = sum(p for _, p in vals)
        if len(vals) < min_days or pieces < min_pieces:
            continue
        xs = sorted(v for v, _ in vals)
        med = xs[len(xs) // 2]
        lo, hi = xs[int(len(xs) * 0.1)], xs[min(len(xs) - 1, int(len(xs) * 0.9))]
        spread = round(100.0 * (hi - lo) / med, 1) if med else 0
        out[cloth] = {"ppt": round(med), "days": len(xs), "spread": spread,
                      "pieces": pieces, "trusted": spread <= 10}
    _ppt_cache.update(at=now, data=out)
    return out


PRODUCTION_GROUPS = {"day": "day", "shift": "day || '.' || letter", "loom": "loom",
                     "cloth": "cloth"}


def production_grouped(date_from, date_to, group="day"):
    """Выработка по дням, сменам, станкам или кодам ткани — с полотенцами.

    Полотенца считаются по каждому коду ткани отдельно (у разных тканей разное
    число панелей) и только потом складываются.
    """
    key = PRODUCTION_GROUPS[group]
    panels = panels_by_cloth()
    acc = {}
    with fact() as db:
        for r in db.execute(
                "SELECT " + key + " k, cloth, SUM(picks) picks, SUM(meters) meters,"
                " SUM(pieces) pieces, SUM(run_min) run, SUM(stop_min) stop"
                " FROM shift_full WHERE day BETWEEN ? AND ? AND run_min > 5"
                " GROUP BY k, cloth", (date_from, date_to)):
            a = acc.setdefault(r["k"], {"key": r["k"], "picks": 0, "meters": 0.0,
                                        "rows_woven": 0, "towels": 0, "run_min": 0.0,
                                        "stop_min": 0.0})
            a["picks"] += r["picks"] or 0
            a["meters"] += r["meters"] or 0
            a["rows_woven"] += int(r["pieces"] or 0)
            a["towels"] += int((r["pieces"] or 0) * panels.get(r["cloth"] or "", 1))
            a["run_min"] += r["run"] or 0
            a["stop_min"] += r["stop"] or 0
        looms = {r["k"]: r["n"] for r in db.execute(
            "SELECT " + key + " k, COUNT(DISTINCT loom) n FROM shift_full"
            " WHERE day BETWEEN ? AND ? AND run_min > 5 GROUP BY k", (date_from, date_to))}
    out = []
    for k in sorted(acc):
        a = acc[k]
        cal = a["run_min"] + a["stop_min"]
        out.append({**a, "meters": round(a["meters"]), "run_min": round(a["run_min"]),
                    "stop_min": round(a["stop_min"]), "looms": looms.get(k, 0),
                    "effic_pct": round(100 * a["run_min"] / cal, 1) if cal else 0})
    return out


def production(date_from, date_to):
    """Выработка за период: ряды, полотенца, метры, пики."""
    panels = panels_by_cloth()
    rows = []
    with fact() as db:
        for r in db.execute(
                "SELECT loom, cloth, SUM(picks) picks, SUM(meters) meters,"
                " SUM(pieces) pieces, SUM(run_min) run_min, SUM(stop_min) stop_min"
                " FROM shift_full WHERE day BETWEEN ? AND ? AND run_min > 5"
                " GROUP BY loom, cloth", (date_from, date_to)):
            p = panels.get(r["cloth"], 1)
            rows.append({
                "loom": r["loom"], "cloth": r["cloth"], "panels": p,
                "picks": r["picks"] or 0, "meters": round(r["meters"] or 0),
                "rows_woven": int(r["pieces"] or 0),
                "towels": int((r["pieces"] or 0) * p),
                "run_min": r["run_min"] or 0, "stop_min": r["stop_min"] or 0,
            })
    return rows


def bottlenecks(date_from, date_to, looms=None, shifts=None, max_age=120):
    """Где цех теряет время: по причинам, станкам, сменам и людям.

    Ответ держим две минуты: данные дописываются не чаще, а один и тот же
    отчёт за 30 дней открывают и мастер, и начальник, и экран в кабинете.
    """
    key = ("bottlenecks", date_from, date_to, tuple(looms or ()), tuple(shifts or ()))
    return cache.get(key, max_age, lambda: _bottlenecks(date_from, date_to, looms, shifts))


def _bottlenecks(date_from, date_to, looms=None, shifts=None):
    where = ["day BETWEEN ? AND ?"]
    args = [date_from, date_to]
    if looms:
        where.append("loom IN (%s)" % ",".join("?" * len(looms)))
        args += looms
    if shifts:
        where.append("letter IN (%s)" % ",".join("?" * len(shifts)))
        args += list(shifts)
    cond = " AND ".join(where)

    # Один проход по свёртке — станок × смена × причина, — а разрезы по
    # причинам, станкам и сменам складываются в Python из пары тысяч строк.
    # Замер на 80 станках за год: три отдельных GROUP BY — 4,5 с, один — 1,9 с.
    # Строки берём кортежами: доступ по имени к тридцати колонкам гистограммы
    # стоил бы ещё столько же.
    with fact() as db:
        db.row_factory = None
        rows = db.execute(
            "SELECT loom, letter, cause, SUM(n), SUM(dur_sec), " +
            ", ".join("SUM(%s)" % h for h in H) +
            " FROM stop_day WHERE " + cond + " GROUP BY loom, letter, cause", args).fetchall()
        # Пики за тот же период — чтобы привести обрывы к 100 тысячам.
        picks = dict(db.execute(
            "SELECT loom, SUM(picks) FROM shift_full WHERE day BETWEEN ? AND ?"
            " AND run_min > 5 GROUP BY loom", (date_from, date_to)).fetchall())

    width = len(H) + 2                     # количество, секунды, корзины реакции
    c_acc, l_acc, s_acc = {}, {}, {}
    l_extra = defaultdict(lambda: [0, 0, 0, 0])   # уток, основа+ворс, ручные, ручные сек
    for loom, letter, cause, *vals in rows:
        vals = [v or 0 for v in vals]
        for acc, key in ((c_acc, cause), (l_acc, loom), (s_acc, letter if letter else None)):
            if key is None:
                continue
            a = acc.get(key)
            if a is None:
                acc[key] = list(vals)
            else:
                for i in range(width):
                    a[i] += vals[i]
        e = l_extra[loom]
        if cause == "Weft":
            e[0] += vals[0]
        elif cause in ("Warp", "Warp_top"):
            e[1] += vals[0]
        elif cause == "Manual":
            e[2] += vals[0]
            e[3] += vals[1]

    resp_all = [0] * len(H)
    for a in c_acc.values():
        hist_add(resp_all, a[2:])
    by_cause = {c: {"cause": c, "name": CAUSE_RU.get(c, c), "count": a[0],
                    "minutes": round(a[1] / 60), "mttr_sec": round(a[1] / a[0]) if a[0] else 0,
                    "resp_median": hist_q(a[2:], 0.5)} for c, a in c_acc.items()}
    by_loom = {l: {"loom": l, "stops": a[0], "lost_min": round(a[1] / 60),
                   "weft_ct": l_extra[l][0], "warp_ct": l_extra[l][1],
                   "manual_ct": l_extra[l][2], "manual_min": round(l_extra[l][3] / 60),
                   "resp_median": hist_q(a[2:], 0.5), "resp_p90": hist_q(a[2:], 0.9)}
               for l, a in l_acc.items()}
    by_shift = {s: {"shift": s, "stops": a[0], "lost_min": round(a[1] / 60),
                    "resp_median": hist_q(a[2:], 0.5)} for s, a in sorted(s_acc.items())}

    for loom, a in by_loom.items():
        p = picks.get(loom, 0)
        k = 100000.0 / p if p else 0
        a["picks"] = p
        a["weft_per_100k"] = round(a["weft_ct"] * k, 1) if k else None
        a["warp_per_100k"] = round(a["warp_ct"] * k, 1) if k else None

    causes = sorted(by_cause.values(), key=lambda x: -x["minutes"])
    total_min = sum(c["minutes"] for c in causes) or 1
    for c in causes:
        c["share"] = round(100.0 * c["minutes"] / total_min, 1)

    looms_out = sorted(by_loom.values(), key=lambda x: -x["lost_min"])
    weft_rates = sorted(x["weft_per_100k"] for x in looms_out if x["weft_per_100k"])
    warp_rates = sorted(x["warp_per_100k"] for x in looms_out if x["warp_per_100k"])

    return {
        "from": date_from, "to": date_to,
        "by_cause": causes,
        "by_loom": looms_out,
        "by_shift": sorted(by_shift.values(), key=lambda x: x["shift"]),
        "by_operator": operators(date_from, date_to),
        # Квантили — по гистограмме свёртки, с точностью до доли корзины.
        "response": {
            "count": sum(resp_all),
            "median": hist_q(resp_all, 0.5), "p75": hist_q(resp_all, 0.75),
            "p90": hist_q(resp_all, 0.9), "approx": True,
        },
        "totals": {
            "stops": sum(c["count"] for c in causes),
            "lost_h": round(total_min / 60, 1),
            "looms": len(looms_out),
            "weft_median": weft_rates[len(weft_rates) // 2] if weft_rates else None,
            "warp_median": warp_rates[len(warp_rates) // 2] if warp_rates else None,
        },
    }


def operators(date_from, date_to):
    """Реакция и потери по людям: останов привязывается к тому, кто был на смене."""
    db = shop()
    who = {}
    for r in db.execute(
            "SELECT a.day, a.shift, a.loom, o.code, o.name FROM assignment a"
            " JOIN operator o ON o.id = a.operator_id WHERE a.day BETWEEN ? AND ?",
            (date_from, date_to)):
        who[(r["day"], r["shift"], r["loom"])] = (r["code"], r["name"])
    db.close()
    if not who:
        return []

    acc = defaultdict(lambda: {"stops": 0, "lost_sec": 0, "hist": [0] * len(H), "looms": set()})
    with fact() as db:
        db.row_factory = None
        for day, letter, loom, n, sec, *hist in db.execute(
                "SELECT day, letter, loom, SUM(n), SUM(dur_sec), " +
                ", ".join("SUM(%s)" % h for h in H) +
                " FROM stop_day WHERE day BETWEEN ? AND ? GROUP BY day, letter, loom",
                (date_from, date_to)):
            key = who.get((day, letter, loom))
            if not key:
                continue
            a = acc[key]
            a["stops"] += n or 0
            a["lost_sec"] += sec or 0
            a["looms"].add(loom)
            hist_add(a["hist"], [x or 0 for x in hist])

    out = []
    for (code, name), a in acc.items():
        out.append({
            "code": code, "name": name, "stops": a["stops"],
            "lost_min": round(a["lost_sec"] / 60), "looms": len(a["looms"]),
            "resp_median": hist_q(a["hist"], 0.5), "resp_p90": hist_q(a["hist"], 0.9),
        })
    out.sort(key=lambda x: -(x["resp_median"] or 0))
    return out
