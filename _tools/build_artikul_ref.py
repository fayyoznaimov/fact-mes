"""Строит справочник артикулов для производственного отчёта.

Заправочные данные (PPT, вес штуки, число панелей, пряжа) в FACT не хранятся —
они берутся из вашего отчёта. Ключ справочника — фактический код ткани из FACT
(поле cloth), потому что дизайн в отчёте ставят по плану и он расходится с тем,
что реально стоит на станке.

    python build_artikul_ref.py --report artikul_ref_raw.csv --day 2026.09.11
"""
import argparse
import csv
import io
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MIRROR = os.path.join(os.path.dirname(HERE), "factdata", "shift-shift")
FACT = "http://172.0.30.9"

norm_cloth = lambda c: re.sub(r"[^A-Z0-9]", "", (c or "").replace("%20", "").upper())


def read_shift(shift):
    """Строки смены: из локального зеркала, иначе с сервера FACT."""
    path = os.path.join(MIRROR, f"{shift}.txt")
    if os.path.exists(path):
        text = io.open(path, encoding="utf-8", errors="replace").read()
    else:
        with urllib.request.urlopen(f"{FACT}/factdata/shift-shift/{shift}.txt", timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
    out = {}
    for line in text.splitlines():
        d = {}
        for field in line.split(","):
            p = field.strip().split(" ", 1)
            if len(p) == 2:
                d[p[0]] = p[1]
        if "mac_name" in d:
            out[d["mac_name"]] = d
    return out


def num(v):
    v = (v or "").strip().replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=os.path.join(HERE, "artikul_ref_raw.csv"))
    ap.add_argument("--day", required=True, help="дата отчёта, например 2026.09.11")
    ap.add_argument("--out", default=os.path.join(HERE, "artikul_ref.json"))
    a = ap.parse_args()

    cloth_by_loom = {}
    for idx in range(3):
        for loom, d in read_shift(f"{a.day}.{idx}").items():
            cloth_by_loom.setdefault(loom, d.get("cloth", ""))

    ref = {}
    if os.path.exists(a.out):
        ref = json.load(io.open(a.out, encoding="utf-8"))
    before = len(ref)

    added = skipped = 0
    for r in csv.DictReader(io.open(a.report, encoding="utf-8-sig"), delimiter=";"):
        loom = (r.get("loom") or "").strip()
        cloth = cloth_by_loom.get(loom)
        if not loom or not cloth:
            skipped += 1
            continue
        key = "CLOTH|" + norm_cloth(cloth)
        ref[key] = {
            "cloth": cloth, "loom_seen": loom, "day": a.day,
            "design_report": (r.get("design") or "").strip(),
            "size_cm": int(re.sub(r"[^\d]", "", r.get("size") or "0") or 0),
            "ppt": num(r.get("ppt")), "weight_kg": num(r.get("weight")),
            "panels": num(r.get("panels")), "gsm": num(r.get("gsm")),
            "rpm_plan": num(r.get("rpm")),
            "pile_count": (r.get("pile_cnt") or "").strip(),
            "ground_count": (r.get("ground_cnt") or "").strip(),
            "loto": (r.get("loto") or "").strip(),
            "weft": [(r.get(f"weft{i}") or "").strip() for i in (1, 2, 3, 4)],
            "source": f"отчёт {a.day}, станок {loom}",
        }
        added += 1

    json.dump(ref, io.open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Справочник: {a.out}")
    print(f"  было записей: {before}, добавлено по коду ткани: {added}, стало: {len(ref)}")
    if skipped:
        print(f"  пропущено строк отчёта (станок не найден в FACT за {a.day}): {skipped}")
    print("\nВажно: заправочные данные привязаны к тому коду ткани, который стоял на станке")
    print("в этот день. Если в отчёте строка была заполнена по плановому артикулу,")
    print("проверьте PPT и вес у этих записей.")


if __name__ == "__main__":
    main()
