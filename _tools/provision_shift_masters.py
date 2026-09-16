"""Создать учётные записи мастеров из JSON в stdin. Пароли вывести один раз.

Каждая запись: login, name, code (табельный номер). Существующие логины
не изменяются. Вывод с паролями хранить вне git и передать администратору.
"""
import json
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '_app'))
import auth
import storage

ACCESS = {'sections': ['cards', 'assign', 'tickets', 'manual', 'history', 'plan'],
          'permissions': ['assign', 'tickets']}


def provision(records):
    conn = storage.shop()
    conn.close()
    conn = auth.db()
    result = []
    try:
        conn.execute('BEGIN IMMEDIATE')
        for record in records:
            login = record['login'].strip().lower()
            if conn.execute('SELECT 1 FROM app_user WHERE login=?', (login,)).fetchone():
                raise ValueError('Логин уже существует: ' + login)
            matches = conn.execute('SELECT id, role FROM operator WHERE code=?',
                                   (str(record['code']),)).fetchall()
            if len(matches) > 1:
                raise ValueError('Неоднозначный табельный номер: ' + str(record['code']))
            if matches:
                employee = matches[0]['id']
                conn.execute("UPDATE operator SET role='master', active=1 WHERE id=?", (employee,))
            else:
                employee = conn.execute("INSERT INTO operator(code,name,role) VALUES (?,?,'master')",
                                        (str(record['code']), record['name'])).lastrowid
            password = secrets.token_urlsafe(12)
            salt = secrets.token_hex(16)
            user = conn.execute(
                "INSERT INTO app_user(login,name,role,pwd_hash,pwd_salt,must_change) VALUES (?,?,'master',?,?,1)",
                (login, record['name'], auth._hash(password, salt), salt)).lastrowid
            conn.execute('INSERT INTO app_user_access VALUES (?,?)', (user, json.dumps(ACCESS)))
            conn.execute('INSERT INTO app_user_employee VALUES (?,?)', (user, employee))
            result.append(dict(record, password=password))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return result


if __name__ == '__main__':
    print(json.dumps(provision(json.load(sys.stdin)), ensure_ascii=False, indent=2))
