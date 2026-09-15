"""Нагрузочная проверка: мониторы на толчках и люди с отчётами одновременно.

    python loadtest.py                                   # 30 мониторов, 10 человек, 30 секунд
    python loadtest.py --monitors 60 --users 20 --seconds 60
    python loadtest.py --url http://server:8780 --login admin --password admin

Что меряется:

    толчок     за сколько новая доска доходит до всех мониторов после того, как
               что-то поменялось (завели тикет, пришёл снимок FACT);
    отчёты     сколько запросов в секунду держат отчёты и дашборды, пока
               мониторы висят на соединении, и какие у них задержки.

Толчок вызывается так же, как в жизни: сборщик записал новый снимок станков.
Скрипт трогает файл снимка `run/live.json`, поэтому запускать его нужно на том же
сервере, что и приложение. Отчёты читаются по временному ключу API с правом
чтения: скрипт выдаёт его себе в начале и отзывает в конце.
"""
import argparse
import http.client
import os
import statistics
import sys
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "_app"))


class Monitor(threading.Thread):
    """Один монитор: держит поток и записывает, когда пришла каждая версия доски."""
    daemon = True

    def __init__(self, host, port):
        super().__init__()
        self.host, self.port = host, port
        self.got = {}           # номер версии -> время прихода
        self.error = None

    def run(self):
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=120)
            conn.request("GET", "/api/stream")
            resp = conn.getresponse()
            ver = None
            while True:
                line = resp.fp.readline()
                if not line:
                    break
                line = line.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("id: "):
                    ver = int(line[4:])
                elif line == "" and ver is not None:
                    self.got.setdefault(ver, time.time())
                    ver = None
        except Exception as e:
            self.error = "%s: %s" % (type(e).__name__, e)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8780")
    ap.add_argument("--monitors", type=int, default=30)
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--pushes", type=int, default=5)
    args = ap.parse_args()
    u = urllib.parse.urlparse(args.url)
    host, port = u.hostname, u.port or 80

    import api
    import reports
    import storage
    key = api.create_key("нагрузочная проверка", ["read"], "loadtest")
    auth = {"Authorization": "Bearer " + key["key"]}
    try:
        run(args, host, port, auth, reports.latest_day(), storage.LIVE_FILE)
    finally:
        db = storage.shop()
        db.execute("DELETE FROM api_key WHERE id=?", (key["id"],))
        db.commit()
        db.close()


def run(args, host, port, auth, day, live_file):

    # --- мониторы ---
    mons = [Monitor(host, port) for _ in range(args.monitors)]
    t0 = time.time()
    for m in mons:
        m.start()
    while time.time() - t0 < 15 and sum(1 for m in mons if m.got) < len(mons):
        time.sleep(0.1)
    connected = sum(1 for m in mons if m.got)
    print("Мониторов подключилось: %d из %d за %.1f с" % (connected, len(mons), time.time() - t0))

    # --- люди с отчётами, пока мониторы висят ---
    paths = ["/api/live", "/api/report?day=" + day, "/api/cards",
             "/api/bottlenecks?from=2026.08.14&to=" + day,
             "/api/manual_stops?from=2026.08.14&to=" + day,
             "/api/plan", "/api/v1/looms", "/api/dashboard?day=" + day, "/"]
    lat, errors, stop = {p: [] for p in paths}, [], time.time() + args.seconds

    def user(i):
        k = i
        while time.time() < stop:
            p = paths[k % len(paths)]
            k += 1
            t = time.perf_counter()
            try:
                urllib.request.urlopen(urllib.request.Request(
                    args.url + p, headers={"Accept-Encoding": "gzip", **auth}), timeout=60).read()
                lat[p].append((time.perf_counter() - t) * 1000)
            except Exception as e:
                errors.append("%s %s" % (p, e))

    users = [threading.Thread(target=user, args=(i,), daemon=True) for i in range(args.users)]
    for t in users:
        t.start()

    # --- толчки: «сборщик записал новый снимок» — трогаем файл снимка и ждём,
    # пока новая доска дойдёт до всех мониторов. Сервер замечает файл раз в
    # секунду, так что в задержку входит и это ожидание. ---
    delays = []
    for _ in range(args.pushes):
        time.sleep(max(1.0, args.seconds / (args.pushes + 1)))
        before = [max(m.got) if m.got else 0 for m in mons]
        tp = time.time()
        os.utime(live_file, None)
        deadline = tp + 10
        while time.time() < deadline:
            if all(any(v > b for v in m.got) for m, b in zip(mons, before) if m.got):
                break
            time.sleep(0.02)
        for m, b in zip(mons, before):
            new = [m.got[v] for v in m.got if v > b]
            if new:
                delays.append((min(new) - tp) * 1000)
    for t in users:
        t.join()

    total = sum(len(v) for v in lat.values())
    print("\nОтчёты: %d человек, %d с, запросов %d (%.0f в секунду), ошибок %d"
          % (args.users, args.seconds, total, total / args.seconds, len(errors)))
    print("  %-44s %8s %8s %8s" % ("адрес", "медиана", "95 %", "запросов"))
    for p, xs in lat.items():
        if xs:
            print("  %-44s %6.0f мс %6.0f мс %8d" % (p[:44], statistics.median(xs), pct(xs, 0.95), len(xs)))
    if delays:
        print("\nТолчок до мониторов: %d доставок, медиана %.0f мс, 95 %% %.0f мс, худшая %.0f мс"
              % (len(delays), statistics.median(delays), pct(delays, 0.95), max(delays)))
    bad = [m.error for m in mons if m.error]
    if bad:
        print("Оборвались мониторы: %d (%s)" % (len(bad), bad[0]))
    if errors:
        print("Первые ошибки:", errors[:3])


if __name__ == "__main__":
    main()
