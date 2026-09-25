"""HTTP: маршруты, права, отдача страниц и толчки на мониторы.

Здесь только приём запроса, проверка прав и вызов нужного модуля — никаких
расчётов и никакого SQL. Расчёты живут в reports.py, metrics.py, payroll.py,
people.py, planning.py и tickets.py, доступ к базам — в storage.py.

Три вида адресов:

    /api/…        внутренние, для страниц приложения; вход по cookie;
    /api/v1/…     внешний API для 1С и других программ; вход по ключу (api.py);
    /api/stream   толчки на мониторы: соединение держится, данные приходят,
                  как только поменялись (Server-Sent Events).
"""
import argparse
import base64
import gzip
import hashlib
import http.cookies
import json
import os
import re
import time
from datetime import datetime

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import api
import auth
import cache
import collector
import changes
import dashboard
import doc_kinds
import documents
import hub
import integration
import livestate
import logs
import loomplan
import loomsetup
import metrics
import machinehistory
import notify
import people
import payroll
import planning
import reports
import storage
import tickets
import yarns

LOG = logs.get("web")
STARTED_AT = time.time()
MAX_BODY = 5 * 1024 * 1024      # больше пяти мегабайт от 1С не бывает — это ошибка
PING_SEC = 15                   # пустая строка в поток, чтобы соединение не рвали

HERE = os.path.dirname(os.path.abspath(__file__))

# Право, которое нужно, чтобы выполнить запрос, меняющий данные.
GUARD = {
    "/api/assignments": "assign",
    "/api/operators": "people",
    "/api/operators/delete": "people",
    "/api/operators/import_fact": "people",
    "/api/operators/import": "people",  # список людей из другой системы или Excel
    "/api/settings": "settings",
    "/api/export_excel": "export",
    "/api/loom_article": "setup_edit",  # заправка независимо от расстановки
    "/api/assign_one": "assign",        # оператор на один станок
    "/api/assign_copy": "assign",       # повторить расстановку прошлой смены
    "/api/assign_from_fact": "assign",  # взять расстановку из данных FACT
    "/api/plan/order": "plan_edit",     # заказы и сроки
    "/api/plan/assign": "plan_edit",
    "/api/plan/drop": "plan_edit",
    "/api/plan/close": "plan_edit",
    "/api/plan/import_1c": "plan_edit",
    "/api/plan/ppt": "setup_edit",      # пиков на изделие: из 1С или вручную
    "/api/plan/cloth_map": "setup_edit", # код ткани на станке = артикул 1С
    "/api/keys": "users",               # ключи внешнего API
    "/api/keys/revoke": "users",
    "/api/shift_doc": "assign",         # расстановка на смену
    "/api/shift_doc/confirm": "assign",
    "/api/shift_doc/fill": "assign",
    "/api/loom_setup": "setup_edit",    # заправка станка: GSM, вес, PPT, пряжа, лот
    "/api/loom_setup/bulk": "setup_edit",
    "/api/yarns": "setup_edit",
    "/api/yarns/update": "setup_edit",
    "/api/loom_plan/upload": "plan_edit",
    "/api/yarns/import": "setup_edit",
    "/api/loom_plan/cells": "plan_edit",
}

# Журнал изменений: чей раздел открывает изменения какой таблицы.
CHANGE_SECTIONS = {
    "assignment": "assign", "shift_master": "assign", "shift_doc": "assign",
    "loom_setup": "setup", "tech_card": "setup", "tech_card_yarn": "setup", "tech_card_loom": "setup",
    "yarn": "setup", "yarn_lot": "setup",
    "loom_plan": "plan", "cloth_map": "plan", "ppt_manual": "plan", "loom_article": "plan",
    "plan_order": "plan", "plan_loom": "plan",
    "ticket": "tickets", "operator": "people", "setting": "settings", "rate_period": "settings",
    "app_user": "users", "app_user_access": "users", "app_user_employee": "users", "api_key": "users",
}

# Статика и описание доступны до входа, производственные данные — после входа.
# Терминалу нужна собственная учётная запись с разрешённым разделом «Дашборд».
PUBLIC_GET = {"/api/me", "/api/health", "/api/docs"}
GET_SECTIONS = {
    "/api/live": ("dash", "tickets", "walk", "wall"),
    "/api/stream": ("dash", "tickets", "walk", "cards", "wall"),
    "/api/forecast": ("dash", "wall"),
    "/api/cards": ("dash", "setup", "cards"),
    "/api/setup_documents": ("setup",),
    "/api/yarn_analysis": ("setup", "report"),
    "/api/assignment_periods": ("assign",),
    "/api/production_events": ("assign", "setup", "tickets", "history"),
    "/api/machine_signals": ("history",),
    "/api/tickets": ("tickets", "dash", "history"),
    "/api/shifts": tuple(auth.SECTIONS),
    "/api/report_days": tuple(auth.SECTIONS),
    "/api/days": tuple(auth.SECTIONS),
    "/api/stop_days": tuple(auth.SECTIONS),
    "/api/report": ("report",),
    "/api/operators": ("people", "assign", "salary", "kpi", "walk"),
    "/api/assignments": ("assign", "salary", "walk"),
    "/api/shift_doc": ("assign",),
    "/api/shift_docs": ("assign",),
    "/api/setup_grid": ("setup",),
    "/api/yarns": ("setup", "dash", "settings"),
    "/api/salary": ("salary",),
    "/api/kpi": ("kpi",),
    "/api/settings": ("settings",),
    "/api/dashboard": ("dash",),
    "/api/plan": ("plan", "setup", "dash", "settings"),
    "/api/loom_plan/catalog": ("plan", "setup"),
    "/api/ppt_check": ("plan", "setup", "settings"),
    "/api/onec/messages": ("plan", "settings"),
    "/api/onec/message": ("plan", "settings"),
    "/api/loom_plan": ("plan",),
    "/api/gantt": ("plan",),
    "/api/loom_timeline": ("plan", "history"),
    "/api/machine_history": ("history",),
    "/api/bottlenecks": ("bottle",),
    "/api/manual_stops": ("manual",),
    "/api/production": ("report", "plan", "dash"),
    "/api/explorer": ("explorer",),
    "/api/walk": ("walk",),
    "/api/excel": ("report",),
    "/api/users": ("users",),
    "/api/access_catalog": ("users",),
    "/api/keys": ("users", "settings"),
    "/api/logs": ("settings",),
    # Документы: список фильтруется по разделам вида (зарплата — только в «Зарплате»).
    "/api/documents": tuple(auth.SECTIONS),
    "/api/documents/get": tuple(auth.SECTIONS),
    "/api/documents/verify": tuple(auth.SECTIONS),
    "/api/rates": ("salary", "settings"),
    "/api/reasons": ("settings", "tickets"),
    "/api/change_log": tuple(auth.SECTIONS),
    "/api/report_period": ("report",),
}
GET_ACTIONS = {"/api/users": "users", "/api/access_catalog": "users", "/api/keys": "users",
               "/api/logs": "settings", "/api/excel": "export"}
# Для входа по cookie внешний API не должен обходить права внутренних страниц.
V1_READ_ALIAS = {
    "/api/v1/looms": "/api/live", "/api/v1/forecast": "/api/forecast",
    "/api/v1/production": "/api/production", "/api/v1/downtime": "/api/bottlenecks",
    "/api/v1/manual-stops": "/api/manual_stops", "/api/v1/tickets": "/api/tickets",
    "/api/v1/orders": "/api/plan", "/api/v1/cloth-map": "/api/plan",
    "/api/v1/loom-plan": "/api/loom_plan", "/api/v1/1c": "/api/onec/messages",
}
V1_WRITE_ACTION = {
    "/api/v1/orders": "plan_edit", "/api/v1/1c": "plan_edit",
    "/api/v1/production-orders": "plan_edit", "/api/v1/cloth-map": "setup_edit",
    "/api/v1/tickets": "tickets",
}


def may_read(user, path):
    sections = GET_SECTIONS.get(path, ())
    return auth.can_section(user, *sections) and (path not in GET_ACTIONS or may(user, GET_ACTIONS[path]))


def current_token(handler):
    """Токен из cookie, либо None; некорректная cookie не даёт сессию."""
    raw = handler.headers.get("Cookie")
    if not raw:
        return None
    try:
        jar = http.cookies.SimpleCookie(raw)
    except http.cookies.CookieError:
        return None
    return jar["sid"].value if "sid" in jar else None


def current_user(handler):
    """Пользователь текущей сессии по cookie, либо None."""
    user = auth.user_by_token(current_token(handler)) if auth else None
    import productionlog
    productionlog.ACTOR.set(user['login'] if user else 'неавторизован')
    return user


def may(user, permission):
    """Проверяет право пользователя; модуль авторизации обязателен для запуска."""
    return auth.can(user, permission)


_page_cache = {}
_INLINE_SCRIPT = re.compile(rb"<script>(.*?)</script>", re.S)


def page_csp(data):
    """Политика безопасности страницы: выполняются только наши встроенные скрипты
    (по хешу) и файлы с нашего адреса. Разметка, попавшая в страницу из данных
    (<img onerror>, <svg onload>, <script>), не выполнится, даже если где-то
    забыли экранировать вывод."""
    hashes = " ".join("'sha256-%s'" % base64.b64encode(hashlib.sha256(m).digest()).decode()
                      for m in _INLINE_SCRIPT.findall(data))
    return ("default-src 'self'; script-src 'self' %s; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; img-src 'self' data: blob:; "
            "connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'self'" % hashes)


def page_bytes(name):
    """Страница из памяти; перечитывается только если файл изменился."""
    path = os.path.join(HERE, name)
    mtime = os.path.getmtime(path)
    c = _page_cache.get(name)
    if not c or c["mtime"] != mtime:
        data = open(path, "rb").read()
        c = {"mtime": mtime, "data": data, "csp": page_csp(data),
             "etag": '"%s"' % hashlib.sha1(data).hexdigest()[:20]}
        _page_cache[name] = c
    return c["data"]


class Handler(BaseHTTPRequestHandler):
    # Keep-alive: монитор в цехе держит одно соединение вместо нового на каждый
    # запрос. Content-Length мы ставим всегда, так что это безопасно.
    protocol_version = "HTTP/1.1"
    # Таймаут сокета: клиент, который не присылает запрос или не читает ответ
    # минуту, отпускает поток сервера (раньше держал бесконечно). Поток толчков
    # мониторов пишет пинг каждые PING_SEC секунд и под таймаут не попадает.
    timeout = 60

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        # Сжатие: страница и ответы по сети цеха идут в разы легче, а на десяти
        # одновременных пользователях это заметно снимает нагрузку.
        encoding = None
        if len(data) > 1024 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            data = gzip.compress(data, 6)
            encoding = "gzip"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if encoding:
            self.send_header("Content-Encoding", encoding)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _not_modified(self, etag):
        """Браузер уже держит эту версию файла — «304», без тела (93 КБ страницы
        не качаются на каждом открытии)."""
        if etag and etag in (self.headers.get("If-None-Match") or ""):
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        return False

    def _send_page(self, name):
        """HTML-страница приложения с политикой безопасности."""
        data = page_bytes(name)
        c = _page_cache[name]
        if self._not_modified(c["etag"]):
            return
        self._send(200, data, "text/html; charset=utf-8", {
            "Content-Security-Policy": c["csp"], "ETag": c["etag"], "Cache-Control": "no-cache",
            "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": "same-origin"})

    STATIC_TYPES = {".woff2": "font/woff2", ".css": "text/css; charset=utf-8",
                    ".txt": "text/plain; charset=utf-8", ".js": "text/javascript; charset=utf-8"}

    def _send_static(self, name, max_age=0):
        """Файл из _app (шрифты, скрипт перевода) с ETag."""
        data = page_bytes(name)
        c = _page_cache[name]
        if self._not_modified(c["etag"]):
            return
        ctype = self.STATIC_TYPES.get(os.path.splitext(name)[1], "application/octet-stream")
        self._send(200, data, ctype, {"ETag": c["etag"],
                   "Cache-Control": "public, max-age=%d" % max_age if max_age else "no-cache"})

    def log_message(self, *a):
        pass

    def _read_body(self, limit=MAX_BODY):
        # При отказе непрочитанное тело нельзя принять за следующий запрос
        # HTTP/1.1. Отрицательная длина заставляла read(-1) ждать закрытия сокета.
        was_closed = self.close_connection
        self.close_connection = True
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") is not None:
            raise ValueError("Transfer-Encoding не поддерживается; укажите Content-Length")
        raw = lengths[0].strip() if lengths else "0"
        if len(lengths) > 1 or not raw.isascii() or not raw.isdigit():
            raise ValueError("некорректный Content-Length")
        n = int(raw)
        if n > limit:
            raise OverflowError("тело запроса больше %d МБ" % (limit // 1024 // 1024))
        data = self.rfile.read(n)
        if len(data) != n:
            raise ValueError("тело запроса получено не полностью")
        self.close_connection = was_closed
        return data

    def _body(self):
        return json.loads(self._read_body() or b"{}")

    # --- толчки на мониторы ---

    def _stream(self):
        """Server-Sent Events: монитор держит соединение, мы пишем в него доску,
        как только она поменялась, а в тишине — пустую строку раз в 15 секунд."""
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        hub.HUB.join()
        seen = None
        try:
            self.wfile.write(b"retry: 3000\n\n")
            while True:
                ver = hub.HUB.version if seen is None else hub.HUB.wait(seen, PING_SEC)
                # Уже открытый поток тоже прекращается после отзыва доступа.
                key = api.check(self.headers)
                if not ((key and "read" in (key.get("scopes") or "").split())
                        or may_read(current_user(self), "/api/stream")):
                    break
                if ver != seen:
                    data = LIVE_EVENT.get(ver)
                    self.wfile.write(b"id: %d\nevent: board\ndata: " % ver + data + b"\n\n")
                    seen = ver
                else:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass            # монитор выключили или перезагрузили — это нормально
        finally:
            hub.HUB.leave()

    # --- внешний API ---

    def _api(self, method, path, q, body):
        if path == "/api/v1/health":
            return self._send(200, health())
        if path == "/api/v1/openapi.json":
            return self._send(200, api.openapi())
        key = api.check(self.headers)
        user = None if key else current_user(self)
        route = api.ROUTES.get((method, path))
        if user and not key and route:
            allowed = (may_read(user, V1_READ_ALIAS.get(path, "")) if method == "GET"
                       else may(user, V1_WRITE_ACTION.get(path, "")))
            if not allowed:
                return self._send(403, {"success": False, "error": "нет доступа к этому разделу или действию"})
        # Проверка выше учитывает конкретный адрес, а не общее право read/write.
        can = (lambda p: True) if user and route else None
        code, obj = api.handle(method, path, q, body, key, can, user["login"] if user else "")
        # Каждая попытка записи — в журнал, и отказ тоже: «отправили, а ничего не
        # пришло» иначе не разобрать (ключ не подошёл, не тот адрес, пустой список).
        if method == "POST":
            nums = ""
            try:
                nums = " ".join(sorted({str(o.get("orderNumber")) for o in integration.orders_of(body or {})
                                        if isinstance(o, dict) and o.get("orderNumber")}))
            except Exception:
                pass
            LOG.info("API %s %s от %s: %s%s%s%s", method, path, self.client_address[0], code,
                     " (ключ %s)" % key["name"] if key else (" (вход)" if user else " (без ключа или ключ не подошёл)"),
                     " заказы %s" % nums if nums else " заказов в теле нет",
                     "" if code == 200 else " — " + str(obj.get("error", "")))
        return self._send(code, obj)

    # --- чтение ---

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._send_page("ui.html")
            if u.path == "/ui_i18n.js":
                return self._send_static("ui_i18n.js")
            if u.path.startswith("/fonts/"):
                # Шрифты — с нашего сервера: без интернета цеховой ПК ждал Google.
                name = u.path[len("/fonts/"):]
                if (not re.fullmatch(r"[a-z0-9-]+\.(woff2|css|txt)", name)
                        or not os.path.isfile(os.path.join(HERE, "fonts", name))):
                    return self._send(404, {"error": "нет такого файла"})
                return self._send_static("fonts/" + name, max_age=7 * 86400)
            if u.path.startswith("/api/v1/"):
                return self._api("GET", u.path, q, None)
            if u.path.startswith("/api/") and u.path not in PUBLIC_GET:
                key = api.check(self.headers)
                user = current_user(self)
                key_read = bool(key and "read" in (key.get("scopes") or "").split())
                if not user and not key_read:
                    return self._send(401, {"error": "нужно войти"})
                # Ключ read сохраняет доступ интеграций; управление доступом,
                # ключами и журналом никогда не было доступно простому ключу.
                if not (key_read and u.path not in ("/api/users", "/api/access_catalog", "/api/keys", "/api/logs")):
                    if not may_read(user, u.path):
                        return self._send(403, {"error": "нет доступа к этому разделу"})
            if u.path == "/api/stream":
                return self._stream()
            if u.path == "/api/me":
                user = current_user(self)
                perms = sorted(p for p in (auth.PERMISSIONS if auth else {}) if may(user, p))
                return self._send(200, {"user": user, "permissions": perms,
                                        "roles": auth.ROLES, "sections": user["sections"] if user else [],
                                        "access_catalog": auth.access_catalog() if user else None})
            if u.path == "/api/access_catalog":
                return self._send(200, auth.access_catalog())
            if u.path == "/api/users":
                if not may(current_user(self), "users"):
                    return self._send(403, {"error": "нет прав"})
                return self._send(200, {"users": auth.list_users(), "access_catalog": auth.access_catalog()})
            if u.path == "/wall":
                user = current_user(self)
                if not user:
                    return self._send_page("ui.html")
                if not may_read(user, "/api/live"):
                    return self._send(403, {"error": "нет доступа к доске цеха"})
                return self._send_page("wall.html")
            if u.path == "/api/live":
                return self._send(200, live_payload(q))
            if u.path == "/api/forecast":
                return self._send(200, dashboard.forecast(int(q.get("hours", 12)) * 60))
            if u.path == "/api/tickets":
                return self._send(200, {
                    "tickets": tickets.ticket_list(limit=min(int(q.get("limit", 80)), 5000),
                                                   only_open=q.get("open") == "1",
                                                   day=q.get("day"),
                                                   shift_from=q.get("from"), shift_to=q.get("to")),
                    "categories": tickets.categories("operator"),
                    "summary": tickets.summary(int(q.get("hours", 24))),
                    "can_edit": may(current_user(self), "tickets")})
            if u.path == "/api/shifts":
                return self._send(200, {"shifts": [{"day": d, "shift": s}
                                                   for d, s in reports.available_shifts()]})
            if u.path == "/api/report":
                return self._send(200, {"day": q.get("day"),
                                        "rows": reports.report_day(q.get("day", ""))})
            if u.path == "/api/report_period":
                return self._send(200, reports.report_period(q.get("from", ""), q.get("to", "")))
            if u.path == "/api/report_days":
                return self._send(200, {"days": reports.report_days()})
            if u.path == "/api/days":
                return self._send(200, {"days": reports.all_days()})
            if u.path == "/api/operators":
                return self._send(200, {"operators": people.list_operators()})
            if u.path == "/api/assignments":
                return self._send(200, people.get_assignments(q.get("day"), q.get("shift")))
            if u.path == "/api/shift_doc":
                return self._send(200, people.get_shift_doc(q.get("day", ""), q.get("shift", "A")))
            if u.path == "/api/setup_grid":
                return self._send(200, loomsetup.grid(q.get("day") or tickets.current_shift()[:10]))
            if u.path == "/api/yarns":
                return self._send(200, {"yarns": yarns.all_yarns(), "by_slot": yarns.by_slot()})
            if u.path == "/api/shift_docs":
                return self._send(200, {"docs": people.list_shift_docs(q.get("from", ""),
                                                                      q.get("to", "9999"))})
            if u.path == "/api/salary":
                return self._send(200, payroll.salary_for_shift(q.get("day", ""),
                                                                q.get("shift", "")))
            if u.path == "/api/kpi":
                return self._send(200, payroll.kpi(q.get("from", ""), q.get("to", "9999"),
                                                   q.get("role", "operator")))
            if u.path == "/api/settings":
                return self._send(200, storage.all_settings())
            if u.path == "/api/dashboard":
                # День не задан — текущий (раньше пустой день ронял ответ в 500).
                return self._send(200, dashboard.rows(q.get("day") or tickets.current_shift()[:10],
                                                      q.get("shift", "")))
            if u.path == "/cards":
                user = current_user(self)
                if not user:
                    return self._send_page("ui.html")
                if not may_read(user, "/api/cards"):
                    return self._send(403, {"error": "нет доступа к техкартам"})
                return self._send_page("cards.html")
            if u.path == "/api/cards":
                return self._send(200, dashboard.cards(q.get("day") or "",
                                                       q.get("shift", "")))
            if u.path == '/api/setup_documents':
                return self._send(200, {'documents':loomsetup.documents(q.get('loom',''),before=q.get('before'))})
            if u.path == '/api/yarn_analysis':
                return self._send(200, loomsetup.yarn_analysis(q.get('from',''),q.get('to','')))
            if u.path == '/api/assignment_periods':
                import productionlog
                return self._send(200, productionlog.assignment_periods(q.get('day',''),q.get('shift',''),q.get('loom','')))
            if u.path == '/api/production_events':
                import productionlog
                entity=q.get('entity','assignment')
                sections={'assignment':'assign','shift_master':'assign','shift_doc':'assign',
                          'loom_setup':'setup','tech_card':'setup','tech_card_yarn':'setup',
                          'ticket':'tickets','operator':'people','loom_plan':'plan'}
                if not auth.can_section(current_user(self),sections.get(entity,'users')):
                    return self._send(403, {'error':'нет доступа к журналу'})
                return self._send(200, {'events':productionlog.events(entity,q.get('loom',''),record_id=q.get('id'))})
            if u.path == "/api/change_log":
                import productionlog
                user = current_user(self)
                wanted = [e for e in (q.get("entity") or ",".join(CHANGE_SECTIONS)).split(",")
                          if e in CHANGE_SECTIONS and auth.can_section(user, CHANGE_SECTIONS[e])]
                return self._send(200, {
                    "operations": productionlog.change_log(wanted, q.get("from", ""), q.get("to", ""),
                                                           q.get("actor", ""), q.get("q", ""), int(q.get("limit", 300))),
                    "entities": [{"id": e, "title": changes.ENTITY[e]} for e in CHANGE_SECTIONS
                                 if auth.can_section(user, CHANGE_SECTIONS[e])]})
            if u.path == "/api/documents":
                user = current_user(self)
                documents.kind("setup")             # виды регистрируются при первом обращении
                wanted = [t for t in (q.get("type") or ",".join(documents.KINDS)).split(",")
                          if t in documents.KINDS and auth.can_section(user, documents.KINDS[t].section)]
                return self._send(200, {
                    "documents": documents.list_docs(wanted, q.get("from", ""), q.get("to", ""),
                                                     q.get("status", ""), int(q.get("limit", 200))),
                    "kinds": [{"id": k.name, "title": k.title,
                               "can_post": may(user, k.permission)} for k in documents.KINDS.values()
                              if auth.can_section(user, k.section)]})
            if u.path in ("/api/documents/get", "/api/documents/verify"):
                d = documents.get(q.get("id", "0"))
                if not auth.can_section(current_user(self), documents.kind(d["type"]).section):
                    return self._send(403, {"error": "нет доступа к документу"})
                if u.path.endswith("verify"):
                    d = documents.verify(d["id"])
                return self._send(200, d)
            if u.path == "/api/reasons":
                return self._send(200, {"reasons": tickets.categories(),
                                        "categories": doc_kinds.REASON_CATEGORY,
                                        "applies": doc_kinds.REASON_APPLIES})
            if u.path == "/api/rates":
                db = storage.shop()
                try:
                    rows = [dict(r) for r in db.execute(
                        "SELECT r.*, d.number, d.status FROM rate_period r LEFT JOIN doc d ON d.id=r.doc_id"
                        " ORDER BY r.valid_from DESC, r.id DESC")]
                    today = tickets.current_shift()[:10]
                    rate, unit = storage.rate_for(db, q.get("day") or today)
                finally:
                    db.close()
                return self._send(200, {"day": q.get("day") or today, "rate": rate, "unit": unit,
                                        "periods": rows})
            if u.path == '/api/machine_signals':
                import productionlog
                return self._send(200, productionlog.signal_history(q.get('loom',''),q.get('day',''),q.get('period','day')))
            if u.path == "/api/plan":
                return self._send(200, {"orders": planning.orders(q.get("closed") == "1"),
                                        "plan_only": planning.plan_only_orders(),
                                        "products": planning.products(),
                                        "cloth_map": planning.cloth_map_list(),
                                        "unmapped": planning.unmapped_cloths()})
            if u.path == "/api/loom_plan/catalog":
                return self._send(200, {"orders": loomplan.catalog()})
            if u.path == "/api/ppt_check":
                import pptcheck
                frm, to = pptcheck.default_period()
                return self._send(200, pptcheck.check(q.get("from") or frm, q.get("to") or to))
            if u.path == "/api/onec/messages":
                return self._send(200, {"messages": integration.messages(int(q.get("limit", 100)))})
            if u.path == "/api/onec/message":
                return self._send(200, integration.message(int(q.get("id", 0))))
            if u.path == "/api/loom_plan":
                return self._send(200, loomplan.grid(q.get("from") or tickets.current_shift()[:10],
                                                     q.get("to") or q.get("from") or "9999"))
            if u.path == "/api/machine_history":
                try:
                    result = machinehistory.timeline(q.get("day", ""), q.get("period", "day"),
                                                     q.get("looms", ""))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                return self._send(200, result)
            if u.path in ("/api/gantt", "/api/loom_timeline"):
                # Ганта плана и факта по станкам и остановы станка по секундам
                try:
                    if u.path == "/api/gantt":
                        return self._send(200, loomplan.gantt(q.get("from") or tickets.current_shift()[:10],
                                                              q.get("to", "")))
                    return self._send(200, loomplan.loom_timeline(q.get("loom", ""), q.get("from", ""),
                                                                  q.get("to", "")))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
            if u.path == "/api/bottlenecks":
                return self._send(200, metrics.bottlenecks(
                    q.get("from", "0000"), q.get("to", "9999"),
                    [l for l in (q.get("looms") or "").split(",") if l] or None,
                    [c for c in (q.get("shifts") or "") if c in "ABC"] or None))
            if u.path == "/api/manual_stops":
                return self._send(200, reports.lds_manual(q.get("from", "0000"),
                                                          q.get("to", "9999"),
                                                          q.get("group", "day")))
            if u.path == "/api/production":
                return self._send(200, {"rows": metrics.production(q.get("from", "0000"),
                                                                   q.get("to", "9999"))})
            if u.path == "/api/stop_days":
                return self._send(200, {"days": metrics.available_days()})
            if u.path == "/api/explorer":
                return self._send(200, reports.explorer(q))
            if u.path == "/api/walk":
                return self._send(200, reports.walk(q.get("day", ""), q.get("shift", "")))
            if u.path == "/api/excel":
                return self._send_excel(q.get("day", ""))
            if u.path == "/api/health":
                return self._send(200, health())
            if u.path == "/api/docs":
                docs = api.docs_html()
                docs = docs if isinstance(docs, bytes) else docs.encode()
                return self._send(200, docs, "text/html; charset=utf-8",
                                  {"Content-Security-Policy": page_csp(docs)})
            if u.path == "/api/keys":
                if not may(current_user(self), "users"):
                    return self._send(403, {"error": "нет прав"})
                return self._send(200, {"keys": api.list_keys(), "scopes": api.SCOPES})
            if u.path == "/api/logs":
                if not may(current_user(self), "settings"):
                    return self._send(403, {"error": "нет прав"})
                return self._send(200, {"lines": logs.tail(int(q.get("lines", 200)))})
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            return          # браузер ушёл, не дождавшись ответа, — отвечать некому
        except ValueError as e:
            # Неверный запрос (нет дня, неверная смена) — не сбой сервера.
            LOG.warning("GET %s: %s", u.path, e)
            return self._send(400, {"error": str(e)})
        except Exception as e:
            LOG.exception("GET %s: %s", self.path, e)
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        self._send(404, {"error": "нет такого адреса"})

    def _send_excel(self, day):
        path = reports.excel_path(day)
        if not os.path.exists(path):
            return self._send(404, {"error": "файл ещё не собран"})
        data = open(path, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type",
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition",
                         f'attachment; filename="ProductionReport_{day.replace(".", "-")}.xlsx"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # --- запись ---

    def _plan_upload(self):
        """Файл плана цеха (.xlsx) приходит телом запроса как есть, без формы."""
        me = current_user(self)
        if not may(me, GUARD["/api/loom_plan/upload"]):
            self.close_connection = True
            return self._send(403, {"error": "нет прав на это действие"})
        try:
            r = loomplan.import_xlsx(self._read_body(4 * MAX_BODY), me["login"] if me else "")
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        LOG.info("план цеха %s–%s: станков %s, клеток %s (%s)", r["from"], r["to"], r["looms"],
                 r["cells"], me["login"] if me else "")
        return self._send(200, r)

    def _yarn_import(self):
        """Справочник пряжи из 1С: табличный документ (.mxl) телом запроса как есть."""
        me = current_user(self)
        if not may(me, GUARD["/api/yarns/import"]):
            self.close_connection = True
            return self._send(403, {"error": "нет прав на это действие"})
        try:
            import yarnref
            r = yarnref.import_mxl(self._read_body(4 * MAX_BODY), me["login"] if me else "")
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        LOG.info("справочник пряжи из 1С: %d позиций (новых %d), пряжи добавлено %d",
                 r["items"], r["new"], len(r["yarns_added"]))
        return self._send(200, r)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/loom_plan/upload":
                return self._plan_upload()
            if u.path == "/api/yarns/import":
                return self._yarn_import()
            body = self._body()
            if u.path.startswith("/api/v1/"):
                return self._api("POST", u.path, {k: v[0] for k, v in parse_qs(u.query).items()},
                                 body)
            # Запросы браузера — только JSON с явным типом: форма с чужого сайта
            # (text/plain, form-urlencoded) сюда не пройдёт, даже если браузер
            # когда-нибудь пошлёт с ней cookie. Раньше тело разбиралось как JSON
            # при любом Content-Type, защита держалась на одном SameSite=Lax.
            if not isinstance(body, dict):
                raise ValueError("ожидается JSON-объект")
            # Ключ API (программы) подделать с чужого сайта нельзя — только cookie.
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            by_key = self.headers.get("X-Api-Key") or (self.headers.get("Authorization") or "").startswith("Bearer ")
            if ctype != "application/json" and not by_key:
                return self._send(415, {"error": "ожидается Content-Type: application/json"})
            if u.path == "/api/login":
                return self._login(body)
            if u.path == "/api/logout":
                return self._logout()
            if u.path == "/api/password":
                me = current_user(self)
                if not me:
                    return self._send(401, {"error": "нужно войти"})
                try:
                    target = int(body.get("user_id") or me["id"])
                except (TypeError, ValueError):
                    raise ValueError("user_id: нужен номер пользователя")
                if target != me["id"] and not may(me, "users"):
                    return self._send(403, {"error": "нет прав"})
                # Администратор, задавая пароль другому, решает, просить ли сменить его при входе.
                auth.set_password(target, body.get("password", ""),
                                  must_change=bool(body.get("must_change")) and target != me["id"],
                                  keep_token=current_token(self) if target == me["id"] else None)
                return self._send(200, {"ok": True})
            if u.path == "/api/users":
                me = current_user(self)
                if not may(me, "users"):
                    return self._send(403, {"error": "нет прав"})
                access_args = {"access": body["access"]} if "access" in body else {}
                if "employee_id" in body:
                    access_args["employee_id"] = body["employee_id"]
                if body.get("id"):
                    auth.update_user(body["id"], body.get("name"), body.get("role"),
                                     body.get("active"), actor_id=me["id"], **access_args)
                else:
                    auth.create_user(body.get("login"), body.get("name"),
                                     body.get("role", "viewer"), body.get("password", ""),
                                     must_change=bool(body.get("must_change")), **access_args)
                return self._send(200, {"ok": True})
            if u.path.startswith("/api/tickets/"):
                return self._tickets(u.path, body)
            if u.path.startswith("/api/documents/"):
                return self._documents(u.path, body)

            # Всё, что меняет данные, требует права.
            need = GUARD.get(u.path)
            me = current_user(self)
            if need and not may(me, need):
                return self._send(403, {"error": "нет прав на это действие"})
            who = me["login"] if me else ""

            if u.path == "/api/operators":
                people.save_operator(body)
                return self._send(200, {"ok": True})
            if u.path == "/api/operators/delete":
                people.delete_operator(body["id"])
                return self._send(200, {"ok": True})
            if u.path == "/api/operators/import_fact":
                return self._send(200, people.import_operators_from_fact())
            if u.path == "/api/operators/import":
                r = people.import_people(body.get("text", ""))
                LOG.info("список людей загрузил %s: добавлено %s, обновлено %s",
                         who, r["added"], r["updated"])
                return self._send(200, r)
            if u.path == "/api/export_excel":
                return self._send(200, reports.export_excel(body.get("day", "")))
            if u.path == "/api/assignments":
                people.save_assignments(body)
                return self._send(200, {"ok": True})
            if u.path == "/api/assign_one":
                people.assign_one(body["day"], body["shift"], body["loom"],
                                  body.get("operator_id"))
                return self._send(200, {"ok": True})
            if u.path == "/api/assign_copy":
                return self._send(200, people.copy_assignments(body["day"], body["shift"]))
            if u.path == "/api/shift_doc":
                d = people.save_shift_doc(body["day"], body["shift"], body, who)
                LOG.info("расстановка смены %s за %s сохранена (%s)", body["shift"], body["day"], who)
                return self._send(200, d)
            if u.path == "/api/shift_doc/confirm":
                d = people.confirm_shift_doc(body["day"], body["shift"], who,
                                             bool(body.get("confirmed", True)))
                LOG.info("расстановка смены %s за %s: %s (%s)", body["shift"], body["day"],
                         d["doc"]["status"], who)
                return self._send(200, d)
            if u.path == "/api/shift_doc/fill":
                return self._send(200, people.fill_shift_doc(body["day"], body["shift"],
                                                             body.get("how", "prev"), who))
            if u.path == "/api/loom_setup":
                r = loomsetup.save(body.get("looms") or [], body.get("from_day", ""),
                                   body.get("values") or {}, who, body.get('effective_at'))
                LOG.info("заправка %s с %s ввёл %s", ", ".join(r["looms"]), r["from_day"], who)
                return self._send(200, r)
            if u.path == "/api/loom_setup/bulk":
                r = loomsetup.save_many(body.get("rows") or [], body.get("from_day", ""), who, body.get('effective_at'))
                LOG.info("заправка таблицей: %d станков с %s ввёл %s", len(r["looms"]),
                         r["from_day"], who)
                return self._send(200, r)
            if u.path == "/api/yarns":
                r = yarns.add(body.get("name", ""), body.get("kind", ""))
                LOG.info("пряжа «%s» в справочник (%s)", r["name"], who)
                return self._send(200, r)
            if u.path == "/api/yarns/update":
                return self._send(200, yarns.update(int(body["id"]), body.get("name"),
                                                    body.get("kind"), body.get("active")))
            if u.path == "/api/assign_from_fact":
                r = people.import_assignments_from_fact(
                    body["day"], body.get("shifts") or ("A", "B", "C"),
                    bool(body.get("overwrite")))
                LOG.info("расстановка из FACT за %s: станков %s, записей %s",
                         body.get("day"), r.get("found"), r.get("assigned"))
                return self._send(200, r)
            if u.path == "/api/keys":
                k = api.create_key(body.get("name", ""), body.get("scopes") or [], who)
                LOG.info("ключ API «%s» (%s) выдал %s", k["name"], " ".join(k["scopes"]), who)
                return self._send(200, k)
            if u.path == "/api/keys/revoke":
                api.revoke_key(int(body["id"]))
                LOG.info("ключ API №%s отозвал %s", body.get("id"), who)
                return self._send(200, {"ok": True})
            if u.path == "/api/loom_plan/cells":
                r = loomplan.set_cells(body.get("changes") or [], who)
                LOG.info("план цеха: клеток %d изменил %s", r["ok"], who)
                return self._send(200, r)
            if u.path.startswith("/api/plan/"):
                if u.path == "/api/plan/order":
                    oid = planning.add_order(body["order_no"], body["product_code"],
                                             body["qty_towels"], body.get("due_day"),
                                             body.get("source", "вручную"), body.get("note", ""))
                    LOG.info("заказ %s (%s) на %s полотенец добавил %s",
                             body.get("order_no"), body.get("product_code"),
                             body.get("qty_towels"), who)
                    return self._send(200, {"ok": True, "id": oid})
                if u.path == "/api/plan/assign":
                    planning.assign_loom(body["order_id"], body["loom"],
                                         body.get("from_day"), body.get("qty_towels"))
                    return self._send(200, {"ok": True})
                if u.path == "/api/plan/drop":
                    planning.drop_loom(body["order_id"], body["loom"])
                    return self._send(200, {"ok": True})
                if u.path == "/api/plan/close":
                    planning.close_order(body["order_id"], bool(body.get("closed", True)))
                    return self._send(200, {"ok": True})
                if u.path == "/api/plan/import_1c":
                    r = planning.import_from_1c()
                    LOG.info("заказы из 1С: %s", r)
                    return self._send(200, r)
                if u.path == "/api/plan/ppt":
                    planning.set_ppt(body["key"], body["ppt"], body.get("panels"),
                                     body.get("source", "вручную"), who)
                    return self._send(200, {"ok": True})
                if u.path == "/api/plan/cloth_map":
                    planning.set_cloth_map(body.get("cloth_code", ""),
                                           body.get("product_code", ""), who)
                    LOG.info("код ткани «%s» = артикул «%s» (%s)", body.get("cloth_code"),
                             body.get("product_code") or "—", who)
                    return self._send(200, {"ok": True})
                return self._send(404, {"error": "нет такого адреса"})
            if u.path == "/api/loom_article":
                if body.get("product_code"):
                    dashboard.set_article(body["loom"], body["product_code"],
                                          body.get("day"), who, body.get("note", ""))
                else:
                    dashboard.clear_article(body["loom"], body.get("day"))
                LOG.info("станок %s: заправлено «%s» (поставил %s)",
                         body.get("loom"), body.get("product_code") or "—", who)
                return self._send(200, {"ok": True})
            if u.path == "/api/settings":
                storage.save_settings(body, who)
                LOG.info("настройки изменены: %s", body)
                tickets.invalidate()        # пороги андона видны на досках сразу
                return self._send(200, {"ok": True})
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            return
        except OverflowError as e:
            return self._send(413, {"error": str(e)})
        except (ValueError, KeyError) as e:
            # Ошибка в том, что прислали: пустое поле, неверная дата. Это не
            # сбой сервера — отвечаем понятно и не пишем трассировку в журнал.
            LOG.warning("POST %s: %s", u.path, e)
            return self._send(400, {"error": str(e) if isinstance(e, ValueError)
                                    else "не хватает поля %s" % e})
        except Exception as e:
            LOG.exception("POST %s: %s", self.path, e)
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        self._send(404, {"error": "нет такого адреса"})

    def _documents(self, path, body):
        """Проверка, проведение и отмена документа. Право — по виду документа."""
        me = current_user(self)
        if not me:
            return self._send(401, {"error": "нужно войти"})
        action = path.rsplit("/", 1)[-1]
        if action == "cancel":
            d = documents.get(body.get("id", 0))
            name = d["type"]
        else:
            name = body.get("type", "")
        k = documents.kind(name)
        if action == "preview":
            # Проверка ничего не пишет: её видит всякий, кому открыт раздел, — ведомость
            # за период для мастерицы, отчёт за период для наблюдателя.
            if not (may(me, k.permission) or auth.can_section(me, k.section)):
                return self._send(403, {"error": "нет доступа к документу «%s»" % k.title})
            checked = documents.preview(name, body.get("payload") or {})
            checked["may_post"] = may(me, k.permission)
            return self._send(200, checked)
        if not may(me, k.permission):
            return self._send(403, {"error": "нет прав на документ «%s»" % k.title})
        if action == "post":
            payload = body.get("payload") or {}
            try:
                r = documents.post(name, payload, body.get("checksum"), me["login"],
                                   body.get("comment", ""), payload.get("supersedes_id"))
            except documents.Stale as e:
                # Человек подтверждал другие данные: показать новую проверку.
                return self._send(409, {"error": "Данные изменились после проверки (%s). Проверьте документ ещё раз." % e,
                                        "preview": documents.preview(name, payload)})
            LOG.info("документ %s «%s» провёл %s", r["number"], k.title, me["login"])
            return self._send(200, r)
        if action == "cancel":
            r = documents.cancel(d["id"], body.get("reason", ""), me["login"])
            LOG.info("документ %s отменил %s: %s", d["number"], me["login"], body.get("reason", ""))
            return self._send(200, r)
        return self._send(404, {"error": "нет такого действия"})

    def _login(self, body):
        name = (body.get("login") or "").strip().lower()
        ip = self.client_address[0]
        wait = auth.locked_for(name, ip) if auth else 0
        if wait:
            LOG.warning("вход закрыт на %d с: логин «%s», адрес %s", wait, name, ip)
            return self._send(429, {"error": "слишком много неудачных попыток, "
                                             "подождите %d секунд" % wait})
        token = auth.login(body.get("login"), body.get("password"), ip) if auth else None
        if not token:
            LOG.warning("неудачный вход: логин «%s», адрес %s", name, ip)
            return self._send(401, {"error": "неверный логин или пароль"})
        LOG.info("вход: «%s» с адреса %s", name, ip)
        user = auth.user_by_token(token)
        data = json.dumps({"ok": True, "user": user}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie",
                         f"sid={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _logout(self):
        raw = self.headers.get("Cookie")
        if auth and raw and "sid=" in raw:
            jar = http.cookies.SimpleCookie(raw)
            if "sid" in jar:
                auth.logout(jar["sid"].value)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", "sid=; Path=/; Max-Age=0")
        self.send_header("Content-Length", "15")
        self.end_headers()
        self.wfile.write(b'{"ok": true}   ')

    def _tickets(self, path, body):
        me = current_user(self)
        if not may(me, "tickets"):
            return self._send(403, {"error": "нет прав на тикеты"})
        who = me["login"] if me else "—"
        if path == "/api/tickets/new":
            tid = tickets.open_ticket(body["loom"], who, body.get("category_id"),
                                      body.get("comment", ""))
            return self._send(200, {"ok": True, "id": tid})
        if path == "/api/tickets/classify":
            extra = {"was": body["was"]} if "was" in body else {}
            try:
                tickets.classify(body["id"], body.get("category_id"), who, body.get("comment", ""), **extra)
            except tickets.Conflict as e:
                return self._send(409, {"error": str(e)})
            return self._send(200, {"ok": True})
        if path == "/api/tickets/close":
            tickets.close_ticket(body["id"], who)
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "нет такого адреса"})


def live_payload(q):
    """Живое состояние станков плюс обрывы за день — то, что показывает доска цеха.

    Ответ доски кэшируется, поэтому копируем его, прежде чем дописывать: иначе
    числа за один день осели бы в кэше и уехали на все мониторы.
    """
    board = tickets.board()
    data = dict(board)
    data["looms"] = [dict(r) for r in board["looms"]]

    day = q.get("day") or reports.latest_day()
    letter = q.get("shift", "")
    stats, totals = reports.loom_day_stats(day, letter)
    for row in data["looms"]:
        row["breaks"] = stats.get(row["loom"])
    data["stats_day"] = day
    data["stats_shift"] = letter
    data["stats_totals"] = totals
    # Данные устарели — что говорит журнал опроса FACT (начат ли и закончен ли сбор).
    if data.get("stale"):
        data["fact_collect"] = (collector.read_status() or {}).get("fact_collect")
    return data


# То, что уходит в поток на мониторы: собирается один раз на версию доски,
# двадцать мониторов получают одни и те же готовые байты.
LIVE_EVENT = hub.PerVersion(lambda: json.dumps(
    live_payload({}), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _age_sec(iso):
    try:
        return int(time.time() - datetime.fromisoformat(iso).timestamp())
    except (TypeError, ValueError):
        return None


def health():
    """Живо ли приложение — для мониторинга и для дежурного по цеху.

    Отвечает без входа: это не данные, а состояние службы.
    """
    out = {"ok": True, "uptime_sec": int(time.time() - STARTED_AT),
           "source": tickets.SOURCE["mode"], "monitors_connected": hub.HUB.listeners,
           "checks": {}}
    try:
        db = storage.shop()
        db.execute("SELECT COUNT(*) FROM setting").fetchone()
        db.close()
        out["checks"]["shop_db"] = "ок"
    except Exception as e:
        out["ok"] = False
        out["checks"]["shop_db"] = f"{type(e).__name__}: {e}"
    try:
        with storage.fact() as db:
            n = db.execute("SELECT COUNT(*) c FROM shift_full").fetchone()["c"]
            last = db.execute("SELECT MAX(day) d FROM stop_day").fetchone()["d"]
        out["checks"]["fact_db"] = f"ок, смен {n}, остановы по {last}"
    except Exception as e:
        out["ok"] = False
        out["checks"]["fact_db"] = f"{type(e).__name__}: {e}"

    s = collector.read_status()
    live_mode = tickets.SOURCE["mode"] == "fact"
    if s and collector.alive(s):
        live = s.get("live") or {}
        ing = s.get("ingest") or {}
        age = _age_sec(live.get("at"))
        out["checks"]["collector"] = "ок: pid %s, снимок FACT %s, станков %s, стоит %s" % (
            s.get("pid"), live.get("dir", "—"), live.get("looms", "—"), live.get("stopped", "—"))
        out["checks"]["ingest"] = ("ок: %s, остановов за проход %s, %s мс" % (
            (ing.get("at") or "—")[11:19], ing.get("stop_rows", 0), ing.get("ms", 0))
            if ing else "ещё не было прохода")
        # Снимок обновляется, только когда FACT выложил новый (раз в минуту).
        if live_mode and (age is None or age > tickets.STALE_SEC):
            out["ok"] = False
            # Причина — из журнала опроса FACT, если он её показывает; иначе последняя
            # ошибка сборщика (она может быть про смены, а не про живой снимок).
            fc = s.get("fact_collect") or {}
            why = ("сбор в FACT начат в %s и не закончен — перезапустите программу сбора на ПК FACT"
                   % fc["started"][11:16]) if fc.get("started") and not fc.get("completed") \
                else (s.get("last_error") or "FACT не выкладывает новых снимков")
            out["checks"]["fact"] = "нет свежего снимка %s мин: %s" % (
                round(age / 60) if age is not None else "—", why)
        elif live_mode:
            out["checks"]["fact"] = "ок, снимок %d с назад" % age
        # Часы станков против FACT: расхождение режет смену не там.
        snap = livestate.load() or {}
        skew = {n: ((st.get("details") or {}).get("clock_skew_sec"))
                for n, st in (snap.get("looms") or {}).items()}
        off = sorted((n, v) for n, v in skew.items() if v is not None and abs(v) >= 60)
        out["checks"]["loom_clocks"] = ("ок, все в пределах минуты" if not off else
            "расходятся с FACT: " + ", ".join("%s %+d мин" % (n, round(v / 60)) for n, v in off))
    else:
        out["checks"]["collector"] = "не работает"
        if live_mode:
            out["ok"] = False
    if not live_mode:
        out["checks"]["fact"] = "не нужен: работаем по зеркалу"
    out["collector"] = ({k: s.get(k) for k in ("pid", "host", "source", "url", "started_at",
                                               "live", "ingest", "onec", "fact_http", "last_error",
                                               "last_error_at")} if s else None)
    return out


class Server(ThreadingHTTPServer):
    # Очередь соединений: после перезапуска сервера 30 мониторов и десяток
    # людей переподключаются разом, а по умолчанию очередь — пять мест.
    request_queue_size = 128
    daemon_threads = True


def main():
    cfg = storage.config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=cfg.get("host", "0.0.0.0"),
                    help="адрес прослушивания; 127.0.0.1 — только локальный доступ")
    ap.add_argument("--port", type=int, default=cfg.get("port", 8780))
    ap.add_argument("--fact", metavar="URL", default=cfg.get("fact"),
                    help="брать живое состояние станков прямо с FACT, например http://172.0.30.9")
    ap.add_argument("--mirror", action="store_true",
                    help="работать по зеркалу, даже если адрес FACT задан в config.json")
    ap.add_argument("--no-collector", action="store_true",
                    help="не запускать сборщик внутри приложения (он работает отдельно)")
    args = ap.parse_args()

    logs.setup()
    if not os.path.exists(storage.FACT_DB):
        raise SystemExit(f"Не найдена база станков: {storage.FACT_DB}")
    t0 = time.time()
    info = storage.prepare()
    if info["rollup_built"]:
        LOG.info("свёртка остановов построена за %.1f с", time.time() - t0)
    if info["tech_cards_moved"]:
        LOG.info("техкарты 1С перенесены в цеховую базу: %d", info["tech_cards_moved"])
    if auth:
        auth.cleanup_sessions()
        temp = auth.ensure_admin()
        if temp:
            LOG.info("создан администратор admin, временный пароль напечатан в консоль")
            print(f"  создан администратор: admin / {temp} (пароль сменить при первом входе)")

    if args.fact and not args.mirror:
        tickets.SOURCE.update(mode="fact", url=args.fact.rstrip("/"))
    src = livestate.source_from(tickets.SOURCE["mode"], tickets.SOURCE["url"])
    # Снимок станков поменялся (сборщик здесь или отдельным процессом) —
    # доску пересобрать и толкнуть все мониторы. Файл проверяется четыре раза
    # в секунду: это один вызов stat, а толчок доходит за четверть секунды.
    hub.watch_file(storage.LIVE_FILE, tickets.invalidate, every=0.25)

    def fresh_data():
        cache.clear()           # дописаны смены и остановы — отчёты пересчитать
        tickets.invalidate()
    running = None if args.no_collector else collector.start_in_app(src, on_ingest=fresh_data)

    LOG.info("запуск: порт %s, источник %s", args.port,
             tickets.SOURCE["url"] if tickets.SOURCE["mode"] == "fact" else "зеркало")
    print(f"Приложение цеха: http://localhost:{args.port}")
    print(f"  доска для мониторов: http://localhost:{args.port}/wall")
    print(f"  описание API:        http://localhost:{args.port}/api/docs")
    print(f"  проверка живости:    http://localhost:{args.port}/api/health")
    print(f"  журнал:              {logs.LOG_FILE}")
    if tickets.SOURCE["mode"] == "fact":
        print(f"  живое состояние: {tickets.SOURCE['url']} — тикеты и андон автоматически")
    else:
        print("  живое состояние: зеркало factdata (тикеты вручную; для живых данных — --fact)")
    print("  сборщик данных: " + ("в приложении" if running else "отдельным процессом"
                                  if not args.no_collector else "выключен ключом --no-collector"))
    if notify.start():
        LOG.info("телеграм подключён: сводки, тревога при молчании FACT, андон")
        print("  телеграм: сводка после смены, тревога, станки без причины")
    else:
        print("  телеграм: не настроен (token и chat_id в config.json)")
    Server((args.host, args.port), Handler).serve_forever()
