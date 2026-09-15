"""Клиент для чтения данных Toyota FACT по HTTP (только чтение).

Использование:
    python fact_api.py                    # список доступных смен
    python fact_api.py 2026.09.12.0       # итоги смены -> таблица + CSV
    python fact_api.py current            # текущее состояние станков
"""
import csv
import re
import sys
import urllib.request

FACT = "http://172.0.30.9"
SHIFT_LEN_MIN = 480

# Индексы категорий в stop_ct / stop_tm, подтверждённые сверкой с отчётом FACT.
# Остальные индексы FACT суммирует в столбец UnSelect.
STOP_WARP_TOP, STOP_WARP, STOP_WEFT = 0, 1, 5


def _get(path):
    with urllib.request.urlopen(FACT + path, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _parse_line(line):
    """'key v1 v2,key2 v' -> {'key': ['v1','v2'], 'key2': ['v']}"""
    rec = {}
    for field in line.strip().strip(",").split(","):
        parts = field.strip().split(" ")
        if parts and parts[0]:
            rec[parts[0]] = parts[1:]
    return rec


def list_shifts():
    html = _get("/factdata/shift-shift/")
    return sorted(set(re.findall(r'href="(\d{4}\.\d\d\.\d\d\.\d)\.txt"', html)))


def get_shift_raw(shift_id):
    text = _get(f"/factdata/shift-shift/{shift_id}.txt")
    return [_parse_line(l) for l in text.splitlines() if l.strip()]


def get_shift(shift_id):
    """Итоги смены по станкам, посчитанные по формулам макроса shiftreport.xlsm."""
    rows = []
    for r in get_shift_raw(shift_id):
        f = lambda k, i=0: float(r[k][i]) if k in r and len(r[k]) > i and r[k][i] else 0.0
        run = f("run_tm")
        # Простой в отчёте FACT = большее из суммы остановов и времени «без работы» (isc_tm, последний элемент):
        # так в простой попадают периоды без связи со станком.
        stop = max(f("stop_ttm"), float(r["isc_tm"][-1]) if r.get("isc_tm") else 0.0)
        prod = f("seisan")  # тыс. уточин
        ct = [int(float(x)) for x in r.get("stop_ct", [])]
        tm = [float(x) for x in r.get("stop_tm", [])]
        other = [i for i in range(len(ct)) if i not in (STOP_WARP_TOP, STOP_WARP, STOP_WEFT)]
        rows.append({
            "shift": shift_id,
            "loom": r["mac_name"][0],
            "style": " ".join(r.get("style", [])),
            "rpm": 0 if run < 5 else round(1000 * prod / run),
            "effic_pct": 0.0 if run == 0 else round(100 * run / (run + stop), 1),
            "run_min": run,
            "stop_min": round(stop, 3),
            "product_kpick": prod,
            "warp_top_ct": ct[STOP_WARP_TOP], "warp_top_min": tm[STOP_WARP_TOP],
            "warp_ct": ct[STOP_WARP], "warp_min": tm[STOP_WARP],
            "weft_ct": ct[STOP_WEFT], "weft_min": tm[STOP_WEFT],
            "unselect_ct": sum(ct[i] for i in other), "unselect_min": round(sum(tm[i] for i in other), 3),
            "total_ct": sum(ct),
            "stop_ct_raw": " ".join(map(str, ct)),
            "stop_tm_raw": " ".join(map(str, tm)),
        })
    return rows


def get_current():
    return [_parse_line(l) for l in _get("/factdata/current/current.txt").splitlines() if l.strip()]


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg is None:
        print("\n".join(list_shifts()))
    elif arg == "current":
        for r in get_current():
            print(r["mac_name"][0], r["shift"][0], " ".join(r.get("style", [])), "doff_fcst", r.get("doff_fcst", ["?"])[0])
    else:
        rows = get_shift(arg)
        out = f"fact_shift_{arg}.csv"
        with open(out, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=rows[0].keys(), delimiter=";")
            w.writeheader()
            w.writerows(rows)
        for r in rows:
            print(f'{r["loom"]:4} {r["style"]:10} RPM {r["rpm"]:4}  КПД {r["effic_pct"]:5.1f}%  '
                  f'уток {r["weft_ct"]:3}  основа {r["warp_ct"]:3}  верх.навой {r["warp_top_ct"]:3}  прочие {r["unselect_ct"]:3}')
        print(f"\nСохранено: {out}")
