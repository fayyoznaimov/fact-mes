"""Готовит данные производственного отчёта за день: пишет их в базу и в CSV для Excel.

    python make_excel_report.py 2026.09.11

Делает две вещи:
  1. складывает строки отчёта в таблицу report_daily базы fact.db — чтобы потом
     анализировать историю отчётов;
  2. выгружает rows-файл строго в порядке колонок вашего шаблона (A…AK),
     который затем заполняет fill_template.ps1.
"""
import argparse
import csv
import io
import json
import os
import re
import sqlite3
import sys
import zlib
from collections import Counter
from datetime import datetime, timedelta, timezone

from build_shift_report import parse_cloth, fact_meta, load_shifts

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "fact.db")
MIRROR = os.path.join(os.path.dirname(HERE), "factdata", "shift-shift")
SHOP_DB = os.path.join(os.path.dirname(HERE), "_app", "shop.db")

# Пряжа и её лот в колонке LOTO: одна ячейка на станок, поэтому подписываем, чей лот.
# Места пряжи (как типы компонентов 1С) и их подписи в колонке лотов:
# В — ворс, Г — грунт, У — уток, К — кромка, Кк — кромка кручёная, Кп — кромка
# полиэстер, Б — бордюр, Бк — бордюр кручёная, Бп — бордюр полиэстер.
LOT_LABELS = (("pile", "В"), ("ground", "Г"), ("weft1", "У"), ("weft2", "К"), ("hemply", "Кк"),
              ("hempoly", "Кп"), ("weft3", "Б"), ("fancyply", "Бк"), ("weft4", "Бп"))


SHOP_TZ = timezone(timedelta(hours=5))       # время цеха — Ташкент, без переходов


def running_speed(day, stride=3):
    """Скорость станка из FACT за сутки отчёта (07:00 — 07:00 следующего дня):
    самое частое значение Rpm минутных снимков, пока станок работает.

    Так обороты пишет ручной отчёт цеха (с панели станка): сверка 23.09 — у 30
    из 35 станков в пределах 5 об/мин. Среднее «прокидки / время работы» из
    сменного файла ниже на ~4 % (разгон и торможение), и 100 % выработки по нему
    занижалась. Снимков нет — {} (тогда отчёт берёт среднее из смен)."""
    if not os.path.exists(SHOP_DB):
        return {}
    start = datetime.strptime(day, "%Y.%m.%d").replace(hour=7, tzinfo=SHOP_TZ)
    a, b = int(start.timestamp()), int((start + timedelta(days=1)).timestamp())
    db = sqlite3.connect(f"file:{SHOP_DB}?mode=ro", uri=True, timeout=10)
    seen = {}
    try:
        rows = db.execute("SELECT data FROM machine_sample WHERE at >= ? AND at < ? ORDER BY at",
                          (a, b)).fetchall()
    except sqlite3.OperationalError:
        rows = []                   # архива снимков ещё нет
    finally:
        db.close()
    for (blob,) in rows[::stride]:  # каждый третий снимок — скорость меняется редко
        for loom, v in json.loads(zlib.decompress(blob)).items():
            if v.get("running") and v.get("rpm"):
                seen.setdefault(loom, Counter())[int(v["rpm"])] += 1
    return {loom: c.most_common(1)[0][0] for loom, c in seen.items()}


def loom_setups(day):
    """Заправка, введённая вручную в приложении: GSM, вес штуки, PPT, панели,
    пряжа и лот. Действует с дня заправки до следующей записи по станку."""
    if not os.path.exists(SHOP_DB):
        return {}
    db = sqlite3.connect(SHOP_DB)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT * FROM loom_setup s WHERE from_day <= ? AND from_day = ("
            " SELECT MAX(from_day) FROM loom_setup b WHERE b.loom = s.loom AND b.from_day <= ?)",
            (day, day)).fetchall()
    except sqlite3.OperationalError:
        rows = []                   # таблицы ещё нет — приложение не запускалось
    finally:
        db.close()
    return {r["loom"]: dict(r) for r in rows}


def loom_ppt(day, cloths):
    """PPT по счётчикам станка (_app/pptloom.py); без приложения рядом — пусто."""
    app = os.path.join(os.path.dirname(HERE), "_app")
    if app not in sys.path:
        sys.path.insert(0, app)
    try:
        import pptloom
        return pptloom.for_day(day, cloths)
    except Exception as e:          # отчёт важнее: без PPT по станку он всё равно строится
        print("  PPT по станку не посчитан: %s: %s" % (type(e).__name__, e))
        return {}


# Колонка пряжи техкарты 1С -> поле заправки.
# Место техкарты 1С -> место заправки: каждое своё, с лотом. В Excel 4 колонки утка:
# уток, кромка (с кручёной и полиэстером), бордюр (с кручёной), бордюр полиэстер.
PLAN_SLOTS = {"vors": "pile", "karenoy": "ground", "utog1": "weft1",
              "utog2": "weft2", "utog2p": "hemply", "utog2x": "hempoly",
              "utog3": "weft3", "utog3p": "fancyply", "utog4": "weft4"}


def plan_setups(day):
    """Заправка по плану цеха: на станке в этот день стоит заказ. Дизайн (как в
    плане: «D186/6» — дизайн/клиент), размер и GSM — из плана; у заказа есть
    техкарта 1С — из неё PPT, вес, панели, размер, GSM, пряжа и лоты. Ручной
    ввод главнее, техкарта главнее плана. Других источников нет: старый
    справочник по коду ткани (artikul_ref.json) отчёт больше не использует."""
    if not os.path.exists(SHOP_DB):
        return {}
    db = sqlite3.connect(SHOP_DB)
    db.row_factory = sqlite3.Row
    out = {}
    try:
        # Надбавка к расчётному весу штуки (угар краски), % — из настроек цеха.
        try:
            row = db.execute("SELECT value FROM setting WHERE key='weight_allowance_pct'").fetchone()
            allowance = float(row[0]) if row and row[0] not in (None, "") else 10.0
        except (sqlite3.OperationalError, ValueError):
            allowance = 10.0
        for r in db.execute(
                # Техкарта — именно того изделия заказа, что стоит в клетке: в одном
                # заказе 1С бывают десятки изделий с разными PPT, весом и пряжей.
                "SELECT p.loom, p.order_no, p.design, p.client, p.gsm plan_gsm, p.size plan_size,"
                " t.product_code, t.ppt, t.weight_kg, t.panels, t.gsm, t.size_cm, t.size card_size"
                " FROM loom_plan p LEFT JOIN tech_card t ON t.product_code = p.product_code"
                " AND t.order_number = p.order_no"
                " WHERE p.day = ?", (day,)):
            # Решение цеха: дизайн, размер и GSM — из 1С (изделие заказа по плану),
            # нет изделия 1С — из плана. PPT, вес штуки, пряжу и лоты вносят руками
            # (вкладка «Заправка»): ручные значения точнее — PPT по счётчикам станка
            # совпадает с ними, а не с 1С. Панели — из 1С, пока не введены руками.
            # Дизайн без клиента: «220100 TerryCloth 390» -> «TerryCloth», в плане
            # «D327/64» — дизайн D327, клиент 64.
            design = ""
            if r["product_code"]:
                design = re.sub(r"\s*\d{3,4}$", "", re.sub(r"^\d+\s*", "", r["product_code"])).strip()
            design = design or r["design"] or ""
            m = re.match(r"\s*(\d{2,3})", r["plan_size"] or "")
            # Вес штуки: ширина × длина (м) × GSM (г/м²) + надбавка на угар краски.
            # 70×140, 450 GSM: 0,7 × 1,4 × 450 = 441 г (как в 1С), +10 % = 0,485 кг.
            dims = re.search(r"(\d{2,3})\s*[*xх×X]\s*(\d{2,3})", r["card_size"] or r["plan_size"] or "")
            gsm = r["gsm"] or r["plan_gsm"]
            weight_calc = (round(int(dims.group(1)) * int(dims.group(2)) / 1e4 * gsm / 1000
                                 * (1 + allowance / 100), 4) if dims and gsm else None)
            out[r["loom"]] = {"panels": r["panels"], "gsm_1c": r["gsm"], "gsm_plan": r["plan_gsm"],
                              "weight_calc": weight_calc,
                              "design": design or None, "client": r["client"] or None,
                              "size_cm": r["size_cm"] or (int(m.group(1)) if m else None),
                              "order_no": r["order_no"], "_card": r["product_code"]}
        # Пряжа и лоты — из техкарты 1С, каждое место отдельно (ворс, грунт, уток,
        # кромка, бордюр…). Введённое руками во вкладке «Заправка» главнее.
        for s in out.values():
            if not s.get("_card"):
                continue
            for y in db.execute("SELECT slot, yarn_code, lot FROM tech_card_yarn"
                                " WHERE order_number=? AND product_code=?", (s["order_no"], s["_card"])):
                f = PLAN_SLOTS.get(y["slot"])
                if f:
                    s[f + "_yarn"], s[f + "_lot"] = y["yarn_code"], y["lot"]
    except sqlite3.OperationalError:
        pass                        # плана или техкарт ещё нет
    finally:
        db.close()
    return out

SCHEMA = """
CREATE TABLE IF NOT EXISTS report_daily (
    day TEXT NOT NULL, loom TEXT NOT NULL,
    sr INTEGER, size_cm INTEGER, rpm INTEGER, ppt REAL, weight_kg REAL, panels REAL,
    prod100_kg REAL, design TEXT, client TEXT, gsm REAL,
    yarns TEXT,                      -- пряжа и лоты по местам (JSON) — для приложения
    pile_count TEXT, ground_count TEXT, loto TEXT,
    weft1 TEXT, weft2 TEXT, weft3 TEXT, weft4 TEXT,
    eff_a REAL, eff_b REAL, eff_c REAL, eff_total REAL,
    pile_a INTEGER, pile_b INTEGER, pile_c INTEGER, pile_total INTEGER,
    weft_a INTEGER, weft_b INTEGER, weft_c INTEGER, weft_total INTEGER,
    ground_a INTEGER, ground_b INTEGER, ground_c INTEGER, ground_total INTEGER,
    other_a INTEGER, other_b INTEGER, other_c INTEGER, other_total INTEGER,
    picks REAL, achieved_kg REAL, cloth TEXT, art_found INTEGER,
    ppt_src TEXT,                    -- fact: PPT посчитан по счётчикам станка, руками не введён
    built_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (day, loom)
);
CREATE INDEX IF NOT EXISTS idx_report_day ON report_daily(day);
"""

# Порядок колонок листа TOYOTA: A…AK. Пустые строки — ячейки с формулами шаблона.
COLUMNS = ["sr", "size", "rpm", "ppt", "weight", "panels", "", "design", "gsm",
           "pile_count", "ground_count", "loto", "weft1", "weft2", "weft3", "weft4", "loom",
           "eff_a", "eff_b", "eff_c", "",
           "pile_a", "pile_b", "pile_c", "",
           "weft_a", "weft_b", "weft_c", "",
           "ground_a", "ground_b", "ground_c", "",
           "other_a", "other_b", "other_c", "other_total"]


def mending_for(day):
    """Среднее время одного останова по сменам, в секундах (ТЗ: время / количество).

    Отдельно по ворсу, утку и основе — из таблицы shift_full.
    """
    out = {}
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    for r in db.execute(
            "SELECT loom, letter, top_ct, top_stop_min, weft_ct, weft_stop_min,"
            " warp_ct, warp_stop_min FROM shift_full WHERE day=?", (day,)):
        slot = {"A": 0, "B": 1, "C": 2}.get(r["letter"])
        if slot is None:
            continue
        d = out.setdefault(r["loom"], {"vors": [""] * 3, "utog": [""] * 3, "karenoy": [""] * 3})
        for name, ct, tm in (("vors", r["top_ct"], r["top_stop_min"]),
                             ("utog", r["weft_ct"], r["weft_stop_min"]),
                             ("karenoy", r["warp_ct"], r["warp_stop_min"])):
            d[name][slot] = round(tm * 60 / ct) if ct else ""
    db.close()
    return out


def build(day):
    # Заправка (PPT, вес, панели, пряжа, лоты, GSM, размер) — только из техкарты 1С
    # изделия по плану и ручного ввода. Старый справочник по коду ткани со станка
    # (artikul_ref.json — снимок ручного отчёта за 11.09) не используем: код
    # набирают руками, и он часто остаётся от прежнего изделия.
    meta = {}
    for i in range(3):
        # Коды тканей берём из локального зеркала; сеть — только если файла нет,
        # иначе отчёт молча остаётся без артикулов, когда сервер недоступен.
        path = os.path.join(MIRROR, f"{day}.{i}.txt")
        if os.path.exists(path):
            for line in io.open(path, encoding="utf-8", errors="replace"):
                d = {}
                for field in line.split(","):
                    p = field.strip().split(" ", 1)
                    if len(p) == 2:
                        d[p[0]] = p[1]
                if "mac_name" in d:
                    meta.setdefault(d["mac_name"], d)
            continue
        # В сеть не ходим: работаем по зеркалу. Смены, которой в зеркале нет,
        # просто не будет в отчёте — иначе каждый пересчёт висит на таймаутах.
    if not meta:
        print("  ВНИМАНИЕ: коды тканей не найдены ни в зеркале, ни на сервере —"
              " артикулы в отчёте будут пустыми")
    per_loom = load_shifts(day, DB)
    if not per_loom:
        sys.exit(f"Нет данных за {day}")
    mend = mending_for(day)      # среднее время одного останова по сменам, сек
    speed = running_speed(day)   # обороты — как на панели станка, из снимков FACT
    manual = loom_setups(day)    # введённое вручную главнее техкарты заказа из плана,
    setups = plan_setups(day)    # техкарта — главнее справочника артикулов
    for loom, m in manual.items():
        s = setups.setdefault(loom, {})
        s.update({k: v for k, v in m.items() if v not in (None, "")})
    # PPT по станку — из счётчиков FACT (прокидки и ряды текущей ткани), когда
    # руками не введён. Только станки, считающие штукой ряд (D); у J штука — отрез.
    fact_ppt = loom_ppt(day, {loom: (meta.get(loom) or {}).get("cloth", "") for loom in per_loom})

    out = []
    for loom, shifts in per_loom.items():
        cloth = (meta.get(loom) or {}).get("cloth", "")
        art = {}
        s = setups.get(loom) or {}
        if s:
            # GSM — из 1С; нет изделия 1С — введённый руками, иначе из плана.
            s["gsm"] = s.get("gsm_1c") or s.get("gsm") or s.get("gsm_plan")
            # Вес штуки — введённый руками, иначе расчётный (размер × GSM + угар).
            s["weight_kg"] = s.get("weight_kg") or s.get("weight_calc")
        size = s.get("size_cm")
        if s:
            for field, ref_field in (("ppt", "ppt"), ("weight_kg", "weight_kg"), ("panels", "panels"),
                                     ("gsm", "gsm"), ("pile_yarn", "pile_count"),
                                     ("ground_yarn", "ground_count")):
                if s.get(field) not in (None, ""):
                    art[ref_field] = s[field]
            # В Excel 4 колонки утка: уток, кромка (+ кручёная, полиэстер), бордюр
            # (+ кручёная), бордюр полиэстер. В приложении — каждое место отдельно.
            join = lambda *ys: " + ".join(v for v in (s.get(y + "_yarn") for y in ys) if v)
            art["weft"] = [join("weft1"), join("weft2", "hemply", "hempoly"),
                           join("weft3", "fancyply"), join("weft4")]
            lots = " ".join(f"{lbl}:{s[y + '_lot']}" for y, lbl in LOT_LABELS if s.get(y + "_lot"))
            if lots:
                art["loto"] = lots
            m_ = manual.get(loom) or {}
            art["yarns"] = [{"slot": y, "yarn": s.get(y + "_yarn"), "lot": s.get(y + "_lot"),
                             "manual": bool(m_.get(y + "_yarn") or m_.get(y + "_lot"))}
                            for y, _ in LOT_LABELS if s.get(y + "_yarn") or s.get(y + "_lot")]

        g = lambda L, k: (shifts[L][k] if L in shifts else 0)
        worked = [L for L in "ABC" if g(L, "run_min") > 5]
        eff = [round(g(L, "effic_pct")) if L in worked else None for L in "ABC"]
        done = [e for e in eff if e is not None]
        pile = [g(L, "warp_top_ct") for L in "ABC"]
        weft = [g(L, "weft_ct") for L in "ABC"]
        grnd = [g(L, "warp_ct") for L in "ABC"]
        # «Прочие остановы» в ручном отчёте цеха — ручные остановы и отключения
        # питания (категории FACT 8 и 9 из 13), а не «неотобранные», как было.
        def manual_stops(L):
            v = [int(x) for x in re.findall(r"-?\d+", (shifts.get(L) or {}).get("stop_ct_raw") or "")]
            return v[8] + v[9] if len(v) >= 10 else 0
        other = [manual_stops(L) for L in "ABC"]
        picks = sum(g(L, "product_kpick") for L in "ABC") * 1000
        rpms = [g(L, "rpm") for L in "ABC" if g(L, "rpm")]
        rpm_src = "fact" if speed.get(loom) else "avg"
        rpm = speed.get(loom) or (round(sum(rpms) / len(rpms)) if rpms else 0)

        ppt, wt, pn = art.get("ppt"), art.get("weight_kg"), art.get("panels")
        ppt_src = None
        if not ppt and fact_ppt.get(loom):
            ppt, ppt_src = fact_ppt[loom]["ppt"], "fact"
        prod100 = round(pn * wt * (rpm * 480 * len(worked) / ppt), 1) if (ppt and wt and pn and rpm and worked) else None
        achieved = round(pn * wt * (picks / ppt), 1) if (ppt and wt and pn) else None

        out.append({
            "loom": loom, "cloth": cloth,
            # Размер пишем как в вашем файле — текстом «70 CM», иначе колонка
            # с её форматом показывает решётки вместо числа.
            "size": f"{size} CM" if size else "",
            "rpm": rpm, "rpm_src": rpm_src, "ppt": ppt, "ppt_src": ppt_src, "weight": wt, "panels": pn,
            # Дизайн — из плана цеха или заказа 1С («D186/6»: дизайн/клиент). Разбор
            # кода ткани со станка даёт не тот артикул, поэтому без плана — пусто.
            "prod100": prod100, "design": s.get("design") or "", "client": s.get("client") or "",
            "yarns": art.get("yarns") or [],
            "gsm": art.get("gsm") or "",
            "pile_count": art.get("pile_count", ""), "ground_count": art.get("ground_count", ""),
            "loto": art.get("loto", ""),
            **{f"weft{i+1}": (art.get("weft") or ["", "", "", ""])[i] for i in range(4)},
            "eff_a": eff[0], "eff_b": eff[1], "eff_c": eff[2],
            "eff_total": round(sum(done) / len(done), 1) if done else 0,
            "pile_a": pile[0], "pile_b": pile[1], "pile_c": pile[2], "pile_total": sum(pile),
            "weft_a": weft[0], "weft_b": weft[1], "weft_c": weft[2], "weft_total": sum(weft),
            "ground_a": grnd[0], "ground_b": grnd[1], "ground_c": grnd[2], "ground_total": sum(grnd),
            "other_a": other[0], "other_b": other[1], "other_c": other[2], "other_total": sum(other),
            # 1 — заправка есть (техкарта 1С или ручной ввод), 0 — нет техкарты 1С.
            "picks": picks, "achieved": achieved, "art_found": 1 if art.get("ppt") else 0,
            "mending": mend.get(loom, {}),
        })

    out.sort(key=lambda r: r["weft_total"], reverse=True)     # как в вашем файле
    # Sr# в ручном отчёте — постоянный номер станка, а не место в сортировке:
    # J1…J28 — 1…28, D1…D12 — 29…40.
    order = sorted(out, key=lambda r: loom_key(r["loom"]))
    for i, r in enumerate(order, 1):
        r["sr"] = i
    return out


def loom_key(loom):
    m = re.match(r"([A-Za-z]*)(\d+)", loom or "")
    if not m:
        return (9, 0, loom or "")
    return ({"J": 0, "D": 1}.get(m.group(1).upper(), 2), int(m.group(2)), loom)


def save_db(day, rows):
    db = sqlite3.connect(DB)
    db.executescript(SCHEMA)
    # Клиент — отдельно от дизайна (раньше писали «D327/64» одной строкой).
    have = [c[1] for c in db.execute("PRAGMA table_info(report_daily)")]
    for col in ("client", "yarns", "ppt_src"):           # клиент — отдельно от дизайна; пряжа по местам
        if col not in have:
            db.execute("ALTER TABLE report_daily ADD COLUMN %s TEXT" % col)
    db.execute("DELETE FROM report_daily WHERE day=?", (day,))
    db.executemany(
        "INSERT INTO report_daily (day, loom, sr, size_cm, rpm, ppt, weight_kg, panels, prod100_kg,"
        " design, client, yarns, gsm, pile_count, ground_count, loto, weft1, weft2, weft3, weft4,"
        " eff_a, eff_b, eff_c, eff_total, pile_a, pile_b, pile_c, pile_total,"
        " weft_a, weft_b, weft_c, weft_total, ground_a, ground_b, ground_c, ground_total,"
        " other_a, other_b, other_c, other_total, picks, achieved_kg, cloth, art_found, ppt_src)"
        " VALUES (" + ",".join("?" * 45) + ")",
        # В лист размер идёт текстом («70 CM»), в базу — числом, чтобы по нему можно было считать.
        [(day, r["loom"], r["sr"], int(re.sub(r"\D", "", str(r["size"])) or 0) or None,
          r["rpm"], r["ppt"], r["weight"], r["panels"],
          r["prod100"], r["design"], r.get("client") or None,
          json.dumps(r.get("yarns") or [], ensure_ascii=False), r["gsm"] or None,
          r["pile_count"], r["ground_count"], r["loto"],
          r["weft1"], r["weft2"], r["weft3"], r["weft4"],
          r["eff_a"], r["eff_b"], r["eff_c"], r["eff_total"],
          r["pile_a"], r["pile_b"], r["pile_c"], r["pile_total"],
          r["weft_a"], r["weft_b"], r["weft_c"], r["weft_total"],
          r["ground_a"], r["ground_b"], r["ground_c"], r["ground_total"],
          r["other_a"], r["other_b"], r["other_c"], r["other_total"],
          r["picks"], r["achieved"], r["cloth"], r["art_found"], r.get("ppt_src")) for r in rows])
    db.commit()
    n = db.execute("SELECT COUNT(DISTINCT day) FROM report_daily").fetchone()[0]
    db.close()
    return n


def write_rows_csv(day, rows, path):
    with io.open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        for r in rows:
            line = ["" if c == "" else ("" if r.get(c) is None else r.get(c)) for c in COLUMNS]
            # Служебные колонки 38 и 39: в лист не пишутся, нужны для шапки отчёта
            # (Achieved Production) — заполнение шаблона берёт их отсюда.
            line += [r.get("picks") or "", r.get("achieved") or ""]
            # Колонки 41-49: среднее время одного останова по сменам (сек) —
            # ворс A/B/C, уток A/B/C, основа A/B/C. Идут в лист в AR:AZ.
            m = r.get("mending") or {}
            for name in ("vors", "utog", "karenoy"):
                line += (m.get(name) or ["", "", ""])
            w.writerow(line)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("day", help="дата, например 2026.09.11")
    a = ap.parse_args()
    rows = build(a.day)
    days = save_db(a.day, rows)
    csv_path = write_rows_csv(a.day, rows, os.path.join(HERE, f"_rows_{a.day}.csv"))
    total100 = sum(r["prod100"] for r in rows if r["prod100"])
    totalfact = sum(r["achieved"] for r in rows if r["achieved"])
    print(f"Данные за {a.day}: {len(rows)} станков")
    print(f"  в базе отчётов теперь дней: {days}")
    print(f"  100% {total100:.0f} кг, факт {totalfact:.0f} кг, "
          f"эффективность {100*totalfact/total100:.1f}%" if total100 else "")
    missing = [r["loom"] for r in rows if not r["art_found"]]
    if missing:
        print(f"  без артикула в справочнике: {', '.join(missing)}")
    print(f"  файл для Excel: {os.path.basename(csv_path)}")
