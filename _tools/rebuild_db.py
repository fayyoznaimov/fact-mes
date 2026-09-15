"""Пересобирает базу смен из локального зеркала FACT — со всеми полями для отчёта.

Разбор общий с приложением (`_app/ingest.py`): тот же код дописывает свежие
смены на лету в сборщике, здесь — вся история разом. Считается:
  • время устранения обрыва   = время останова − время ожидания оператора
  • время ожидания оператора  = сколько станок стоял, пока к нему не подошли
  • MTTR по утку, ворсу и основе
  • выработку в уточинах, метрах и штуках (для расчёта зарплаты)

    python rebuild_db.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "_app"))

import ingest    # noqa: E402
import storage   # noqa: E402

MIRROR = os.path.join(storage.FACTDATA, "shift-shift")


def main():
    db = storage.fact_rw()
    ingest.ensure_schema(db)
    files = sorted(f for f in os.listdir(MIRROR) if ingest.SHIFT_FILE.match(f))
    print(f"Файлов смен в зеркале: {len(files)}")

    total = 0
    for fn in files:
        text = io.open(os.path.join(MIRROR, fn), encoding="utf-8", errors="replace").read()
        total += ingest.upsert_shift(db, fn[:-4], text)
    db.commit()

    n_shift, n_loom, n_day = db.execute(
        "SELECT COUNT(DISTINCT shift), COUNT(DISTINCT loom), COUNT(DISTINCT day) FROM shift_full").fetchone()
    print(f"Записано строк: {total} — {n_shift} смен, {n_loom} станков, {n_day} дней")
    print("\nПроверка на смене 2026.09.12.A (сверьте с отчётом Toyota):")
    for r in db.execute(
            "SELECT loom, warp_ct+top_ct, ROUND((warp_fix_min+top_fix_min)/(warp_ct+top_ct)*60) ,"
            " weft_ct, ROUND(weft_mttr_sec), ROUND(wait_total_min)"
            " FROM shift_full WHERE shift='2026.09.12.0' AND loom IN ('D1','D2','J10') ORDER BY loom"):
        print(f"  {r[0]:4} основа+ворс {r[1]:3} шт, MTTR {r[2]:3} сек | "
              f"уток {r[3]:3} шт, MTTR {r[4]:3} сек | ожидание оператора {r[5]:3} мин")
    db.close()


if __name__ == "__main__":
    main()
