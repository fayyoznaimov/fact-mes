"""Проверка работающего приложения: всё ли отвечает после установки или обновления.

    python selftest.py                                  # проверка по адресу localhost:8780
    python selftest.py --url http://172.0.30.10:8780
    python selftest.py --login admin --password ...     # заодно проверить вход и права

Без логина проверяются страницы, доска мониторов, живое состояние и здоровье
службы — то, что должно работать даже до входа. С логином добавляются отчёты,
зарплата и справочники.

Возвращает код 0, если всё в порядке, иначе 1 — так проверку можно поставить
в планировщик и получать письмо, когда цех встал.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
import http.cookiejar

OK, BAD = "ок", "ОШИБКА"


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, path, timeout=60):
        t0 = time.perf_counter()
        with self.op.open(self.base + path, timeout=timeout) as r:
            body = r.read()
        return body, (time.perf_counter() - t0) * 1000

    def post(self, path, obj, timeout=60):
        req = urllib.request.Request(self.base + path, json.dumps(obj).encode(),
                                     {"Content-Type": "application/json"})
        with self.op.open(req, timeout=timeout) as r:
            return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8780")
    ap.add_argument("--login")
    ap.add_argument("--password")
    args = ap.parse_args()

    c = Client(args.url)
    bad = 0

    def check(name, fn):
        nonlocal bad
        try:
            note = fn()
            print("  %-28s %s  %s" % (name, OK, note or ""))
        except Exception as e:
            bad += 1
            print("  %-28s %s  %s: %s" % (name, BAD, type(e).__name__, e))

    print("Проверка %s" % args.url)

    def page():
        body, ms = c.get("/")
        assert b"<title>" in body or b"nav" in body, "страница пустая"
        return "%d КБ, %.0f мс" % (len(body) / 1024, ms)

    def wall():
        body, ms = c.get("/wall")
        assert b"\xd0\x94\xd0\xbe\xd1\x81\xd0\xba\xd0\xb0" in body, "не доска цеха"
        return "%d КБ, %.0f мс" % (len(body) / 1024, ms)

    def health():
        h = json.loads(c.get("/api/health")[0])
        assert h["ok"], "служба нездорова: %s" % h["checks"]
        return "; ".join("%s: %s" % kv for kv in h["checks"].items())

    def live():
        d = json.loads(c.get("/api/live")[0])
        assert d["looms"], "нет станков: %s" % d.get("error")
        t = d["totals"]
        return "станков %d, работает %d, стоит %d, без причины %d" % (
            t["looms"], t["running"], t["stopped"], t["no_reason"])

    def ticket_list():
        d = json.loads(c.get("/api/live")[0])
        assert d.get("categories"), "нет категорий тикетов"
        return "открытых тикетов %d, без тикета %d" % (d["totals"]["open_tickets"],
                                                      d["totals"].get("no_ticket", 0))

    def stream():
        # Первый кадр доски приходит сразу после подключения.
        import http.client
        from urllib.parse import urlparse
        u = urlparse(c.base)
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=10)
        t0 = time.perf_counter()
        conn.request("GET", "/api/stream")
        resp = conn.getresponse()
        got = b""
        while b"event: board" not in got:
            line = resp.fp.readline()
            assert line, "поток оборвался"
            got += line
        conn.close()
        return "первый кадр за %.0f мс" % ((time.perf_counter() - t0) * 1000)

    def closed():
        try:
            c.get("/api/salary?day=2026.01.01&shift=A")
        except urllib.error.HTTPError as e:
            assert e.code == 401, "ответ %s" % e.code
            return "зарплата без входа закрыта"
        raise AssertionError("зарплата отдаётся без входа")

    check("страница приложения", page)
    check("доска мониторов", wall)
    check("здоровье службы", health)
    check("живое состояние станков", live)
    check("тикеты", ticket_list)
    check("толчки на мониторы", stream)
    check("закрытые данные", closed)

    if args.login and args.password:
        def sign_in():
            r = c.post("/api/login", {"login": args.login, "password": args.password})
            assert r.get("ok"), "вход не прошёл"
            return "роль %s" % r["user"]["role"]

        def report():
            days = json.loads(c.get("/api/report_days")[0])["days"]
            assert days, "нет дней с отчётом"
            rows = json.loads(c.get("/api/report?day=" + days[0])[0])["rows"]
            assert rows, "отчёт за %s пустой" % days[0]
            return "%s: строк %d" % (days[0], len(rows))

        def salary():
            sh = json.loads(c.get("/api/shifts")[0])["shifts"]
            assert sh, "нет смен"
            s = json.loads(c.get("/api/salary?day=%s&shift=%s" % (sh[0]["day"], sh[0]["shift"]))[0])
            return "смена %s.%s: начислено %s сум" % (sh[0]["day"], sh[0]["shift"],
                                                      s["totals"]["salary"])

        def people_dir():
            ops = json.loads(c.get("/api/operators")[0])["operators"]
            return "операторов %d" % len(ops)

        check("вход", sign_in)
        check("производственный отчёт", report)
        check("зарплата", salary)
        check("справочник операторов", people_dir)
    else:
        print("  (вход не проверялся: запустите с --login и --password)")

    print("Итог: %s" % ("всё в порядке" if not bad else "ошибок %d" % bad))
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
