"""Пользователи, вход и права доступа.

Пароли хранятся только в виде хэша (PBKDF2-SHA256, 120 000 итераций) — восстановить
их нельзя, можно только задать новый. Сессия живёт в cookie и протухает через сутки
без активности.

Роли:
  admin    — всё, включая пользователей и ставку
  master   — назначения на смену, тикеты, отчёты, выгрузка
  operator — тикеты и просмотр
  viewer   — только просмотр
"""
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "shop.db")

SESSION_HOURS = 24
ITERATIONS = 120_000

ROLES = {
    "admin": "Администратор",
    "master": "Мастер смены",
    "operator": "Оператор",
    "viewer": "Наблюдатель",
}

# Что кому разрешено. Ключ — право, значение — роли, которым оно доступно.
PERMISSIONS = {
    "view": {"admin", "master", "operator", "viewer"},      # смотреть отчёты и дашборды
    "tickets": {"admin", "master", "operator"},             # классифицировать остановы
    "assign": {"admin", "master"},                          # назначать операторов на смену
    "export": {"admin", "master"},                          # собирать Excel
    "people": {"admin", "master"},                          # справочник операторов
    "settings": {"admin"},                                  # ставка и параметры
    "users": {"admin"},                                     # пользователи и права
    "plan_edit": {"admin", "master"},                       # план отдельно от расстановки
    "setup_edit": {"admin", "master"},                      # заправка отдельно от расстановки
}

# Разделы и действия независимы: видимость раздела не даёт права менять данные.
# Отсутствие app_user_access означает прежний набор роли, поэтому миграция не
# расширяет возможности существующих пользователей и не требует их перезаписи.
SECTIONS = {
    "dash": ("Дашборд", "Dashboard"),
    "cards": ("Карточки станков", "Machine cards"),
    "tickets": ("Тикеты", "Tickets"),
    "walk": ("Обход цеха", "Shop floor walk"),
    "setup": ("Заправка", "Machine setup"),
    "assign": ("Расстановка", "Shift assignments"),
    "plan": ("План", "Production plan"),
    "report": ("Производственный отчёт", "Production report"),
    "explorer": ("Простои", "Downtime"),
    "history": ("История станков", "Machine history"),
    "bottle": ("Узкие места", "Bottlenecks"),
    "manual": ("Ручные остановы", "Manual stops"),
    "kpi": ("KPI", "KPI"),
    "salary": ("Зарплата", "Payroll"),
    "people": ("Операторы", "Operators"),
    "settings": ("Настройки", "Settings"),
    "users": ("Пользователи", "Users"),
}
ACTION_INFO = {
    "tickets": ("Классифицировать и закрывать тикеты", "Classify and close tickets", ["tickets", "dash"]),
    "assign": ("Редактировать расстановку", "Edit shift assignments", ["assign", "salary"]),
    "plan_edit": ("Редактировать и импортировать план", "Edit and import plan", ["plan"]),
    "setup_edit": ("Менять заправку и справочник пряжи", "Edit machine setup and yarns", ["setup", "dash", "settings"]),
    "export": ("Выгружать Excel", "Export Excel", ["report"]),
    "people": ("Редактировать операторов", "Edit operators", ["people"]),
    "settings": ("Менять настройки", "Edit settings", ["settings"]),
    "users": ("Управлять пользователями и ключами API", "Manage users and API keys", ["users", "settings"]),
}
ADMIN_ONLY = {"users"}
_UNSET = object()


def role_access(role):
    """Шаблоны воспроизводят прежнюю видимость меню и права действий."""
    if role not in ROLES:
        return {"sections": [], "permissions": []}
    old_gates = {"assign": "assign", "people": "people", "settings": "settings", "users": "users"}
    return {
        "sections": [s for s in SECTIONS if s not in old_gates or role in PERMISSIONS[old_gates[s]]],
        "permissions": [p for p in ACTION_INFO if role in PERMISSIONS[p]],
    }


def access_catalog():
    return {
        "sections": [{"id": k, "name": v[0], "name_en": v[1],
                      "legacy": k in ("bottle", "kpi")} for k, v in SECTIONS.items()],
        "permissions": [{"id": k, "name": v[0], "name_en": v[1], "sections": v[2],
                         "admin_only": k in ADMIN_ONLY} for k, v in ACTION_INFO.items()],
        "role_defaults": {role: role_access(role) for role in ROLES},
    }


def _validate_access(value, role):
    if value is None:
        return None
    if role == "admin":
        raise ValueError("у администратора всегда полный доступ; выберите другую роль для ограничений")
    if not isinstance(value, dict) or set(value) != {"sections", "permissions"}:
        raise ValueError("access: нужны массивы sections и permissions")
    out = {}
    for field, allowed in (("sections", SECTIONS), ("permissions", ACTION_INFO)):
        items = value[field]
        if not isinstance(items, list) or any(not isinstance(x, str) or x not in allowed for x in items):
            raise ValueError("неизвестное значение или неверный список " + field)
        out[field] = sorted(set(items))
    if "users" in out["sections"] or ADMIN_ONLY.intersection(out["permissions"]):
        raise ValueError("управлять пользователями и ключами API может только администратор")
    for permission in out["permissions"]:
        if not set(out["sections"]).intersection(ACTION_INFO[permission][2]):
            raise ValueError("для действия «%s» откройте соответствующий раздел" % ACTION_INFO[permission][0])
    return out


def _user_access(row):
    """Испорченная индивидуальная настройка закрывает доступ, а не расширяет его."""
    user = dict(row)
    raw = user.pop("access_json", None)
    custom = None
    if raw is not None and user.get("role") != "admin":
        try:
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise ValueError("повреждены индивидуальные права")
            custom = _validate_access(decoded, user["role"])
        except (ValueError, TypeError):
            custom = {"sections": [], "permissions": []}
    access = custom if custom is not None else role_access(user.get("role"))
    user.update(access)
    user["access_mode"] = "custom" if custom is not None else "role"
    return user


def can_section(user, *sections):
    return bool(user) and bool(set(user.get("sections", role_access(user.get("role"))["sections"]))
                              .intersection(sections))

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    pwd_hash TEXT NOT NULL,
    pwd_salt TEXT NOT NULL,
    must_change INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    last_login TEXT
);
CREATE TABLE IF NOT EXISTS app_session (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_user(id),
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_user ON app_session(user_id);
CREATE TABLE IF NOT EXISTS login_fail (
    login TEXT NOT NULL,
    ip TEXT,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fail_at ON login_fail(at);
CREATE TABLE IF NOT EXISTS app_user_access (
    user_id INTEGER PRIMARY KEY REFERENCES app_user(id),
    access_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_user_employee (
    user_id INTEGER PRIMARY KEY REFERENCES app_user(id),
    operator_id INTEGER NOT NULL UNIQUE REFERENCES operator(id)
);
"""

# Защита от перебора пароля: после пяти неудач за четверть часа вход с этого
# адреса закрывается на пять минут. Цеховой сети это не мешает — человек
# ошибается два-три раза, а не пятьдесят.
FAIL_LIMIT = 5
FAIL_WINDOW_MIN = 15
LOCK_MIN = 5


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(salt), ITERATIONS).hex()


def create_user(login, name, role, password, must_change=True, access=None):
    if role not in ROLES:
        raise ValueError("неизвестная роль")
    login = (login or "").strip().lower()
    if not login or not password:
        raise ValueError("нужны логин и пароль")
    if len(password) < 6:
        raise ValueError("пароль короче шести символов")
    access = _validate_access(access, role)
    salt = secrets.token_hex(16)
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO app_user (login, name, role, pwd_hash, pwd_salt, must_change)"
            " VALUES (?,?,?,?,?,?)",
            (login, (name or login).strip(), role, _hash(password, salt), salt,
             1 if must_change else 0))
        if access is not None:
            conn.execute("INSERT INTO app_user_access VALUES (?,?)",
                         (cur.lastrowid, json.dumps(access, ensure_ascii=False)))
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"пользователь «{login}» уже есть")
    finally:
        conn.close()


def set_password(user_id, password, must_change=False, keep_token=None):
    """Меняет пароль и отзывает прежние сессии в одной транзакции.

    При смене своего пароля веб-клиент сохраняет только текущую сессию.
    При сбросе администратором или из консоли закрываются все сессии цели.
    """
    if not password or len(password) < 6:
        raise ValueError("пароль короче шести символов")
    salt = secrets.token_hex(16)
    conn = db()
    conn.execute("UPDATE app_user SET pwd_hash=?, pwd_salt=?, must_change=? WHERE id=?",
                 (_hash(password, salt), salt, 1 if must_change else 0, user_id))
    conn.execute("DELETE FROM app_session WHERE user_id=? AND token IS NOT ?",
                 (user_id, keep_token))
    conn.commit()
    conn.close()


def update_user(user_id, name=None, role=None, active=None, access=_UNSET, actor_id=None):
    sets, args = [], []
    if name is not None:
        sets.append("name=?"); args.append(name.strip())
    if role is not None:
        if role not in ROLES:
            raise ValueError("неизвестная роль")
        sets.append("role=?"); args.append(role)
    if active is not None:
        if type(active) not in (bool, int) or active not in (True, False, 0, 1):
            raise ValueError("active: нужно true или false")
        sets.append("active=?"); args.append(1 if active else 0)
    if not sets and access is _UNSET:
        return
    conn = db()
    try:
        # Последнего администратора нельзя одновременно отключить из двух окон.
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT * FROM app_user WHERE id=?", (user_id,)).fetchone()
        if not old:
            raise ValueError("пользователь не найден")
        next_role = role if role is not None else old["role"]
        next_active = bool(active) if active is not None else bool(old["active"])
        if actor_id == old["id"] and (not next_active or (old["role"] == "admin" and next_role != "admin")):
            raise ValueError("нельзя отключить себя или снять с себя роль администратора")
        if old["role"] == "admin" and old["active"] and (next_role != "admin" or not next_active):
            count = conn.execute("SELECT COUNT(*) FROM app_user WHERE role='admin' AND active=1").fetchone()[0]
            if count <= 1:
                raise ValueError("нельзя отключить или понизить последнего администратора")
        if access is not _UNSET:
            access = _validate_access(access, next_role)
        if sets:
            conn.execute(f"UPDATE app_user SET {', '.join(sets)} WHERE id=?", [*args, user_id])
        if access is None or next_role == "admin":
            conn.execute("DELETE FROM app_user_access WHERE user_id=?", (user_id,))
        elif access is not _UNSET:
            conn.execute("INSERT OR REPLACE INTO app_user_access VALUES (?,?)",
                         (user_id, json.dumps(access, ensure_ascii=False)))
        if not next_active:
            conn.execute("DELETE FROM app_session WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def list_users():
    conn = db()
    rows = [_user_access(r) for r in conn.execute(
        "SELECT u.id, u.login, u.name, u.role, u.active, u.must_change, u.created_at, u.last_login, a.access_json"
        " FROM app_user u LEFT JOIN app_user_access a ON a.user_id=u.id ORDER BY u.role, u.login")]
    conn.close()
    return rows


def locked_for(login_name, ip=None):
    """Сколько секунд вход закрыт после неудачных попыток; 0 — открыт."""
    since = (datetime.now().astimezone()
             - timedelta(minutes=FAIL_WINDOW_MIN)).isoformat(timespec="seconds")
    conn = db()
    rows = conn.execute(
        "SELECT at FROM login_fail WHERE login=? AND ip IS ? AND at >= ? ORDER BY at DESC",
        ((login_name or "").strip().lower(), ip, since)).fetchall()
    conn.close()
    if len(rows) < FAIL_LIMIT:
        return 0
    last = datetime.fromisoformat(rows[0]["at"])
    left = (last + timedelta(minutes=LOCK_MIN)) - datetime.now().astimezone()
    return max(0, int(left.total_seconds()))


def login(login_name, password, ip=None):
    """Возвращает токен сессии или None. Ответ одинаковый при любой ошибке —
    чтобы нельзя было подобрать существующие логины."""
    name = (login_name or "").strip().lower()
    conn = db()
    row = conn.execute("SELECT * FROM app_user WHERE login=? AND active=1",
                       (name,)).fetchone()
    if not row or _hash(password or "", row["pwd_salt"]) != row["pwd_hash"]:
        conn.execute("INSERT INTO login_fail (login, ip, at) VALUES (?,?,?)",
                     (name, ip, datetime.now().astimezone().isoformat(timespec="seconds")))
        conn.commit()
        conn.close()
        return None
    conn.execute("DELETE FROM login_fail WHERE login=? AND ip IS ?", (name, ip))
    token = secrets.token_urlsafe(32)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    conn.execute("INSERT INTO app_session (token, user_id, created_at, last_seen, ip)"
                 " VALUES (?,?,?,?,?)", (token, row["id"], now, now, ip))
    conn.execute("UPDATE app_user SET last_login=? WHERE id=?", (now, row["id"]))
    conn.commit()
    conn.close()
    return token


def logout(token):
    conn = db()
    conn.execute("DELETE FROM app_session WHERE token=?", (token,))
    conn.commit()
    conn.close()


def user_by_token(token):
    """Пользователь по токену сессии; попутно продлевает сессию."""
    if not token:
        return None
    conn = db()
    row = conn.execute(
        "SELECT u.*, s.last_seen, a.access_json FROM app_session s JOIN app_user u ON u.id=s.user_id"
        " LEFT JOIN app_user_access a ON a.user_id=u.id"
        " WHERE s.token=? AND u.active=1", (token,)).fetchone()
    if not row:
        conn.close()
        return None
    try:
        seen = datetime.fromisoformat(row["last_seen"])
    except ValueError:
        seen = datetime.now().astimezone()
    if datetime.now().astimezone() - seen > timedelta(hours=SESSION_HOURS):
        conn.execute("DELETE FROM app_session WHERE token=?", (token,))
        conn.commit()
        conn.close()
        return None
    conn.execute("UPDATE app_session SET last_seen=? WHERE token=?",
                 (datetime.now().astimezone().isoformat(timespec="seconds"), token))
    conn.commit()
    user = _user_access({k: row[k] for k in ("id", "login", "name", "role", "must_change", "access_json")})
    link = conn.execute("SELECT operator_id FROM app_user_employee WHERE user_id=?", (row["id"],)).fetchone()
    user["employee_id"] = link["operator_id"] if link else None
    conn.close()
    return user


def can(user, permission):
    if not user:
        return False
    if permission == "view":
        return bool(user.get("sections", role_access(user.get("role"))["sections"]))
    if permission in ADMIN_ONLY and user.get("role") != "admin":
        return False
    return permission in user.get("permissions", role_access(user.get("role"))["permissions"])


def ensure_admin():
    """При первом запуске создаёт администратора с временным паролем.

    Пароль печатается в консоль один раз и требует смены при первом входе —
    задавать его за пользователя нельзя.
    """
    conn = db()
    n = conn.execute("SELECT COUNT(*) c FROM app_user").fetchone()["c"]
    conn.close()
    if n:
        return None
    password = secrets.token_urlsafe(9)
    create_user("admin", "Администратор", "admin", password, must_change=True)
    return password


def cleanup_sessions():
    """Убирает просроченные сессии и старые отметки неудачных входов."""
    now = datetime.now().astimezone()
    conn = db()
    conn.execute("DELETE FROM app_session WHERE last_seen < ?",
                 ((now - timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds"),))
    conn.execute("DELETE FROM login_fail WHERE at < ?",
                 ((now - timedelta(days=7)).isoformat(timespec="seconds"),))
    conn.commit()
    conn.close()
