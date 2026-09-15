"""Разбор файлов FACT и запись в базу станков.

Один и тот же код работает в двух местах:

    _tools/rebuild_db.py, rebuild_stops.py   пересобрать базу целиком из зеркала;
    collector.py                             дописывать свежие смены и остановы
                                             каждые пару минут, пока цех работает.

Раньше разбор жил только в скриптах пересборки, и база обновлялась вручную раз
в сутки. Теперь сборщик вызывает те же функции по мере появления данных.

Плюс свёртка `stop_day`: остановы, сложенные по дню, станку, смене и причине,
с гистограммой времени реакции оператора. «Узкие места» за 30 дней читали
217 тысяч строк и считали медианы в Python — 2,4 секунды на 40 станках и
28 секунд за всю историю. Свёртка в сотню раз меньше, а медиана по гистограмме
считается без перебора строк.
"""
import re

# --- смены: factdata/shift-shift/<день>.<0|1|2>.txt ---------------------------

# Индексы категорий остановов в stop_ct / stop_tm / stop_wtm.
TOP, WARP, WEFT, MANUAL, POWER = 0, 1, 5, 8, 9
NAMED = (TOP, WARP, WEFT, MANUAL, POWER)
SHIFT_FILE = re.compile(r"^(\d{4}\.\d\d\.\d\d\.[012])\.txt$")

SHIFT_SCHEMA = """
CREATE TABLE IF NOT EXISTS shift_full (
    shift TEXT NOT NULL, loom TEXT NOT NULL, day TEXT, letter TEXT,
    style TEXT, cloth TEXT, beam TEXT, ubeam TEXT,
    rpm INTEGER, effic_pct REAL, run_min REAL, stop_min REAL,
    picks REAL, meters REAL, pieces REAL,
    weft_ct INTEGER, weft_stop_min REAL, weft_wait_min REAL, weft_fix_min REAL, weft_mttr_sec REAL,
    warp_ct INTEGER, warp_stop_min REAL, warp_wait_min REAL, warp_fix_min REAL, warp_mttr_sec REAL,
    top_ct INTEGER, top_stop_min REAL, top_wait_min REAL, top_fix_min REAL, top_mttr_sec REAL,
    manual_ct INTEGER, manual_min REAL, manual_wait_min REAL,
    power_min REAL, other_ct INTEGER, other_min REAL,
    wait_total_min REAL, stops_total INTEGER,
    stop_ct_raw TEXT, stop_tm_raw TEXT, stop_wtm_raw TEXT,
    PRIMARY KEY (shift, loom)
);
CREATE INDEX IF NOT EXISTS idx_full_day ON shift_full(day);
CREATE INDEX IF NOT EXISTS idx_full_loom ON shift_full(loom);
"""


def _fields(line):
    """'key v1 v2,key2 v' -> {'key': 'v1 v2', 'key2': 'v'}"""
    d = {}
    for field in line.split(","):
        p = field.strip().split(" ", 1)
        if len(p) == 2:
            d[p[0]] = p[1]
    return d


def _num(x):
    try:
        return float(x)
    except ValueError:
        return 0.0


def _nums(s, n=13):
    out = [_num(x) for x in (s or "").split()]
    return (out + [0.0] * n)[:n]


def shift_rows(shift, text):
    """Строки таблицы shift_full из файла одной смены.

    Время устранения обрыва = время останова − ожидание оператора; MTTR по утку,
    ворсу и основе; выработка в пиках, метрах и штуках (рядах).
    """
    day, letter = shift[:10], "ABC"[int(shift[-1])]
    rows = []
    for line in text.splitlines():
        d = _fields(line)
        if "mac_name" not in d:
            continue
        ct = [int(x) for x in _nums(d.get("stop_ct"))]
        tm = _nums(d.get("stop_tm"))
        wt = _nums(d.get("stop_wtm"))
        seisan = _nums(d.get("seisan"), 4)
        run = _num(d.get("run_tm", 0) or 0)
        stop = _num(d.get("stop_ttm", 0) or 0)
        cal = run + stop

        def grp(i):
            """количество, простой, ожидание, устранение, MTTR (сек)"""
            fix = max(0.0, tm[i] - wt[i])
            return ct[i], tm[i], wt[i], fix, (fix * 60 / ct[i] if ct[i] else 0)

        w_ct, w_tm, w_wt, w_fix, w_mttr = grp(WEFT)
        p_ct, p_tm, p_wt, p_fix, p_mttr = grp(WARP)
        t_ct, t_tm, t_wt, t_fix, t_mttr = grp(TOP)
        other_ct = sum(c for i, c in enumerate(ct) if i not in NAMED)
        other_tm = sum(t for i, t in enumerate(tm) if i not in NAMED)

        rows.append((
            shift, d["mac_name"], day, letter,
            d.get("style", ""), d.get("cloth", ""), d.get("beam", ""), d.get("ubeam", ""),
            round(1000 * seisan[0] / run) if run > 5 else 0,
            round(100 * run / cal, 1) if cal else 0, round(run, 2), round(stop, 2),
            round(seisan[0] * 1000), round(seisan[1], 1), round(seisan[3], 1),
            w_ct, round(w_tm, 2), round(w_wt, 2), round(w_fix, 2), round(w_mttr, 1),
            p_ct, round(p_tm, 2), round(p_wt, 2), round(p_fix, 2), round(p_mttr, 1),
            t_ct, round(t_tm, 2), round(t_wt, 2), round(t_fix, 2), round(t_mttr, 1),
            ct[MANUAL], round(tm[MANUAL], 2), round(wt[MANUAL], 2),
            round(tm[POWER], 2), other_ct, round(other_tm, 2),
            round(sum(wt), 2), sum(ct),
            " ".join(map(str, ct)), " ".join(map(str, tm)), " ".join(map(str, wt)),
        ))
    return rows


# Та же смена в том виде, в каком её читает производственный отчёт
# (_tools/make_excel_report.py, лист TOYOTA): простой — как в отчёте FACT,
# большее из суммы остановов и времени «без работы» (isc_tm).
SHIFT_LOOM_SCHEMA = """
CREATE TABLE IF NOT EXISTS shift_loom (
    shift TEXT NOT NULL, loom TEXT NOT NULL, style TEXT, rpm INTEGER, effic_pct REAL,
    run_min REAL, stop_min REAL, product_kpick REAL,
    warp_top_ct INTEGER, warp_top_min REAL, warp_ct INTEGER, warp_min REAL,
    weft_ct INTEGER, weft_min REAL, unselect_ct INTEGER, unselect_min REAL, total_ct INTEGER,
    stop_ct_raw TEXT, stop_tm_raw TEXT,
    PRIMARY KEY (shift, loom)
);
"""
SHIFT_LOOM_COLS = ("shift, loom, style, rpm, effic_pct, run_min, stop_min, product_kpick,"
                   " warp_top_ct, warp_top_min, warp_ct, warp_min, weft_ct, weft_min,"
                   " unselect_ct, unselect_min, total_ct, stop_ct_raw, stop_tm_raw")


def shift_loom_rows(shift, text):
    """Строки shift_loom — по формулам макроса Toyota shiftreport.xlsm."""
    rows = []
    for line in text.splitlines():
        d = _fields(line)
        if "mac_name" not in d:
            continue
        run = _num(d.get("run_tm", 0) or 0)
        isc = (d.get("isc_tm") or "").split()
        stop = max(_num(d.get("stop_ttm", 0) or 0), _num(isc[-1]) if isc else 0.0)
        prod = _nums(d.get("seisan"), 4)[0]
        ct = [int(x) for x in _nums(d.get("stop_ct"))]
        tm = _nums(d.get("stop_tm"))
        other = [i for i in range(len(ct)) if i not in (TOP, WARP, WEFT)]
        rows.append((shift, d["mac_name"], d.get("style", ""),
                     0 if run < 5 else round(1000 * prod / run),
                     0.0 if run == 0 else round(100 * run / (run + stop), 1),
                     run, round(stop, 3), prod,
                     ct[TOP], tm[TOP], ct[WARP], tm[WARP], ct[WEFT], tm[WEFT],
                     sum(ct[i] for i in other), round(sum(tm[i] for i in other), 3), sum(ct),
                     " ".join(map(str, ct)), " ".join(map(str, tm))))
    return rows


def upsert_shift(db, shift, text):
    """Смена в обе таблицы: shift_full — для приложения, shift_loom — для
    производственного отчёта. Раньше shift_loom заполнял только старый скрипт
    сбора, и отчёт за новые дни ходил за данными в FACT по сети."""
    rows = shift_rows(shift, text)
    if rows:
        db.executemany("INSERT OR REPLACE INTO shift_full VALUES (" + ",".join("?" * 41) + ")",
                       rows)
        db.executemany("INSERT OR REPLACE INTO shift_loom (" + SHIFT_LOOM_COLS + ") VALUES ("
                       + ",".join("?" * 19) + ")", shift_loom_rows(shift, text))
    return len(rows)


# --- остановы: factdata/stop_history/<день>/<номер>.txt -----------------------
#
#   00:01:21,00:01:55,0005,2026.09.11.2,21,Weft,186698,948,1037,156,34,Towel,00:01:52,0
#   начало   конец    код  смена         ?  причина пики метры ярды штуки сек артикул приход

LETTERS = {"0": "A", "1": "B", "2": "C"}

STOP_SCHEMA = """
CREATE TABLE IF NOT EXISTS stop_log (
    day TEXT NOT NULL,
    loom TEXT NOT NULL,
    shift TEXT,
    letter TEXT,
    code TEXT,
    cause TEXT,
    start_sec INTEGER,      -- секунд от начала суток
    dur_sec INTEGER,        -- сколько стоял
    resp_sec INTEGER,       -- сколько ждал оператора (NULL, если отметки нет)
    picks INTEGER,          -- счётчик пиков на момент останова
    pieces INTEGER,         -- счётчик рядов
    style TEXT,             -- артикул, который шёл на станке
    PRIMARY KEY (day, loom, start_sec, code)
);
CREATE INDEX IF NOT EXISTS idx_stop_day ON stop_log(day);
CREATE INDEX IF NOT EXISTS idx_stop_loom ON stop_log(day, loom);
CREATE INDEX IF NOT EXISTS idx_stop_cause ON stop_log(cause, day);
"""

_MAC = re.compile(r"mac_name\s+(\S+?)[,\r\n]")


def _secs(hhmmss):
    p = (hhmmss or "").split(":")
    if len(p) != 3:
        return None
    try:
        return int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2])
    except ValueError:
        return None


def stop_rows(text):
    """(станок, строки) из файла остановов одного станка за день.

    Двенадцатая колонка — артикул, а не обороты: у станков с текстовым
    артикулом («Towel») чтение её числом отбрасывало все строки.
    """
    m = _MAC.search(text)
    if not m:
        return None, []
    loom = m.group(1)
    out = []
    for line in text.splitlines():
        p = line.split(",")
        if len(p) < 13 or ":" not in p[0] or not p[0][:1].isdigit():
            continue
        start = _secs(p[0])
        try:
            dur = int(p[10])
            picks, pieces = int(p[6]), int(p[9])
        except (ValueError, IndexError):
            continue
        arrive = _secs(p[12])
        resp = None
        if arrive is not None and start is not None:
            resp = arrive - start
            # Отрицательное или огромное — отметка через полночь либо сбой.
            if resp < 0 or resp > 3600:
                resp = None
        shift = p[3]
        out.append((loom, shift, LETTERS.get(shift[-1:], ""), p[2], p[5],
                    start, dur, resp, picks, pieces, p[11].strip()))
    return loom, out


def replace_stop_day(db, day, rows):
    """Остановы дня целиком: файл станка за день дописывается весь день,
    поэтому день заменяем, а не дополняем. Свёртка пересчитывается следом."""
    db.execute("DELETE FROM stop_log WHERE day=?", (day,))
    db.executemany(
        "INSERT OR IGNORE INTO stop_log (day, loom, shift, letter, code, cause,"
        " start_sec, dur_sec, resp_sec, picks, pieces, style)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [(day,) + r for r in rows])
    rollup_day(db, day)
    return len(rows)


# --- свёртка остановов --------------------------------------------------------
#
# Границы корзин времени реакции, сек. Медиана по цеху — 7 с, 90 % — около
# минуты, поэтому внизу корзины по секунде-две, вверху — крупные.
RESP_EDGES = (0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 75, 90,
              120, 150, 180, 240, 300, 450, 600, 900, 1200, 1800, 3601)
H = tuple("h%d" % i for i in range(len(RESP_EDGES) - 1))

# Ключ — календарный день и смена FACT: ночная смена 11-го идёт до семи утра
# 12-го, и отчёт по производственным дням (как в LDS) должен отнести её
# остановы к 11-му, а «Узкие места» по календарю — к 12-му. Хранится и то, и то.
# WITHOUT ROWID: строки лежат в порядке ключа, выборка за период читается
# подряд, а не вразброс по файлу.
ROLLUP_SCHEMA = """
CREATE TABLE IF NOT EXISTS stop_day (
    day TEXT NOT NULL,          -- календарный день останова
    loom TEXT NOT NULL,
    shift TEXT NOT NULL,        -- смена FACT: 2026.09.11.2 — ночная смена 11-го
    letter TEXT NOT NULL,
    cause TEXT NOT NULL,
    n INTEGER NOT NULL, dur_sec INTEGER NOT NULL,
    resp_n INTEGER NOT NULL, resp_sum INTEGER NOT NULL,
    %s,
    PRIMARY KEY (day, loom, shift, cause)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_stop_day_shift ON stop_day(shift, loom);
""" % ", ".join("%s INTEGER NOT NULL DEFAULT 0" % h for h in H)

_HIST = ", ".join("SUM(CASE WHEN resp_sec >= %d AND resp_sec < %d THEN 1 ELSE 0 END)" % (a, b)
                  for a, b in zip(RESP_EDGES, RESP_EDGES[1:]))
_ROLLUP = ("INSERT OR REPLACE INTO stop_day (day, loom, shift, letter, cause, n, dur_sec,"
           " resp_n, resp_sum, " + ", ".join(H) + ")"
           " SELECT day, loom, COALESCE(shift, ''), COALESCE(MAX(letter), ''),"
           " COALESCE(cause, ''), COUNT(*), COALESCE(SUM(dur_sec), 0), COUNT(resp_sec),"
           " COALESCE(SUM(resp_sec), 0), " + _HIST +
           " FROM stop_log %s GROUP BY day, loom, COALESCE(shift, ''), COALESCE(cause, '')")

# Готовый кусок SELECT для сумм гистограммы — им пользуются отчёты.
HIST_SUMS = ", ".join("SUM(%s) %s" % (h, h) for h in H)


def rollup_day(db, day):
    db.execute("DELETE FROM stop_day WHERE day=?", (day,))
    db.execute(_ROLLUP % "WHERE day = ?", (day,))


def rollup_all(db):
    db.execute("DELETE FROM stop_day")
    db.execute(_ROLLUP % "")


def hist_of(row):
    """Гистограмма реакции из строки запроса с колонками h0..h13."""
    return [int(row[h] or 0) for h in H]


def hist_add(acc, hist):
    for i, c in enumerate(hist):
        acc[i] += c
    return acc


def hist_q(counts, q):
    """Квантиль по гистограмме: внутри корзины считаем значения равномерными.

    Ошибка — доли корзины: для медианы 7 с это ±2 с, для управленческого
    решения («подходят за 7 секунд, а на D9 — за 29») этого хватает.
    """
    total = sum(counts)
    if not total:
        return None
    target = q * total
    acc = 0
    for i, c in enumerate(counts):
        if c and acc + c >= target:
            lo, hi = RESP_EDGES[i], min(RESP_EDGES[i + 1], 3600)
            return int(round(lo + (target - acc) / c * (hi - lo)))
        acc += c
    return 3600


# --- схема целиком ------------------------------------------------------------

def ensure_schema(db):
    cols = [r[1] for r in db.execute("PRAGMA table_info(stop_log)")]
    if cols and "style" not in cols:
        # Старая таблица держала обороты вместо артикула — пересобирается целиком.
        db.execute("DROP TABLE stop_log")
    rcols = [r[1] for r in db.execute("PRAGMA table_info(stop_day)")]
    if rcols and ("shift" not in rcols or H[-1] not in rcols or "h%d" % len(H) in rcols):
        # Поменялся ключ или корзины гистограммы — свёртка строится заново (секунды).
        db.execute("DROP TABLE stop_day")
    db.executescript(SHIFT_SCHEMA + SHIFT_LOOM_SCHEMA + STOP_SCHEMA + ROLLUP_SCHEMA)


def ensure_rollup(db):
    """Свёртка строится один раз, если её ещё нет. Дальше её ведёт сборщик."""
    has_rollup = db.execute("SELECT 1 FROM stop_day LIMIT 1").fetchone()
    has_stops = db.execute("SELECT 1 FROM stop_log LIMIT 1").fetchone()
    if has_stops and not has_rollup:
        rollup_all(db)
        db.commit()
        return True
    return False
