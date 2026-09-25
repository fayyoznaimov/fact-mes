"""Живое состояние станков: что FACT выложил в последнем снимке.

FACT раз в минуту пересоздаёт папку `factdata/opestate/<метка>/`: список
станков с состоянием (list_data.txt), расположение в цехе (layout.txt) и файл
на каждый станок — флаги причины останова, остаток основы, прогнозы съёма ткани
и схода навоев.

Здесь — чтение этого снимка из любого источника (FACT по сети или папка
зеркала) и сохранение его в `run/live.json`. Сборщик пишет файл, веб-сервер и
мониторы его читают: состояние собирается один раз на снимок FACT, а не на
каждый запрос каждого монитора.
"""
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate, parsedate_to_datetime

import storage

OPESTATE = "factdata/opestate"

# Флаги в файле станка — в порядке проверки: сначала то, что важнее.
CAUSE_FLAGS = ["Power_off", "Machine_failure", "Warp_out", "Cloth_doffing", "Cloth_mending",
               "Out_of_product", "Manual", "Warp_top", "Warp", "False_selvage",
               "Leno_L", "Leno_R", "Weft"]

# Остаток основы и длина навоя приходят от станка в десятых долях метра:
# Beam_length_meter=50000 — это навой на 5 000 м, а не на 50 км.
BEAM_SCALE = 10.0


# --- источники ----------------------------------------------------------------

class MirrorSource:
    """Папка зеркала на диске: для работы без сети и для проверки."""
    kind = "mirror"

    def __init__(self, root=storage.ROOT):
        self.root = root

    def _path(self, rel):
        return os.path.join(self.root, *rel.strip("/").split("/"))

    def list(self, rel):
        path = self._path(rel)
        dirs, files = [], []
        for name in os.listdir(path):
            (dirs if os.path.isdir(os.path.join(path, name)) else files).append(name)
        return dirs, files

    def read(self, rel, since=None):
        """(данные, время изменения); данные None, если файл не менялся с `since`."""
        path = self._path(rel)
        m = os.path.getmtime(path)
        if since is not None and m <= since:
            return None, m
        with open(path, "rb") as f:
            return f.read(), m


class HttpSource:
    """Сервер FACT: листинги Apache и файлы. Только чтение.

    Файлы спрашиваем с If-Modified-Since: неизменившийся файл сервер не
    отдаёт заново, и опрос каждые две минуты почти не грузит сеть.
    """
    kind = "fact"
    _LINK = re.compile(r'<a href="([^"]+)"', re.I)

    def __init__(self, url, timeout=10):
        self.url = url.rstrip("/")
        self.timeout = timeout
        # Сколько мы спрашиваем у FACT — видно на /api/health, чтобы нагрузку на
        # компьютер Toyota можно было проверить в любой момент, а не на глаз.
        self._n = {"requests": 0, "not_modified": 0, "bytes": 0, "since": time.time()}
        self._nlock = threading.Lock()

    def _count(self, requests=0, not_modified=0, nbytes=0):
        with self._nlock:
            self._n["requests"] += requests
            self._n["not_modified"] += not_modified
            self._n["bytes"] += nbytes

    def usage(self):
        """Запросы к FACT с запуска: всего, сколько из них «не изменился», трафик."""
        with self._nlock:
            n = dict(self._n)
        minutes = max((time.time() - n["since"]) / 60, 1)
        return {"requests": n["requests"], "not_modified": n["not_modified"],
                "kb": round(n["bytes"] / 1024), "per_min": round(n["requests"] / minutes, 1),
                "kb_per_min": round(n["bytes"] / 1024 / minutes, 1),
                "minutes": round(minutes)}

    def _open(self, rel, since=None):
        req = urllib.request.Request(self.url + "/" + urllib.parse.quote(rel.lstrip("/")))
        if since:
            req.add_header("If-Modified-Since", formatdate(since, usegmt=True))
        self._count(requests=1)
        return urllib.request.urlopen(req, timeout=self.timeout)

    def list(self, rel):
        with self._open(rel.rstrip("/") + "/") as r:
            raw = r.read()
        self._count(nbytes=len(raw))
        body = raw.decode("utf-8", "replace")
        dirs, files = [], []
        for href in self._LINK.findall(body):
            href = html.unescape(href)
            if href.startswith(("?", "/", "#", "mailto:")) or href in ("../", "./"):
                continue
            name = urllib.parse.unquote(href)
            (dirs if name.endswith("/") else files).append(name.rstrip("/"))
        return dirs, files

    def read(self, rel, since=None):
        try:
            with self._open(rel, since) as r:
                data = r.read()
                lm = r.headers.get("Last-Modified")
            self._count(nbytes=len(data))
            try:
                m = parsedate_to_datetime(lm).timestamp() if lm else time.time()
            except (TypeError, ValueError):
                m = time.time()
            return data, m
        except urllib.error.HTTPError as e:
            if e.code == 304:
                self._count(not_modified=1)
                return None, since
            raise


def source_from(mode, url=None):
    return HttpSource(url) if mode == "fact" and url else MirrorSource()


# --- разбор файлов снимка -----------------------------------------------------

def loom_file(ip):
    """192.168.1.11 -> 192168001011: FACT дополняет до трёх цифр каждый октет,
    а не адрес целиком."""
    return "".join(part.zfill(3) for part in (ip or "").split("."))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def parse_layout(text):
    """layout.txt: колонка,ряд,?,?,ip,тип,имя — расположение станков в цехе."""
    looms = {}
    for line in text.splitlines():
        p = line.split(",")
        if len(p) >= 7 and p[4]:
            looms[p[6]] = {"col": int(_f(p[0])), "row": int(_f(p[1])), "ip": p[4], "type": p[5]}
    return looms


def parse_list(text):
    """list_data.txt: ip, станок, артикул, состояние, секунд в нём, КПД смены,
    КПД за сутки, остановов за смену, за сутки, обороты, …, минут до съёма,
    …, минут до схода навоя, навой ворса есть, …, минут до схода навоя ворса."""
    out = {}
    for line in text.splitlines():
        p = line.split(",")
        if len(p) < 10 or not p[1]:
            continue
        g = lambda i: p[i] if len(p) > i else ""
        out[p[1]] = {
            "loom": p[1], "ip": p[0], "style": p[2] or "—",
            "state": p[3], "state_sec": int(_f(p[4])),
            "effic_shift": _f(p[5]), "effic_24h": _f(p[6]),
            "stops_shift": int(_f(p[7])), "stops_24h": int(_f(p[8])), "rpm": int(_f(p[9])),
            "running": p[3] == "Run",
            "doff_min": int(_f(g(11))), "beam_out_min": int(_f(g(13))),
            "top_beam_use": int(_f(g(14))), "top_beam_out_min": int(_f(g(16))),
        }
    return out


def parse_loom(text):
    """Файл одного станка: флаги причины, счётчики и заданные значения."""
    lines = text.splitlines()
    kv = dict(l.split("=", 1) for l in lines if "=" in l)
    clean = lambda v: (v or "").strip().strip('"')
    num = lambda k: _f(kv.get(k))
    try:
        fact_time = int(lines[1])
    except (IndexError, ValueError):
        fact_time = None
    return {
        "cause": next((f for f in CAUSE_FLAGS if kv.get(f, "").strip() == "1"), "Unknown"),
        "fact_time": fact_time,
        "signals": {k.strip(): clean(v)[:500] for k, v in kv.items()},
        "model": clean(kv.get("mac_type2")),
        "cloth_name": clean(kv.get("Cloth_name")),
        "style_name": clean(kv.get("Style_name")),
        "beam_name": clean(kv.get("Beam_name")),
        "remaining_m": round(num("Remaining_Length_meter") / BEAM_SCALE),
        "beam_length_m": round(num("Beam_length_meter") / BEAM_SCALE),
        "doff_min": int(num("Cloth_change_time")),
        "beam_out_min": int(num("Beam_out_time")),
        "top_beam_use": int(num("Top_beam_use")),
        "top_beam_out_min": int(num("Top_beam_out_time")),
        "oee_shift": num("Shift_efficiency"), "oee_24h": num("24h_efficiency"),
        "rpm": int(num("Rpm")), "cloth_length_m": num("Cloth_length_meter"),
        "stop_time_sec": int(num("Stop_time")),
        "tension": num("Tension"), "flow": num("Flow"), "system_pressure": num("System_pressure"),
    }


# Журнал опроса станков программой FACT (opestate/collect_log.txt, предыдущие —
# collect_log1..3): «[2026/09/25 02:55:29] J10 (192.168.1.40) ---> POWER_OFF».
# Это данные самого FACT о связи со станком — не наша догадка по нулевым флагам.
COLLECT_LOG = "collect_log.txt"
_COLLECT_LINE = re.compile(r"^\[(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d)\]\s+(\S+)\s+\(([\d.]+)\)\s+--->\s+(.+?)\s*$")
# Что FACT ответил про станок -> причина простоя. SUCCEED — связь есть, причину
# берём из флагов, как всегда.
LINK_CAUSE = {"POWER_OFF": "Power_off", "System ERROR": "No_link"}


def parse_collect_log(text):
    """{started, finished, completed, looms: {станок: ответ FACT}} одного опроса."""
    out = {"started": None, "finished": None, "completed": False, "looms": {}}
    for line in (text or "").splitlines():
        line = line.strip()
        stamp = line[1:20] if line.startswith("[") else None
        if "START DATA COLLECTING" in line:
            out["started"] = stamp
        elif "END DATA COLLECTING" in line:
            out["finished"] = stamp
        elif "COMPLETED" in line:
            out["completed"] = True
        m = _COLLECT_LINE.match(line)
        if m:
            out["looms"][m.group(2)] = m.group(4)
    return out


def state_dirs(src):
    """Папки снимков, от свежей к старой: FACT пишет новую раз в минуту."""
    dirs = [d for d in src.list(OPESTATE)[0] if d.isdigit()]
    if not dirs:
        raise RuntimeError("нет папок состояния в opestate")
    return sorted(dirs, key=int, reverse=True)


def latest_dir(src):
    return state_dirs(src)[0]


def snapshot(src, state_dir=None, workers=8, prev=None, full=True, link=None):
    """Снимок: все станки с причиной останова и подробностями.

    full=False и prev (прошлый снимок) — файлы читаем только у стоящих станков:
    причина останова нужна каждую минуту, а у работающих подробности (остаток
    основы, код ткани) меняются медленно — берём их из прошлого снимка. Прогнозы
    съёма и схода навоя приходят в list_data.txt и обновляются каждую минуту.
    Так FACT получает ~10 запросов в минуту вместо 42."""
    d = state_dir or latest_dir(src)
    read = lambda rel: src.read(rel)[0].decode("utf-8", "replace")
    looms = parse_list(read("%s/%s/list_data.txt" % (OPESTATE, d)))
    old = {} if full else ((prev or {}).get("looms") or {})
    if old:
        layout = {n: {k: st[k] for k in ("col", "row", "ip", "type") if k in st}
                  for n, st in old.items()}
    else:
        layout = parse_layout(read("%s/%s/layout.txt" % (OPESTATE, d)))
    first = next(iter(looms), None)     # его читаем всегда: по нему — время FACT

    def need(name):
        return (not old or name == first or not looms[name]["running"]
                or not (old.get(name) or {}).get("details"))

    def one(name):
        if not need(name):
            return name, dict(old[name]["details"], fact_time=old[name].get('details_at'))
        ip = (layout.get(name) or looms.get(name) or {}).get("ip")
        try:
            return name, parse_loom(read("%s/%s/loom/%s.txt" % (OPESTATE, d, loom_file(ip))))
        except (OSError, urllib.error.URLError, ValueError):
            return name, None

    # Файлы станков читаем параллельно: по сети восемьдесят запросов подряд
    # заняли бы несколько секунд, а снимок должен успевать за минуту FACT.
    with ThreadPoolExecutor(max_workers=workers) as ex:
        details = dict(ex.map(one, list(looms)))

    missing, fact_times = [], []
    for name, st in looms.items():
        st.update(layout.get(name, {}))
        det = details.get(name)
        if det is None:
            missing.append(name)
            det = {}
        if det.get("fact_time"):
            fact_times.append(det["fact_time"])
        st["details"] = {k: v for k, v in det.items() if k not in ("cause", "fact_time")}
        st['details_at'] = det.get('fact_time')
        # Ответ FACT о связи со станком в этом опросе (журнал collect_log).
        answer = (link or {}).get(name)
        if answer:
            st["fact_link"] = answer
        if answer == "POWER_OFF":
            st["running"] = False            # FACT: станок обесточен — работать не может
        if st["running"]:
            st["cause"] = "Run"
        elif answer in LINK_CAUSE:
            st["cause"] = LINK_CAUSE[answer]
        else:
            cause = st["state"]
            if cause in ("Stop", "Unknown", ""):
                cause = det.get("cause") or "Unknown"
            st["cause"] = cause
    return {
        "dir": d, "source": src.kind, "read_at": time.time(),
        "fact_time": max(fact_times) if fact_times else None,
        "looms": looms, "missing": missing,
        "full": not old, "files_read": sum(1 for n in looms if need(n)),
    }


# --- файл снимка --------------------------------------------------------------

def save(snap, path=None):
    """Атомарно: монитор никогда не прочитает наполовину записанный файл."""
    path = path or storage.LIVE_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


_file = {"mtime": None, "data": None}


def load(path=None):
    """Последний снимок, записанный сборщиком; None, если его нет."""
    path = path or storage.LIVE_FILE
    try:
        m = os.path.getmtime(path)
    except OSError:
        return None
    if m != _file["mtime"]:
        try:
            with open(path, encoding="utf-8") as f:
                _file["data"] = json.load(f)
            _file["mtime"] = m
        except (OSError, ValueError):
            return _file["data"]
    return _file["data"]


def lag_sec(snap, now=None):
    """На сколько снимок отстаёт от жизни: FACT собрал данные, мы их прочитали.

    Секунды простоя на доске досчитываются на эту величину — иначе станок,
    который стоит пять минут, до следующего снимка показывал бы четыре.
    Больше двух минут не досчитываем: часы FACT могут идти не так, как наши.
    """
    if not snap or snap.get("source") != "fact" or not snap.get("fact_time"):
        return 0
    now = now or time.time()
    return int(min(max(0, now - snap["fact_time"]), 120))
