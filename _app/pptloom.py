"""PPT по станку: прокидки на ряд из счётчиков FACT.

Точного PPT (прокидок в рисунке, «676 / 3484 УТОК» на экране станка) FACT не
отдаёт: рисунок живёт только в памяти станка. Зато в файле состояния станка
каждую минуту есть счётчики текущей ткани — Cloth_length_pick (прокидки) и
Cloth_length_piece (готовые ряды). Ряд прибавляется ровно на границе рисунка,
поэтому между двумя моментами прироста ряда прошло целое число рисунков:

    ряд N закончился на прокидке P_N, a_N <= P_N <= b_N
    (a — показание до прироста, b — после; разница — прокидки за минуту),
    PPT = (P_k - P_i) / (k - i)  =>  (a_k - b_i)/(k-i) <= PPT <= (b_k - a_i)/(k-i).

Пересечение по всем парам сужается до одной-двух прокидок: на D1 вышло 3485
при 3484 на экране (станок нумерует положение с нуля). Снимки — machine_sample
(productionlog.archive_sample), расчёт за день кэшируется в loom_ppt.

Станки J считают «штукой» отрез рулона (Cut_length_pic ≈ 135 000 прокидок), а не
ряд: счётчик растёт раз в сутки, PPT из него не выходит — такие станки
отсекаются по MAX_PPT и числу переходов.
"""
import json
import time
import zlib
from datetime import datetime, timedelta

import productionlog
import storage

MIN_ROWS = 8            # меньше переходов — интервал слишком широк
MAX_PPT = 20000         # больше — станок считает штукой отрез рулона, а не ряд
MAX_WIDTH = 0.01        # интервал шире 1 % (±0,5 %) — не доверяем
CACHE_SEC = 1800        # идущий день пересчитываем не чаще раза в полчаса
FALLBACK_DAYS = 14      # нет расчёта за день — берём прошлый по той же ткани

SCHEMA = """
CREATE TABLE IF NOT EXISTS loom_ppt (
    day TEXT NOT NULL, loom TEXT NOT NULL, cloth TEXT,
    ppt INTEGER, lo REAL, hi REAL, rows INTEGER, built_at INTEGER,
    PRIMARY KEY (day, loom)
);
"""


def _window(day):
    """Отчётный день: смены A, B, C — с 07:00 дня до 07:00 следующего."""
    start = datetime.strptime(day, "%Y.%m.%d").replace(hour=7, tzinfo=productionlog.TZ)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def _series(start, end):
    """{станок: [(время, прокидки, ряды, ткань)]} из сохранённых снимков FACT."""
    db = storage.shop_readonly()
    out = {}
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='machine_sample'").fetchone():
            return out
        for row in db.execute("SELECT at, data FROM machine_sample WHERE at BETWEEN ? AND ? ORDER BY at",
                              (start, end)):
            for loom, v in json.loads(zlib.decompress(row["data"])).items():
                g = (v.get("details") or {}).get("signals") or {}
                try:
                    out.setdefault(loom, []).append((row["at"], int(g["Cloth_length_pick"]),
                                                     int(g["Cloth_length_piece"]), g.get("Cloth_name") or ""))
                except (KeyError, TypeError, ValueError):
                    continue
    finally:
        db.close()
    return out


def segments(rows):
    """Куски одной ткани без сброса счётчиков (съём ткани обнуляет их)."""
    seg, cur = [], []
    for r in rows:
        if cur and (r[3] != cur[-1][3] or r[1] < cur[-1][1] or r[2] < cur[-1][2]):
            seg.append(cur)
            cur = []
        cur.append(r)
    if cur:
        seg.append(cur)
    return seg


def estimate(seg):
    """(нижняя, верхняя граница PPT, переходов) по одному куску или None."""
    ev = [(b[2], a[1], b[1]) for a, b in zip(seg, seg[1:]) if b[2] == a[2] + 1]
    if len(ev) < MIN_ROWS:
        return None
    lo, hi = 0.0, float("inf")
    for i, (ni, ai, bi) in enumerate(ev):
        for nk, ak, bk in ev[i + 1:]:
            n = nk - ni
            lo = max(lo, (ak - bi) / n)
            hi = min(hi, (bk - ai) / n)
    return lo, hi, len(ev)


def compute(day):
    """{станок: {ppt, lo, hi, rows, cloth}} за отчётный день — только уверенные."""
    out = {}
    for loom, rows in _series(*_window(day)).items():
        best = None
        for seg in segments(rows):
            e = estimate(seg)
            if not e:
                continue
            lo, hi, n = e
            mid = (lo + hi) / 2
            # Противоречие (lo > hi) — счётчики сбились; широкий интервал — мало данных.
            if lo > hi or not 0 < mid <= MAX_PPT or hi - lo > max(4.0, mid * MAX_WIDTH):
                continue
            if best is None or n > best["rows"]:
                best = {"ppt": int(round(mid)), "lo": round(lo, 1), "hi": round(hi, 1),
                        "rows": n, "cloth": seg[0][3]}
        if best:
            out[loom] = best
    return out


def for_day(day, cloths=None):
    """PPT по станку на отчётный день; cloths — {станок: код ткани} из отчёта.

    Нет своего расчёта за день — берётся последний за FALLBACK_DAYS по той же ткани."""
    db = storage.shop()
    try:
        db.executescript(SCHEMA)
        built = db.execute("SELECT MIN(built_at) FROM loom_ppt WHERE day=?", (day,)).fetchone()[0]
        end = _window(day)[1]
        # Прошедший день считаем один раз (после его конца); идущий — раз в полчаса.
        stale = built is None or (built < end + 600 and time.time() - built > CACHE_SEC)
        if stale:
            fresh = compute(day)
            now = int(time.time())
            db.execute("DELETE FROM loom_ppt WHERE day=?", (day,))
            db.executemany("INSERT INTO loom_ppt VALUES (?,?,?,?,?,?,?,?)",
                           [(day, loom, e["cloth"], e["ppt"], e["lo"], e["hi"], e["rows"], now)
                            for loom, e in fresh.items()]
                           or [(day, "", None, None, None, None, 0, now)])   # отметка «посчитано»
            db.commit()
        out = {r["loom"]: dict(r) for r in db.execute(
            "SELECT * FROM loom_ppt WHERE day=? AND loom<>''", (day,))}
        since = (datetime.strptime(day, "%Y.%m.%d") - timedelta(days=FALLBACK_DAYS)).strftime("%Y.%m.%d")
        for loom, cloth in (cloths or {}).items():
            if loom in out or not cloth:
                continue
            r = db.execute("SELECT * FROM loom_ppt WHERE loom=? AND cloth=? AND day<? AND day>=?"
                           " ORDER BY day DESC LIMIT 1", (loom, cloth, day, since)).fetchone()
            if r:
                out[loom] = dict(r)
        return out
    finally:
        db.close()
