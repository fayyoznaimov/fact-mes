"""Тикеты простоев и андон: почему станок стоит и кто этим занят.

Станок сам называет причину, только когда её видит датчик — уток, основа, ворс,
ложная кромка. Всё остальное FACT сваливает в «ручной останов» и «прочее»: это
больше половины потерянного времени цеха. В FACT нет ввода причины длинного
останова — в пакистанской LDS для этого у мастеров RFID-карты, у нас тикет:
человек вызывает электрика или ТОиР, и время простоя уходит в эту причину.

Правило разбора (как договорились в цехе):

    станок стоит и сам назвал причину  -> причина от станка, тикет её не перебивает;
    станок обесточен (Power_off)       -> причину даёт тикет: ТОиР, наладка, электрика;
    станок стоит молча (ручной, прочее)-> причину даёт тикет;
    тикета нет                         -> так и пишем: причина не указана.

Андон — стоящий станок без причины не должен теряться на доске:

    меньше 2 минут      ожидание: оператор, скорее всего, уже у станка;
    от 2 минут          «нет тикета» — плитка фиолетовая, наверх доски;
    от 10 минут         тревога — плитка мигает красным;
    от 15 минут         мастеру в телеграм, один раз на останов.

Пороги — в настройках цеха. Обрыв, который станок назвал сам, в андон не
попадает, пока не затянется дольше 15 минут: тогда это уже не обрыв, а проблема.

Живое состояние читается из снимка, который пишет сборщик (collector.py).
Если сборщика нет — читаем FACT или зеркало сами, как раньше.
"""
import threading
import time
from datetime import datetime, timedelta

import hub
import livestate
import storage
from livestate import CAUSE_FLAGS, loom_file  # noqa: F401 — для старых вызовов
from storage import shop

# Откуда брать живое состояние: mirror — папка зеркала, fact — сервер по сети.
SOURCE = {"mode": "mirror", "url": "http://172.0.30.9"}

STALE_SEC = 180         # снимок старше — данные на доске уже не живые
TICKET_MIN_SEC = 120    # тикет заводим, если останов длится дольше этого
LONG_STOP_SEC = 900     # длинный останов заводит тикет даже с причиной от станка

# Сигналы, которые станок выставляет сам. Если такой сигнал есть — он и есть
# причина простоя (коды FACT: 0004–0019 уток, 2414 основа, 2415 ворс, 0001 кромка).
TECH_SIGNALS = {"Weft", "Warp", "Warp_top", "False_selvage", "Leno_L", "Leno_R"}

CAUSE_RU = {
    "Run": "Работает", "Stop": "Стоит", "Unknown": "Не определена",
    "Machine_failure": "Отказ станка", "Power_off": "Обесточен",
    "Warp_out": "Конец навоя", "Cloth_doffing": "Съём ткани", "Cloth_mending": "Починка ткани",
    "Out_of_product": "Нет продукции", "Manual": "Ручной останов", "Warp_top": "Ворс (верхний навой)",
    "Warp": "Основа", "False_selvage": "Ложная кромка", "Leno_L": "Перевивка (лев)",
    "Leno_R": "Перевивка (прав)", "Weft": "Уток",
}

# Английские названия — для доски, где смотрят и наладчики Toyota, и цех.
CAUSE_EN = {
    "Run": "Running", "Stop": "Stopped", "Unknown": "Undefined",
    "Machine_failure": "Machine failure", "Power_off": "Power off",
    "Warp_out": "Warp out", "Cloth_doffing": "Cloth doffing", "Cloth_mending": "Cloth mending",
    "Out_of_product": "Out of product", "Manual": "Manual stop", "Warp_top": "Pile warp",
    "Warp": "Ground warp", "False_selvage": "False selvage", "Leno_L": "Leno left",
    "Leno_R": "Leno right", "Weft": "Weft",
}

# Категории тикетов.
#   reason  — как причина называется в отчёте;
#   applies — при каком состоянии станка тикет становится причиной простоя:
#             off — обесточен, stop — стоит без сигнала, any — в обоих случаях;
#   call    — это вызов человека (электрик, механик), а не вид работы.
CATEGORIES = [
    {"id": "electrical",    "name": "Вызов электрика",    "en": "Electrician",
     "reason": "Электрическая проблема", "applies": "any",  "call": True},
    {"id": "toir",          "name": "ТОиР",               "en": "Maintenance",
     "reason": "ТОиР", "applies": "any",  "call": True},
    {"id": "naladka",       "name": "Наладка",            "en": "Setup",
     "reason": "Наладка", "applies": "any",  "call": True},
    {"id": "pol_master",    "name": "Pol Master",         "en": "Pol Master",
     "reason": "Pol Master", "applies": "any",  "call": True},
    {"id": "designer",      "name": "Designer",           "en": "Designer",
     "reason": "Designer", "applies": "any",  "call": True},
    {"id": "beam_short",    "name": "Beam Short",         "en": "Beam Short",
     "reason": "Beam Short", "applies": "any",  "call": False},
    {"id": "zapravka",      "name": "Zapravka (Article)", "en": "Zapravka (Article)",
     "reason": "Zapravka (Article)", "applies": "any",  "call": False},
    {"id": "abr_p_vors",    "name": "ABR P (vors)",       "en": "ABR P (pile)",
     "reason": "ABR P (vors)", "applies": "stop", "call": False},
    {"id": "abr_p_karinoy", "name": "ABR P (Karinoy)",    "en": "ABR P (ground)",
     "reason": "ABR P (Karinoy)", "applies": "stop", "call": False},
]
CATEGORY_BY_ID = {c["id"]: c for c in CATEGORIES}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticket (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loom TEXT NOT NULL,
    started_at TEXT NOT NULL,        -- начало останова
    ended_at TEXT,                   -- NULL = станок ещё стоит
    duration_sec INTEGER NOT NULL DEFAULT 0,
    fact_cause TEXT,                 -- что сказал станок (Manual, Power_off, Weft, ...)
    style TEXT,
    shift TEXT,
    category_id TEXT,                -- что выбрал человек
    comment TEXT,
    opened_by TEXT,                  -- кто завёл: 'авто' или логин
    classified_by TEXT,
    classified_at TEXT,
    escalated_at TEXT,               -- когда ушло мастеру: стоит без причины
    UNIQUE (loom, started_at)
);
CREATE INDEX IF NOT EXISTS idx_ticket_open ON ticket(ended_at);
CREATE INDEX IF NOT EXISTS idx_ticket_started ON ticket(started_at);
CREATE INDEX IF NOT EXISTS idx_ticket_loom ON ticket(loom, started_at);
"""

_migrated = False


def db():
    """Та же цеховая база, что и у остального приложения, плюс таблица тикетов."""
    global _migrated
    conn = shop()
    conn.executescript(SCHEMA)
    if not _migrated:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(ticket)")]
        if "escalated_at" not in cols:
            conn.execute("ALTER TABLE ticket ADD COLUMN escalated_at TEXT")
            conn.commit()
        _migrated = True
    return conn


# --- разбор причины ----------------------------------------------------------

def machine_state(cause):
    """off — обесточен, tech — станок назвал причину, stop — стоит молча."""
    if cause == "Power_off":
        return "off"
    if cause in TECH_SIGNALS:
        return "tech"
    return "stop"


def resolve_reason(cause, category_id=None):
    """Итоговая причина простоя и откуда она взялась."""
    state = machine_state(cause)
    if state == "tech":
        return CAUSE_RU.get(cause, cause), "сигнал станка"
    cat = CATEGORY_BY_ID.get(category_id or "")
    if cat and cat["applies"] in ("any", state):
        return cat["reason"], "тикет"
    if state == "off":
        return "Обесточен, причина не указана", "нет данных"
    return CAUSE_RU.get(cause, cause) or "Не определено", "нет данных"


# --- живое состояние ---------------------------------------------------------

_direct = {"at": 0, "snap": None}
_direct_lock = threading.Lock()


def snapshot_now(max_age=20):
    """Снимок станков: от сборщика, а если его нет — читаем источник сами.

    Устаревший снимок сборщика отдаём как есть, а не лезем в FACT из каждого
    запроса: доска пометит его «данные не живые», и это честнее, чем двадцать
    мониторов, повисших на таймауте к серверу, который не отвечает.
    """
    snap = livestate.load()
    if snap and snap.get("source") == SOURCE["mode"]:
        return snap
    with _direct_lock:
        if _direct["snap"] and time.time() - _direct["at"] < max_age:
            return _direct["snap"]
        s = livestate.snapshot(livestate.source_from(SOURCE["mode"], SOURCE["url"]))
        _direct.update(at=time.time(), snap=s)
        return s


def state_now(max_age=20):
    """(папка снимка, {станок: состояние}) — секунды простоя досчитаны до «сейчас»."""
    snap = snapshot_now(max_age)
    lag = livestate.lag_sec(snap)
    looms = snap["looms"]
    if lag:
        looms = {k: {**st, "state_sec": st["state_sec"] + lag} for k, st in looms.items()}
    return snap["dir"], looms


def current_shift(now=None):
    """Смены по настройке станков: A 07:00, B 15:00, C 23:00."""
    now = now or datetime.now().astimezone()
    h = now.hour
    if 7 <= h < 15:
        letter, day = "A", now
    elif 15 <= h < 23:
        letter, day = "B", now
    else:
        letter = "C"
        day = now if h >= 23 else now - timedelta(days=1)
    return "%s.%s" % (day.strftime("%Y.%m.%d"), letter)


# --- андон -------------------------------------------------------------------

def andon_settings():
    s = storage.all_settings()

    def g(k):
        try:
            return max(0, int(float(s.get(k) or storage.DEFAULTS[k])))
        except ValueError:
            return int(storage.DEFAULTS[k])
    return {"warn_min": g("andon_warn_min"), "alarm_min": g("andon_alarm_min"),
            "notify_min": g("andon_notify_min")}


def andon_level(st, ticket, cause, an):
    """run, ticket (причина указана), tech (обрыв, станок сам знает),
    wait (только что встал), noticket (стоит без причины), alarm (давно)."""
    if st["running"]:
        return "run"
    if ticket and ticket["category_id"]:
        return "ticket"
    sec = st["state_sec"]
    if machine_state(cause) == "tech" and sec < LONG_STOP_SEC:
        return "tech"
    if sec >= an["alarm_min"] * 60:
        return "alarm"
    if sec >= an["warn_min"] * 60:
        return "noticket"
    return "wait"


def andon_candidates():
    """Станки, которые стоят без причины дольше порога и о которых мастеру
    ещё не писали. Только чтение: отметка ставится после того, как сообщение
    действительно ушло (mark_escalated) — иначе доска писала бы «мастеру
    сообщено», когда телеграм не настроен или не ответил."""
    an = andon_settings()
    limit = an["notify_min"] * 60
    if not limit:
        return []
    _, live = state_now(max_age=0)
    conn = db()
    open_t = {r["loom"]: r for r in conn.execute("SELECT * FROM ticket WHERE ended_at IS NULL")}
    conn.close()
    out = []
    for loom, st in live.items():
        t = open_t.get(loom)
        if st["running"] or not t or t["category_id"] or t["escalated_at"]:
            continue
        cause = st.get("cause", st["state"])
        sec = st["state_sec"]
        if sec < limit or (machine_state(cause) == "tech" and sec < max(limit, LONG_STOP_SEC)):
            continue
        out.append({"loom": loom, "sec": sec, "cause": cause,
                    "cause_ru": CAUSE_RU.get(cause, cause), "style": st.get("style"),
                    "ticket_id": t["id"], "shift": current_shift()})
    return out


def mark_escalated(ticket_ids):
    """Отметить, что мастеру написали: один останов — одно сообщение, даже если
    сборщик перезапустился."""
    if not ticket_ids:
        return
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    conn = db()
    conn.executemany("UPDATE ticket SET escalated_at=? WHERE id=?", [(now, i) for i in ticket_ids])
    conn.commit()
    conn.close()
    invalidate()


# --- доска для монитора ------------------------------------------------------

_board_cache = {"at": 0, "data": None}
_board_lock = threading.Lock()


def invalidate():
    """Что-то поменялось: доску пересобрать, мониторы толкнуть."""
    _board_cache["data"] = None
    hub.HUB.bump()


def board(max_age=5):
    """Что показывать на мониторе: каждый станок, его состояние и причина.

    Двадцать мониторов спрашивают одно и то же — держим готовый ответ несколько
    секунд. Пересобирает его только один поток: остальные в это время получают
    прежний ответ, а не встают в очередь.
    """
    fresh = _board_cache["data"] and time.time() - _board_cache["at"] < max_age
    if fresh:
        return _board_cache["data"]
    if not _board_lock.acquire(blocking=_board_cache["data"] is None):
        return _board_cache["data"]
    try:
        if _board_cache["data"] and time.time() - _board_cache["at"] < max_age:
            return _board_cache["data"]
        return _board_build()
    finally:
        _board_lock.release()


def _board_build():
    snap = None
    try:
        snap = snapshot_now()
        state_dir, live = state_now()
        error = None
    except Exception as e:
        state_dir, live, error = None, {}, "%s: %s" % (type(e).__name__, e)

    an = andon_settings()
    conn = db()
    open_t = {r["loom"]: dict(r) for r in
              conn.execute("SELECT * FROM ticket WHERE ended_at IS NULL")}
    conn.close()

    rows = []
    for name, st in live.items():
        t = open_t.get(name)
        cause = st.get("cause", st["state"])
        reason, src = resolve_reason(cause, t["category_id"] if t else None)
        level = andon_level(st, t, cause, an)
        rows.append({
            "loom": name, "style": st["style"], "running": st["running"],
            "state": st["state"], "state_sec": st["state_sec"], "rpm": st["rpm"],
            "effic_shift": st["effic_shift"], "stops_shift": st["stops_shift"],
            "col": st.get("col"), "row": st.get("row"),
            "cause": cause, "cause_ru": CAUSE_RU.get(cause, cause),
            "machine": machine_state(cause) if not st["running"] else "run",
            "reason": None if st["running"] else reason,
            "reason_from": None if st["running"] else src,
            "ticket_id": t["id"] if t else None,
            "ticket_category": t["category_id"] if t else None,
            "andon": level,
            "needs_ticket": level in ("noticket", "alarm"),
            "escalated": bool(t and t.get("escalated_at")),
        })
    # Наверху доски — то, что дольше всех стоит без объяснения.
    rank = {"alarm": 0, "noticket": 1, "wait": 2, "ticket": 3, "tech": 4, "run": 5}
    rows.sort(key=lambda r: (rank[r["andon"]], -r["state_sec"]))

    age = int(time.time() - snap["read_at"]) if snap else None
    stopped = [r for r in rows if not r["running"]]
    payload = {
        "looms": rows, "categories": CATEGORIES, "shift": current_shift(),
        "source": SOURCE["mode"], "state_dir": state_dir, "error": error,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "andon": an,
        "snapshot_age_sec": age,
        "stale": bool(snap and SOURCE["mode"] == "fact" and age is not None and age > STALE_SEC),
        "totals": {
            "looms": len(rows),
            "running": len(rows) - len(stopped),
            "stopped": len(stopped),
            "off": sum(1 for r in stopped if r["machine"] == "off"),
            "no_reason": sum(1 for r in stopped if r["reason_from"] == "нет данных"),
            "no_ticket": sum(1 for r in rows if r["needs_ticket"]),
            "alarm": sum(1 for r in rows if r["andon"] == "alarm"),
            "open_tickets": len(open_t),
        },
    }
    _board_cache.update(at=time.time(), data=payload)
    return payload


# --- тикеты ------------------------------------------------------------------

def open_ticket(loom, who="вручную", category_id=None, comment=""):
    """Завести тикет на станок прямо с монитора."""
    _, live = state_now()
    st = live.get(loom)
    if not st:
        raise ValueError("станок «%s» не найден" % loom)
    if category_id and category_id not in CATEGORY_BY_ID:
        raise ValueError("неизвестная категория")
    now = datetime.now().astimezone()
    started = now - timedelta(seconds=st["state_sec"] if not st["running"] else 0)
    conn = db()
    # Тикет на этот останов мог уже завести сборщик — тогда пишем в него.
    row = conn.execute("SELECT id FROM ticket WHERE loom=? AND ended_at IS NULL"
                       " ORDER BY started_at DESC LIMIT 1", (loom,)).fetchone()
    if row and not st["running"]:
        tid = row["id"]
    else:
        cur = conn.execute(
            "INSERT OR IGNORE INTO ticket (loom, started_at, duration_sec, fact_cause, style,"
            " shift, category_id, comment, opened_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (loom, started.isoformat(timespec="seconds"), st["state_sec"],
             st.get("cause", st["state"]), st["style"], current_shift(now),
             category_id, (comment or "").strip()[:500], who))
        if cur.rowcount == 0:
            row = conn.execute("SELECT id FROM ticket WHERE loom=? AND started_at=?",
                               (loom, started.isoformat(timespec="seconds"))).fetchone()
            tid = row["id"] if row else None
        else:
            tid = cur.lastrowid
    if category_id:
        conn.execute("UPDATE ticket SET category_id=?, classified_by=?, classified_at=?,"
                     " comment=COALESCE(NULLIF(?, ''), comment) WHERE id=?",
                     (category_id, who, now.isoformat(timespec="seconds"),
                      (comment or "").strip()[:500], tid))
    conn.commit()
    conn.close()
    invalidate()        # на мониторе причина должна появиться сразу
    return tid


def classify(ticket_id, category_id, who, comment=""):
    if category_id not in CATEGORY_BY_ID:
        raise ValueError("неизвестная категория")
    conn = db()
    conn.execute(
        "UPDATE ticket SET category_id=?, comment=?, classified_by=?, classified_at=? WHERE id=?",
        (category_id, (comment or "").strip()[:500], (who or "")[:60],
         datetime.now().astimezone().isoformat(timespec="seconds"), ticket_id))
    conn.commit()
    conn.close()
    invalidate()


def close_ticket(ticket_id, who=""):
    conn = db()
    row = conn.execute("SELECT * FROM ticket WHERE id=?", (ticket_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("тикет не найден")
    now = datetime.now().astimezone()
    sec = int((now - datetime.fromisoformat(row["started_at"])).total_seconds())
    conn.execute("UPDATE ticket SET ended_at=?, duration_sec=? WHERE id=?",
                 (now.isoformat(timespec="seconds"), max(sec, row["duration_sec"]), ticket_id))
    conn.commit()
    conn.close()
    invalidate()


def _row(r):
    d = dict(r)
    reason, src = resolve_reason(d.get("fact_cause") or "Unknown", d.get("category_id"))
    d["reason"] = reason
    d["reason_from"] = src
    d["cause_ru"] = CAUSE_RU.get(d.get("fact_cause") or "", d.get("fact_cause"))
    d["category_name"] = (CATEGORY_BY_ID.get(d.get("category_id") or "") or {}).get("name")
    d["open"] = d["ended_at"] is None
    return d


def ticket_list(limit=80, only_open=False, day=None, date_from=None, date_to=None):
    conn = db()
    sql = "SELECT * FROM ticket"
    args, where = [], []
    if only_open:
        where.append("ended_at IS NULL")
    if day:
        where.append("substr(started_at,1,10)=?")
        args.append(day.replace(".", "-"))
    if date_from:
        where.append("substr(started_at,1,10)>=?")
        args.append(date_from.replace(".", "-"))
    if date_to:
        where.append("substr(started_at,1,10)<=?")
        args.append(date_to.replace(".", "-"))
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY (ended_at IS NULL) DESC, started_at DESC LIMIT ?"
    args.append(limit)
    rows = [_row(r) for r in conn.execute(sql, args)]
    conn.close()
    return rows


def summary(hours=24):
    """Потери по причинам за последние сутки — как их видит цех, а не FACT."""
    since = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
    conn = db()
    rows = conn.execute("SELECT * FROM ticket WHERE started_at >= ?", (since,)).fetchall()
    conn.close()
    by = {}
    for r in rows:
        reason, src = resolve_reason(r["fact_cause"] or "Unknown", r["category_id"])
        b = by.setdefault(reason, {"reason": reason, "from": src, "count": 0, "minutes": 0})
        b["count"] += 1
        b["minutes"] += round((r["duration_sec"] or 0) / 60)
    return sorted(by.values(), key=lambda x: -x["minutes"])


# --- автоматическое ведение тикетов -----------------------------------------

def poll_once():
    """Останов дольше двух минут заводит тикет, поехавший станок — закрывает.

    Вызывается сборщиком на каждый новый снимок FACT (раз в минуту).
    """
    _, live = state_now(max_age=0)
    now = datetime.now().astimezone()
    conn = db()
    open_rows = {r["loom"]: r for r in
                 conn.execute("SELECT * FROM ticket WHERE ended_at IS NULL")}
    changed = False
    for loom, st in live.items():
        t = open_rows.get(loom)
        if st["running"]:
            if t:
                sec = int((now - datetime.fromisoformat(t["started_at"])).total_seconds())
                conn.execute("UPDATE ticket SET ended_at=?, duration_sec=? WHERE id=?",
                             (now.isoformat(timespec="seconds"), max(sec, t["duration_sec"]),
                              t["id"]))
                changed = True
            continue
        sec = st["state_sec"]
        cause = st.get("cause", st["state"])
        if t:
            conn.execute("UPDATE ticket SET duration_sec=?, fact_cause=? WHERE id=?",
                         (sec, cause, t["id"]))
            continue
        # Причину, которую станок назвал сам, разбирать не надо — только если
        # останов затянулся: тогда это уже не обрыв, а проблема.
        tech = machine_state(cause) == "tech"
        if sec < TICKET_MIN_SEC or (tech and sec < LONG_STOP_SEC):
            continue
        started = now - timedelta(seconds=sec)
        conn.execute(
            "INSERT OR IGNORE INTO ticket (loom, started_at, duration_sec, fact_cause,"
            " style, shift, opened_by) VALUES (?,?,?,?,?,?,'авто')",
            (loom, started.isoformat(timespec="seconds"), sec, cause, st["style"],
             current_shift(now)))
        changed = True
    conn.commit()
    conn.close()
    if changed:
        invalidate()
