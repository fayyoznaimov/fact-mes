"""Документы учёта: проверка → подтверждение человеком → проведение.

Всё, что меняет учёт (заправка, ставка, зарплатная ведомость, утверждённый
отчёт), проходит один путь:

1. preview — сервер проверяет ввод и показывает, что изменится: ошибки
   (провести нельзя), предупреждения (можно, но человек должен их видеть),
   изменения «было → станет», итоги. Ничего не пишет.
2. post — человек подтвердил то, что видел. Сервер считает проверку заново;
   если данные за это время изменились (кто-то другой сохранил заправку,
   пришли пики), контрольная сумма не совпадёт — документ не проводится,
   человеку показывается новая проверка.
3. Проведённый документ неизменяем (триггеры в storage.DOC_SCHEMA). Исправление —
   новый документ, заменяющий прежний (supersedes_id); отмена — только с причиной.

Кто, когда, что — в самом документе (created_by/at, payload, result),
построчные изменения таблиц — в production_event той же транзакцией.
"""
import hashlib
import json

import productionlog
from storage import shop


class Stale(Exception):
    """Данные изменились после проверки: нужно проверить заново."""


class Kind:
    """Вид документа.

    check(db, payload) -> dict(title, period=(from, to), errors, warnings,
    changes, summary, result); детерминирован для одних и тех же данных.
    apply(db, doc_id, payload, checked, who) — запись в учётные таблицы в
    транзакции документа. after(payload, checked) — работа после фиксации
    (пересборка отчётов), её сбой документ не отменяет.
    """

    def __init__(self, name, title, prefix, permission, section, check, apply=None,
                 after=None, cancel=None, lock_check=True):
        self.name, self.title, self.prefix = name, title, prefix
        self.permission, self.section = permission, section
        self.check, self.apply, self.after, self.cancel = check, apply, after, cancel
        # Дорогую проверку (ведомость за месяц читает FACT) не держим под
        # блокировкой записи: сверяем сумму до блокировки, а под ней — что
        # после проверки никто не провёл документ того же вида.
        self.lock_check = lock_check


KINDS = {}


def register(kind):
    KINDS[kind.name] = kind
    return kind


def kind(name):
    _load()
    if name not in KINDS:
        raise ValueError("неизвестный вид документа")
    return KINDS[name]


def _load():
    # Виды регистрируются модулями предметной области; импорт ленивый,
    # чтобы documents не тянул их при каждом импорте storage.
    import doc_kinds  # noqa: F401


def checksum(name, payload, checked):
    basis = {k: checked.get(k) for k in ("errors", "warnings", "changes", "summary", "result", "period")}
    raw = json.dumps({"type": name, "payload": payload, "checked": basis},
                     ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _checked(k, db, payload):
    c = k.check(db, payload)
    c.setdefault("errors", [])
    c.setdefault("warnings", [])
    c.setdefault("changes", [])
    c.setdefault("summary", {})
    c.setdefault("result", {})
    period = c.get("period") or (None, None)
    c["period"] = list(period)
    return c


def preview(name, payload):
    k = kind(name)
    db = shop()
    try:
        c = _checked(k, db, payload or {})
    finally:
        db.close()
    c["type"], c["type_title"] = k.name, k.title
    c["checksum"] = checksum(k.name, payload or {}, c)
    c["can_post"] = not c["errors"]
    return c


def _next_number(db, k, created_at):
    year = created_at[:4]
    stem = "%s-%s-" % (k.prefix, year)
    row = db.execute("SELECT number FROM doc WHERE number LIKE ? ORDER BY id DESC LIMIT 1",
                     (stem + "%",)).fetchone()
    last = int(row["number"][len(stem):]) if row else 0
    return "%s%04d" % (stem, last + 1)


def post(name, payload, expected, who, comment="", supersedes_id=None):
    """Провести то, что человек видел в проверке с суммой expected."""
    k = kind(name)
    payload = payload or {}
    supersedes_id = supersedes_id or payload.get("supersedes_id")
    if supersedes_id and k.cancel is False:
        raise ValueError("%s не заменяется: проведите новый документ" % k.title)
    if not expected:
        raise ValueError("документ проводится только после проверки")
    token = productionlog.ACTOR.set(who or "система")
    db = shop()
    try:
        if not k.lock_check:
            c = _checked(k, db, payload)
            if checksum(k.name, payload, c) != expected:
                raise Stale("данные изменились после проверки")
            last = db.execute("SELECT COALESCE(MAX(id),0) FROM doc").fetchone()[0]
        db.execute("BEGIN IMMEDIATE")
        if k.lock_check:
            c = _checked(k, db, payload)
            if checksum(k.name, payload, c) != expected:
                raise Stale("данные изменились после проверки")
        elif db.execute("SELECT 1 FROM doc WHERE id > ? AND type = ?", (last, k.name)).fetchone():
            raise Stale("пока шла проверка, проведён другой документ этого вида")
        if c["errors"]:
            raise ValueError("документ не проведён: " + "; ".join(c["errors"][:5]))
        old = None
        if supersedes_id:
            old = db.execute("SELECT * FROM doc WHERE id=?", (int(supersedes_id),)).fetchone()
            if not old or old["type"] != k.name:
                raise ValueError("заменяемый документ не найден")
            if old["status"] != "posted":
                raise ValueError("заменяемый документ уже отменён")
        at = productionlog.now()
        number = _next_number(db, k, at)
        result = {key: c[key] for key in ("title", "errors", "warnings", "changes", "summary", "result")
                  if key in c}
        cur = db.execute(
            "INSERT INTO doc (type, number, title, period_from, period_to, comment, supersedes_id,"
            " created_by, created_at, payload_json, result_json, checksum)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (k.name, number, c.get("title") or k.title, c["period"][0], c["period"][1],
             (comment or "").strip() or None, old["id"] if old else None, who or "система", at,
             json.dumps(payload, ensure_ascii=False, sort_keys=True),
             json.dumps(result, ensure_ascii=False, sort_keys=True, default=str), expected))
        doc_id = cur.lastrowid
        if old:
            _cancel_row(db, k, old, who, "заменён документом %s" % number)
        if k.apply:
            k.apply(db, doc_id, payload, c, who)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
        productionlog.ACTOR.reset(token)
    extra = None
    if k.after:
        try:
            extra = k.after(payload, c)
        except Exception as e:          # документ проведён; пересборку можно повторить
            extra = {"after_error": "%s: %s" % (type(e).__name__, e)}
    return {"id": doc_id, "number": number, "after": extra}


def _cancel_row(db, k, row, who, reason):
    if k.cancel:
        k.cancel(db, dict(row), who)
    db.execute("UPDATE doc SET status='cancelled', cancelled_by=?, cancelled_at=?, cancel_reason=?"
               " WHERE id=?", (who or "система", productionlog.now(), reason, row["id"]))


def cancel(doc_id, reason, who):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ValueError("укажите причину отмены")
    token = productionlog.ACTOR.set(who or "система")
    db = shop()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM doc WHERE id=?", (int(doc_id),)).fetchone()
        if not row:
            raise ValueError("документ не найден")
        if row["status"] != "posted":
            raise ValueError("документ уже отменён")
        k = kind(row["type"])
        if k.cancel is False:
            raise ValueError("%s не отменяется: проведите новый документ с нужными значениями" % k.title)
        _cancel_row(db, k, row, who, reason)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
        productionlog.ACTOR.reset(token)
    return {"ok": True}


def _row(r, full=False):
    d = {k: r[k] for k in ("id", "type", "number", "status", "title", "period_from", "period_to",
                            "comment", "supersedes_id", "created_by", "created_at",
                            "cancelled_by", "cancelled_at", "cancel_reason")}
    d["type_title"] = KINDS[r["type"]].title if r["type"] in KINDS else r["type"]
    result = json.loads(r["result_json"])
    d["summary"] = result.get("summary") or {}
    d["warnings_count"] = len(result.get("warnings") or [])
    if full:
        d["payload"] = json.loads(r["payload_json"])
        d.update({k: result.get(k) for k in ("warnings", "changes", "result")})
    d["search"] = " ".join(str(x) for x in (r["number"], r["title"], r["created_by"], r["comment"] or "",
                                              r["cancel_reason"] or ""))
    return d


def list_docs(types, date_from="", date_to="", status="", limit=200):
    """Документы видов types, период которых пересекается с [date_from, date_to]."""
    _load()
    types = [t for t in types if t in KINDS]
    if not types:
        return []
    where = ["type IN (%s)" % ",".join("?" * len(types))]
    args = list(types)
    if date_from:
        where.append("COALESCE(period_to, period_from, substr(created_at,1,10)) >= ?")
        args.append(date_from)
    if date_to:
        where.append("COALESCE(period_from, substr(created_at,1,10)) <= ?")
        args.append(date_to)
    if status in ("posted", "cancelled"):
        where.append("status = ?")
        args.append(status)
    db = shop()
    try:
        rows = db.execute("SELECT * FROM doc WHERE %s ORDER BY id DESC LIMIT ?" % " AND ".join(where),
                          (*args, min(max(int(limit), 1), 1000))).fetchall()
        return [_row(r) for r in rows]
    finally:
        db.close()


def get(doc_id):
    _load()
    db = shop()
    try:
        r = db.execute("SELECT * FROM doc WHERE id=?", (int(doc_id),)).fetchone()
        if not r:
            raise ValueError("документ не найден")
        d = _row(r, full=True)
        d["replaced_by"] = [dict(id=x["id"], number=x["number"]) for x in
                            db.execute("SELECT id, number FROM doc WHERE supersedes_id=?", (r["id"],))]
        d["history"] = [dict(at=e["at"], actor=e["actor"], action=e["action"],
                             before=json.loads(e["before_json"]) if e["before_json"] else None,
                             after=json.loads(e["after_json"]) if e["after_json"] else None)
                        for e in db.execute(
                            "SELECT * FROM production_event WHERE entity='doc' AND "
                            "COALESCE(json_extract(after_json,'$.id'),json_extract(before_json,'$.id'))=?"
                            " ORDER BY id", (r["id"],))]
        for h in d["history"]:      # тело документа в истории не дублируем
            for side in ("before", "after"):
                if h[side]:
                    h[side] = {k: v for k, v in h[side].items()
                               if k not in ("payload_json", "result_json", "checksum")}
            h["text"] = ("Проведён" if h["action"] == "INSERT" else
                         "Отменён: %s" % (h["after"] or {}).get("cancel_reason") if h["action"] == "UPDATE"
                         and (h["after"] or {}).get("status") == "cancelled" else h["action"])
        if r["type"] == "setup":
            import loomsetup
            d["looms"] = [loomsetup.version(db, x) for x in
                          db.execute("SELECT * FROM setup_document WHERE doc_id=? ORDER BY loom", (r["id"],))]
            for x in d["looms"]:
                x.pop("snapshot", None)
        if r["supersedes_id"]:
            old = db.execute("SELECT number, created_by, created_at FROM doc WHERE id=?", (r["supersedes_id"],)).fetchone()
            d["supersedes"] = dict(id=r["supersedes_id"], number=old["number"], created_by=old["created_by"],
                                   created_at=old["created_at"]) if old else None
        return d
    finally:
        db.close()


def verify(doc_id):
    """Сверка проведённого документа с тем, что проверка дала бы сейчас."""
    d = get(doc_id)
    k = kind(d["type"])
    db = shop()
    try:
        now = _checked(k, db, d["payload"])
    finally:
        db.close()
    same = json.dumps(now["result"], sort_keys=True, default=str) == \
        json.dumps(d["result"], sort_keys=True, default=str)
    return {"id": d["id"], "number": d["number"], "same": same,
            "posted": {"summary": d["summary"], "result": d["result"]},
            "now": {"summary": now["summary"], "result": now["result"], "errors": now["errors"],
                    "warnings": now["warnings"]}}
