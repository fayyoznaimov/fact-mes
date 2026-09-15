"""Сборщик: качает смены из Toyota FACT в SQLite.

    python fact_collect.py            # добрать новые смены
    python fact_collect.py --all      # перекачать всё заново
"""
import sqlite3
import sys

import fact_api

DB = "fact.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS shift_loom (
    shift TEXT NOT NULL,
    loom TEXT NOT NULL,
    style TEXT,
    rpm INTEGER,
    effic_pct REAL,
    run_min REAL,
    stop_min REAL,
    product_kpick REAL,
    warp_top_ct INTEGER, warp_top_min REAL,
    warp_ct INTEGER, warp_min REAL,
    weft_ct INTEGER, weft_min REAL,
    unselect_ct INTEGER, unselect_min REAL,
    total_ct INTEGER,
    stop_ct_raw TEXT,
    stop_tm_raw TEXT,
    PRIMARY KEY (shift, loom)
);
CREATE INDEX IF NOT EXISTS idx_shift ON shift_loom(shift);
CREATE INDEX IF NOT EXISTS idx_loom ON shift_loom(loom);
"""

COLS = ["shift", "loom", "style", "rpm", "effic_pct", "run_min", "stop_min", "product_kpick",
        "warp_top_ct", "warp_top_min", "warp_ct", "warp_min", "weft_ct", "weft_min",
        "unselect_ct", "unselect_min", "total_ct", "stop_ct_raw", "stop_tm_raw"]


def main():
    full = "--all" in sys.argv
    db = sqlite3.connect(DB)
    db.executescript(SCHEMA)

    have = set() if full else {r[0] for r in db.execute("SELECT DISTINCT shift FROM shift_loom")}
    shifts = fact_api.list_shifts()
    todo = [s for s in shifts if s not in have]
    print(f"Смен на сервере FACT: {len(shifts)}, уже в базе: {len(have)}, качаю: {len(todo)}")

    added = 0
    for i, shift in enumerate(todo, 1):
        try:
            rows = fact_api.get_shift(shift)
        except Exception as e:  # смена может быть пустой или файл битый
            print(f"  {shift}: пропуск ({e})")
            continue
        db.executemany(
            f"INSERT OR REPLACE INTO shift_loom ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
            [[r[c] for c in COLS] for r in rows],
        )
        db.commit()
        added += len(rows)
        if i % 20 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}  последняя: {shift}")

    total, = db.execute("SELECT COUNT(*) FROM shift_loom").fetchone()
    first, last = db.execute("SELECT MIN(shift), MAX(shift) FROM shift_loom").fetchone()
    print(f"\nДобавлено строк: {added}. Всего в базе: {total} ({first} … {last})")
    db.close()


if __name__ == "__main__":
    main()
