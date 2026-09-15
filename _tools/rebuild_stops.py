"""Загрузка пособытийных остановов из FACT в базу.

`factdata/stop_history/<день>/<номер>.txt` — по файлу на станок за день, в каждом
по одной строке на останов:

    00:01:21,00:01:55,0005,2026.09.11.2,21,Weft,186698,948,1037,156,34,Towel,00:01:52,0
    начало  конец    код  смена         ?  причина пики  метры ярды штуки сек артикул приход_оператора

Разбор общий с приложением (`_app/ingest.py`): сборщик дописывает сегодняшние
остановы на лету, здесь — вся история. Вместе с остановами пересчитывается
свёртка `stop_day`, на которой работают «Узкие места» и сводка ручных остановов.

Это самый ценный файл во всём зеркале: каждый останов с **временем прихода
оператора**. Из него считаются MTTR, время реакции и обрывность — то, чего нет
ни в одном отчёте FACT.

    python rebuild_stops.py            # все дни
    python rebuild_stops.py 2026.09    # только сентябрь
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "_app"))

import ingest    # noqa: E402
import storage   # noqa: E402

SRC = os.path.join(storage.FACTDATA, "stop_history")


def read_day(folder):
    """Строки одного дня по всем станкам."""
    out = []
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".txt"):
            continue
        try:
            text = open(os.path.join(folder, fn), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        out += ingest.stop_rows(text)[1]
    return out


def main():
    if not os.path.isdir(SRC):
        raise SystemExit("Нет папки с историей остановов: %s" % SRC)
    only = sys.argv[1] if len(sys.argv) > 1 else ""

    db = storage.fact_rw()
    ingest.ensure_schema(db)
    days = sorted(d for d in os.listdir(SRC)
                  if os.path.isdir(os.path.join(SRC, d)) and d.startswith(only))
    t0 = time.time()
    total = 0
    for day in days:
        n = ingest.replace_stop_day(db, day, read_day(os.path.join(SRC, day)))
        db.commit()
        total += n
        print("  %s: остановов %d" % (day, n))

    n = db.execute("SELECT COUNT(*) FROM stop_log").fetchone()[0]
    resp = db.execute("SELECT COUNT(resp_sec) FROM stop_log").fetchone()[0]
    looms = db.execute("SELECT COUNT(DISTINCT loom) FROM stop_log").fetchone()[0]
    db.close()
    print("Дней %d, записей за проход %d, в базе %d по %d станкам"
          " (с отметкой прихода %d, %.0f%%), %.1f с"
          % (len(days), total, n, looms, resp, 100.0 * resp / n if n else 0, time.time() - t0))


if __name__ == "__main__":
    main()
