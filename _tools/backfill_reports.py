"""Заливает в базу отчёты за все дни, какие есть в зеркале FACT.

    python backfill_reports.py              # все дни
    python backfill_reports.py --from 2026.08.01
"""
import argparse
import os
import sqlite3
import sys
import time

from make_excel_report import build, save_db

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "fact.db")


def all_days():
    db = sqlite3.connect(DB)
    try:
        days = [r[0] for r in db.execute(
            "SELECT DISTINCT substr(shift,1,10) d FROM shift_loom ORDER BY d")]
    finally:
        db.close()
    return days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="since", help="с какой даты, например 2026.08.01")
    ap.add_argument("--force", action="store_true", help="пересчитать даже уже залитые дни")
    a = ap.parse_args()

    days = all_days()
    if a.since:
        days = [d for d in days if d >= a.since]

    db = sqlite3.connect(DB)
    done = set()
    try:
        done = {r[0] for r in db.execute("SELECT DISTINCT day FROM report_daily")}
    except sqlite3.OperationalError:
        pass          # таблицы ещё нет — создастся при первой записи
    db.close()

    todo = days if a.force else [d for d in days if d not in done]
    print(f"Дней в зеркале: {len(days)}, уже в базе: {len(done)}, к заливке: {len(todo)}")

    ok = empty = failed = 0
    t0 = time.time()
    for i, day in enumerate(todo, 1):
        try:
            rows = build(day)
        except SystemExit:
            empty += 1
            continue
        except Exception as e:
            print(f"  {day}: ошибка — {type(e).__name__}: {e}")
            failed += 1
            continue
        save_db(day, rows)
        ok += 1
        if i % 10 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}  последний: {day}")

    db = sqlite3.connect(DB)
    n_days, n_rows = db.execute("SELECT COUNT(DISTINCT day), COUNT(*) FROM report_daily").fetchone()
    first, last = db.execute("SELECT MIN(day), MAX(day) FROM report_daily").fetchone()
    db.close()
    print(f"\nЗалито дней: {ok}, пустых: {empty}, с ошибкой: {failed}, время {time.time()-t0:.0f} с")
    print(f"В базе отчётов: {n_days} дней, {n_rows} строк ({first} … {last})")


if __name__ == "__main__":
    main()
