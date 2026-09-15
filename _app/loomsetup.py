"""Заправка станка, введённая вручную: GSM, вес штуки, PPT, панели, пряжа и лот.

Часть этих данных пока не приходит ни из FACT, ни из 1С: вес штуки и лот
пряжи знает только цех. Запись действует с указанного дня, пока станок не
перезаправят. Пустое поле значит «как в справочнике»: берётся значение из
справочника артикулов или техкарты 1С.

Вводить можно по одному станку (щелчок по номеру станка в отчёте) или таблицей
на все станки сразу — вкладка «Заправка», как раньше в Excel. Пряжа проверяется
по справочнику (yarns.py): одно написание на одну пряжу.

Отчёт (лист TOYOTA, `_tools/make_excel_report.py`) читает эту таблицу сам;
после сохранения отчёт пересобирается за все дни, начиная с дня заправки.
"""
import json
import re
from datetime import datetime

import yarns
from storage import fact, shop

NUMBERS = {"gsm": (100, 1500), "weight_kg": (0.01, 5), "ppt": (200, 9000), "panels": (1, 12)}
# Места пряжи — как типы компонентов в техкарте 1С, у каждого свой лот:
# weft1 — уток, weft2 — кромка, weft3 — бордюр, weft4 — бордюр полиэстер.
YARNS = ("pile", "ground", "weft1", "weft2", "hemply", "hempoly", "weft3", "fancyply", "weft4")
TEXTS = tuple("%s_%s" % (y, k) for y in YARNS for k in ("yarn", "lot"))
FIELDS = tuple(NUMBERS) + TEXTS
YARN_RU = {"pile": "ворс", "ground": "грунт", "weft1": "уток", "weft2": "кромка",
           "hemply": "кромка кручёная", "hempoly": "кромка полиэстер", "weft3": "бордюр",
           "fancyply": "бордюр кручёная", "weft4": "бордюр полиэстер"}
NAMES = {"gsm": "GSM", "weight_kg": "вес штуки", "ppt": "PPT", "panels": "панели"}
MAX_DAYS = 62           # дальше назад отчёт при сохранении не пересобираем


def effective(day):
    """{станок: заправка, действующая в этот день} — только введённое вручную."""
    db = shop()
    rows = db.execute(
        "SELECT * FROM loom_setup s WHERE from_day <= ? AND from_day = ("
        " SELECT MAX(from_day) FROM loom_setup b WHERE b.loom = s.loom AND b.from_day <= ?)",
        (day, day)).fetchall()
    db.close()
    return {r["loom"]: dict(r) for r in rows}


def _number(field, raw):
    s = str(raw if raw is not None else "").strip().replace(",", ".").replace(" ", "")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        raise ValueError("%s: «%s» — не число" % (NAMES[field], raw))
    # Вес штуки часто пишут в граммах: 635 — это 0,635 кг.
    if field == "weight_kg" and v > NUMBERS["weight_kg"][1]:
        v = v / 1000.0
    lo, hi = NUMBERS[field]
    if not lo <= v <= hi:
        raise ValueError("%s: %s — вне разумных границ %s–%s" % (NAMES[field], raw, lo, hi))
    return int(round(v)) if field == "panels" else round(v, 4)


def _clean(values):
    """Проверенная строка заправки: числа в границах, пряжа — из справочника."""
    row = {f: _number(f, values.get(f, "")) for f in NUMBERS}
    for y in YARNS:
        try:
            row[y + "_yarn"] = yarns.resolve(values.get(y + "_yarn"))
        except ValueError as e:
            raise ValueError("%s: %s" % (YARN_RU[y], e))
        lot = re.sub(r"\s+", " ", str(values.get(y + "_lot") or "").strip().upper())
        row[y + "_lot"] = lot[:40] or None
    return row


def _check_day(from_day):
    try:
        datetime.strptime(from_day or "", "%Y.%m.%d")
    except ValueError:
        raise ValueError("день заправки: нужна дата вида 2026.09.14")


def _write(pairs, from_day, who):
    """Записать [(станок, строка)] и пересобрать отчёт с дня заправки."""
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    db = shop()
    db.executemany(
        "INSERT OR REPLACE INTO loom_setup (loom, from_day, %s, set_by, set_at) VALUES (%s)"
        % (", ".join(FIELDS), ",".join("?" * (len(FIELDS) + 4))),
        [(loom, from_day, *[row[f] for f in FIELDS], who, now) for loom, row in pairs])
    db.commit()
    db.close()
    with fact() as f:
        days = [r[0] for r in f.execute(
            "SELECT DISTINCT day FROM shift_full WHERE day >= ? ORDER BY day LIMIT ?",
            (from_day, MAX_DAYS))]
    import reports
    return reports.rebuild_daily_reports(days)


def save(looms, from_day, values, who=""):
    """Одна заправка на один или несколько станков (окно по номеру станка)."""
    looms = sorted({(l or "").strip().upper() for l in looms if (l or "").strip()})
    if not looms:
        raise ValueError("не указан станок")
    _check_day(from_day)
    row = _clean(values)
    days = _write([(loom, row) for loom in looms], from_day, who)
    return {"looms": looms, "from_day": from_day, "days": days}


def save_many(rows, from_day, who=""):
    """Таблица заправки: у каждого станка своя строка. Либо сохраняется всё,
    либо ничего — с перечнем, что поправить: половина сохранённой таблицы
    путает больше, чем ошибка."""
    _check_day(from_day)
    pairs, errors = [], []
    for r in rows or []:
        loom = (r.get("loom") or "").strip().upper()
        if not loom:
            continue
        try:
            pairs.append((loom, _clean(r.get("values") or {})))
        except ValueError as e:
            errors.append("%s — %s" % (loom, e))
    if errors:
        more = " и ещё %d" % (len(errors) - 10) if len(errors) > 10 else ""
        raise ValueError("ничего не сохранено: " + "; ".join(errors[:10]) + more)
    if not pairs:
        raise ValueError("изменений нет")
    days = _write(pairs, from_day, who)
    return {"looms": [p[0] for p in pairs], "from_day": from_day, "days": days}


def _loom_key(loom):
    m = re.match(r"^([A-Za-z]+)(\d+)$", loom or "")
    return (m.group(1), int(m.group(2))) if m else (loom or "", 0)


def grid(day):
    """Все станки на день для таблицы заправки: что действует и что введено вручную.

    Справочные значения берутся из отчёта за этот день (или ближайший прошлый),
    пряжа — в справочном написании, чтобы таблица не пестрела «ошибками»
    из-за пробелов."""
    import reports
    days = reports.report_days()
    rd = next((d for d in days if d <= day), days[0] if days else None)
    rows = reports.report_day(rd) if rd else []
    setups = effective(day)
    out = []
    for r in sorted(rows, key=lambda x: _loom_key(x["loom"])):
        s = setups.get(r["loom"]) or {}
        ref = {"gsm": r.get("gsm"), "weight_kg": r.get("weight_kg"), "ppt": r.get("ppt"),
               "panels": r.get("panels")}
        # Пряжа и лоты — по местам, как их собрал отчёт (из техкарты 1С изделия по плану).
        try:
            for y in json.loads(r.get("yarns") or "[]"):
                ref[y["slot"] + "_yarn"], ref[y["slot"] + "_lot"] = y.get("yarn"), y.get("lot")
        except (ValueError, TypeError, KeyError):
            pass
        values, manual = {}, {}
        for f in FIELDS:
            if s.get(f) not in (None, ""):
                values[f], manual[f] = s[f], True
            else:
                v = ref.get(f)
                if f.endswith("_yarn"):
                    v = yarns.canon(v) if v not in (None, "", "0") else ""
                values[f] = v
        out.append({"loom": r["loom"], "cloth": r.get("cloth"), "design": r.get("design"),
                    "values": values,
                    "manual": manual, "from_day": s.get("from_day"), "set_by": s.get("set_by")})
    return {"day": day, "report_day": rd, "rows": out}
