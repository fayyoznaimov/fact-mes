"""Проверка перед подключением: готово ли всё к работе с живым FACT и 1С.

    python golive.py                                     по config.json
    python golive.py --fact http://172.0.30.9            проверить FACT
    python golive.py --onec http://1c/... --token "Basic ..."
    python golive.py --telegram                          ещё и пробное сообщение

Каждая строка — одна проверка: «ок», «внимание» (работать можно, но стоит
поправить) или «ОШИБКА» (с тем, что сделать). Код возврата 0, если ошибок нет,
— проверку можно поставить в планировщик после обновления.

FACT и 1С только читаются: скрипт ничего туда не пишет.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

import collector
import livestate
import storage

OK, WARN, BAD = "ок", "внимание", "ОШИБКА"
TASK_NAME = "Цех — приложение"


class Report:
    def __init__(self):
        self.bad = 0
        self.warn = 0

    def line(self, level, what, note=""):
        if level == BAD:
            self.bad += 1
        elif level == WARN:
            self.warn += 1
        print("  %-9s %-34s %s" % (level, what, note))

    def section(self, title):
        print("\n" + title)


def check_local(r, cfg):
    r.section("Сервер цеха")
    v = sys.version_info
    r.line(OK if v >= (3, 9) else BAD, "Python", "%d.%d.%d" % v[:3]
           + ("" if v >= (3, 9) else " — нужен 3.9 или новее"))
    if os.path.exists(storage.CONFIG_PATH):
        r.line(OK, "config.json", storage.CONFIG_PATH)
    else:
        r.line(WARN, "config.json", "нет — скопируйте config.example.json и впишите адрес FACT")
    free = shutil.disk_usage(storage.ROOT).free / 1e9
    r.line(OK if free > 5 else WARN if free > 1 else BAD, "место на диске",
           "%.1f ГБ свободно" % free + ("" if free > 5 else " — база растёт на ~1 ГБ в год"))

    try:
        storage.prepare()
        with storage.fact() as db:
            n = db.execute("SELECT COUNT(*) FROM stop_log").fetchone()[0]
            last = db.execute("SELECT MAX(day) FROM stop_day").fetchone()[0]
            shifts = db.execute("SELECT MAX(shift) FROM shift_full").fetchone()[0]
        r.line(OK, "база станков", "остановов %s, свёртка по %s, последняя смена %s"
               % (f"{n:,}".replace(",", " "), last, shifts))
    except Exception as e:
        r.line(BAD, "база станков", "%s: %s" % (type(e).__name__, e))
    try:
        db = storage.shop()
        res = db.execute("PRAGMA quick_check").fetchone()[0]
        users = db.execute("SELECT COUNT(*) FROM app_user WHERE active=1").fetchone()[0]
        keys = db.execute("SELECT scopes FROM api_key WHERE active=1").fetchall()
        db.close()
        r.line(OK if res == "ok" else BAD, "цеховая база", "целостность: %s, пользователей %d"
               % (res, users))
        if any("write" in (k[0] or "") for k in keys):
            r.line(OK, "ключ API для 1С", "есть ключ с правом присылать заказы")
        else:
            r.line(WARN, "ключ API для 1С", "нет — выдайте в «Настройках», если 1С будет слать сама")
    except Exception as e:
        r.line(BAD, "цеховая база", "%s: %s" % (type(e).__name__, e))

    port = cfg.get("port", 8780)
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/api/health" % port, timeout=5) as resp:
            h = json.loads(resp.read())
        r.line(OK if h.get("ok") else WARN, "приложение", "отвечает на порту %s; мониторов на "
               "толчках %s" % (port, h.get("monitors_connected")))
        for k, v in (h.get("checks") or {}).items():
            if not str(v).startswith(("ок", "не нужен")):
                r.line(WARN, "  " + k, v)
    except Exception as e:
        r.line(WARN, "приложение", "не отвечает на порту %s (%s) — запустите app.py или задание "
               "планировщика" % (port, type(e).__name__))

    s = collector.read_status()
    if collector.alive(s):
        live = s.get("live") or {}
        r.line(OK, "сборщик данных", "pid %s, источник %s, снимок %s, станков %s"
               % (s.get("pid"), s.get("source"), live.get("dir"), live.get("looms")))
        if s.get("last_error"):
            r.line(WARN, "  последняя ошибка", s["last_error"])
    else:
        r.line(WARN, "сборщик данных", "не работает — он запускается вместе с приложением")

    if os.name == "nt":
        try:
            q = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True,
                               timeout=15)
            r.line(OK if q.returncode == 0 else WARN, "автозапуск",
                   "задание «%s» есть" % TASK_NAME if q.returncode == 0 else
                   "задания нет — _deploy\\install_autostart.ps1 от администратора")
        except Exception as e:
            r.line(WARN, "автозапуск", "не проверить: %s" % e)

    tg = cfg.get("telegram") or {}
    r.line(OK if tg.get("token") and tg.get("chat_id") else WARN, "телеграм",
           "настроен" if tg.get("token") and tg.get("chat_id")
           else "не настроен — сводок, тревог и андона в телефон не будет")


def check_fact(r, url, expect_looms):
    r.section("FACT: %s" % url)
    src = livestate.HttpSource(url, timeout=10)
    t0 = time.perf_counter()
    try:
        d = livestate.latest_dir(src)
        r.line(OK, "сервер отвечает", "свежий снимок %s, %.0f мс" % (d, (time.perf_counter() - t0) * 1000))
    except Exception as e:
        r.line(BAD, "сервер отвечает", "%s: %s — проверьте сеть до %s и что Apache FACT запущен"
               % (type(e).__name__, e, url))
        return
    t0 = time.perf_counter()
    try:
        snap = livestate.snapshot(src, d)
    except Exception as e:
        r.line(BAD, "снимок станков", "%s: %s" % (type(e).__name__, e))
        return
    ms = (time.perf_counter() - t0) * 1000
    n = len(snap["looms"])
    r.line(OK if n >= expect_looms else WARN, "станков в снимке",
           "%d, прочитано за %.0f мс" % (n, ms)
           + ("" if n >= expect_looms else " — ждали %d: не все станки в сети FACT" % expect_looms))
    if snap["missing"]:
        r.line(WARN, "файлы станков", "нет у " + ", ".join(snap["missing"]))
    if snap.get("fact_time"):
        skew = time.time() - snap["fact_time"]
        r.line(OK if abs(skew) < 180 else WARN, "время снимка",
               "%d с назад" % skew + ("" if abs(skew) < 180 else
                                      " — снимок старый или часы FACT и сервера расходятся"))
    stopped = [st for st in snap["looms"].values() if not st["running"]]
    r.line(OK, "состояние", "работает %d, стоит %d" % (n - len(stopped), len(stopped)))

    today = datetime.now().strftime("%Y.%m.%d")
    for rel, what in (("factdata/stop_history/%s" % today, "остановы за сегодня"),
                      ("factdata/shift-shift", "итоги смен"),
                      ("factdata/operator", "операторы")):
        try:
            dirs, files = src.list(rel)
            r.line(OK, what, "%s: файлов %d" % (rel, len(files) + len(dirs)))
        except Exception as e:
            r.line(WARN if "operator" in rel else BAD, what, "%s: %s" % (rel, e))


def check_onec(r, url, token):
    r.section("1С: %s" % url)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    if token:
        req.add_header("Authorization", token)
    try:
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
        import integration
        orders = integration.orders_of(payload)
        with_ppt = sum(1 for o in orders if o.get("weftPerOneRow"))
        with_cloth = sum(1 for o in orders if o.get("clothCode") or o.get("loomClothCode"))
        r.line(OK if orders else WARN, "заказы", "%d за %.0f мс" % (len(orders), (time.perf_counter() - t0) * 1000))
        r.line(OK if with_ppt == len(orders) else WARN, "пики на изделие (weftPerOneRow)",
               "заполнены у %d из %d" % (with_ppt, len(orders)))
        r.line(OK if with_cloth else WARN, "код ткани станка (clothCode)",
               "есть у %d из %d" % (with_cloth, len(orders)) + ("" if with_cloth else
               " — без него связку кодов делать руками во вкладке «План»"))
    except Exception as e:
        r.line(BAD, "ответ 1С", "%s: %s" % (type(e).__name__, e))


def main():
    cfg = storage.config()
    onec = cfg.get("onec") or {}
    ap = argparse.ArgumentParser()
    ap.add_argument("--fact", default=cfg.get("fact"), help="адрес FACT")
    ap.add_argument("--onec", default=onec.get("url"), help="адрес выгрузки заказов 1С")
    ap.add_argument("--token", default=onec.get("token"), help="заголовок Authorization для 1С")
    ap.add_argument("--looms", type=int, default=cfg.get("looms", 40),
                    help="сколько станков должно быть в FACT")
    ap.add_argument("--telegram", action="store_true", help="отправить пробное сообщение")
    args = ap.parse_args()

    print("Проверка перед подключением · %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    r = Report()
    check_local(r, cfg)
    if args.fact:
        check_fact(r, args.fact.rstrip("/"), args.looms)
    else:
        r.section("FACT")
        r.line(WARN, "адрес FACT", "не задан: --fact http://172.0.30.9 или \"fact\" в config.json")
    if args.onec:
        check_onec(r, args.onec, args.token)
    if args.telegram:
        import notify
        r.section("Телеграм")
        ok = notify.send("Проверка связи перед подключением: приложение цеха на месте.")
        r.line(OK if ok else BAD, "пробное сообщение", "ушло" if ok else "не ушло — token и chat_id")

    print("\nИтог: %s" % ("всё готово" if not r.bad and not r.warn else
                          "ошибок %d, предупреждений %d" % (r.bad, r.warn)))
    raise SystemExit(1 if r.bad else 0)


if __name__ == "__main__":
    main()
