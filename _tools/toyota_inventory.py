"""Инвентаризация сигналов только по локальному зеркалу Toyota, без сети.

    python toyota_inventory.py --mirror <папка factdata>

Выводит агрегаты, не содержимое файлов, имена персонала или адреса станков.
Единицы измерения не угадывает; числовые диапазоны остаются в формате Toyota.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re


def inventory(root):
    counts = Counter()
    numbers = defaultdict(list)
    rows = list((root / "opestate").glob("*/loom/*.txt"))
    records = 0
    for path in rows:
        fields = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"^([A-Za-z_][A-Za-z_0-9]*)[= ](.*)$", line)
            if match:
                fields[match[1]] = match[2]
        if not fields:
            continue
        records += 1
        for name, raw in fields.items():
            counts[name] += 1
            try:
                numbers[name].append(float(raw))
            except ValueError:
                pass
    signals = {}
    for name in sorted(counts):
        values = numbers[name]
        signals[name] = {"present": counts[name], "numeric": len(values)}
        if values:
            signals[name].update(min=min(values), max=max(values),
                                 nonzero=sum(value != 0 for value in values))
    families = {}
    for name in ("opestate", "shift-shift", "stop_history", "stop_event", "cloth",
                 "air_flow", "air_pressure", "pressure", "tension", "motor_watt",
                 "temp_humi", "work_anlys"):
        files = [path for path in (root / name).rglob("*") if path.is_file()]
        row = {"files": len(files), "bytes": sum(path.stat().st_size for path in files)}
        newest = root / name / "newdata.txt"
        if newest.is_file():
            lines = newest.read_text(encoding="utf-8", errors="replace").splitlines()
            row["timestamp_raw"] = lines[0] if lines else None
            row["rows"] = len(lines[1:])
            values = []
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) == 2:
                    try:
                        values.append(float(parts[1]))
                    except ValueError:
                        pass
            if values:
                row.update(min=min(values), max=max(values),
                           nonzero=sum(value != 0 for value in values))
        families[name] = row
    return {"scope": "local mirror, read only", "loom_files": len(rows),
            "loom_records": records, "fields": signals, "families": families}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mirror", required=True, type=Path)
    args = ap.parse_args()
    if not (args.mirror / "opestate").is_dir():
        raise SystemExit("Укажите локальную папку factdata с каталогом opestate")
    print(json.dumps(inventory(args.mirror), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
