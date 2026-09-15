"""Зеркалирование данных Toyota FACT на локальный диск.

Обходит листинги Apache рекурсивно и сохраняет всё дерево как есть.
Файлы, уже скачанные с тем же размером, пропускаются — можно запускать повторно.

    python fact_mirror.py
    python fact_mirror.py --dest D:\\FACT_archive --only factdata/stop_history
"""
import argparse
import html
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

FACT = "http://172.0.30.9"
DEST_DEFAULT = r"C:\Users\Asus\Documents\FACT_archive"

# Что зеркалим. Порядок = приоритет: самое ценное первым.
ROOTS = [
    "factdata/stop_history/",   # журнал каждого останова с кодом причины — главное
    "factdata/stop_event/",     # включения/выключения питания
    "factdata/shift-shift/",    # итоги по сменам
    "factdata/shift-date/",
    "factdata/shift-week/",
    "factdata/shift-month/",
    "factdata/loom/",           # полные данные станков
    "factdata/current/",
    "factdata/cloth/",
    "factdata/plan/",
    "factdata/plan_history/",
    "factdata/operator/",
    "factdata/mainte/",
    "factdata/setting/",
    "factdata/index/",
    "factdata/air_pressure/",
    "factdata/air_flow/",
    "factdata/pressure/",
    "factdata/tension/",
    "factdata/motor_watt/",
    "factdata/temp_humi/",
    "factdata/work_anlys/",
    "factdata/opestate/",
    "factdata/DashBoard/",
    "factdata/hds/",
    "factdata/export/",
    "factdata/log/",
    "fact/xlsfile/",            # шаблоны отчётов с формулами Toyota
]

SKIP_HREF = re.compile(r"^(\?|/|#|mailto:)")
LINK = re.compile(r'<a href="([^"]+)"', re.I)


def fetch(url, timeout=30, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if attempt == tries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def listing(url):
    """Ссылки из листинга Apache: (имена папок, имена файлов)."""
    body = fetch(url).decode("utf-8", "replace")
    dirs, files = [], []
    for href in LINK.findall(body):
        href = html.unescape(href)
        if SKIP_HREF.match(href) or href in ("../",):
            continue
        (dirs if href.endswith("/") else files).append(href)
    return dirs, files


def mirror(rel, dest, stats, depth=0):
    url = FACT + "/" + rel
    try:
        dirs, files = listing(url)
    except Exception as e:
        print(f"  ! не открылся каталог {rel}: {e}", flush=True)
        stats["errors"] += 1
        return

    local_dir = os.path.join(dest, *rel.strip("/").split("/"))
    os.makedirs(local_dir, exist_ok=True)

    for name in files:
        local = os.path.join(local_dir, urllib.parse.unquote(name))
        try:
            if os.path.exists(local) and os.path.getsize(local) > 0:
                stats["skipped"] += 1
                continue
            data = fetch(url + name)
            with open(local, "wb") as fh:
                fh.write(data)
            stats["files"] += 1
            stats["bytes"] += len(data)
            if stats["files"] % 200 == 0:
                print(f"  {stats['files']} файлов, {stats['bytes']/1e6:.0f} МБ … сейчас {rel}", flush=True)
        except Exception as e:
            print(f"  ! {rel}{name}: {e}", flush=True)
            stats["errors"] += 1

    for d in dirs:
        mirror(rel + d, dest, stats, depth + 1)


def main():
    global FACT
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=DEST_DEFAULT)
    ap.add_argument("--fact", default=FACT)
    ap.add_argument("--only", help="зеркалить только этот путь, например factdata/loom/")
    args = ap.parse_args()

    FACT = args.fact.rstrip("/")
    roots = [args.only.strip("/") + "/"] if args.only else ROOTS

    os.makedirs(args.dest, exist_ok=True)
    stats = {"files": 0, "bytes": 0, "skipped": 0, "errors": 0}
    started = datetime.now()
    print(f"Зеркалирование {FACT} -> {args.dest}")
    print(f"Начало: {started:%H:%M:%S}\n", flush=True)

    for root in roots:
        t0 = time.time()
        before = stats["files"]
        print(f"[{root}]", flush=True)
        mirror(root, args.dest, stats)
        print(f"  готово: +{stats['files']-before} файлов за {time.time()-t0:.0f} с\n", flush=True)

    dur = (datetime.now() - started).total_seconds()
    print(f"ИТОГО: {stats['files']} новых файлов, {stats['bytes']/1e6:.1f} МБ, "
          f"пропущено (уже были) {stats['skipped']}, ошибок {stats['errors']}, время {dur/60:.1f} мин")
    print(f"Папка: {args.dest}")


if __name__ == "__main__":
    main()
