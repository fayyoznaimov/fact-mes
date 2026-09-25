"""Интервалы состояний станка (loom_state) — по минутным снимкам FACT.

Каждая строка — одно непрерывное состояние: работа или останов с причиной.

  start      начало. Если FACT дал счётчик «секунд в состоянии» (list_data.txt),
             то время снимка минус счётчик — точное начало по станку
             (start_exact=1). Иначе — время первого снимка, где мы его видели
             (обесточенный станок: у FACT для него счётчика нет).
  seen_to    последний снимок, где состояние ещё было. Конец не выдумываем:
             между последним снимком этого состояния и началом следующего
             станок мог побывать в другом, не попавшем в снимки (счётчик
             показывает такие смены: 25.09 у D10 «работа 14 с», через минуту
             «работа 9 с» — между снимками был останов).

Одно состояние продолжается через пропуск снимков (FACT висел, сервер
перезапускали), только если его счётчик это подтверждает. Снимок не новее
уже записанного пропускается: после перезапуска сборщик заново читает
последний снимок FACT.
"""
import json
import threading
import zlib

import storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS loom_state (
 id INTEGER PRIMARY KEY, loom TEXT NOT NULL, running INTEGER NOT NULL, cause TEXT NOT NULL,
 style TEXT, start INTEGER NOT NULL, start_exact INTEGER NOT NULL, seen_to INTEGER NOT NULL,
 samples INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ls_loom ON loom_state(loom, seen_to);
CREATE INDEX IF NOT EXISTS ls_seen ON loom_state(seen_to);
"""
STEP_SEC = 150        # соседние снимки FACT — раз в минуту; больше — пропуск
SLACK_SEC = 2         # счётчик и время снимка округлены до секунды
NO_COUNTER = ("Power_off", "No_link")   # у FACT для них счётчика нет или он от прошлого состояния
_LOCK = threading.Lock()
_READY = threading.Event()   # архив дочитан — можно писать живые снимки


def ensure(db):
    db.executescript(SCHEMA)


def _last(db, loom):
    return db.execute("SELECT * FROM loom_state WHERE loom=? ORDER BY seen_to DESC, id DESC LIMIT 1",
                      (loom,)).fetchone()


def _apply(db, t, looms):
    """Один снимок: t — время FACT, looms — {станок: состояние} из livestate."""
    for name, st in looms.items():
        running = 1 if st.get("running") else 0
        cause = "Run" if running else (st.get("cause") or "Unknown")
        sec = st.get("state_sec") or 0
        start = t - sec if sec > 0 and cause not in NO_COUNTER else None
        last = _last(db, name)
        if last and t <= last["seen_to"]:
            continue                                   # этот снимок или старше уже учтён
        if last and last["running"] == running and last["cause"] == cause:
            step = t - last["seen_to"]
            if start is None:
                same = step <= STEP_SEC
            elif last["start_exact"]:
                # Счётчик начался после прошлого снимка — было другое состояние между ними.
                same = start <= last["seen_to"] + SLACK_SEC
            else:
                same = step <= STEP_SEC or start <= last["seen_to"] + SLACK_SEC
            if same:
                # Первый счётчик у состояния, начатого без него, уточняет начало назад.
                exact = not last["start_exact"] and start is not None and start < last["start"]
                db.execute("UPDATE loom_state SET seen_to=?, samples=samples+1, style=COALESCE(?, style)"
                           + (", start=?, start_exact=1" if exact else "") + " WHERE id=?",
                           (t, st.get("style"), *((start,) if exact else ()), last["id"]))
                continue
        exact = start is not None
        if start is None:
            start = t
        if last and start < last["seen_to"]:
            # Счётчик нового состояния уходит раньше, чем мы видели прошлое: верим снимку.
            start, exact = last["seen_to"], False
        db.execute("INSERT INTO loom_state (loom, running, cause, style, start, start_exact, seen_to)"
                   " VALUES (?,?,?,?,?,?,?)", (name, running, cause, st.get("style"), start, int(exact), t))


def record(snap):
    """Добавить снимок сборщика. Только живой FACT и только со временем FACT.
    До конца catch_up() снимки не пишем: он сам дочитает их из архива."""
    if not snap or snap.get("source") != "fact" or not snap.get("fact_time"):
        return
    with _LOCK:
        if not _READY.is_set():
            return
        db = storage.shop()
        try:
            ensure(db)
            db.execute("BEGIN IMMEDIATE")
            _apply(db, int(snap["fact_time"]), snap.get("looms") or {})
            db.commit()
        finally:
            db.close()


def catch_up(batch=200):
    """Дочитать архив минутных снимков (machine_sample) после последнего
    записанного интервала: в первый раз — весь, после перезапуска — пусто.
    Частями, блокировку между ними отпускаем. Возвращает число снимков."""
    done = 0
    while True:
        with _LOCK:
            db = storage.shop()
            try:
                ensure(db)
                after = db.execute("SELECT MAX(seen_to) FROM loom_state").fetchone()[0]
                rows = db.execute("SELECT at, data FROM machine_sample WHERE at > ? ORDER BY at LIMIT ?",
                                  (after if after is not None else -1, batch)).fetchall()
                if rows:
                    db.execute("BEGIN IMMEDIATE")
                    for r in rows:
                        _apply(db, int(r["at"]), json.loads(zlib.decompress(r["data"])))
                    db.commit()
                    done += len(rows)
                if len(rows) < batch:
                    # Последняя часть прочитана под блокировкой: снимок, записанный в
                    # архив после неё, дойдёт через record().
                    _READY.set()
                    return done
            finally:
                db.close()


def intervals(start, end, looms=None):
    """{станок: [интервал, …]} пересекающиеся с [start, end). Интервал — словарь
    с началом, концом (seen_to), причиной и признаком точного начала."""
    db = storage.shop_readonly()
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='loom_state'").fetchone():
            return {}
        sql = "SELECT * FROM loom_state WHERE seen_to > ? AND start < ?"
        args = [start, end]
        if looms:
            sql += " AND loom IN (%s)" % ",".join("?" for _ in looms)
            args += list(looms)
        out = {}
        for r in db.execute(sql + " ORDER BY loom, start", args):
            out.setdefault(r["loom"], []).append({
                "start": r["start"], "end": r["seen_to"], "running": bool(r["running"]),
                "cause": r["cause"], "style": r["style"], "exact": bool(r["start_exact"])})
        return out
    finally:
        db.close()


def current(looms=None):
    """{станок: последний интервал} — с какого времени идёт нынешнее состояние.
    Для обесточенного это единственный источник: FACT его счётчик не даёт."""
    db = storage.shop_readonly()
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='loom_state'").fetchone():
            return {}
        # SQLite: при MAX() остальные столбцы берутся из той же строки.
        rows = db.execute("SELECT loom, running, cause, start, start_exact, MAX(seen_to) AS seen_to"
                          " FROM loom_state GROUP BY loom").fetchall()
        return {r["loom"]: {"running": bool(r["running"]), "cause": r["cause"], "start": r["start"],
                            "exact": bool(r["start_exact"]), "end": r["seen_to"]}
                for r in rows if not looms or r["loom"] in looms}
    finally:
        db.close()
