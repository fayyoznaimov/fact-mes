"""Виды документов: заправка, ставка, зарплатная ведомость.

Проверка каждого вида возвращает то, что человек увидит перед подтверждением:
ошибки, предупреждения, изменения «было → станет» и итоги. Проверка не пишет в
базу и даёт один и тот же результат на одних и тех же данных — по нему
считается контрольная сумма подтверждения (documents.checksum).
"""
import json
import re
from datetime import datetime, timedelta

import documents
import loomsetup
import productionlog
from documents import Kind, register

SHIFT_START = {"A": 7, "B": 15, "C": 23}
PAYROLL_MAX_DAYS = 62


def _day(value, name):
    try:
        return datetime.strptime(value or "", "%Y.%m.%d")
    except ValueError:
        raise ValueError("%s: нужна дата вида 2026.09.16" % name) from None


def _today():
    return datetime.now(productionlog.TZ).strftime("%Y.%m.%d")


def _same(a, b):
    if a in (None, "") and b in (None, ""):
        return True
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return str(a) == str(b)


# --- заправка ---------------------------------------------------------------

def _field_title(field):
    if field in loomsetup.NAMES:
        return loomsetup.NAMES[field]
    slot, part = field.rsplit("_", 1)
    return "%s — %s" % (loomsetup.YARN_RU.get(slot, slot), "пряжа" if part == "yarn" else "лот")


def check_setup(db, payload):
    errors, warnings, changes, pairs = [], [], [], []
    from_day = payload.get("from_day") or ""
    effective_at = payload.get("effective_at") or None
    try:
        _day(from_day, "день заправки")
        loomsetup.valid_at(from_day, effective_at)
    except ValueError as e:
        return {"title": "Заправка", "errors": [str(e)]}
    seen = set()
    for r in payload.get("rows") or []:
        loom = (r.get("loom") or "").strip().upper()
        if not loom:
            continue
        if loom in seen:
            errors.append("%s — станок повторяется в документе" % loom)
            continue
        seen.add(loom)
        try:
            pairs.append((loom, loomsetup._clean(r.get("values") or {})))
        except ValueError as e:
            errors.append("%s — %s" % (loom, e))
    if not pairs and not errors:
        errors.append("не указан ни один станок")
    unchanged = []
    for loom, row in pairs:
        cur = db.execute("SELECT * FROM loom_setup WHERE loom=? AND from_day<=? ORDER BY from_day DESC LIMIT 1",
                         (loom, from_day)).fetchone()
        cur = dict(cur) if cur else {}
        manual_diff = [f for f in loomsetup.FIELDS if not _same(cur.get(f), row[f])]
        if not manual_diff:
            unchanged.append(loom)
        else:
            import changes as human
            before_snap = loomsetup.document_snapshot(db, loom, from_day, {f: cur.get(f) for f in loomsetup.FIELDS})
            after_snap = loomsetup.document_snapshot(db, loom, from_day, row)
            context = human.setup_context(after_snap)
            for x in human.setup_fields(before_snap, after_snap):
                if x["field"] in manual_diff or x["changed"]:
                    changes.append(dict(x, loom=loom, title=x["label"], context=context,
                                        since=cur.get("from_day"), since_by=cur.get("set_by")))
        if cur.get("from_day") == from_day:
            warnings.append("%s — заменит заправку с %s, введённую %s %s" % (
                loom, from_day, cur.get("set_by") or "—", (cur.get("set_at") or "")[:16].replace("T", " ")))
        later = db.execute("SELECT MIN(from_day) FROM loom_setup WHERE loom=? AND from_day>?",
                           (loom, from_day)).fetchone()[0]
        if later:
            warnings.append("%s — с %s уже действует более поздняя заправка: эта будет действовать только до неё"
                            % (loom, later))
        for slot in loomsetup.YARNS:
            if row[slot + "_yarn"] and not row[slot + "_lot"]:
                warnings.append("%s — %s %s без лота" % (loom, loomsetup.YARN_RU[slot], row[slot + "_yarn"]))
    if pairs and len(unchanged) == len(pairs):
        errors.append("изменений нет: значения совпадают с действующей заправкой")
    elif unchanged:
        warnings.append("без изменений: " + ", ".join(unchanged))
    today = _today()
    if from_day > today:
        warnings.append("заправка с будущего дня %s" % from_day)
    elif from_day < today:
        days = (_day(today, "") - _day(from_day, "")).days
        warnings.append("отчёт будет пересобран с %s (%d дн.)%s" % (
            from_day, min(days, loomsetup.MAX_DAYS),
            "; дни старше %d не пересобираются" % loomsetup.MAX_DAYS if days > loomsetup.MAX_DAYS else ""))
    looms = [loom for loom, _ in pairs]
    title = "Заправка с %s%s: %s" % (from_day, " " + effective_at[11:16] if effective_at else "",
                                     ", ".join(looms[:6]) + (" и ещё %d" % (len(looms) - 6) if len(looms) > 6 else ""))
    return {"title": title, "period": (from_day, None), "errors": errors, "warnings": warnings,
            "changes": changes,
            "summary": {"looms": len(pairs), "changed_looms": len(pairs) - len(unchanged),
                        "changed_fields": len(changes), "from_day": from_day},
            "result": {"from_day": from_day, "effective_at": effective_at,
                       "rows": [{"loom": loom, "values": row} for loom, row in pairs]}}


def apply_setup(db, doc_id, payload, checked, who):
    r = checked["result"]
    loomsetup.store(db, [(x["loom"], x["values"]) for x in r["rows"]], r["from_day"], who,
                    r["effective_at"], doc_id)


def after_setup(payload, checked):
    return {"days": loomsetup.rebuild(checked["result"]["from_day"])}


register(Kind("setup", "Заправка", "ЗАП", "setup_edit", "setup", check_setup, apply_setup,
              after=after_setup, cancel=False))


# --- ставка -----------------------------------------------------------------

UNITS = {"kpick": "за 1000 пиков", "pick": "за пик"}


def check_rate(db, payload):
    from storage import rate_for
    errors, warnings = [], []
    valid_from = payload.get("valid_from") or ""
    try:
        _day(valid_from, "действует с")
    except ValueError as e:
        return {"title": "Ставка", "errors": [str(e)]}
    try:
        rate = round(float(str(payload.get("rate", "")).replace(",", ".").replace(" ", "")), 4)
    except ValueError:
        return {"title": "Ставка", "errors": ["ставка: нужно число"]}
    unit = payload.get("unit") or "kpick"
    if unit not in UNITS:
        errors.append("единица ставки: за 1000 пиков или за пик")
    if not 0 < rate < 1_000_000:
        errors.append("ставка должна быть больше нуля")
    old_rate, old_unit = rate_for(db, valid_from)
    if _same(old_rate, rate) and old_unit == unit:
        errors.append("ставка с %s уже %s сум %s" % (valid_from, rate, UNITS.get(unit, unit)))
    same_day = db.execute(
        "SELECT r.rate FROM rate_period r LEFT JOIN doc d ON d.id=r.doc_id WHERE r.valid_from=?"
        " AND (r.doc_id IS NULL OR d.status='posted')", (valid_from,)).fetchone()
    if same_day:
        warnings.append("с %s уже введена ставка %s — действовать будет новая" % (valid_from, same_day[0]))
    later = db.execute(
        "SELECT MIN(r.valid_from) FROM rate_period r LEFT JOIN doc d ON d.id=r.doc_id WHERE r.valid_from>?"
        " AND (r.doc_id IS NULL OR d.status='posted')", (valid_from,)).fetchone()[0]
    if later:
        warnings.append("с %s действует более поздняя ставка: эта будет действовать только до неё" % later)
    if valid_from <= _today():
        warnings.append("смены с %s будут считаться по новой ставке" % valid_from)
        stale = db.execute("SELECT number, period_from, period_to FROM doc WHERE type='payroll'"
                           " AND status='posted' AND period_to >= ?", (valid_from,)).fetchall()
        if stale:
            warnings.append("проведённые ведомости не меняются, их нужно заменить: " + ", ".join(
                "%s (%s–%s)" % (r["number"], r["period_from"], r["period_to"]) for r in stale))
    return {"title": "Ставка %s сум %s с %s" % (rate, UNITS.get(unit, unit), valid_from),
            "period": (valid_from, None), "errors": errors, "warnings": warnings,
            "changes": [dict(field="rate", title="Ставка, сум", before=old_rate, after=rate),
                        dict(field="unit", title="Единица", before=UNITS.get(old_unit, old_unit),
                             after=UNITS.get(unit, unit))],
            "summary": {"rate": rate, "unit": unit, "valid_from": valid_from},
            "result": {"rate": rate, "unit": unit, "valid_from": valid_from}}


def apply_rate(db, doc_id, payload, checked, who):
    r = checked["result"]
    db.execute("INSERT INTO rate_period (valid_from, rate, unit, doc_id, set_by, set_at) VALUES (?,?,?,?,?,?)",
               (r["valid_from"], r["rate"], r["unit"], doc_id, who or "система", productionlog.now()))


# Отменённая ставка перестаёт действовать сама: rate_for смотрит статус документа.
register(Kind("rate", "Ставка", "СТ", "settings", "settings", check_rate, apply_rate))


# --- зарплатная ведомость ----------------------------------------------------

def check_payroll(db, payload):
    import payroll
    errors, warnings = [], []
    try:
        first = _day(payload.get("from"), "с")
        last = _day(payload.get("to"), "по")
    except ValueError as e:
        return {"title": "Зарплатная ведомость", "errors": [str(e)]}
    date_from, date_to = payload["from"], payload["to"]
    if first > last:
        return {"title": "Зарплатная ведомость", "errors": ["начало периода позже конца"]}
    if (last - first).days + 1 > PAYROLL_MAX_DAYS:
        return {"title": "Зарплатная ведомость",
                "errors": ["период ведомости — не больше %d дней" % PAYROLL_MAX_DAYS]}
    now = datetime.now(productionlog.TZ)
    last_end = last.replace(tzinfo=productionlog.TZ) + timedelta(hours=SHIFT_START["C"] + 8)
    if last_end > now:
        errors.append("смены по %s ещё не закончились: ведомость — только за закрытые смены" % date_to)
    replaces = payload.get("supersedes_id")
    overlap = db.execute("SELECT id, number, period_from, period_to FROM doc WHERE type='payroll'"
                         " AND status='posted' AND period_from <= ? AND period_to >= ?",
                         (date_to, date_from)).fetchall()
    for r in overlap:
        if replaces and int(replaces) == r["id"]:
            continue
        errors.append("период пересекается с проведённой ведомостью %s (%s–%s): замените или отмените её"
                      % (r["number"], r["period_from"], r["period_to"]))
    people, shifts, empty, rates = {}, [], [], []
    day = first
    while day <= last:
        d = day.strftime("%Y.%m.%d")
        for letter in "ABC":
            s = payroll.salary_for_shift(d, letter)
            if not s["looms"]:
                empty.append("%s %s" % (d, letter))
                continue
            if not rates or rates[-1][1:] != (s["rate"], s["rate_unit"]):
                rates.append((d, s["rate"], s["rate_unit"]))
            line = dict(day=d, shift=letter, rate=s["rate"], unit=s["rate_unit"],
                        salary=s["totals"]["salary"], unassigned_salary=s["totals"]["unassigned_salary"],
                        kpicks=s["totals"]["kpicks"],
                        operators=[dict(operator_id=o["operator_id"], salary=o["salary"], kpicks=o["kpicks"],
                                        looms=o["looms"]) for o in s["operators"]])
            shifts.append(line)
            if s["unassigned_looms"]:
                warnings.append("%s %s: без оператора %d ст. (%s) — не распределено %s сум" % (
                    d, letter, len(s["unassigned_looms"]), ", ".join(s["unassigned_looms"][:8]),
                    "{:,}".format(s["totals"]["unassigned_salary"]).replace(",", " ")))
            for o in s["operators"]:
                p = people.setdefault(o["operator_id"], dict(operator_id=o["operator_id"], code=o["code"],
                                                              name=o["name"], shifts=0, kpicks=0.0, salary=0))
                p["shifts"] += 1
                p["kpicks"] = round(p["kpicks"] + o["kpicks"], 1)
                p["salary"] += o["salary"]
        day += timedelta(days=1)
    if not shifts:
        errors.append("за период нет смен с выработкой")
    if empty:
        warnings.append("нет выработки в %d сменах: %s" % (len(empty), ", ".join(empty[:10]) +
                                                          (" …" if len(empty) > 10 else "")))
    if len(rates) > 1:
        warnings.append("в периоде разные ставки: " + "; ".join(
            "%g сум %s с %s" % (r, UNITS.get(u, u), d) for d, r, u in rates))
    operators = sorted(people.values(), key=lambda x: (-x["salary"], x["name"]))
    changes = []
    if replaces:
        old = db.execute("SELECT result_json FROM doc WHERE id=? AND type='payroll'", (int(replaces),)).fetchone()
        if not old:
            errors.append("заменяемая ведомость не найдена")
        else:
            before = {o["operator_id"]: o for o in json.loads(old[0]).get("result", {}).get("operators", [])}
            after = {o["operator_id"]: o for o in operators}
            for oid in sorted(set(before) | set(after), key=lambda x: (after.get(x) or before.get(x))["name"]):
                b, a = before.get(oid), after.get(oid)
                if not b or not a or b["salary"] != a["salary"]:
                    changes.append(dict(field="salary", title=(a or b)["name"],
                                        before=b["salary"] if b else None, after=a["salary"] if a else None))
    total = sum(o["salary"] for o in operators)
    return {"title": "Зарплатная ведомость %s–%s" % (date_from, date_to), "period": (date_from, date_to),
            "errors": errors, "warnings": warnings, "changes": changes,
            "summary": {"from": date_from, "to": date_to, "shifts": len(shifts), "operators": len(operators),
                        "salary": total,
                        "unassigned_salary": sum(x["unassigned_salary"] for x in shifts)},
            "result": {"operators": operators, "shifts": shifts}}


register(Kind("payroll", "Зарплатная ведомость", "ЗП", "payroll", "salary", check_payroll,
              lock_check=False))


# --- причина простоя (справочник) ----------------------------------------------

REASON_FIELDS = (("name", "Название"), ("name_en", "Название по-английски"), ("reason", "Как в отчёте"),
                 ("applies", "Когда действует"), ("is_call", "Вызов человека"), ("category", "Категория"),
                 ("color", "Цвет"), ("sort", "Порядок"), ("in_operator", "Предлагать в цеху"),
                 ("in_analytics", "Предлагать при разборе"), ("important", "Важная"), ("active", "Действует"))
REASON_CATEGORY = {"scheduled": "плановый простой", "unscheduled": "внеплановый простой",
                   "undefined": "не определено"}
REASON_APPLIES = {"any": "станок стоит или обесточен", "stop": "станок стоит",
                  "off": "станок обесточен"}
REASON_WORDS = {"category": REASON_CATEGORY, "applies": REASON_APPLIES}
REASON_FLAGS = ("is_call", "in_operator", "in_analytics", "important", "active")


def _reason_text(field, value):
    if field in REASON_WORDS:
        return REASON_WORDS[field].get(value, value)
    if field in REASON_FLAGS:
        return "да" if value else "нет"
    return value


def check_reason(db, payload):
    errors, warnings, changes = [], [], []
    r = dict(payload.get("reason") or {})
    code = (r.get("id") or "").strip().lower()
    if not re.match(r"^[a-z][a-z0-9_]{1,29}$", code):
        return {"title": "Причина простоя", "errors": ["код причины: латиница, цифры и подчёркивание, 2–30 знаков"]}
    row = db.execute("SELECT * FROM stop_reason WHERE id=?", (code,)).fetchone()
    old = dict(row) if row else {}
    new = dict(old) if old else dict(id=code, applies="any", is_call=0, category="unscheduled",
                                     color=None, sort=100, in_operator=1, in_analytics=1,
                                     important=0, active=1, builtin=0, name_en=None)
    for field, _ in REASON_FIELDS:
        if field not in r:
            continue
        v = r[field]
        if field in REASON_FLAGS:
            v = int(bool(v))
        elif field == "sort":
            try:
                v = int(v)
            except (TypeError, ValueError):
                errors.append("порядок: нужно число")
                continue
        else:
            v = (str(v).strip() or None) if v is not None else None
        new[field] = v
    if not new.get("name"):
        errors.append("название обязательно")
    if not new.get("reason"):
        new["reason"] = new.get("name")
    if new.get("category") not in REASON_CATEGORY:
        errors.append("категория: плановый, внеплановый или не определено")
    if new.get("applies") not in REASON_APPLIES:
        errors.append("когда действует: станок стоит, обесточен или и то и другое")
    has_tickets = db.execute("SELECT 1 FROM sqlite_master WHERE name='ticket'").fetchone()
    used = db.execute("SELECT COUNT(*) FROM ticket WHERE category_id=?", (code,)).fetchone()[0] if has_tickets else 0
    for field, title in REASON_FIELDS:
        if not _same(old.get(field), new.get(field)):
            changes.append(dict(field=field, title=title, label=title,
                                before=_reason_text(field, old.get(field)) if old else None,
                                after=_reason_text(field, new.get(field)), changed=True))
    if old and not changes:
        errors.append("изменений нет")
    if not old:
        warnings.append("новая причина простоя: её увидят в списке сразу после проведения")
    if old and used and not _same(old.get("reason"), new.get("reason")):
        warnings.append("причина стоит в %d тикетах: в отчётах за прошлые дни она будет называться по-новому" % used)
    if old and old.get("active") and not new.get("active"):
        open_now = db.execute("SELECT COUNT(*) FROM ticket WHERE category_id=? AND ended_at IS NULL",
                              (code,)).fetchone()[0] if has_tickets else 0
        warnings.append("причину перестанут предлагать; прошлые %d тикетов останутся с ней%s" % (
            used, ", в том числе %d открытых" % open_now if open_now else ""))
    if old.get("builtin") and not _same(old.get("name"), new.get("name")):
        warnings.append("это причина из первой версии приложения — её название встречается в старых отчётах")
    return {"title": "Причина простоя «%s»" % (new.get("name") or code), "period": (None, None),
            "errors": errors, "warnings": warnings, "changes": changes,
            "summary": {"id": code, "name": new.get("name"), "category": REASON_CATEGORY.get(new.get("category")),
                        "tickets": used, "new": not old},
            "result": {"reason": new}}


def apply_reason(db, doc_id, payload, checked, who):
    r = checked["result"]["reason"]
    db.execute(
        "INSERT INTO stop_reason (id, name, name_en, reason, applies, is_call, category, color, sort,"
        " in_operator, in_analytics, important, active, builtin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(id) DO UPDATE SET name=excluded.name, name_en=excluded.name_en, reason=excluded.reason,"
        " applies=excluded.applies, is_call=excluded.is_call, category=excluded.category, color=excluded.color,"
        " sort=excluded.sort, in_operator=excluded.in_operator, in_analytics=excluded.in_analytics,"
        " important=excluded.important, active=excluded.active",
        (r["id"], r["name"], r.get("name_en"), r["reason"], r["applies"], int(r["is_call"]), r["category"],
         r.get("color"), int(r["sort"]), int(r["in_operator"]), int(r["in_analytics"]), int(r["important"]),
         int(r["active"]), int(r.get("builtin") or 0)))


def after_reason(payload, checked):
    import tickets
    tickets.invalidate()        # список причин на мониторах и досках — сразу новый
    return None


register(Kind("reason", "Причина простоя", "ПРЧ", "settings", "settings", check_reason, apply_reason,
              after=after_reason, cancel=False))


# --- утверждённый производственный отчёт ---------------------------------------

def check_report(db, payload):
    import reports
    date_from, date_to = payload.get("from") or "", payload.get("to") or ""
    try:
        data = reports.report_period(date_from, date_to)
    except ValueError as e:
        return {"title": "Производственный отчёт", "errors": [str(e)]}
    errors, warnings = [], []
    if date_to >= _today():
        errors.append("день %s ещё не закончился: утверждают только прошедшие дни" % date_to)
    if not data["rows"]:
        errors.append("за период нет смен Toyota")
    replaces = payload.get("supersedes_id")
    same = db.execute("SELECT id, number FROM doc WHERE type='report' AND status='posted'"
                      " AND period_from=? AND period_to=?", (date_from, date_to)).fetchall()
    for r in same:
        if not (replaces and int(replaces) == r["id"]):
            errors.append("отчёт за этот период уже утверждён: %s — замените его" % r["number"])
    if data["days_without_report"]:
        warnings.append("дневной отчёт не собран за %d дн.: %s — нет изделия и килограммов" % (
            len(data["days_without_report"]), ", ".join(data["days_without_report"][:10])))
    import report_quality
    kg_quality = data["totals"].get("quality", {}).get("kg")
    if kg_quality and kg_quality["status"] != "complete":
        warnings.append("Выпуск в кг — " + report_quality.note(kg_quality))
    unknown = [r["loom"] for r in data["rows"] if not r["towels_known"]]
    if unknown:
        warnings.append("полотенца не посчитаны (нет панелей): " + ", ".join(unknown[:15]))
    expected = (_day(date_to, "") - _day(date_from, "")).days + 1
    if len(data["days"]) < expected:
        warnings.append("смены есть только за %d из %d дней" % (len(data["days"]), expected))
    changes = []
    if replaces:
        old = db.execute("SELECT result_json FROM doc WHERE id=? AND type='report'", (int(replaces),)).fetchone()
        if old:
            before = {r["loom"]: r for r in json.loads(old[0]).get("result", {}).get("rows", [])}
            after = {r["loom"]: r for r in data["rows"]}
            for loom in sorted(set(before) | set(after), key=loomsetup._loom_key):
                b, a = before.get(loom) or {}, after.get(loom) or {}
                for field, title in (("picks", "пики"), ("towels", "полотенца"), ("kg", "кг"), ("effic", "КПД, %")):
                    if b.get(field) != a.get(field):
                        changes.append(dict(loom=loom, field=field, title=title, before=b.get(field), after=a.get(field)))
    t = data["totals"]
    return {"title": "Производственный отчёт %s–%s" % (date_from, date_to), "period": (date_from, date_to),
            "errors": errors, "warnings": warnings, "changes": changes,
            "summary": {"from": date_from, "to": date_to, "looms": t["looms"], "days": t["days"],
                        "effic": t["effic"], "towels": t["towels"], "kg": t["kg"], "picks": t["picks"]},
            "result": {"rows": data["rows"], "totals": t}}


register(Kind("report", "Производственный отчёт", "ОТЧ", "export", "report", check_report, lock_check=False))

