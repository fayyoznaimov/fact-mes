"""Внешний API: для 1С, телеграм-бота, BI и всего, что появится потом.

Версия в адресе (/api/v1/…): интерфейс для чужих программ меняется только с
новой версией, а внутренние адреса приложения (/api/…) можно править свободно.

Вход — по ключу: заголовок `Authorization: Bearer <ключ>` или `X-Api-Key`.
Ключи заводит администратор в «Настройках», хранится только хэш. Права ключа:

    read     состояние станков, выработка, простои, прогнозы, план;
    write    заказы, техкарты и связка кодов ткани — то, что шлёт 1С;
    tickets  заводить и разбирать тикеты — бот, система ТОиР.

Вошедший в приложение человек тоже может читать API — удобно проверять
адреса прямо из браузера. Описание — /api/v1/openapi.json и /api/docs.
"""
import hashlib
import html
import secrets
import time
from datetime import datetime, timedelta

import dashboard
import integration
import metrics
import planning
import reports
import tickets
from storage import shop

SCOPES = {"read": "читать данные", "write": "присылать заказы и техкарты",
          "tickets": "заводить и разбирать тикеты"}
# Какое право человека заменяет право ключа.
USER_PERM = {"read": "view", "write": "assign", "tickets": "tickets"}


# --- ключи --------------------------------------------------------------------

def _hash(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def create_key(name, scopes, who=""):
    scopes = [s for s in scopes if s in SCOPES]
    if not (name or "").strip():
        raise ValueError("назовите ключ: для кого он (1С, бот, BI)")
    if not scopes:
        raise ValueError("выберите хотя бы одно право")
    key = "mes_" + secrets.token_urlsafe(30)
    db = shop()
    cur = db.execute("INSERT INTO api_key (name, prefix, key_hash, scopes, created_by)"
                     " VALUES (?,?,?,?,?)",
                     (name.strip()[:80], key[:10], _hash(key), " ".join(scopes), who))
    db.commit()
    kid = cur.lastrowid
    db.close()
    return {"id": kid, "key": key, "name": name.strip(), "scopes": scopes}


def list_keys():
    db = shop()
    rows = [dict(r) for r in db.execute(
        "SELECT id, name, prefix, scopes, active, created_by, created_at, last_used_at"
        " FROM api_key ORDER BY active DESC, id DESC")]
    db.close()
    return rows


def revoke_key(kid):
    db = shop()
    db.execute("UPDATE api_key SET active=0 WHERE id=?", (kid,))
    db.commit()
    db.close()


_used = {}


def check(headers):
    """Ключ из заголовков запроса или None."""
    raw = (headers.get("X-Api-Key") or "").strip()
    auth = headers.get("Authorization") or ""
    if auth[:7].lower() == "bearer ":
        raw = auth[7:].strip()
    if not raw:
        return None
    h = _hash(raw)
    db = shop()
    row = db.execute("SELECT * FROM api_key WHERE key_hash=? AND active=1", (h,)).fetchone()
    # Время последнего обращения пишем не чаще раза в минуту: запись на каждый
    # запрос опроса из 1С была бы лишней нагрузкой на базу.
    if row and time.time() - _used.get(row["id"], 0) > 60:
        _used[row["id"]] = time.time()
        db.execute("UPDATE api_key SET last_used_at=? WHERE id=?",
                   (datetime.now().astimezone().isoformat(timespec="seconds"), row["id"]))
        db.commit()
    db.close()
    return dict(row) if row else None


# --- помощники ----------------------------------------------------------------

def _period(q, days=7):
    """Период из ?from=&to=; по умолчанию — последние `days` дней с данными."""
    to = planning.norm_day(q.get("to")) or reports.latest_day() or datetime.now().strftime("%Y.%m.%d")
    frm = planning.norm_day(q.get("from"))
    if not frm:
        frm = (datetime.strptime(to, "%Y.%m.%d") - timedelta(days=days - 1)).strftime("%Y.%m.%d")
    return frm, to


def _list(body, key):
    items = body.get(key) if isinstance(body, dict) else body
    if not isinstance(items, list):
        raise ValueError("нужен список «%s»" % key)
    return items


# --- чтение -------------------------------------------------------------------

def looms(q, body, who):
    b = tickets.board()
    det = dashboard.loom_details()
    out = []
    for r in b["looms"]:
        d = det.get(r["loom"], {})
        out.append({
            "loom": r["loom"], "running": r["running"], "state": r["state"],
            "state_sec": r["state_sec"], "cause": r["cause"], "cause_ru": r["cause_ru"],
            "reason": r["reason"], "reason_from": r["reason_from"], "andon": r["andon"],
            "ticket_id": r["ticket_id"], "ticket_category": r["ticket_category"],
            "style": r["style"], "cloth": d.get("cloth_name"), "rpm": r["rpm"],
            "effic_shift": r["effic_shift"], "remaining_m": d.get("remaining_m"),
            "doff_in_min": d.get("doff_min"), "beam_out_in_min": d.get("beam_out_min"),
            "top_beam_out_in_min": d.get("top_beam_out_min") if d.get("top_beam_use") else None,
        })
    return {"updated_at": b["updated_at"], "shift": b["shift"], "stale": b["stale"],
            "source": b["source"], "totals": b["totals"], "looms": out}


def forecast(q, body, who):
    return dashboard.forecast(int(q.get("hours") or 12) * 60)


def production(q, body, who):
    frm, to = _period(q)
    group = q.get("group") or "day"
    if group not in metrics.PRODUCTION_GROUPS:
        raise ValueError("group: одно из %s" % ", ".join(metrics.PRODUCTION_GROUPS))
    return {"from": frm, "to": to, "group": group,
            "rows": metrics.production_grouped(frm, to, group)}


def downtime(q, body, who):
    frm, to = _period(q, 30)
    b = metrics.bottlenecks(frm, to)
    return {"from": frm, "to": to, "totals": b["totals"], "response_sec": b["response"],
            "by_cause": b["by_cause"], "by_loom": b["by_loom"], "by_shift": b["by_shift"]}


def manual_stops(q, body, who):
    frm, to = _period(q)
    group = q.get("group") or "day"
    if group not in ("day", "loom", "shift"):
        raise ValueError("group: day, loom или shift")
    return reports.lds_manual(frm, to, group)


def ticket_list(q, body, who):
    frm, to = _period(q, 1)
    return {"from": frm, "to": to,
            "tickets": tickets.ticket_list(limit=min(int(q.get("limit") or 500), 5000),
                                           only_open=q.get("open") == "1",
                                           date_from=frm, date_to=to),
            "categories": tickets.CATEGORIES}


def orders_get(q, body, who):
    return {"orders": planning.orders(q.get("closed") == "1")}


def cloth_map_get(q, body, who):
    return {"map": planning.cloth_map_list(), "unmapped": planning.unmapped_cloths()}


# --- запись -------------------------------------------------------------------

def orders_post(q, body, who):
    """Заказы из 1С или другой системы. Повторная отправка того же заказа
    обновляет его, а не заводит второй."""
    done, errors = [], []
    for i, o in enumerate(_list(body, "orders")):
        try:
            product = o.get("product_code") or o.get("productCode")
            oid = planning.add_order(o.get("order_no") or o.get("orderNumber"), product,
                                     o.get("qty_towels") or o.get("quantity"),
                                     o.get("due_day") or o.get("dueDate"),
                                     source=o.get("source") or "API", note=o.get("note") or "")
            for loom in o.get("looms") or []:
                planning.assign_loom(oid, loom, o.get("from_day"), keep_existing=True)
            if o.get("cloth_code"):
                planning.set_cloth_map(o["cloth_code"], product, who)
            if o.get("ppt"):
                planning.set_ppt(product, o["ppt"], o.get("panels"), "1С", who)
            done.append({"index": i, "id": oid})
        except (ValueError, TypeError, KeyError) as e:
            errors.append({"index": i, "error": str(e)})
    return {"ok": len(done), "orders": done, "errors": errors}


def production_orders(q, body, who):
    return integration.handle_1c(body, who=who)


def onec_get(q, body, who):
    return integration.stored_orders(q.get("order"), q.get("from"), q.get("limit"))


def loom_plan_get(q, body, who):
    import loomplan
    frm, to = _period(q, 14)
    return loomplan.grid(frm, to)


def cloth_map_post(q, body, who):
    n = 0
    for m in _list(body, "map"):
        planning.set_cloth_map(m.get("cloth_code") or "", m.get("product_code") or "", who)
        n += 1
    return {"ok": n}


def ticket_post(q, body, who):
    """Завести тикет на станок или указать причину у открытого."""
    if body.get("ticket_id"):
        tickets.classify(int(body["ticket_id"]), body.get("category_id"), who,
                         body.get("comment", ""))
        return {"ok": True, "id": int(body["ticket_id"])}
    if not body.get("loom"):
        raise ValueError("нужен станок (loom) или номер тикета (ticket_id)")
    tid = tickets.open_ticket(body["loom"], who, body.get("category_id"), body.get("comment", ""))
    return {"ok": True, "id": tid}


# --- маршруты и описание -----------------------------------------------------

P_FROM = {"name": "from", "in": "query", "schema": {"type": "string", "example": "2026.09.01"},
          "description": "с какого дня (2026.09.01 или 2026-09-01)"}
P_TO = {"name": "to", "in": "query", "schema": {"type": "string", "example": "2026.09.12"},
        "description": "по какой день включительно; по умолчанию — последний с данными"}


def _group(values, default):
    return {"name": "group", "in": "query",
            "schema": {"type": "string", "enum": list(values), "default": default},
            "description": "разрез"}


ROUTES = {
    ("GET", "/api/v1/looms"): (looms, "read", "Состояние всех станков сейчас: работает или "
                               "стоит, причина, тикет, андон, прогнозы съёма и схода навоя", []),
    ("GET", "/api/v1/forecast"): (forecast, "read", "Съём ткани и сход навоев на ближайшие часы",
                                  [{"name": "hours", "in": "query",
                                    "schema": {"type": "integer", "default": 12}}]),
    ("GET", "/api/v1/production"): (production, "read", "Выработка: пики, метры, ряды, "
                                    "полотенца (ряды × панели), КПД",
                                    [P_FROM, P_TO, _group(("day", "shift", "loom", "cloth"), "day")]),
    ("GET", "/api/v1/downtime"): (downtime, "read", "Простои: по причинам, станкам и сменам, "
                                  "MTTR, время реакции оператора, обрывность на 100 тыс. пиков",
                                  [P_FROM, P_TO]),
    ("GET", "/api/v1/manual-stops"): (manual_stops, "read", "Сводка ручных остановов — как "
                                      "Manual Stoppages Summary в LDS: Shed/Time/Prod Eff и "
                                      "длинные остановы по причинам",
                                      [P_FROM, P_TO, _group(("day", "shift", "loom"), "day")]),
    ("GET", "/api/v1/tickets"): (ticket_list, "read", "Тикеты за период",
                                 [P_FROM, P_TO, {"name": "open", "in": "query",
                                                 "schema": {"type": "string", "enum": ["1"]}}]),
    ("GET", "/api/v1/orders"): (orders_get, "read", "План: заказы с фактом, темпом и прогнозом", []),
    ("GET", "/api/v1/cloth-map"): (cloth_map_get, "read", "Связка кодов ткани с артикулами 1С "
                                   "и коды, которые ещё не связаны", []),
    ("POST", "/api/v1/orders"): (orders_post, "write", "Прислать заказы (обновляет по номеру и "
                                 "изделию)", "orders"),
    ("GET", "/api/v1/loom-plan"): (loom_plan_get, "read", "План цеха по станкам и дням "
                                   "(заказ, изделие, клиент, GSM, ворс) и факт по тем же дням",
                                   [P_FROM, P_TO]),
    ("GET", "/api/v1/1c"): (onec_get, "read", "Что прислала 1С: заказы последней версией, в том "
                            "же формате, в каком 1С их шлёт (GSM, дизайн, вес, PPT, пряжа, лоты)",
                            [{"name": "order", "in": "query", "schema": {"type": "string",
                                                                          "example": "1708"},
                              "description": "номер заказа или uuid"},
                             {"name": "from", "in": "query", "schema": {"type": "string",
                                                                         "example": "2026.09.14"},
                              "description": "полученные с этого дня"},
                             {"name": "limit", "in": "query",
                              "schema": {"type": "integer", "default": 1000}}]),
    ("POST", "/api/v1/1c"): (production_orders, "write", "Запрос 1С в её конверте как есть: "
                             "actionType CreateOrUpdateProductionOrderAPI — заказы и техкарты. "
                             "Отвечает сразу, success=true", "onec"),
    ("POST", "/api/v1/production-orders"): (production_orders, "write", "То же, что /api/v1/1c: "
                                            "конверт 1С или просто productionOrders", "production"),
    ("POST", "/api/v1/cloth-map"): (cloth_map_post, "write", "Связать коды ткани с артикулами",
                                    "map"),
    ("POST", "/api/v1/tickets"): (ticket_post, "tickets", "Завести тикет или указать причину",
                                  "ticket"),
}

BODIES = {
    "onec": {"actionType": "CreateOrUpdateProductionOrderAPI", "wait": True, "waitTimeout": 60000,
             "data": {"productionOrders": [{
                 "uuid": "cb049ee0-b805-4ee6-88d7-2c4f48799600", "orderNumber": 1708,
                 "productCode": "220100 TerryCloth 390", "gsm": 390,
                 "sizeInfo": {"size": "220*100", "numberLines": 1}, "weight": 0.858,
                 "totalQuantity": 3120, "totalNumberRolls": 39, "secondsPerRow": 233,
                 "weftPerOneRow": 1459, "secondsPerPcs": 233,
                 "technologies": {"components": [
                     {"productCode": "16/1 Ring Иштихан Суровый Ворс 630 Лот №41",
                      "type": "Pile yarn", "quantity": 597.52, "measurement": "в граммах"},
                     {"productCode": "20/2 OE Навои Суровый Основа 550 Лот №107",
                      "type": "Ground yarn", "quantity": 187.27, "measurement": "в граммах"},
                     {"productCode": "14/1 OE Навои Суровый Уток 700 Лот №103",
                      "type": "Weft yarn", "quantity": 159.01, "measurement": "в граммах"}],
                     "workCenters": ["D-01", "D-02", "J-09", "J-10"]}}]}},
    "orders": {"orders": [{"order_no": "4512", "product_code": "70140 Hotel 450",
                           "qty_towels": 12000, "due_day": "2026-10-01",
                           "looms": ["D10", "D11"], "cloth_code": "70140HOTEL500",
                           "ppt": 1661, "panels": 2}]},
    "production": {"productionOrders": [{"productCode": "70140 Hotel 450", "orderNumber": 4512,
                                         "weftPerOneRow": 1661, "totalQuantity": 12000,
                                         "sizeInfo": {"size": "70*140", "numberLines": 2},
                                         "clothCode": "70140HOTEL500",
                                         "technologies": {"workCenters": ["D-10", "D-11"],
                                                          "components": []}}]},
    "map": {"map": [{"cloth_code": "3050X7360", "product_code": "3060  D152 320"}]},
    "ticket": {"loom": "D7", "category_id": "electrical", "comment": "вызвали электрика"},
}


def handle(method, path, q, body, key, user_can, who):
    """(код ответа, тело). user_can(право) — для вошедшего человека, иначе None."""
    # «success» в каждом ответе: 1С проверяет его, а не код HTTP.
    route = ROUTES.get((method, path))
    if not route:
        return 404, {"success": False, "error": "нет такого адреса", "docs": "/api/docs"}
    fn, scope = route[0], route[1]
    if key:
        if scope not in (key.get("scopes") or "").split():
            return 403, {"success": False, "error": "у ключа нет права «%s»" % scope}
        who = "api:" + key["name"]
    elif not (user_can and user_can(USER_PERM[scope])):
        return 401, {"success": False,
                     "error": "нужен ключ API: заголовок Authorization: Bearer <ключ>"}
    try:
        return 200, fn(q, body or {}, who)
    except (ValueError, KeyError, TypeError) as e:
        return 400, {"success": False, "error": str(e)}


def openapi():
    paths = {}
    for (method, path), (fn, scope, summary, extra) in ROUTES.items():
        op = {"summary": summary, "description": "Право ключа: %s (%s)" % (scope, SCOPES[scope]),
              "security": [{"key": []}], "responses": {"200": {"description": "ок"},
                                                      "400": {"description": "ошибка в запросе"},
                                                      "401": {"description": "нет ключа"},
                                                      "403": {"description": "у ключа нет права"}}}
        if method == "GET":
            op["parameters"] = extra
        else:
            op["requestBody"] = {"required": True, "content": {"application/json": {
                "schema": {"type": "object"}, "example": BODIES[extra]}}}
        paths.setdefault(path, {})[method.lower()] = op
    paths["/api/v1/health"] = {"get": {"summary": "Живо ли приложение и сборщик — без ключа",
                                       "responses": {"200": {"description": "ок"}}}}
    return {"openapi": "3.0.3",
            "info": {"title": "MES ткацкого цеха", "version": "1.0",
                     "description": "Данные станков Toyota (FACT), простои, тикеты, план."},
            "components": {"securitySchemes": {"key": {"type": "http", "scheme": "bearer"}}},
            "paths": paths}


def docs_html():
    """Описание для программиста 1С: адреса, права, пример запроса."""
    e = html.escape
    rows = []
    for (method, path), (fn, scope, summary, extra) in ROUTES.items():
        if method == "GET":
            params = ", ".join("<code>%s</code>" % e(p["name"]) for p in extra) or "—"
            example = "curl -H \"Authorization: Bearer $KEY\" http://server:8780%s" % path
        else:
            import json
            params = "<pre>%s</pre>" % e(json.dumps(BODIES[extra], ensure_ascii=False, indent=1))
            example = ("curl -X POST -H \"Authorization: Bearer $KEY\" -H \"Content-Type: "
                       "application/json\" -d @body.json http://server:8780%s" % path)
        rows.append("<tr><td><b>%s</b></td><td><code>%s</code></td><td>%s</td><td>%s</td>"
                    "<td>%s<br><small><code>%s</code></small></td></tr>"
                    % (method, e(path), e(scope), params, e(summary), e(example)))
    return ("""<meta charset="utf-8"><title>API цеха</title>
<style>
:root{--bg:#f4f3ef;--ink:#14130f;--muted:#6b6a64;--rule:#d6d5cc;--card:#fcfcfb}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--ink:#f2f2ee;--muted:#a3a29b;--rule:#34332f;--card:#1b1b19}}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "IBM Plex Sans","Segoe UI",system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:22px;margin:0 0 6px} p{max-width:80ch;color:var(--muted)}
.t{overflow-x:auto;border:1px solid var(--rule);background:var(--card)}
table{border-collapse:collapse;width:100%%;font-size:13px}
td,th{border-bottom:1px solid var(--rule);padding:8px 10px;text-align:left;vertical-align:top}
th{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
code,pre{font-family:"IBM Plex Mono",Consolas,monospace;font-size:12px}
pre{margin:0;white-space:pre-wrap}
</style>
<main>
<h1>API цеха, версия 1</h1>
<p>Ключ выдаёт администратор в «Настройках» приложения. Передавайте его в заголовке
<code>Authorization: Bearer &lt;ключ&gt;</code>. Даты — <code>2026.09.01</code> или
<code>2026-09-01</code>. Повторная отправка заказа с тем же номером и изделием обновляет
его. Машиночитаемое описание — <a href="/api/v1/openapi.json">/api/v1/openapi.json</a>.</p>
<div class="t"><table><thead><tr><th>Метод</th><th>Адрес</th><th>Право</th>
<th>Параметры / тело</th><th>Что делает</th></tr></thead><tbody>%s</tbody></table></div>
</main>""" % "".join(rows)).encode("utf-8")
