"""Люди цеха: справочник, назначения на смену и документы расстановки.

Оператор привязывается к станкам на смену — от этого считается его зарплата и
KPI. Мастер и мастерицы привязываются к смене целиком.

На каждый день заводятся три документа расстановки — смены A, B и C. Сборщик
создаёт их сам в начале дня и заполняет тем, что было в ту же смену в прошлый
раз (бригады стоят на своих станках); мастер правит и утверждает.
"""
import os
import re
from datetime import datetime

from reports import shift_rows
from storage import MIRROR_OPERATOR, shop

ROLES = {"operator": "оператор", "master": "мастерица", "foreman": "мастер"}
SHIFT_HOURS = {"A": "07:00–15:00", "B": "15:00–23:00", "C": "23:00–07:00"}


def list_operators():
    db = shop()
    rows = [dict(r) for r in db.execute("SELECT * FROM operator ORDER BY role, name")]
    db.close()
    return rows


def save_operator(body):
    if body.get("role", "operator") not in ROLES:
        raise ValueError("роль: оператор, мастерица или мастер")
    db = shop()
    if body.get("id"):
        db.execute("UPDATE operator SET code=?, name=?, role=?, active=? WHERE id=?",
                   (body["code"].strip(), body["name"].strip(), body.get("role", "operator"),
                    1 if body.get("active", True) else 0, body["id"]))
    else:
        db.execute("INSERT INTO operator (code, name, role) VALUES (?,?,?)",
                   (body["code"].strip(), body["name"].strip(), body.get("role", "operator")))
    db.commit()
    db.close()


def delete_operator(op_id):
    db = shop()
    db.execute("DELETE FROM operator WHERE id=?", (op_id,))
    db.commit()
    db.close()


def get_assignments(day, shift):
    db = shop()
    a = [dict(r) for r in db.execute(
        "SELECT loom, operator_id FROM assignment WHERE day=? AND shift=?", (day, shift))]
    m = [r["operator_id"] for r in db.execute(
        "SELECT operator_id FROM shift_master WHERE day=? AND shift=?", (day, shift))]
    db.close()
    looms = [r["loom"] for r in shift_rows(day or "", shift or "")]
    return {"assignments": a, "masters": m, "looms": looms}


def save_assignments(body):
    day, sh = body["day"], body["shift"]
    db = shop()
    if "assignments" in body:
        db.execute("DELETE FROM assignment WHERE day=? AND shift=?", (day, sh))
        db.executemany(
            "INSERT INTO assignment (day, shift, loom, operator_id) VALUES (?,?,?,?)",
            [(day, sh, a["loom"], a["operator_id"]) for a in body["assignments"]
             if a.get("operator_id")])
    if "masters" in body:
        db.execute("DELETE FROM shift_master WHERE day=? AND shift=?", (day, sh))
        db.executemany(
            "INSERT INTO shift_master (day, shift, operator_id) VALUES (?,?,?)",
            [(day, sh, m) for m in body["masters"]])
    db.commit()
    db.close()


def assign_one(day, shift, loom, operator_id):
    """Назначить оператора на один станок (или снять, если operator_id пуст).

    Нужно, чтобы мастер назначал прямо в таблице выработки, не пересохраняя
    всю смену целиком.
    """
    db = shop()
    if operator_id:
        db.execute("INSERT OR REPLACE INTO assignment (day, shift, loom, operator_id)"
                   " VALUES (?,?,?,?)", (day, shift, loom, operator_id))
    else:
        db.execute("DELETE FROM assignment WHERE day=? AND shift=? AND loom=?",
                   (day, shift, loom))
    db.commit()
    db.close()


def copy_assignments(to_day, to_shift, from_day=None, from_shift=None):
    """Повторить расстановку с прошлой смены: люди обычно стоят на тех же станках."""
    db = shop()
    if not from_day:
        prev = db.execute(
            "SELECT day, shift FROM assignment WHERE (day < ?) OR (day = ? AND shift <> ?)"
            " ORDER BY day DESC, shift DESC LIMIT 1", (to_day, to_day, to_shift)).fetchone()
        if not prev:
            db.close()
            return {"copied": 0, "from": None}
        from_day, from_shift = prev["day"], prev["shift"]
    src = db.execute("SELECT loom, operator_id FROM assignment WHERE day=? AND shift=?",
                     (from_day, from_shift)).fetchall()
    db.execute("DELETE FROM assignment WHERE day=? AND shift=?", (to_day, to_shift))
    db.executemany("INSERT INTO assignment (day, shift, loom, operator_id) VALUES (?,?,?,?)",
                   [(to_day, to_shift, r["loom"], r["operator_id"]) for r in src])
    masters = db.execute("SELECT operator_id FROM shift_master WHERE day=? AND shift=?",
                         (from_day, from_shift)).fetchall()
    db.execute("DELETE FROM shift_master WHERE day=? AND shift=?", (to_day, to_shift))
    db.executemany("INSERT INTO shift_master (day, shift, operator_id) VALUES (?,?,?)",
                   [(to_day, to_shift, m["operator_id"]) for m in masters])
    db.commit()
    db.close()
    return {"copied": len(src), "from": "%s.%s" % (from_day, from_shift)}


def fact_operators(day):
    """Кто стоял на станках в этот день — по данным самого FACT.

    В `factdata/operator/<день>.txt` одна строка на станок: `mac_name D1 …
    ope_name Saboxat30 … mac_type2 JAT810`. Имя и код слиты в одну строку и
    пишутся вразнобой («DILOROM41», «DILOROM 41», «SABOXAT30»), поэтому
    сопоставляем по коду — он стабилен.
    """
    path = os.path.join(MIRROR_OPERATOR, "%s.txt" % day)
    if not os.path.isfile(path):
        return {}
    out = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            loom = re.search(r"mac_name ([A-Za-z]+\d+)", line)
            name = re.search(r"ope_name ([^,]*)", line)
            model = re.search(r"mac_type2 ([^,]*)", line)
            if not loom:
                continue
            raw = (name.group(1).strip() if name else "")
            m = re.match(r"^(.*?)[\s_-]*(\d{1,4})\s*$", raw)
            out[loom.group(1).upper()] = {
                "raw": raw,
                "name": (m.group(1).strip().title() if m and m.group(1).strip() else raw),
                "code": m.group(2) if m else "",
                "model": (model.group(1).strip() if model else ""),
            }
    return out


def import_assignments_from_fact(day, shifts=("A", "B", "C"), overwrite=False):
    """Расставляет операторов по станкам из данных FACT.

    FACT знает оператора на сутки, а не на смену, поэтому одна и та же
    расстановка ставится на все смены дня. Уже проставленное вручную не трогаем,
    пока не попросят явно (`overwrite`).
    """
    fact_ops = fact_operators(day)
    if not fact_ops:
        return {"day": day, "found": 0, "assigned": 0, "no_operator": [], "error":
                "нет файла операторов за этот день"}

    db = shop()
    by_code = {r["code"]: r["id"] for r in
               db.execute("SELECT id, code FROM operator WHERE role='operator'")}
    assigned, missing = 0, []
    for loom, info in sorted(fact_ops.items()):
        op_id = by_code.get(info["code"])
        if not op_id:
            if info["raw"]:
                missing.append("%s: %s" % (loom, info["raw"]))
            continue
        for sh in shifts:
            if not overwrite and db.execute(
                    "SELECT 1 FROM assignment WHERE day=? AND shift=? AND loom=?",
                    (day, sh, loom)).fetchone():
                continue
            db.execute("INSERT OR REPLACE INTO assignment (day, shift, loom, operator_id)"
                       " VALUES (?,?,?,?)", (day, sh, loom, op_id))
            assigned += 1
    db.commit()
    db.close()
    return {"day": day, "found": len(fact_ops), "assigned": assigned,
            "no_operator": missing}


def import_operators_from_fact():
    """Берёт имена операторов из данных FACT: «Saboxat30» -> код 30, имя Saboxat."""
    names = set()
    if os.path.isdir(MIRROR_OPERATOR):
        files = sorted(f for f in os.listdir(MIRROR_OPERATOR) if f.endswith(".txt"))[-30:]
        for fn in files:
            with open(os.path.join(MIRROR_OPERATOR, fn), encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    m = re.search(r"ope_name ([^,]+)", line)
                    if m and m.group(1).strip():
                        names.add(m.group(1).strip())

    db = shop()
    added = 0
    for raw in sorted(names):
        m = re.match(r"^(.*?)[\s_-]*(\d{1,4})\s*$", raw)
        if m and m.group(1).strip():
            name, code = m.group(1).strip(), m.group(2)
        else:
            name, code = raw, ""
        if not code:
            continue
        cur = db.execute("SELECT id FROM operator WHERE code=? AND role='operator'",
                         (code,)).fetchone()
        if cur:
            continue
        db.execute("INSERT INTO operator (code, name, role) VALUES (?,?,'operator')",
                   (code, name.title()))
        added += 1
    db.commit()
    total = db.execute("SELECT COUNT(*) c FROM operator").fetchone()["c"]
    db.close()
    return {"found": len(names), "added": added, "total": total}


# --- список людей из другой системы или Excel ---------------------------------

# Заголовки колонок, как в таблице пользователей и в Excel.
HEADERS = {"отображаемое имя": "display", "фио": "display", "фамилия": "last", "имя": "first",
           "отчество": "middle", "табельный номер": "code", "табельный": "code",
           "таб. номер": "code", "таб.номер": "code", "код": "code", "должность": "role",
           "роль": "role", "заблокирован": "blocked"}
YES = {"да", "1", "true", "x", "✓", "+", "yes", "истина"}


def _role_of(text):
    """В таблице пользователей цеха мастерицы записаны должностью «Мастер»,
    поэтому «Мастер» — это мастерица. Мастер смены — только «мастер смены»
    или «сменный мастер»."""
    t = (text or "").strip().lower()
    if "мастер" in t and "смен" in t:
        return "foreman"
    if "мастер" in t:
        return "master"
    return "operator"


def _cells(line):
    """Строка из Excel или таблицы в браузере — через табуляцию; из текста —
    через два пробела или точку с запятой."""
    parts = line.split("\t") if "\t" in line else re.split(r"\s{2,}|;", line.strip())
    return [p.strip() for p in parts]


def import_people(text):
    """Загрузить людей из вставленного списка: табельный номер, имя, должность.

    Табельный номер — это код оператора в FACT («Saboxat30» — табельный 30),
    поэтому человек ищется по нему: у знакомых обновляются имя, должность и
    блокировка, новые добавляются. Повторы в списке считаются один раз — в
    таблице пользователей страницы, бывает, повторяются.
    """
    lines = [l for l in (text or "").splitlines() if l.strip()]
    if not lines:
        raise ValueError("список пуст")
    head = [c.lower() for c in _cells(lines[0])]
    cols = {HEADERS[c]: i for i, c in enumerate(head) if c in HEADERS}
    if "code" in cols:
        lines = lines[1:]
    else:
        cols = None

    people, skipped, repeats = {}, [], 0
    for line in lines:
        cells = _cells(line)
        if cols:
            g = lambda k: cells[cols[k]] if k in cols and cols[k] < len(cells) else ""
            code = g("code")
            name = g("display") or " ".join(x for x in (g("last"), g("first"), g("middle")) if x)
            role, blocked = _role_of(g("role")), g("blocked").lower() in YES
        else:
            # Без заголовка: табельный — последнее число в строке (первое бывает
            # номером строки), имя — первый текст, должность — где «оператор» или «мастер».
            nums = [c for c in cells if re.fullmatch(r"\d{1,6}", c)]
            words = [c for c in cells if c and not re.fullmatch(r"\d{1,6}", c)]
            roles = [c for c in words if re.search(r"оператор|мастер", c, re.I)]
            words = [c for c in words if c not in roles and c.lower() not in YES | {"false", "нет"}]
            code = nums[-1] if nums else ""
            name = words[0] if words else ""
            if name and " " not in name and len(words) > 1:
                name = "%s %s" % (words[0], words[1])     # фамилия и имя в разных колонках
            role, blocked = _role_of(roles[0] if roles else ""), False
        code, name = code.strip().lstrip("0") or code.strip(), re.sub(r"\s+", " ", name).strip()
        if not code or not name:
            skipped.append(line.strip()[:60])
            continue
        if code in people:
            repeats += 1
            continue
        people[code] = (name[:80], role, 0 if blocked else 1)

    added = updated = same = 0
    db = shop()
    try:
        for code, (name, role, active) in people.items():
            cur = db.execute("SELECT * FROM operator WHERE code=? ORDER BY (role=?) DESC LIMIT 1",
                             (code, role)).fetchone()
            if cur and (cur["name"], cur["role"], cur["active"]) == (name, role, active):
                same += 1
            elif cur:
                db.execute("UPDATE operator SET name=?, role=?, active=? WHERE id=?",
                           (name, role, active, cur["id"]))
                updated += 1
            else:
                db.execute("INSERT INTO operator (code, name, role, active) VALUES (?,?,?,?)",
                           (code, name, role, active))
                added += 1
        db.commit()
    finally:
        db.close()
    return {"in_list": len(people), "added": added, "updated": updated, "same": same,
            "repeats": repeats, "skipped": skipped}


# --- документы расстановки: три на день ---------------------------------------

def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _loom_key(loom):
    m = re.match(r"^([A-Za-z]+)(\d+)$", loom or "")
    return (m.group(1), int(m.group(2))) if m else (loom or "", 0)


def _today():
    import tickets
    return tickets.current_shift()[:10]


def all_looms(day=None, shift=None):
    """Все станки цеха: по живому снимку FACT, итогам смены и прежним расстановкам.

    Для смены, которая ещё не началась, итогов нет — без живого снимка список
    станков в документе был бы пустым."""
    looms = set()
    try:
        import tickets
        looms |= set(tickets.state_now()[1])
    except Exception:
        pass
    if day and shift:
        looms |= {r["loom"] for r in shift_rows(day, shift)}
    db = shop()
    looms |= {r["loom"] for r in db.execute("SELECT DISTINCT loom FROM assignment")}
    db.close()
    return sorted(looms, key=_loom_key)


def _doc(db, day, shift):
    r = db.execute("SELECT * FROM shift_doc WHERE day=? AND shift=?", (day, shift)).fetchone()
    return dict(r) if r else None


def _prev_same_shift(db, day, shift):
    """Последний день до этого, когда в ту же смену была расстановка."""
    r = db.execute("SELECT day FROM assignment WHERE shift=? AND day < ?"
                   " ORDER BY day DESC LIMIT 1", (shift, day)).fetchone()
    return r["day"] if r else None


def _copy_shift(db, from_day, day, shift):
    """Операторы, мастерицы и мастер из той же смены прошлого дня."""
    db.execute("DELETE FROM assignment WHERE day=? AND shift=?", (day, shift))
    db.execute("INSERT INTO assignment (day, shift, loom, operator_id)"
               " SELECT ?, shift, loom, operator_id FROM assignment WHERE day=? AND shift=?",
               (day, from_day, shift))
    db.execute("DELETE FROM shift_master WHERE day=? AND shift=?", (day, shift))
    db.execute("INSERT INTO shift_master (day, shift, operator_id)"
               " SELECT ?, shift, operator_id FROM shift_master WHERE day=? AND shift=?",
               (day, from_day, shift))
    prev = _doc(db, from_day, shift)
    return prev["foreman_id"] if prev else None


def ensure_shift_docs(day, who="авто"):
    """Три документа расстановки на день (A, B, C), если их ещё нет.

    На сегодня и вперёд документ сразу заполняется той же сменой прошлого дня:
    мастеру остаётся поправить, а не набирать сорок станков заново. Прошлые дни
    не заполняются: расстановка за прошлое — это зарплата, её задним числом
    сама система не придумывает."""
    created = []
    fill = day >= _today()
    db = shop()
    try:
        for sh in ("A", "B", "C"):
            if _doc(db, day, sh):
                continue
            have = db.execute("SELECT COUNT(*) c FROM assignment WHERE day=? AND shift=?",
                              (day, sh)).fetchone()["c"]
            source, foreman = ("введено до документа" if have else None), None
            if not have and fill:
                prev = _prev_same_shift(db, day, sh)
                if prev:
                    foreman = _copy_shift(db, prev, day, sh)
                    source = "смена %s за %s" % (sh, prev)
            db.execute("INSERT INTO shift_doc (day, shift, foreman_id, source, updated_by,"
                       " updated_at) VALUES (?,?,?,?,?,?)",
                       (day, sh, foreman, source, who, _now()))
            created.append(sh)
        db.commit()
    finally:
        db.close()
    return created


def get_shift_doc(day, shift):
    if shift not in SHIFT_HOURS:
        raise ValueError("смена: A, B или C")
    ensure_shift_docs(day)
    db = shop()
    doc = _doc(db, day, shift)
    a = {r["loom"]: r["operator_id"] for r in db.execute(
        "SELECT loom, operator_id FROM assignment WHERE day=? AND shift=?", (day, shift))}
    masters = [r["operator_id"] for r in db.execute(
        "SELECT operator_id FROM shift_master WHERE day=? AND shift=?", (day, shift))]
    db.close()
    looms = sorted(set(all_looms(day, shift)) | set(a), key=_loom_key)
    return {"day": day, "shift": shift, "hours": SHIFT_HOURS[shift], "doc": doc,
            "assignments": [{"loom": l, "operator_id": a.get(l)} for l in looms],
            "masters": masters}


def _check_open(db, day, shift):
    doc = _doc(db, day, shift)
    if doc and doc["status"] == "confirmed":
        raise ValueError("документ смены %s за %s утверждён — сначала откройте его для правки"
                         % (shift, day))


def save_shift_doc(day, shift, body, who=""):
    db = shop()
    try:
        _check_open(db, day, shift)
    finally:
        db.close()
    ensure_shift_docs(day)
    save_assignments({"day": day, "shift": shift,
                      "assignments": body.get("assignments") or [],
                      "masters": body.get("masters") or []})
    db = shop()
    db.execute("UPDATE shift_doc SET foreman_id=?, note=?, updated_by=?, updated_at=?,"
               " source=COALESCE(source, 'вручную') WHERE day=? AND shift=?",
               (body.get("foreman_id") or None, (body.get("note") or "").strip()[:300],
                who, _now(), day, shift))
    db.commit()
    db.close()
    return get_shift_doc(day, shift)


def confirm_shift_doc(day, shift, who="", confirmed=True):
    """Утвердить (или открыть для правки). Без мастера смены не утверждаем."""
    db = shop()
    try:
        doc = _doc(db, day, shift)
        if not doc:
            raise ValueError("документа нет")
        if confirmed and not doc["foreman_id"]:
            raise ValueError("укажите мастера смены")
        db.execute("UPDATE shift_doc SET status=?, confirmed_by=?, confirmed_at=? WHERE day=? AND shift=?",
                   ("confirmed" if confirmed else "draft", who if confirmed else None,
                    _now() if confirmed else None, day, shift))
        db.commit()
    finally:
        db.close()
    return get_shift_doc(day, shift)


def fill_shift_doc(day, shift, how, who=""):
    """Заполнить документ заново: как в прошлую ту же смену или по данным FACT."""
    db = shop()
    try:
        _check_open(db, day, shift)
    finally:
        db.close()
    ensure_shift_docs(day)
    if how == "fact":
        r = import_assignments_from_fact(day, (shift,), overwrite=True)
        if r.get("error"):
            raise ValueError(r["error"])
        source = "FACT"
        foreman = None
    else:
        db = shop()
        prev = _prev_same_shift(db, day, shift)
        if not prev:
            db.close()
            raise ValueError("прошлой расстановки смены %s нет" % shift)
        foreman = _copy_shift(db, prev, day, shift)
        db.commit()
        db.close()
        r = {"from": prev}
        source = "смена %s за %s" % (shift, prev)
    db = shop()
    db.execute("UPDATE shift_doc SET source=?, updated_by=?, updated_at=?,"
               " foreman_id=COALESCE(?, foreman_id) WHERE day=? AND shift=?",
               (source, who, _now(), foreman, day, shift))
    db.commit()
    db.close()
    return {**r, "doc": get_shift_doc(day, shift)}


def list_shift_docs(date_from, date_to):
    """Документы за период: статус, мастер, сколько станков расставлено."""
    db = shop()
    docs = [dict(r) for r in db.execute(
        "SELECT d.day, d.shift, d.status, d.source, d.updated_by, d.confirmed_by,"
        " o.name foreman_name, o.code foreman_code FROM shift_doc d"
        " LEFT JOIN operator o ON o.id = d.foreman_id"
        " WHERE d.day BETWEEN ? AND ? ORDER BY d.day DESC, d.shift", (date_from, date_to))]
    looms = {(r["day"], r["shift"]): (r["n"], r["ops"]) for r in db.execute(
        "SELECT day, shift, COUNT(*) n, COUNT(DISTINCT operator_id) ops FROM assignment"
        " WHERE day BETWEEN ? AND ? GROUP BY day, shift", (date_from, date_to))}
    masters = {(r["day"], r["shift"]): r["n"] for r in db.execute(
        "SELECT day, shift, COUNT(*) n FROM shift_master WHERE day BETWEEN ? AND ?"
        " GROUP BY day, shift", (date_from, date_to))}
    db.close()
    for d in docs:
        n, ops = looms.get((d["day"], d["shift"]), (0, 0))
        d.update(looms=n, operators=ops, masters=masters.get((d["day"], d["shift"]), 0))
    return docs
