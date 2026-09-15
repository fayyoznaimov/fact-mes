"""Учёт простоев: детектор остановов станков + тикеты с классификацией причин.

Берёт живое состояние из Toyota FACT (обновляется раз в минуту), заводит тикет
на каждый останов и даёт людям присвоить ему причину: механик, электрик,
замена навоя и т.д. FACT такие остановы сваливает в «UnSelect» без разбора.

Запуск:
    python server.py              # http://localhost:8770
    python server.py --port 8080 --fact http://172.0.30.9
"""
import argparse
import json
import re
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "stops.db"

# --- Настройки ---------------------------------------------------------------

FACT = "http://172.0.30.9"
POLL_SEC = 30           # как часто опрашивать FACT (сам FACT опрашивает станки раз в минуту)
TICKET_MIN_SEC = 120    # тикет заводим, если останов длится дольше этого
# Причины, которые станок определяет сам — по ним тикет не нужен, они и так разобраны.
AUTO_CAUSES = {"Warp_top", "Warp", "Weft", "False_selvage", "Leno_L", "Leno_R"}
# Длинный останов заводит тикет даже с автоматической причиной.
LONG_STOP_SEC = 900

# Категории для классификации. Порядок = порядок кнопок в интерфейсе.
CATEGORIES = [
    {"id": "mechanic",    "name": "Вызов механика",   "kind": "Механическая"},
    {"id": "electric",    "name": "Вызов электрика",  "kind": "Электрическая"},
    {"id": "beam_change", "name": "Замена навоя",     "kind": "Плановая"},
    {"id": "winding",     "name": "Намотка, заправка", "kind": "Технологическая"},
    {"id": "style_change", "name": "Смена артикула",  "kind": "Плановая"},
    {"id": "doffing",     "name": "Съём ткани",       "kind": "Плановая"},
    {"id": "no_yarn",     "name": "Нет пряжи",        "kind": "Снабжение"},
    {"id": "no_operator", "name": "Нет оператора",    "kind": "Организационная"},
    {"id": "other",       "name": "Прочее",           "kind": "Прочее"},
]

# Флаги причины в живом файле станка — в порядке проверки.
CAUSE_FLAGS = ["Machine_failure", "Power_off", "Warp_out", "Cloth_doffing", "Cloth_mending",
               "Out_of_product", "Manual", "Warp_top", "Warp", "False_selvage",
               "Leno_L", "Leno_R", "Weft"]

CAUSE_RU = {
    "Machine_failure": "Отказ станка", "Power_off": "Питание выключено",
    "Warp_out": "Конец навоя", "Cloth_doffing": "Съём ткани", "Cloth_mending": "Починка ткани",
    "Out_of_product": "Нет продукции", "Manual": "Ручной останов", "Warp_top": "Основа (верх)",
    "Warp": "Основа", "False_selvage": "Ложная кромка", "Leno_L": "Перевивка (лев)",
    "Leno_R": "Перевивка (прав)", "Weft": "Уток", "Unknown": "Не определена",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticket (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loom TEXT NOT NULL,
    started_at TEXT NOT NULL,       -- ISO, начало останова
    ended_at TEXT,                  -- NULL = станок ещё стоит
    duration_sec INTEGER NOT NULL DEFAULT 0,
    fact_cause TEXT,                -- что сказал станок (Manual, Weft, ...)
    style TEXT,
    shift TEXT,
    category_id TEXT,               -- что выбрал человек
    comment TEXT,
    classified_by TEXT,
    classified_at TEXT,
    UNIQUE (loom, started_at)
);
CREATE INDEX IF NOT EXISTS idx_open ON ticket(ended_at);
CREATE INDEX IF NOT EXISTS idx_started ON ticket(started_at);
"""


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# --- Чтение FACT -------------------------------------------------------------

def _get(path, timeout=20):
    with urllib.request.urlopen(FACT + path, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def latest_state_dir():
    """FACT пересоздаёт папку состояния каждую минуту — берём самую свежую."""
    html = _get("/factdata/opestate/")
    dirs = [int(d) for d in re.findall(r'href="(\d+)/"', html)]
    if not dirs:
        raise RuntimeError("в /factdata/opestate/ нет папок состояния")
    return str(max(dirs))


def read_layout():
    """layout.txt: колонка,ряд,?,?,ip,тип,имя,подпись — расположение станков в цехе."""
    looms = {}
    for line in _get("/factdata/opestate/%s/layout.txt" % latest_state_dir()).splitlines():
        p = line.split(",")
        if len(p) >= 7 and p[4]:
            looms[p[6]] = {"loom": p[6], "col": int(p[0]), "row": int(p[1]), "ip": p[4], "type": p[5]}
    return looms


def read_live():
    """Живое состояние всех станков: имя -> состояние, причина, секунды простоя, КПД."""
    d = latest_state_dir()
    out = {}
    for line in _get("/factdata/opestate/%s/list_data.txt" % d).splitlines():
        p = line.split(",")
        if len(p) < 10 or not p[1]:
            continue
        out[p[1]] = {
            "loom": p[1], "ip": p[0], "style": p[2] or "—",
            "state": p[3],                       # Run / Manual / Weft / Warp_top / ...
            "state_sec": int(p[4] or 0),         # сколько секунд в этом состоянии
            "effic_shift": float(p[5] or 0),
            "effic_24h": float(p[6] or 0),
            "stops_shift": int(p[7] or 0),
            "rpm": int(p[9] or 0),
            "running": p[3] == "Run",
        }
    return out


def read_loom_detail(ip):
    """Полные флаги одного станка — уточняем причину останова."""
    fn = ip.replace(".", "").rjust(12, "0")
    text = _get("/factdata/opestate/%s/loom/%s.txt" % (latest_state_dir(), fn))
    kv = dict(l.split("=", 1) for l in text.splitlines() if "=" in l)
    cause = next((f for f in CAUSE_FLAGS if kv.get(f) == "1"), "Unknown")
    return {"cause": cause, "stop_sec": int(kv.get("Stop_time", 0)), "rpm": int(kv.get("Rpm", 0))}


def current_shift(now):
    """Смены по настройке станков: A 07:00, B 15:00, C 23:00."""
    h = now.hour
    if 7 <= h < 15:
        letter, day = "A", now
    elif 15 <= h < 23:
        letter, day = "B", now
    else:
        letter = "C"
        day = now if h >= 23 else now.replace(hour=12) - __import__("datetime").timedelta(days=1)
    return "%s.%s" % (day.strftime("%Y.%m.%d"), letter)


# --- Детектор остановов ------------------------------------------------------

class Poller(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__()
        self.live = {}
        self.layout = {}
        self.error = None
        self.updated_at = None

    def run(self):
        while True:
            try:
                self.tick()
                self.error = None
            except Exception as e:
                self.error = "%s: %s" % (type(e).__name__, e)
            time.sleep(POLL_SEC)

    def tick(self):
        live = read_live()
        if not self.layout:
            self.layout = read_layout()
        now = datetime.now(timezone.utc).astimezone()
        conn = db()

        open_rows = {r["loom"]: r for r in conn.execute("SELECT * FROM ticket WHERE ended_at IS NULL")}

        for loom, st in live.items():
            ticket = open_rows.get(loom)

            if st["running"]:
                if ticket:  # станок поехал — закрываем тикет
                    conn.execute(
                        "UPDATE ticket SET ended_at=?, duration_sec=? WHERE id=?",
                        (now.isoformat(timespec="seconds"),
                         int((now - datetime.fromisoformat(ticket["started_at"])).total_seconds()),
                         ticket["id"]))
                continue

            # станок стоит
            sec = st["state_sec"]
            started = now - __import__("datetime").timedelta(seconds=sec)
            cause = st["state"]
            if cause in ("Stop", "Unknown", ""):
                cause = read_loom_detail(st["ip"])["cause"]

            worth_ticket = sec >= TICKET_MIN_SEC and (cause not in AUTO_CAUSES or sec >= LONG_STOP_SEC)
            if not worth_ticket:
                continue

            if ticket:
                conn.execute("UPDATE ticket SET duration_sec=?, fact_cause=? WHERE id=?",
                             (sec, cause, ticket["id"]))
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO ticket (loom, started_at, duration_sec, fact_cause, style, shift)"
                    " VALUES (?,?,?,?,?,?)",
                    (loom, started.isoformat(timespec="seconds"), sec, cause, st["style"],
                     current_shift(now)))

        conn.commit()
        conn.close()
        self.live = live
        self.updated_at = now.isoformat(timespec="seconds")


# --- HTTP --------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    poller = None

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            return self._send(200, (HERE / "app.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/state":
            return self._send(200, self.state_payload())
        if self.path.startswith("/api/report"):
            return self._send(200, self.report_payload())
        self._send(404, {"error": "нет такого адреса"})

    def do_POST(self):
        m = re.match(r"^/api/ticket/(\d+)/classify$", self.path)
        if not m:
            return self._send(404, {"error": "нет такого адреса"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        cat = body.get("category_id")
        if cat not in {c["id"] for c in CATEGORIES}:
            return self._send(400, {"error": "неизвестная категория"})
        conn = db()
        conn.execute(
            "UPDATE ticket SET category_id=?, comment=?, classified_by=?, classified_at=? WHERE id=?",
            (cat, (body.get("comment") or "").strip()[:500], (body.get("who") or "").strip()[:60],
             datetime.now().astimezone().isoformat(timespec="seconds"), int(m.group(1))))
        conn.commit()
        conn.close()
        self._send(200, {"ok": True})

    # --- данные для интерфейса ---

    def state_payload(self):
        p = self.poller
        conn = db()
        tickets = [dict(r) for r in conn.execute(
            "SELECT * FROM ticket WHERE ended_at IS NULL ORDER BY started_at")]
        recent = [dict(r) for r in conn.execute(
            "SELECT * FROM ticket WHERE ended_at IS NOT NULL AND category_id IS NULL"
            " ORDER BY started_at DESC LIMIT 30")]
        conn.close()
        looms = []
        for loom, st in sorted(p.live.items()):
            pos = p.layout.get(loom, {})
            looms.append({**st, "col": pos.get("col"), "row": pos.get("row"),
                          "cause_ru": CAUSE_RU.get(st["state"], st["state"])})
        return {"looms": looms, "open_tickets": tickets, "unclassified_recent": recent,
                "categories": CATEGORIES, "updated_at": p.updated_at, "error": p.error,
                "cause_ru": CAUSE_RU, "shift": current_shift(datetime.now().astimezone())}

    def report_payload(self):
        conn = db()
        since = (datetime.now().astimezone() - __import__("datetime").timedelta(days=1)).isoformat()
        rows = conn.execute(
            "SELECT COALESCE(category_id,'__none__') cat, COUNT(*) n, SUM(duration_sec) sec"
            " FROM ticket WHERE started_at >= ? GROUP BY cat ORDER BY sec DESC", (since,)).fetchall()
        by_loom = conn.execute(
            "SELECT loom, COUNT(*) n, SUM(duration_sec) sec FROM ticket WHERE started_at >= ?"
            " GROUP BY loom ORDER BY sec DESC LIMIT 12", (since,)).fetchall()
        conn.close()
        names = {c["id"]: c["name"] for c in CATEGORIES}
        names["__none__"] = "Без классификации"
        return {"by_category": [{"id": r["cat"], "name": names.get(r["cat"], r["cat"]),
                                 "count": r["n"], "minutes": round((r["sec"] or 0) / 60)} for r in rows],
                "by_loom": [{"loom": r["loom"], "count": r["n"],
                             "minutes": round((r["sec"] or 0) / 60)} for r in by_loom]}


def main():
    global FACT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--fact", default=FACT)
    args = ap.parse_args()
    FACT = args.fact.rstrip("/")

    poller = Poller()
    poller.start()
    Handler.poller = poller
    print("Учёт простоев: http://localhost:%d   (источник: %s)" % (args.port, FACT))
    print("Тикет заводится на останов дольше %d сек; авто-причины (уток, основа) — от %d сек."
          % (TICKET_MIN_SEC, LONG_STOP_SEC))
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
