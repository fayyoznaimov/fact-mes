"""Сброс пароля, когда войти не получается.

Пароли хранятся только хэшем — узнать старый нельзя, можно выдать новый
временный. Запускать на самом сервере, где лежит shop.db:

    python reset_password.py                 # список пользователей
    python reset_password.py admin           # новый временный пароль для admin
    python reset_password.py admin --keep    # не требовать смены при входе
"""
import argparse
import secrets
import sqlite3

import auth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("login", nargs="?", help="кому сбросить пароль")
    ap.add_argument("--keep", action="store_true",
                    help="не требовать смены пароля при первом входе")
    args = ap.parse_args()

    users = auth.list_users()
    if not args.login:
        print("Пользователи:")
        for u in users:
            print("  %-12s %-24s %-14s %s" % (
                u["login"], u["name"], auth.ROLES.get(u["role"], u["role"]),
                "активен" if u["active"] else "отключён"))
        print("\nЧтобы сбросить пароль: python reset_password.py <логин>")
        return

    target = next((u for u in users if u["login"] == args.login.strip().lower()), None)
    if not target:
        raise SystemExit("Нет пользователя «%s»" % args.login)

    password = secrets.token_urlsafe(9)
    auth.set_password(target["id"], password, must_change=not args.keep)
    conn = sqlite3.connect(auth.DB_PATH)
    conn.execute("DELETE FROM app_session WHERE user_id=?", (target["id"],))
    conn.commit()
    conn.close()

    print("Логин:            %s" % target["login"])
    print("Временный пароль: %s" % password)
    if not args.keep:
        print("При входе система попросит задать свой пароль.")
    print("Все прежние сессии этого пользователя закрыты.")


if __name__ == "__main__":
    main()
