"""Completeness of calculated values, independent of production formulas.

Coverage is measured against available source rows, not expected work shifts.
Zero is a known value; None is an unavailable calculation.
"""
import math


def coverage(values):
    values = list(values)
    known = [v for v in values if isinstance(v, (int, float))
             and not isinstance(v, bool) and math.isfinite(v)]
    total, count = len(values), len(known)
    return {"status": "complete" if count and count == total else
            "partial" if count else "unavailable", "known": count, "total": total,
            "value": sum(known) if count else None}


def merge(parts):
    parts = list(parts)
    known, total = sum(p["known"] for p in parts), sum(p["total"] for p in parts)
    return {"status": "complete" if known and known == total else
            "partial" if known else "unavailable", "known": known, "total": total,
            "value": sum(p["value"] or 0 for p in parts) if known else None}


def note(q, unit="станко-дней"):
    if q["status"] == "complete":
        return ""
    if not q["known"]:
        return "Не рассчитано: нет исходных данных для %d %s" % (q["total"], unit)
    return "Частично: рассчитано %d из %d %s" % (q["known"], q["total"], unit)
