"""Справочник пряжи: одно написание на одну пряжу.

В отчётах одна и та же пряжа записана по-разному: «16/1 SPUN» и «16/1SPUN»,
«20/2 spun» и «20/2spun». Для человека это одно и то же, для отбора и сравнения
— разные пряжи. Здесь каждая пряжа записана один раз, а при вводе любое
написание приводится к справочному: без пробелов, регистра и лишних знаков
«16/1spun» находит «16/1 SPUN».

Пряжи, которой нет в справочнике, в заправку не записываем: сначала её
добавляют в справочник (одной кнопкой), потом она доступна всем станкам.
"""
import io
import json
import os
import re

from storage import TOOLS_DIR, fact, shop

KINDS = ("", "pile", "ground", "weft")
FIELDS = ("pile_yarn", "ground_yarn", "weft1_yarn", "weft2_yarn", "hemply_yarn", "hempoly_yarn",
          "weft3_yarn", "fancyply_yarn", "weft4_yarn")
MAX_DAYS = 62


def canon(name):
    """«20/2spun» -> «20/2 SPUN», «12 / 1» -> «12/1», «300den» -> «300 DEN»."""
    s = re.sub(r"\s+", " ", str(name or "").strip().upper())
    s = re.sub(r"\s*/\s*", "/", s)
    return re.sub(r"^(\d+(?:/\d+)?)\s*([A-ZА-ЯЁ])", r"\1 \2", s)


def key(name):
    return canon(name).replace(" ", "")


def all_yarns():
    db = shop()
    rows = [dict(r) for r in db.execute(
        "SELECT id, name, key, kind, active FROM yarn ORDER BY active DESC, name")]
    db.close()
    return rows


# Место заправки -> место техкарты 1С и вид пряжи справочника.
SLOT_1C = {"pile": "vors", "ground": "karenoy", "weft1": "utog1", "weft2": "utog2",
           "hemply": "utog2p", "hempoly": "utog2x", "weft3": "utog3", "fancyply": "utog3p",
           "weft4": "utog4"}
# Какой вид пряжи (по справочнику 1С, «Тип основа пряжи») годится на место.
# Кручёная и полиэстер на кромке и бордюре — это обычно x/2 основы, поэтому там и основа.
SLOT_KINDS = {"pile": ("pile",), "ground": ("ground",), "weft1": ("weft",), "weft2": ("weft",),
              "weft3": ("weft",), "hemply": ("ground", "weft"), "hempoly": ("ground", "weft"),
              "fancyply": ("ground", "weft"), "weft4": ("ground", "weft")}


def by_slot():
    """Отбор пряжи для каждого места заправки: {место: [{name, lots, from_1c}]}.

    Пряжа — только того вида, что годится на место: по партиям справочника 1С
    (одна пряжа бывает и ворсом, и утком — тогда она в обоих списках), для пряжи
    без партий — по виду в справочнике приложения. Сверху — что 1С ставит на это
    место в техкартах (чаще — выше). Лоты: сначала из техкарт этого места, потом
    партии этого вида из справочника 1С, новые — раньше."""
    import yarnref
    db = shop()
    try:
        names = {r["key"]: r["name"] for r in db.execute("SELECT key, name FROM yarn WHERE active=1")}
        dir_kind = {r["name"]: r["kind"] or "" for r in db.execute("SELECT name, kind FROM yarn WHERE active=1")}
        used = {}
        try:
            for r in db.execute("SELECT slot, yarn_code, lot, COUNT(*) n FROM tech_card_yarn"
                                " GROUP BY slot, yarn_code, lot ORDER BY n DESC"):
                used.setdefault(r["slot"], []).append((r["yarn_code"], r["lot"], r["n"]))
        except Exception:
            pass
    finally:
        db.close()
    stock = {}                          # пряжа -> [(лот, вид, поставщик)] из справочника 1С
    for yarn, lots in yarnref.lots_by_yarn().items():
        name = names.get(key(yarn))
        if name:
            stock.setdefault(name, []).extend((l["lot"], l["kind"], l["supplier"]) for l in lots)
    # Есть справочник 1С — в списках только пряжа с партиями в 1С (и то, что стоит в
    # техкартах); старые написания из прежних отчётов («20/2», «15023») не предлагаем.
    # Образцы — в конце списка лотов.
    for name in stock:
        stock[name].sort(key=lambda x: "ОБРАЗЕЦ" in (x[0] or "").upper())
    out = {}
    for slot, s1c in SLOT_1C.items():
        ok = SLOT_KINDS[slot]
        fits = lambda name: (any(k in ok for _, k, _ in stock[name]) if name in stock
                             else not stock and dir_kind.get(name) in ok)
        items, idx = [], {}
        for code, lot, n in used.get(s1c, []):
            name = names.get(key(code))
            if not name:
                continue
            if name not in idx:
                idx[name] = {"name": name, "lots": [], "suppliers": {}, "n": 0, "from_1c": True}
                items.append(idx[name])
            idx[name]["n"] += n
            if lot and lot not in idx[name]["lots"]:
                idx[name]["lots"].append(lot)
        items.sort(key=lambda x: -x["n"])
        for name in sorted(n for n in names.values() if fits(n) and n not in idx):
            idx[name] = {"name": name, "lots": [], "suppliers": {}, "n": 0, "from_1c": False}
            items.append(idx[name])
        for it in items:
            for lot, kind, supplier in stock.get(it["name"], []):
                if kind in ok and lot not in it["lots"]:
                    it["lots"].append(lot)
                if supplier:
                    it["suppliers"].setdefault(lot, supplier)
        out[slot] = items
    return out


def add(name, kind=""):
    """Добавить пряжу. Если такая уже есть (в любом написании) — вернуть её."""
    c = canon(name)
    if not c or c == "0":
        raise ValueError("пустое название пряжи")
    if len(c) > 40:
        raise ValueError("название пряжи длиннее 40 знаков")
    kind = kind if kind in KINDS else ""
    db = shop()
    try:
        cur = db.execute("SELECT name, active FROM yarn WHERE key=?", (key(c),)).fetchone()
        if cur:
            if not cur["active"]:
                db.execute("UPDATE yarn SET active=1 WHERE key=?", (key(c),))
                db.commit()
                return {"name": cur["name"], "restored": True}
            return {"name": cur["name"], "exists": True}
        db.execute("INSERT INTO yarn (name, key, kind) VALUES (?,?,?)", (c, key(c), kind))
        db.commit()
    finally:
        db.close()
    return {"name": c}


def update(yid, name=None, kind=None, active=None):
    """Переименовать, указать вид или скрыть. Переименование переписывает и
    введённые заправки — иначе на станках осталось бы старое написание."""
    rebuild_from = None
    db = shop()
    try:
        cur = db.execute("SELECT * FROM yarn WHERE id=?", (yid,)).fetchone()
        if not cur:
            raise ValueError("пряжа не найдена")
        if kind is not None and kind in KINDS:
            db.execute("UPDATE yarn SET kind=? WHERE id=?", (kind, yid))
        if active is not None:
            db.execute("UPDATE yarn SET active=? WHERE id=?", (1 if active else 0, yid))
        if name is not None:
            c = canon(name)
            if not c:
                raise ValueError("пустое название пряжи")
            if c != cur["name"]:
                if db.execute("SELECT 1 FROM yarn WHERE key=? AND id<>?", (key(c), yid)).fetchone():
                    raise ValueError("«%s» уже есть в справочнике" % c)
                db.execute("UPDATE yarn SET name=?, key=? WHERE id=?", (c, key(c), yid))
                touched = 0
                for f in FIELDS:
                    touched += db.execute("UPDATE loom_setup SET %s=? WHERE %s=?" % (f, f),
                                          (c, cur["name"])).rowcount
                if touched:
                    rebuild_from = db.execute(
                        "SELECT MIN(from_day) FROM loom_setup WHERE ? IN (%s)" % ", ".join(FIELDS),
                        (c,)).fetchone()[0]
        db.commit()
    finally:
        db.close()
    days = []
    if rebuild_from:
        import reports
        with fact() as f:
            want = [r[0] for r in f.execute(
                "SELECT DISTINCT day FROM shift_full WHERE day >= ? ORDER BY day LIMIT ?",
                (rebuild_from, MAX_DAYS))]
        days = reports.rebuild_daily_reports(want)
    return {"ok": True, "days": days}


def resolve(name):
    """Справочное написание пряжи; пусто — None; незнакомая — ошибка."""
    c = canon(name)
    if not c or c == "0":
        return None
    db = shop()
    r = db.execute("SELECT name, active FROM yarn WHERE key=?", (key(c),)).fetchone()
    db.close()
    if not r:
        raise ValueError("пряжи «%s» нет в справочнике — выберите из списка или добавьте её" % c)
    if not r["active"]:
        raise ValueError("пряжа «%s» скрыта в справочнике" % r["name"])
    return r["name"]


def seed_if_empty():
    """Первый справочник — из того, что уже написано в отчётах, справочнике
    артикулов и техкартах 1С. Разные написания одной пряжи сливаются в одно."""
    db = shop()
    try:
        if db.execute("SELECT 1 FROM yarn LIMIT 1").fetchone():
            return 0
        found = {}

        def put(v, kind):
            c = canon(v)
            if c and c != "0" and "ЛОТ" not in c and len(c) <= 40:
                found.setdefault(key(c), (c, kind))

        cols = (("pile_count", "pile"), ("ground_count", "ground"), ("weft1", "weft"),
                ("weft2", "weft"), ("weft3", "weft"), ("weft4", "weft"))
        with fact() as f:
            for col, kind in cols:
                for (v,) in f.execute("SELECT DISTINCT %s FROM report_daily" % col):
                    put(v, kind)
        path = os.path.join(TOOLS_DIR, "artikul_ref.json")
        if os.path.exists(path):
            for a in json.load(io.open(path, encoding="utf-8")).values():
                put(a.get("pile_count"), "pile")
                put(a.get("ground_count"), "ground")
                for w in a.get("weft") or []:
                    put(w, "weft")
        for (v,) in db.execute("SELECT DISTINCT yarn_code FROM tech_card_yarn"):
            put(v, "")
        db.executemany("INSERT OR IGNORE INTO yarn (name, key, kind) VALUES (?,?,?)",
                       [(n, k, kind) for k, (n, kind) in found.items()])
        db.commit()
        return len(found)
    finally:
        db.close()
