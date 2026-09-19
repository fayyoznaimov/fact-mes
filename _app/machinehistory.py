"""История станков из локального журнала Toyota, без запросов к FACT.

В stop_log нет событий Run. Промежутки между остановами можно показать как
расчётную работу только в завершённой смене, когда длительности журнала
согласуются со сменным итогом. Это не подтверждает полноту исходных файлов:
расчёт всегда помечен отдельно от событий. Остальные промежутки — неизвестны.
"""
import re
import threading
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from time import monotonic

import storage
from metrics import CAUSE_RU
import tickets

TZ = timezone(timedelta(hours=5))  # Часовой пояс цеха — Ташкент, без переходов.
MAX_EVENTS = 60000
_BUILD_LOCK = threading.Lock()


def parse_day(value):
    try:
        return date.fromisoformat(value.replace(".", "-"))
    except (ValueError, AttributeError):
        raise ValueError("Дата должна быть в формате ГГГГ-ММ-ДД") from None


def stamp(day, seconds=0):
    return int(datetime.combine(day, time(), TZ).timestamp()) + seconds


def union(intervals):
    out = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if out and start <= out[-1][1]:
            out[-1][1] = max(end, out[-1][1])
        else:
            out.append([start, end])
    return out


def covered(intervals, start, end):
    return sum(max(0, min(b, end) - max(a, start)) for a, b in intervals)


def build_row(loom, records, shifts, start, end, now):
    events, invalid = [], 0
    for r in records:
        if (r["start_sec"] is None or not 0 <= r["start_sec"] < 86400
                or r["dur_sec"] is None or r["dur_sec"] <= 0):
            invalid += 1
            continue
        a = stamp(parse_day(r["day"]), r["start_sec"])
        b = a + r["dur_sec"]
        if a >= end or b <= start or a >= now:
            continue
        events.append({"start": a, "end": b, "cause": r["cause"] or "Other",
                       "reason": CAUSE_RU.get(r["cause"], r["cause"] or "Не определена"),
                       "code": r["code"], "shift": r["shift"], "style": r["style"],
                       "response_sec": r["resp_sec"], "duration_sec": r["dur_sec"]})
    events.sort(key=lambda e: (e["start"], e["end"], e["cause"]))
    stops = union((e["start"], min(e["end"], now)) for e in events)
    estimated, checks = [], []
    for r in shifts:
        hour = {"A": 7, "B": 15, "C": 23}.get(r["letter"])
        if hour is None:
            continue
        a = stamp(parse_day(r["day"]), hour * 3600)
        b = a + 28800
        if a >= end or b <= start:
            continue
        run, stop = r["run_min"], r["stop_min"]
        logged = covered(stops, a, b)
        # Две сводки Toyota округляют минуты; допуск — 60 секунд за смену.
        # Пересечения и некорректные строки не дают уверенности в хронологии.
        overlaps = sum(max(0, min(e["end"], b) - max(e["start"], a))
                       for e in events) > logged
        valid = (not invalid and not overlaps and b <= now and run is not None
                 and stop is not None and run >= 0 and stop >= 0
                 and abs((run + stop) * 60 - 28800) <= 60
                 and abs(stop * 60 - logged) <= 60)
        checks.append({"shift": r["shift"], "run_min": run, "stop_min": stop,
                       "logged_stop_sec": logged, "can_estimate": valid})
        if valid:
            estimated.append((a, b))
    estimated = union(estimated)
    # Непересекающиеся сегменты: длительность остановов не удваивается.
    boundaries = {start, end, max(start, min(now, end))}
    for a, b in stops + estimated:
        boundaries.update((max(start, min(a, end)), max(start, min(b, end))))
    points = sorted(boundaries)
    segments = []
    si = ri = 0
    totals = {"stop": 0, "estimated_run": 0, "unknown": 0, "future": 0}
    for a, b in zip(points, points[1:]):
        while si < len(stops) and stops[si][1] <= a:
            si += 1
        while ri < len(estimated) and estimated[ri][1] <= a:
            ri += 1
        kind = ("future" if a >= now else
                "stop" if si < len(stops) and stops[si][0] <= a else
                "estimated_run" if ri < len(estimated) and estimated[ri][0] <= a else "unknown")
        totals[kind] += b - a
        if segments and segments[-1]["kind"] == kind:
            segments[-1]["end"] = b
        else:
            segments.append({"start": a, "end": b, "kind": kind})
    visible = [e for e in events if e["start"] < min(end, now) and e["end"] > start]
    overlap_sec = sum(max(0, min(e["end"], end, now) - max(e["start"], start))
                      for e in visible) - totals["stop"]
    return {"loom": loom, "events": visible, "segments": segments, "totals": totals,
            "shift_checks": checks, "invalid_records": invalid, "overlap_sec": overlap_sec}


def timeline(day="", period="day", looms=""):
    if period not in ("day", "A", "B", "C"):
        raise ValueError("Период: день либо смена A, B, C")
    selected = tuple(sorted(set(x.strip() for x in looms.split(",") if x.strip())))
    if len(selected) > 80 or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", x) for x in selected):
        raise ValueError("Выберите не более 80 станков")
    chosen = parse_day(day).isoformat() if day else ""
    if chosen and not date(2000, 1, 1) <= parse_day(chosen) <= date(2100, 12, 31):
        raise ValueError("Дата вне диапазона 2000–2100")
    # Пособытийный ответ заметно больше сводных отчётов. Не занимаем до 400
    # мест общего кэша: держим лишь четыре последних запроса, до 30 секунд.
    # Один расчёт за раз защищает SQLite от одновременного открытия истории.
    with _BUILD_LOCK:
        return _cached(chosen, period, selected, storage.FACT_DB, storage.SHOP_DB, int(monotonic() // 30))


def add_observations(row, archive, start, end, now):
    """Заполнять пробелы только между согласующимися соседними снимками.

    Не протягивать состояние через разрыв связи или незамеченный перезапуск.
    Журнал остановов имеет приоритет перед минутными снимками.
    """
    observed, previous = [], None
    for at, machines in archive:
        value = machines.get(row['loom'])
        if not value or value.get('state') in ('Unknown', ''):
            previous = None
            continue
        if previous:
            pa, pv = previous
            gap = at - pa
            if (0 < gap <= 120 and at <= now and value.get('running') == pv.get('running')
                    and value.get('cause') == pv.get('cause') and (value.get('state_sec') or 0) >= gap):
                a, b = max(start, pa), min(end, at)
                if b > a:
                    observed.append(dict(start=a,end=b,kind='observed_run' if value.get('running') else 'observed_stop'))
        previous = at, value
    if not observed:
        return
    points = sorted({v for s in row['segments'] + observed for v in (s['start'],s['end'])})
    result, si, oi = [], 0, 0
    for a,b in zip(points,points[1:]):
        while si < len(row['segments']) and row['segments'][si]['end'] <= a:si += 1
        while oi < len(observed) and observed[oi]['end'] <= a:oi += 1
        if si >= len(row['segments']):break
        kind = row['segments'][si]['kind']
        if kind == 'unknown' and oi < len(observed) and observed[oi]['start'] <= a:
            kind = observed[oi]['kind']
        if result and result[-1]['kind'] == kind:
            result[-1]['end'] = b
        else:
            result.append(dict(start=a,end=b,kind=kind))
    row['segments'] = result
    row['totals'] = {k:sum(s['end']-s['start'] for s in result if s['kind']==k)
                     for k in ('stop','estimated_run','unknown','future','observed_run','observed_stop')}


@lru_cache(maxsize=4)
def _cached(day, period, selected, fact_path, shop_path, bucket):
    return _load(day, period, selected)


def _load(day, period, selected):
    now = int(datetime.now(TZ).timestamp())
    with closing(storage.fact()) as db:
        # Одна согласованная версия журнала и сменных итогов при работе сборщика.
        db.execute("BEGIN")
        meta = db.execute("SELECT MIN(day), MAX(day), MAX(dur_sec) FROM stop_log").fetchone()
        day = parse_day(day or meta[1] or datetime.now(TZ).date().isoformat())
        start = stamp(day, {"day": 0, "A": 7, "B": 15, "C": 23}[period] * 3600)
        end = start + (86400 if period == "day" else 28800)
        # Полные смены для проверки и остановы любой длины, начавшиеся раньше.
        scan_start = stamp(day - timedelta(days=1), 23 * 3600) if period == "day" else start
        scan_end = stamp(day + timedelta(days=1), 7 * 3600) if period == "day" else end
        earliest = datetime.fromtimestamp(scan_start - max(0, meta[2] or 0), TZ).date()
        last = datetime.fromtimestamp(scan_end - 1, TZ).date()
        known = {r[0] for r in db.execute("SELECT DISTINCT loom FROM shift_full")}
        known.update(r[0] for r in db.execute("SELECT DISTINCT loom FROM stop_log WHERE day BETWEEN ? AND ?",
                                             (day.strftime("%Y.%m.%d"), last.strftime("%Y.%m.%d"))))
        catalog = sorted(known, key=lambda s: (re.sub(r"\d+", "", s), int(re.search(r"\d+", s)[0])
                                             if re.search(r"\d+", s) else 0, s))
        chosen = list(selected) if selected else catalog[:80]
        if any(x not in known for x in chosen):
            raise ValueError("Неизвестный станок")
        data, shifts = defaultdict(list), defaultdict(list)
        if chosen:
            marks = ",".join("?" for _ in chosen)
            origin = "(CAST(strftime('%s',replace(day,'.','-')) AS INTEGER)-18000+start_sec)"
            rows = db.execute(f"SELECT * FROM stop_log WHERE day BETWEEN ? AND ? AND loom IN ({marks}) "
                              f"AND (start_sec IS NULL OR start_sec<0 OR start_sec>=86400 OR dur_sec IS NULL OR dur_sec<=0 OR "
                              f"({origin} < ? AND {origin}+dur_sec > ?)) LIMIT ?",
                              (earliest.strftime("%Y.%m.%d"), last.strftime("%Y.%m.%d"),
                               *chosen, scan_end, scan_start, MAX_EVENTS + 1)).fetchall()
            if len(rows) > MAX_EVENTS:
                raise ValueError("Слишком много событий: выберите отдельный ряд или станок")
            for r in rows:
                # Оставляем полные смены даже при просмотре календарного дня.
                data[r["loom"]].append(r)
            for r in db.execute(f"SELECT * FROM shift_full WHERE day BETWEEN ? AND ? AND loom IN ({marks})",
                                ((day - timedelta(days=1)).strftime("%Y.%m.%d"),
                                 day.strftime("%Y.%m.%d"), *chosen)):
                shifts[r["loom"]].append(r)
        result = []
        for loom in catalog:
            if loom not in chosen:
                continue
            row = build_row(loom, data[loom], shifts[loom], scan_start, scan_end, now)
            # Перестроить после проверки полных смен; сохранить их выводы для
            # обрезанного начала/конца календарного дня.
            row["segments"] = [dict(s, start=max(start, s["start"]), end=min(end, s["end"]))
                               for s in row["segments"] if s["start"] < end and s["end"] > start]
            row["events"] = [e for e in row["events"] if e["start"] < end and e["end"] > start]
            row["totals"] = {k: sum(s["end"] - s["start"] for s in row["segments"] if s["kind"] == k)
                             for k in row["totals"]}
            row["overlap_sec"] = sum(max(0, min(e["end"], end, now) - max(e["start"], start))
                                     for e in row["events"]) - row["totals"]["stop"]
            row["tickets"] = []
            result.append(row)
    import productionlog
    archive = productionlog.sample_archive(start, min(end, now))
    for row in result:
        add_observations(row, archive, start, end, now)
    # Тикеты — отдельный источник. Их интервалы не заменяют сигналы Toyota.
    with closing(storage.shop_readonly()) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='ticket'").fetchone() and chosen:
            marks = ",".join("?" for _ in chosen)
            # Широкие границы по дате используют индекс; точная проверка ниже
            # учитывает также старые отметки без UTC-смещения (время цеха).
            ts = db.execute(f"SELECT id,loom,started_at,ended_at,category_id,comment,fact_cause FROM ticket "
                            f"WHERE loom IN ({marks}) AND started_at<? "
                            "AND (ended_at IS NULL OR ended_at>?) LIMIT ?",
                            (*chosen, (datetime.fromtimestamp(end, TZ).date() + timedelta(days=1)).isoformat(),
                             (day - timedelta(days=1)).isoformat(), MAX_EVENTS + 1)).fetchall()
            if len(ts) > MAX_EVENTS:
                raise ValueError("Слишком много тикетов: выберите отдельный станок")
            by_loom = {r["loom"]: r for r in result}
            for t in ts:
                def epoch(value):
                    dt = datetime.fromisoformat(value)
                    return int((dt if dt.tzinfo else dt.replace(tzinfo=TZ)).timestamp())
                try:
                    a, b = epoch(t["started_at"]), epoch(t["ended_at"]) if t["ended_at"] else now
                except (ValueError, TypeError):
                    continue
                if b <= start or a >= min(end, now) or b <= a:
                    continue
                cat = tickets.category(t["category_id"]) or {}
                by_loom[t["loom"]]["tickets"].append({"id": t["id"], "start": a, "end": b,
                    "open": not t["ended_at"], "reason": cat.get("reason", "Причина не указана"),
                    "comment": t["comment"] or "", "cause": t["fact_cause"]})
    return {"day": day.isoformat(), "period": period, "start": start, "end": end,
            "timezone": "+05:00", "generated_at": now, "catalog": catalog,
            "available_from": meta[0], "available_to": meta[1], "rows": result}
