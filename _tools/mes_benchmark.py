"""Нагрузка MES: 20 потоков доски, запись причин, отчёты и импорт 1С.

Только для подготовленной временной песочницы fact_mes_audit_*.
Не принимает адрес рабочего сервера и не обращается к Toyota.
    python mes_benchmark.py --seconds 30
"""
import argparse
import http.client
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import statistics
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8790"


def sandbox():
    if ROOT.parent != Path(tempfile.gettempdir()).resolve() or not ROOT.name.startswith("fact_mes_audit_"):
        raise SystemExit("Разрешена только отдельная временная песочница fact_mes_audit_*")
    marker = ROOT / "audit_sandbox.json"
    if not marker.is_file() or json.loads(marker.read_text()).get("sandbox") is not True:
        raise SystemExit("Нет маркера песочницы")


def main():
    sandbox()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--writers", type=int, default=20)
    ap.add_argument("--users", type=int, default=4)
    args = ap.parse_args()
    if not 5 <= args.seconds <= 120 or not 1 <= args.writers <= 20 or not 0 <= args.users <= 10:
        raise SystemExit("Границы: 5–120 секунд, 1–20 терминалов, 0–10 читателей")
    credentials = json.loads((ROOT / "_app/e2e_secrets.json").read_text(encoding="utf-8"))
    headers = {"Cookie": "sid=" + credentials["admin"]["token"]}
    live_path = ROOT / "_app/run/live.json"
    snap = json.loads(live_path.read_text())
    for st in snap["looms"].values():
        st.update(running=False, state="Manual", cause="Manual", state_sec=600)
    snap.update(read_at=time.time(), source="mirror")
    def save_snapshot():
        temp = live_path.with_suffix(".benchmark.tmp")
        temp.write_text(json.dumps(snap), encoding="utf-8")
        os.replace(temp, live_path)
    save_snapshot()
    time.sleep(.4)
    metrics = {"write": [], "read": [], "onec": [], "rollup": []}
    errors, seen, channels = [], [{} for _ in range(20)], []
    quit_event = threading.Event()

    def request(path, body=None, extra=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=data,
                headers={**headers, "Content-Type": "application/json", **(extra or {})})
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = resp.read()
        result = json.loads(payload)
        if result.get("error") or result.get("success") is False:
            raise RuntimeError(result.get("error") or "операция не выполнена")
        return result

    def monitor(index):
        conn = http.client.HTTPConnection("127.0.0.1", 8790, timeout=args.seconds + 20)
        channels.append(conn)
        try:
            conn.request("GET", "/api/stream")
            resp = conn.getresponse()
            if resp.status != 200:
                raise RuntimeError("SSE HTTP %s" % resp.status)
            while not quit_event.is_set():
                line = resp.readline()
                if not line:
                    break
                if line.startswith(b"data: "):
                    board = json.loads(line[6:])
                    seen[index].setdefault(board["state_dir"], time.perf_counter())
        except Exception as exc:
            if not quit_event.is_set():
                errors.append("SSE: " + type(exc).__name__)
        finally:
            conn.close()

    threads = [threading.Thread(target=monitor, args=(i,), daemon=True) for i in range(20)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 10
    while not all(seen) and time.monotonic() < deadline:
        time.sleep(.05)
    connected = sum(bool(item) for item in seen)
    day = request("/api/report_days")["days"][0]
    looms = sorted(snap["looms"])[:args.writers]
    started = time.monotonic()
    end = started + args.seconds

    def record(kind, fn):
        t0 = time.perf_counter()
        try:
            fn()
            metrics[kind].append((time.perf_counter() - t0) * 1000)
        except Exception as exc:
            errors.append(kind + ": " + type(exc).__name__ + ": " + str(exc)[:100])

    def writer(loom):
        n = 0
        while time.monotonic() < end:
            record("write", lambda: request("/api/tickets/new", {
                "loom": loom, "category_id": "electrical" if n % 2 else "toir"}))
            n += 1
            time.sleep(2)

    paths = ["/api/report?day=" + day, "/api/dashboard?day=" + day, "/api/plan",
             "/api/bottlenecks", "/api/manual_stops?day=" + day]
    def reader(index):
        while time.monotonic() < end:
            record("read", lambda: request(paths[index % len(paths)]))
            index += 1
            time.sleep(.2)

    order = json.loads((ROOT / "postman/order_1557.json").read_text(encoding="utf-8"))
    def onec():
        while time.monotonic() < end:
            record("onec", lambda: request("/api/v1/1c", order,
                   {"Authorization": "Bearer " + credentials["key_1c"]}))
            time.sleep(10)

    # Та же свёртка остановов, что выполняется сборщиком, но без сетевого источника.
    def rollup():
        import sys
        sys.path.insert(0, str(ROOT / "_app"))
        import ingest
        def update():
            db = sqlite3.connect(ROOT / "_tools/fact.db", timeout=15)
            try:
                ingest.rollup_day(db, day)
                db.commit()
            finally:
                db.close()
        while time.monotonic() < end:
            record("rollup", update)
            time.sleep(10)

    workers = [threading.Thread(target=writer, args=(loom,)) for loom in looms]
    workers += [threading.Thread(target=reader, args=(i,)) for i in range(args.users)]
    workers += [threading.Thread(target=onec), threading.Thread(target=rollup)]
    for worker in workers:
        worker.start()
    delivery = []
    missing_deliveries = 0
    for i in range(3):
        time.sleep(args.seconds / 4)
        marker = "benchmark_" + secrets.token_hex(6)
        snap.update(dir=marker, read_at=time.time())
        t0 = time.perf_counter()
        save_snapshot()
        wait_until = time.monotonic() + 5
        while not all(marker in got for got in seen) and time.monotonic() < wait_until:
            time.sleep(.02)
        for got in seen:
            if marker in got:
                delivery.append((got[marker] - t0) * 1000)
            else:
                missing_deliveries += 1
    for worker in workers:
        worker.join()
    quit_event.set()
    for conn in channels:
        conn.close()
    def summary(values):
        values = sorted(values)
        return {"count": len(values), "p50_ms": round(statistics.median(values), 1),
                "p95_ms": round(values[math.ceil(.95 * len(values)) - 1], 1),
                "max_ms": round(max(values), 1)} if values else {"count": 0}
    result = {"looms": len(snap["looms"]), "seconds": args.seconds, "writers": args.writers,
              "readers": args.users, "monitors": connected, "missing_deliveries": missing_deliveries,
              "metrics": {**{name: summary(v) for name, v in metrics.items()}, "delivery": summary(delivery)},
              "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    (ROOT / ("benchmark_%s.json" % len(snap["looms"]))).write_text(json.dumps(result), encoding="utf-8")
    raise SystemExit(1 if errors or missing_deliveries or connected != 20 else 0)


if __name__ == "__main__":
    main()
