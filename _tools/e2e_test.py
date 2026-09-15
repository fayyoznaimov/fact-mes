"""Сквозная проверка приложения цеха на песочнице (копия баз, порт 8790, без FACT).

Каждый шаг: что делаем, что ждём, сколько заняло, размер ответа. Итог — список
ошибок и самых медленных ответов (для оптимизации).
"""
import http.client
import json
import os
import sqlite3
import socket
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8790"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SECRETS = {}
MXL = os.path.join(HERE, "fixtures", "13.mxl")
ORDER_1557 = os.path.join(ROOT, "postman", "order_1557.json")
SHOP = os.path.join(ROOT, "_app", "shop.db")

RESULTS, TIMES = [], []


def req(method, path, body=None, cookie=True, headers=None, raw=None, timeout=180):
    h = dict(headers or {})
    if cookie:
        h["Cookie"] = "sid=" + SECRETS["admin"]["token"]
    data = raw
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            out, code, ctype = resp.read(), resp.status, resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        out, code, ctype = e.read(), e.code, e.headers.get("Content-Type", "")
    ms = (time.perf_counter() - t0) * 1000
    TIMES.append((ms, len(out), method, path.split("?")[0]))
    js = None
    if "json" in ctype:
        try:
            js = json.loads(out)
        except ValueError:
            pass
    return code, js, out, ms


def check(area, name, fn):
    try:
        note = fn()
        RESULTS.append((area, name, True, note or ""))
        print("  ok   %-10s %-44s %s" % (area, name, note or ""))
    except Exception as e:
        RESULTS.append((area, name, False, "%s: %s" % (type(e).__name__, e)))
        print("  FAIL %-10s %-44s %s: %s" % (area, name, type(e).__name__, e))


def ok(path, **kw):
    code, js, out, ms = req("GET", path, **kw)
    assert code == 200, "HTTP %s: %s" % (code, out[:200])
    return js if js is not None else out


def password_sessions():
    def reset():
        login = "e2e_" + secrets.token_hex(8)
        password = secrets.token_urlsafe(20)
        code, _, _, _ = req("POST", "/api/users", {
            "login": login, "name": "Проверка сессий", "role": "viewer", "password": password})
        assert code == 200, code
        try:
            def sign_in(pwd):
                code, _, _, _ = req("POST", "/api/login", {"login": login, "password": pwd}, cookie=False)
                assert code == 200, code
                with sqlite3.connect(SHOP) as db:
                    return db.execute("SELECT s.token FROM app_session s JOIN app_user u ON u.id=s.user_id "
                                      "WHERE u.login=? ORDER BY s.rowid DESC LIMIT 1", (login,)).fetchone()[0]
            first, second = sign_in(password), sign_in(password)
            with sqlite3.connect(SHOP) as db:
                uid = db.execute("SELECT id FROM app_user WHERE login=?", (login,)).fetchone()[0]
            def user(token):
                return ok("/api/me", cookie=False, headers={"Cookie": "sid=" + token})["user"]
            new_password = secrets.token_urlsafe(20)
            code, _, _, _ = req("POST", "/api/password", {"password": new_password}, cookie=False,
                                headers={"Cookie": "sid=" + first})
            assert code == 200, code
            assert user(first) and not user(first)["must_change"], "текущая сессия потеряна"
            assert user(second) is None, "другая сессия сохранилась после смены пароля"
            code, _, _, _ = req("POST", "/api/login", {"login": login, "password": password}, cookie=False)
            assert code == 401, "старый пароль работает"
            third = sign_in(new_password)
            code, _, _, _ = req("POST", "/api/password", {"user_id": uid, "password": secrets.token_urlsafe(20)})
            assert code == 200, code
            assert user(first) is None and user(third) is None, "сброс не отозвал все сессии"
            assert ok("/api/me")["user"]["role"] == "admin", "сессия администратора потеряна"
            return "смена сохраняет текущую сессию; сброс отзывает все сессии пользователя"
        finally:
            with sqlite3.connect(SHOP) as db:
                db.execute("DELETE FROM app_session WHERE user_id IN (SELECT id FROM app_user WHERE login=?)", (login,))
                db.execute("DELETE FROM app_user WHERE login=?", (login,))
                db.execute("DELETE FROM login_fail WHERE login=?", (login,))
    check("вход", "отзыв сессий при смене и сбросе пароля", reset)


def auth_required():
    def missing():
        result = subprocess.run(
            [sys.executable, "-c", "import sys; sys.modules['auth'] = None; import web"],
            cwd=os.path.join(ROOT, "_app"), capture_output=True, text=True, timeout=10)
        assert result.returncode != 0 and "ModuleNotFoundError" in result.stderr, (
            "сервер загрузился без модуля авторизации")
        return "при отсутствии auth запуск прерывается"
    check("права", "сервер не запускается без авторизации", missing)


def http_input():
    for path in ("/api/login", "/api/loom_plan/upload", "/api/yarns/import"):
        for headers, want in (("Content-Length: -1", 400),
                              ("Content-Length: abc", 400),
                              ("Content-Length: 2\r\nContent-Length: 2", 400),
                              ("Transfer-Encoding: chunked", 400),
                              ("Content-Length: 999999999", 413)):
            def invalid(path=path, headers=headers, want=want):
                with socket.create_connection(("127.0.0.1", 8790), timeout=2) as sock:
                    request = ("POST %s HTTP/1.1\r\nHost: localhost\r\n"
                               "Cookie: sid=%s\r\n%s\r\n\r\n{}"
                               "GET /api/me HTTP/1.1\r\nHost: localhost\r\n\r\n") % (
                                   path, SECRETS["admin"]["token"], headers)
                    sock.sendall(request.encode("ascii"))
                    response = http.client.HTTPResponse(sock)
                    response.begin()
                    assert response.status == want, response.status
                    assert "error" in json.loads(response.read())
                    # Ни остаток тела, ни следующий запрос не обрабатываются.
                    assert sock.recv(1) == b"", "соединение после отказа не закрыто"
                    return "HTTP %d, соединение закрыто" % want
            check("HTTP", path + " / " + headers.replace("\r\n", "; "), invalid)
    for raw in (b"[]", b"null", b'"text"', b"42"):
        def invalid_json(raw=raw):
            code, js, _, _ = req("POST", "/api/login", raw=raw, cookie=False, timeout=2)
            assert code == 400 and "error" in js, code
            return "HTTP 400"
        check("HTTP", "JSON без объекта: " + raw.decode(), invalid_json)


# ---------------------------------------------------------------- открытое
def public():
    def page():
        b = ok("/", cookie=False)
        assert b"<title>" in b
        return "%d КБ" % (len(b) // 1024)
    check("открыто", "страница приложения", page)
    check("открыто", "доска мониторов /wall", lambda: "%d КБ" % (len(ok("/wall", cookie=False)) // 1024))
    check("открыто", "здоровье /api/health", lambda: "; ".join(
        "%s=%s" % kv for kv in ok("/api/health", cookie=False)["checks"].items())[:120])

    def live():
        d = ok("/api/live", cookie=False)
        assert "looms" in d and "totals" in d, "ответ без looms/totals"
        if not d["looms"]:
            # В песочнице нет зеркала FACT и сборщик выключен — снимка станков нет.
            h = ok("/api/health", cookie=False)["checks"]
            assert "не работает" in str(h.get("collector")), "станков нет, а сборщик работает"
            return "в песочнице снимка нет (сборщик выключен)"
        return "станков %d" % len(d["looms"])
    check("открыто", "живое состояние /api/live", live)

    def stream():
        c = http.client.HTTPConnection("127.0.0.1", 8790, timeout=15)
        t0 = time.perf_counter()
        c.request("GET", "/api/stream")
        r, got = c.getresponse(), b""
        while b"event: board" not in got:
            line = r.fp.readline()
            assert line, "поток оборвался"
            got += line
        c.close()
        return "первый кадр %.0f мс" % ((time.perf_counter() - t0) * 1000)
    check("открыто", "поток мониторов /api/stream", stream)
    check("открыто", "описание API /api/docs", lambda: "%d КБ" % (len(ok("/api/docs", cookie=False)) // 1024))

    def closed(path):
        def f():
            code, _, _, _ = req("GET", path, cookie=False)
            assert code in (401, 403), "без входа отдаёт HTTP %s" % code
            return "HTTP %s" % code
        return f
    for p in ("/api/salary?day=2026.09.14&shift=A", "/api/report?day=2026.09.14", "/api/setup_grid",
              "/api/users", "/api/keys", "/api/loom_plan", "/api/onec/messages"):
        check("права", "без входа закрыто " + p.split("?")[0], closed(p))

    def post_closed():
        code, _, _, _ = req("POST", "/api/loom_setup", {"looms": ["D2"]}, cookie=False)
        assert code in (401, 403), "запись без входа: HTTP %s" % code
        return "HTTP %s" % code
    check("права", "запись без входа закрыта", post_closed)


# ---------------------------------------------------------------- чтение
def reads():
    me = ok("/api/me")
    check("вход", "сессия /api/me", lambda: "роль %s" % (me.get("user") or me).get("role"))
    days = ok("/api/report_days")["days"]
    day = days[1] if len(days) > 1 else days[0]         # последний полный день
    state = {"day": day}

    def report():
        d = ok("/api/report?day=" + day)
        rows = d["rows"]
        assert len(rows) >= 30, "строк %d" % len(rows)
        with_y = [r for r in rows if json.loads(r.get("yarns") or "[]")]
        with_d = [r for r in rows if r.get("design")]
        assert len(with_y) >= 25, "пряжа по местам только у %d" % len(with_y)
        for r in with_y:
            for y in json.loads(r["yarns"]):
                assert y["slot"] in ("pile", "ground", "weft1", "weft2", "hemply", "hempoly",
                                     "weft3", "fancyply", "weft4"), y
        assert "client" not in json.dumps([{k: v for k, v in r.items() if k == "client_col"} for r in rows])
        state["rows"] = rows
        return "%s: станков %d, с пряжей %d, с дизайном %d" % (day, len(rows), len(with_y), len(with_d))
    check("отчёт", "производственный отчёт за день", report)

    def excel():
        code, js, out, ms = req("POST", "/api/export_excel", {"day": day})
        assert code == 200, "сборка Excel: HTTP %s: %s" % (code, out[:200])
        b = ok("/api/excel?day=" + day)
        assert b[:2] == b"PK", "не xlsx"
        return "%d КБ" % (len(b) // 1024)
    check("отчёт", "Excel за день", excel)

    def grid():
        g = ok("/api/setup_grid?day=" + day)
        rows = g["rows"]
        assert len(rows) >= 30
        keys = set(rows[0]["values"])
        for f in ("pile_yarn", "pile_lot", "hemply_yarn", "fancyply_lot", "weft4_yarn"):
            assert f in keys, "в таблице заправки нет %s" % f
        lots = sum(1 for r in rows if r["values"].get("pile_lot"))
        des = sum(1 for r in rows if r.get("design"))
        assert des >= 30, "дизайн только у %d" % des
        state["grid"] = rows
        return "станков %d, лот ворса у %d, дизайн у %d" % (len(rows), lots, des)
    check("заправка", "таблица заправки", grid)

    def yarn_lists():
        d = ok("/api/yarns")
        bs = d["by_slot"]
        assert set(bs) == {"pile", "ground", "weft1", "weft2", "hemply", "hempoly", "weft3", "fancyply", "weft4"}
        db = sqlite3.connect(SHOP)
        kinds = {}
        for y, k in db.execute("SELECT yarn, kind FROM yarn_lot"):
            kinds.setdefault(y, set()).add(k)
        tc = {}
        for slot, y in db.execute("SELECT slot, yarn_code FROM tech_card_yarn"):
            tc.setdefault(slot, set()).add(y)
        db.close()
        bad = []
        for slot, want in (("pile", {"pile"}), ("ground", {"ground"}), ("weft1", {"weft"})):
            s1c = {"pile": "vors", "ground": "karenoy", "weft1": "utog1"}[slot]
            for it in bs[slot]:
                if it["name"] in kinds and not kinds[it["name"]] & want and it["name"] not in tc.get(s1c, ()):
                    bad.append("%s на %s" % (it["name"], slot))
        assert not bad, "чужой вид в списке: " + ", ".join(bad)
        assert all(it["lots"] for it in bs["pile"][:3]), "у первых пряж ворса нет лотов"
        state["by_slot"] = bs
        return "ворс %d, грунт %d, уток %d; у 16/1 RING ворс-лоты %s" % (
            len(bs["pile"]), len(bs["ground"]), len(bs["weft1"]),
            next((i["lots"][:3] for i in bs["pile"] if i["name"] == "16/1 RING"), "—"))
    check("заправка", "отбор пряжи по месту", yarn_lists)

    simple = [
        ("отчёт", "/api/days"), ("отчёт", "/api/shifts"), ("люди", "/api/operators"),
        ("люди", "/api/assignments?day=%s&shift=A" % day), ("люди", "/api/shift_doc?day=%s&shift=A" % day),
        ("люди", "/api/shift_docs"), ("зарплата", "/api/salary?day=%s&shift=A" % day),
        ("kpi", "/api/kpi"), ("настройки", "/api/settings"), ("дашборд", "/api/dashboard"),
        ("дашборд", "/api/forecast"), ("план", "/api/plan"), ("план", "/api/loom_plan"),
        ("план", "/api/loom_plan/catalog"), ("план", "/api/ppt_check"), ("1С", "/api/onec/messages"),
        ("простои", "/api/bottlenecks"), ("простои", "/api/manual_stops?day=" + day),
        ("простои", "/api/production?day=" + day), ("простои", "/api/stop_days"),
        ("простои", "/api/explorer?day=" + day), ("обход", "/api/walk"), ("тикеты", "/api/tickets"),
        ("настройки", "/api/keys"), ("настройки", "/api/users"), ("настройки", "/api/logs"),
        ("техкарты", "/api/cards"), ("техкарты", "/cards"),
    ]
    for area, p in simple:
        def f(p=p):
            code, js, out, ms = req("GET", p)
            assert code == 200, "HTTP %s: %s" % (code, out[:160])
            return "%.0f мс, %d КБ" % (ms, len(out) // 1024)
        check(area, p.split("?")[0], f)
    return state


# ---------------------------------------------------------------- запись
def writes(state):
    day = state["day"]
    bs = state["by_slot"]
    loom = "D2"

    def import_mxl():
        raw = open(MXL, "rb").read()
        code, js, out, ms = req("POST", "/api/yarns/import", raw=raw,
                                headers={"Content-Type": "application/octet-stream"})
        assert code == 200, "HTTP %s: %s" % (code, out[:200])
        assert js["items"] == 111 and js["new"] == 0 and js["updated"] == 111, js
        return "партий %d, обновлено %d (повторная загрузка не плодит копий)" % (js["items"], js["updated"])
    check("пряжа", "загрузка справочника .mxl повторно", import_mxl)

    def import_bad():
        code, js, out, ms = req("POST", "/api/yarns/import", raw=b"not an mxl",
                                headers={"Content-Type": "application/octet-stream"})
        assert code == 400, "HTTP %s" % code
        return js["error"]
    check("пряжа", "мусор вместо .mxl -> 400", import_bad)

    pile = next(i for i in bs["pile"] if i["lots"])
    weft = next(i for i in bs["weft1"] if i["lots"])

    def save_setup():
        vals = {"ppt": "2150", "weight_kg": "0.61", "pile_yarn": pile["name"], "pile_lot": pile["lots"][0],
                "weft1_yarn": weft["name"], "weft1_lot": weft["lots"][0],
                "hemply_yarn": "20/2 OE", "hemply_lot": "107"}
        code, js, out, ms = req("POST", "/api/loom_setup", {"looms": [loom], "from_day": day, "values": vals})
        assert code == 200, "HTTP %s: %s" % (code, out[:300])
        return "станок %s, пересобрано дней %d, %.1f с" % (loom, len(js.get("days") or []), ms / 1000)
    check("заправка", "ручная заправка станка (пряжа+лот)", save_setup)

    def report_shows_manual():
        rows = ok("/api/report?day=" + day)["rows"]
        r = next(x for x in rows if x["loom"] == loom)
        ys = {y["slot"]: y for y in json.loads(r["yarns"])}
        assert ys["pile"]["yarn"] == pile["name"] and ys["pile"]["lot"] == pile["lots"][0], ys.get("pile")
        assert ys["pile"]["manual"], "ворс не отмечен как ручной"
        assert ys["hemply"]["yarn"] == "20/2 OE" and ys["hemply"]["lot"] == "107", ys.get("hemply")
        assert abs(float(r["ppt"]) - 2150) < 0.5, r["ppt"]
        assert "Кк:107" in (r.get("loto") or ""), r.get("loto")
        return "ворс %s·%s, кромка кручёная 20/2 OE·107, PPT 2150, лоты «%s»" % (
            pile["name"], pile["lots"][0], r["loto"])
    check("заправка", "отчёт показывает ручную заправку", report_shows_manual)

    def grid_marks_manual():
        rows = ok("/api/setup_grid?day=" + day)["rows"]
        r = next(x for x in rows if x["loom"] == loom)
        assert r["manual"].get("pile_yarn") and r["manual"].get("hemply_lot"), r["manual"]
        assert not r["manual"].get("ground_yarn"), "грунт не вводили, а он ручной"
        return "ручные поля: " + ", ".join(sorted(r["manual"]))
    check("заправка", "таблица отмечает ручные поля", grid_marks_manual)

    def bad_yarn():
        code, js, out, ms = req("POST", "/api/loom_setup", {"looms": [loom], "from_day": day,
                                                            "values": {"pile_yarn": "99/9 НЕТТАКОЙ"}})
        assert code == 400, "HTTP %s" % code
        return js["error"][:80]
    check("заправка", "незнакомая пряжа -> 400", bad_yarn)

    def bad_ppt():
        code, js, out, ms = req("POST", "/api/loom_setup", {"looms": [loom], "from_day": day, "values": {"ppt": "50"}})
        assert code == 400, "HTTP %s" % code
        return js["error"][:80]
    check("заправка", "PPT вне границ -> 400", bad_ppt)

    def bulk_all_or_nothing():
        before = sqlite3.connect(SHOP).execute("SELECT COUNT(*) FROM loom_setup").fetchone()[0]
        code, js, out, ms = req("POST", "/api/loom_setup/bulk", {"from_day": day, "rows": [
            {"loom": "D3", "values": {"ppt": "2000"}}, {"loom": "D4", "values": {"ppt": "abc"}}]})
        after = sqlite3.connect(SHOP).execute("SELECT COUNT(*) FROM loom_setup").fetchone()[0]
        assert code == 400 and before == after, "HTTP %s, записей было %d стало %d" % (code, before, after)
        return "ничего не сохранено: " + js["error"][:70]
    check("заправка", "таблица: одна ошибка -> ничего не пишет", bulk_all_or_nothing)

    def lot_upper():
        code, js, out, ms = req("POST", "/api/loom_setup", {"looms": ["D5"], "from_day": day,
                                                            "values": {"pile_lot": "  ab 12  "}})
        assert code == 200, out[:200]
        v = sqlite3.connect(SHOP).execute("SELECT pile_lot FROM loom_setup WHERE loom='D5' AND from_day=?",
                                          (day,)).fetchone()[0]
        assert v == "AB 12", v
        return "лот «  ab 12  » записан как «%s»" % v
    check("заправка", "лот чистится и в верхний регистр", lot_upper)

    # 1С
    key = SECRETS["key_1c"]
    auth = {"Authorization": "Bearer " + key}

    def onec_order():
        body = json.load(open(ORDER_1557, encoding="utf-8"))
        code, js, out, ms = req("POST", "/api/v1/1c", body, cookie=False, headers=auth)
        assert code == 200 and js.get("success"), "HTTP %s: %s" % (code, out[:300])
        return "заказ 1557 принят за %.1f с" % (ms / 1000)
    check("1С", "конверт заказа 1557 по ключу", onec_order)

    def onec_empty():
        code, js, out, ms = req("POST", "/api/v1/1c", {"actionType": "CreateOrUpdateProductionOrderAPI",
                                                       "data": {"productionOrders": []}},
                                cookie=False, headers=auth)
        assert code == 200 and js.get("success"), "HTTP %s: %s" % (code, out[:200])
        return "пустой список — успех с предупреждением"
    check("1С", "пустой конверт", onec_empty)

    def onec_nokey():
        code, js, out, ms = req("POST", "/api/v1/1c", {"data": {}}, cookie=False)
        assert code == 401 and js.get("success") is False, "HTTP %s" % code
        return "HTTP 401"
    check("1С", "без ключа -> 401", onec_nokey)

    def onec_badjson():
        code, js, out, ms = req("POST", "/api/v1/1c", raw=b"{broken", cookie=False,
                                headers=dict(auth, **{"Content-Type": "application/json"}))
        assert code == 400, "HTTP %s" % code
        return "HTTP 400"
    check("1С", "битый JSON -> 400", onec_badjson)

    def onec_read():
        d = ok("/api/v1/1c?order=1557", cookie=False, headers=auth)
        assert d.get("success") is not False
        return "чтение сохранённого: %d КБ" % (len(json.dumps(d)) // 1024)
    check("1С", "GET сохранённого заказа", onec_read)

    def card_after():
        db = sqlite3.connect(SHOP)
        n = db.execute("SELECT COUNT(*) FROM tech_card WHERE order_number='1557'").fetchone()[0]
        y = db.execute("SELECT COUNT(*) FROM tech_card_yarn WHERE order_number='1557'").fetchone()[0]
        db.close()
        assert n and y, "техкарт %d, пряжи %d" % (n, y)
        return "техкарт %d, мест пряжи %d" % (n, y)
    check("1С", "техкарта заказа записана", card_after)


def extra_checks(state):
    """План цеха: поставить заказ в клетку далёкого дня, увидеть, очистить.
    Дашборд и план без параметров — раньше падали в 500."""
    far, loom = "2027.01.04", "J28"
    cat = ok("/api/loom_plan/catalog")["orders"]
    o = next(e for e in cat if len(e["products"]) == 1)

    def put():
        code, js, out, ms = req("POST", "/api/loom_plan/cells",
                                {"changes": [{"loom": loom, "day": far, "order_no": o["order_no"]}]})
        assert code == 200 and js.get("ok") == 1, "HTTP %s: %s" % (code, out[:200])
        g = ok("/api/loom_plan?from=%s&to=%s" % (far, far))
        cells = [c for c in json.dumps(g, ensure_ascii=False).split('"loom"') if loom in c[:8]]
        assert any(str(o["order_no"]) in c for c in cells), "клетка не видна в плане"
        return "заказ %s на %s %s, изделие подобрано" % (o["order_no"], loom, far)
    check("план", "поставить заказ в клетку", put)

    def clear():
        code, js, out, ms = req("POST", "/api/loom_plan/cells",
                                {"changes": [{"loom": loom, "day": far, "order_no": "", "note": ""}]})
        assert code == 200, out[:200]
        n = sqlite3.connect(SHOP).execute("SELECT COUNT(*) FROM loom_plan WHERE loom=? AND day=?",
                                          (loom, far)).fetchone()[0]
        assert n == 0, "клетка не очистилась"
        return "очищена"
    check("план", "очистить клетку", clear)

    def bad_cell():
        code, js, out, ms = req("POST", "/api/loom_plan/cells",
                                {"changes": [{"loom": "Z99", "day": far, "order_no": "1"}]})
        assert code == 400, "HTTP %s" % code
        return js["error"]
    check("план", "чужой станок -> 400", bad_cell)

    for p in ("/api/dashboard", "/api/loom_plan", "/api/cards",
              "/api/dashboard?day=%s&shift=B" % state["day"]):
        def f(p=p):
            code, js, out, ms = req("GET", p)
            assert code == 200, "HTTP %s: %s" % (code, out[:160])
            return "%.0f мс, %d КБ" % (ms, len(out) // 1024)
        check("без дня", p, f)

    def plan_fast():
        code, js, out, ms = req("GET", "/api/plan")
        assert code == 200
        assert ms < 1500, "страница плана %.0f мс" % ms
        return "%.0f мс, заказов %d" % (ms, len(js["orders"]))
    check("скорость", "/api/plan быстрее 1,5 с", plan_fast)


def machine_history():
    def no_auth():
        code, _, _, _ = req("GET", "/api/machine_history", cookie=False)
        assert code == 401, code
    check("история", "без входа история закрыта", no_auth)

    def invalid():
        for query in ("day=bad", "day=2026-02-30", "period=bad", "looms=bad%2Fsql"):
            code, _, _, _ = req("GET", "/api/machine_history?" + query)
            assert code == 400, (query, code)
    check("история", "неверные параметры дают 400", invalid)

    def chronology():
        d = ok("/api/machine_history")
        assert d["end"] - d["start"] == 86400
        assert d["timezone"] == "+05:00"
        assert d["rows"], "нет станков в копии"
        for row in d["rows"]:
            assert sum(row["totals"].values()) == 86400, row["loom"]
            assert row["segments"][0]["start"] == d["start"]
            assert row["segments"][-1]["end"] == d["end"]
            for a, b in zip(row["segments"], row["segments"][1:]):
                assert a["end"] == b["start"], row["loom"]
            assert all(s["end"] > s["start"] for s in row["segments"])
        one = ok("/api/machine_history?day=" + d["day"] + "&period=C&looms=" + d["rows"][0]["loom"])
        assert len(one["rows"]) == 1
        assert one["end"] - one["start"] == 28800
        assert sum(one["rows"][0]["totals"].values()) == 28800
        return "%d станков; сутки и ночная смена; интервалы без разрывов и двойного счёта" % len(d["rows"])
    check("история", "журнал и фильтр ночной смены", chronology)


def main():
    # Проверяем файлы до первого HTTP-запроса, чтобы не выполнять половину
    # пишущего теста при неполной подготовке песочницы.
    secret_path = os.path.join(ROOT, "_app", "e2e_secrets.json")
    for path in (secret_path, SHOP, MXL, ORDER_1557):
        if not os.path.isfile(path):
            raise SystemExit("Не найден файл песочницы: " + path)
    with open(secret_path, encoding="utf-8") as f:
        SECRETS.update(json.load(f))
    t0 = time.time()
    print("Песочница", BASE)
    auth_required()
    password_sessions()
    http_input()
    public()
    state = reads()
    machine_history()
    writes(state)
    extra = globals().get("extra_checks")
    if extra:
        extra(state)
    bad = [r for r in RESULTS if not r[2]]
    print("\nИтог: проверок %d, ошибок %d, %.0f с" % (len(RESULTS), len(bad), time.time() - t0))
    for a, n, _, note in bad:
        print("  ОШИБКА %s / %s — %s" % (a, n, note))
    print("\nСамые медленные ответы:")
    for ms, size, m, p in sorted(TIMES, reverse=True)[:12]:
        print("  %7.0f мс  %6d КБ  %s %s" % (ms, size // 1024, m, p))
    print("\nСамые тяжёлые ответы:")
    for ms, size, m, p in sorted(TIMES, key=lambda x: -x[1])[:8]:
        print("  %6d КБ  %7.0f мс  %s %s" % (size // 1024, ms, m, p))
    json.dump({"results": RESULTS, "times": TIMES}, open(os.path.join(HERE, "e2e_result.json"), "w"),
              ensure_ascii=False)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
