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
    "master": "Мастер",
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
}

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


def create_user(login, name, role, password, must_change=True):
    if role not in ROLES:
        raise ValueError("неизвестная роль")
    login = (login or "").strip().lower()
    if not login or not password:
        raise ValueError("нужны логин и пароль")
    salt = secrets.token_hex(16)
    conn = db()
    try:
        conn.execute(
            "INSERT INTO app_user (login, name, role, pwd_hash, pwd_salt, must_change)"
            " VALUES (?,?,?,?,?,?)",
            (login, (name or login).strip(), role, _hash(password, salt), salt,
             1 if must_change else 0))
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


def update_user(user_id, name=None, role=None, active=None):
    sets, args = [], []
    if name is not None:
        sets.append("name=?"); args.append(name.strip())
    if role is not None:
        if role not in ROLES:
            raise ValueError("неизвестная роль")
        sets.append("role=?"); args.append(role)
    if active is not None:
        sets.append("active=?"); args.append(1 if active else 0)
    if not sets:
        return
    args.append(user_id)
    conn = db()
    conn.execute(f"UPDATE app_user SET {', '.join(sets)} WHERE id=?", args)
    if active is False:
        conn.execute("DELETE FROM app_session WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def list_users():
    conn = db()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, login, name, role, active, must_change, created_at, last_login"
        " FROM app_user ORDER BY role, login")]
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
        "SELECT u.*, s.last_seen FROM app_session s JOIN app_user u ON u.id=s.user_id"
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
    user = {k: row[k] for k in ("id", "login", "name", "role", "must_change")}
    conn.close()
    return user


def can(user, permission):
    return bool(user) and user.get("role") in PERMISSIONS.get(permission, set())


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
