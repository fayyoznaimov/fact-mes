"""Обмен с 1С: производственные заказы и техкарты.

1С отдаёт заказы в формате CreateOrUpdateProductionOrderAPI — список
`productionOrders`: изделие, дизайн, панели, пики на изделие, пряжа с лотами,
станки. Путей два, оба рабочие — какой удобнее программисту 1С:

    толчок   1С сама шлёт POST /api/v1/production-orders с ключом API;
    опрос    сборщик раз в полчаса забирает заказы по адресу из config.json:
             "onec": {"url": "http://1c/...", "token": "Basic ...", "every_min": 30}

Из заказа берём то, чего нет в FACT: размер, пики на изделие (weftPerOneRow),
панели (numberLines), пряжу по типам, станки (workCenters). Если 1С пришлёт
ещё и код ткани, как он набран на станке (clothCode), связка артикула с
кодом ткани появится сама — без неё план не видит факт.
"""
import json
import re
import urllib.request
from datetime import datetime

import planning
import yarns
from storage import shop

# Какие запросы 1С понимаем. 1С присылает конверт:
#   {"actionType": "CreateOrUpdateProductionOrderAPI", "wait": true,
#    "waitTimeout": 60000, "data": {"productionOrders": [...]}}
ACTIONS = {"CreateOrUpdateProductionOrderAPI": "производственные заказы и техкарты"}
SLOT_KIND = {"vors": "pile", "karenoy": "ground", "utog1": "weft", "utog2": "weft",
             "utog2p": "weft", "utog2x": "weft", "utog3": "weft", "utog3p": "weft",
             "utog4": "weft"}

# Тип компонента из 1С -> колонка отчёта (по ТЗ, раздел 4).
YARN_SLOT = {
    "Pile yarn": "vors",              # L  Vors
    "Ground yarn": "karenoy",         # M  Karenoy
    "Weft yarn": "utog1",             # N  Utog 1
    "E hem single yarn": "utog2",     # O  Utog 2 — кромка
    "E hem ply yarn": "utog2p",       # O  Utog 2 — кромка, кручёная нить
    "E hem polyester yarn": "utog2x", # O  Utog 2 — кромка, полиэстер
    "Fancy single yarn": "utog3",     # P  Utog 3 — бордюр
    "Fancy ply yarn": "utog3p",       # P  Utog 3 — бордюр, кручёная нить
    "Fancy polyester yarn": "utog4",  # Q  Utog 4 — бордюр, полиэстер
}
# Типов «ply»/«polyester» в ТЗ не было, и их пряжа с лотами терялась (78 изделий
# из 218). Каждый тип — своё место: у одного изделия бывают и single, и ply.


def norm_loom(w):
    """«D-01», «d1», «D01» -> «D1»: так станки называются в FACT."""
    return re.sub(r"^([A-Za-z]+)-?0*(\d+)$", lambda m: m.group(1).upper() + m.group(2),
                  (w or "").strip())


def gsm_from_code(code):
    """«70140 Hotel 450» -> 450. Берём последнее число, если оно похоже на плотность."""
    for n in reversed(re.findall(r"(\d{3,4})", code or "")):
        if 150 <= int(n) <= 900:
            return int(n)
    return None


def size_cm_from(size, code):
    """«70*140» -> 70. Если размер буквенный (XL), берём из кода изделия."""
    m = re.match(r"\s*(\d+)\s*[*xX×]", size or "")
    if m:
        return int(m.group(1))
    m = re.match(r"\s*(\d{2,3})", code or "")
    return int(m.group(1)) if m else None


def parse_component(text):
    """«16/1 Ring Иштихан Суровый Ворс 630 Лот №41» -> («16/1 RING», «41»).

    Пряжа — цифры и латиница до первого русского слова (дальше поставщик и вид),
    лот — номер после «Лот №». Название приводится к справочному написанию."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    lot = re.search(r"Лот\s*№?\s*([\w-]+)", t, re.I)
    m = re.match(r"^([0-9][0-9/.,]*(?:\s*[A-Za-z][A-Za-z]*)*)", t)
    name = yarns.canon(m.group(1) if m else re.split(r"\s+Лот", t)[0])[:40]
    return name, (lot.group(1) if lot else None)


def orders_of(payload):
    if isinstance(payload, list):
        return payload
    return ((payload.get("data") or {}).get("productionOrders")
            or payload.get("productionOrders") or [])


def load_production_orders(payload, who="1С", make_orders=True):
    """Разбирает ответ 1С в техкарты; по желанию сразу заводит заказы в план."""
    orders = orders_of(payload)
    if not orders:
        raise ValueError("в ответе нет productionOrders")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    cards = n_yarns = links = 0
    no_spec, mapping, new_yarns = [], [], []
    db = shop()
    try:
        for o in orders:
            code = (o.get("productCode") or "").strip()
            if not code:
                continue
            si = o.get("sizeInfo") or {}
            comps = (o.get("technologies") or {}).get("components") or []
            has_spec = not any("Info" in c for c in comps)
            if not has_spec:
                no_spec.append(code)
            cloth = (o.get("clothCode") or o.get("loomClothCode") or "").strip()
            try:
                due = planning.norm_day(o.get("dueDate") or o.get("deadline") or "")
            except ValueError:
                due = None
            # Техкарта — по заказу и номенклатуре: та же номенклатура в другом
            # заказе — другая техкарта (свои количество, срок, лоты).
            onum = str(o.get("orderNumber") or "").strip()
            db.execute(
                "INSERT OR REPLACE INTO tech_card (product_code, uuid, order_number, size, size_cm,"
                " panels, ppt, gsm, weight_kg, seconds_per_row, seconds_per_pcs, total_quantity,"
                " total_rolls, has_spec, cloth_code, due_day, loaded_at)"
                " VALUES (" + ",".join("?" * 17) + ")",
                (code, o.get("uuid"), onum, si.get("size"),
                 size_cm_from(si.get("size"), code), si.get("numberLines"),
                 o.get("weftPerOneRow") or None, o.get("gsm") or gsm_from_code(code),
                 o.get("Weight") or o.get("weight") or None,
                 o.get("secondsPerRow") or None, o.get("secondsPerPcs") or None,
                 o.get("totalQuantity"), o.get("totalNumberRolls"), 1 if has_spec else 0,
                 cloth or None, due, now))
            cards += 1

            db.execute("DELETE FROM tech_card_yarn WHERE order_number=? AND product_code=?",
                       (onum, code))
            for c in comps:
                slot = YARN_SLOT.get(c.get("type"))
                if not slot:
                    continue
                name, lot = parse_component(c.get("productCode", ""))
                db.execute(
                    "INSERT OR REPLACE INTO tech_card_yarn (order_number, product_code, slot,"
                    " yarn_code, lot, grams, description) VALUES (?,?,?,?,?,?,?)",
                    (onum, code, slot, name or c.get("productCode"), lot, c.get("quantity"),
                     c.get("productCode")))
                if name:
                    new_yarns.append((name, SLOT_KIND.get(slot, "")))
                n_yarns += 1

            db.execute("DELETE FROM tech_card_loom WHERE order_number=? AND product_code=?",
                       (onum, code))
            for w in (o.get("technologies") or {}).get("workCenters") or []:
                db.execute("INSERT OR REPLACE INTO tech_card_loom (order_number, product_code, loom)"
                           " VALUES (?,?,?)", (onum, code, norm_loom(w)))
                links += 1
            if cloth:
                mapping.append((cloth, code))
        db.commit()
    finally:
        db.close()

    for cloth, code in mapping:
        planning.set_cloth_map(cloth, code, who)
    # Пряжа из 1С сразу попадает в справочник — одно написание и в отчёте, и в заправке.
    added = 0
    for name, kind in new_yarns:
        try:
            if not yarns.add(name, kind).get("exists"):
                added += 1
        except ValueError:
            pass
    import cache
    cache.clear()           # дизайн и пряжа на дашборде — из свежих техкарт
    out = {"cards": cards, "yarns": n_yarns, "yarns_added": added, "looms": links,
           "no_spec": no_spec, "cloth_mapped": len(mapping)}
    if make_orders:
        out["plan"] = planning.import_from_1c()
    return out


KEEP_MESSAGES = 5000        # столько последних сообщений 1С храним целиком


def _log_message(envelope, who, result, error):
    """Сообщение 1С как есть — в onec_message, вместе с тем, что мы ответили."""
    try:
        orders = [o for o in orders_of(envelope) if isinstance(o, dict)]
    except AttributeError:
        orders = []
    nums = " ".join(str(o.get("orderNumber")) for o in orders if o.get("orderNumber"))
    db = shop()
    try:
        cur = db.execute(
            "INSERT INTO onec_message (received_at, who, action, orders, order_numbers, ok, error,"
            " result, payload) VALUES (?,?,?,?,?,?,?,?,?)",
            (datetime.now().astimezone().isoformat(timespec="seconds"), who,
             envelope.get("actionType") if isinstance(envelope, dict) else None, len(orders),
             nums[:2000], 0 if error else 1, error,
             json.dumps(result, ensure_ascii=False) if result else None,
             json.dumps(envelope, ensure_ascii=False)))
        db.execute("DELETE FROM onec_message WHERE id <= ?", (cur.lastrowid - KEEP_MESSAGES,))
        db.commit()
        return cur.lastrowid
    finally:
        db.close()


def messages(limit=100):
    """Последние сообщения 1С — без тела, для списка на странице."""
    db = shop()
    rows = [dict(r) for r in db.execute(
        "SELECT id, received_at, who, action, orders, order_numbers, ok, error, result"
        " FROM onec_message ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 1000)),))]
    db.close()
    for r in rows:
        r["result"] = json.loads(r["result"]) if r["result"] else None
    return rows


def message(mid):
    """Одно сообщение 1С целиком: что прислали и что ответили."""
    db = shop()
    r = db.execute("SELECT * FROM onec_message WHERE id=?", (mid,)).fetchone()
    db.close()
    if not r:
        raise ValueError("сообщения №%s нет" % mid)
    r = dict(r)
    r["payload"] = json.loads(r["payload"])
    r["result"] = json.loads(r["result"]) if r["result"] else None
    return r


def handle_1c(envelope, who="1С"):
    """Запрос 1С: каждое сообщение сохраняется как есть — и удачное, и с ошибкой."""
    try:
        r = _handle_1c(envelope, who)
    except (ValueError, TypeError, KeyError) as e:
        _log_message(envelope, who, None, str(e))
        raise
    r["message_id"] = _log_message(envelope, who, r, None)
    _store_orders(envelope, r["message_id"])
    return r


def _store_orders(envelope, message_id):
    """Каждый заказ — последней присланной версией, как есть. Повтор заказа
    заменяет прежнюю версию и прибавляет счётчик версий."""
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    db = shop()
    try:
        for o in orders_of(envelope):
            if not isinstance(o, dict):
                continue
            key = str(o.get("uuid") or o.get("orderNumber") or o.get("productCode") or "").strip()
            if not key:
                continue
            db.execute(
                "INSERT INTO onec_order (order_key, order_number, product_code, received_at,"
                " message_id, raw) VALUES (?,?,?,?,?,?) ON CONFLICT(order_key) DO UPDATE SET"
                " order_number=excluded.order_number, product_code=excluded.product_code,"
                " received_at=excluded.received_at, message_id=excluded.message_id,"
                " versions=versions+1, raw=excluded.raw",
                (key, str(o.get("orderNumber") or "") or None, o.get("productCode"), now,
                 message_id, json.dumps(o, ensure_ascii=False)))
        db.commit()
    finally:
        db.close()


def rebuild_from_archive(who="архив 1С"):
    """Пересобрать техкарты из архива 1С: каждая строка заказа лежит в onec_order
    последней версией, как пришла. Нужно после смены ключа техкарт — раньше
    заказы с одной номенклатурой затирали друг друга (1708 затёр 1484)."""
    db = shop()
    raws = [json.loads(r["raw"]) for r in db.execute("SELECT raw FROM onec_order ORDER BY received_at")]
    db.close()
    if not raws:
        return {"cards": 0}
    r = load_production_orders({"productionOrders": raws}, who=who)
    import loomplan
    nums = sorted({str(o.get("orderNumber")) for o in raws if o.get("orderNumber")})
    r["picked"] = loomplan.rematch(orders=nums)
    return r


def stored_orders(order=None, since=None, limit=None):
    """Что прислала 1С: заказы последней версией в её же формате — такой ответ
    можно отправить обратно в POST /api/v1/1c. ?order= — один заказ (номер или
    uuid), ?from= — полученные с этого дня."""
    sql, args = "SELECT * FROM onec_order WHERE 1=1", []
    if order:
        sql += " AND (order_number = ? OR order_key = ?)"
        args += [str(order).strip()] * 2
    if since:
        sql += " AND received_at >= ?"
        args.append(str(since).strip().replace(".", "-"))
    sql += " ORDER BY received_at DESC, order_number DESC LIMIT ?"
    args.append(max(1, min(int(limit or 1000), 10000)))
    db = shop()
    rows = [dict(r) for r in db.execute(sql, args)]
    db.close()
    return {"actionType": "CreateOrUpdateProductionOrderAPI", "count": len(rows),
            "data": {"productionOrders": [json.loads(r["raw"]) for r in rows]},
            "received": [{"orderNumber": r["order_number"], "key": r["order_key"],
                          "productCode": r["product_code"], "received_at": r["received_at"],
                          "versions": r["versions"], "message_id": r["message_id"]}
                         for r in rows]}


def _handle_1c(envelope, who):
    """Запрос 1С в её собственном конверте: actionType + data. Отвечаем сразу —
    ожидание 1С (wait, waitTimeout) нам не нужно, разбор занимает доли секунды."""
    if not isinstance(envelope, dict):
        raise ValueError("нужен JSON-объект")
    action = envelope.get("actionType") or (
        "CreateOrUpdateProductionOrderAPI" if orders_of(envelope) else "")
    if action not in ACTIONS:
        raise ValueError("неизвестный actionType «%s»; понимаем: %s" % (action, ", ".join(ACTIONS)))
    # Пустой список от 1С — «нечего отправлять», а не ошибка: ответ 400 заставил
    # бы 1С считать отправку неудачной. Само сообщение всё равно остаётся в архиве.
    data = envelope.get("data")
    if isinstance(data, dict) and data.get("productionOrders") == []:
        return {"success": True, "actionType": action, "cards": 0, "yarns": 0,
                "warning": "пустой список productionOrders — сохранять нечего"}
    r = load_production_orders(envelope, who=who)
    import loomplan
    nums = sorted({str(o.get("orderNumber")) for o in orders_of(envelope) if o.get("orderNumber")})
    # Клеткам плана этих заказов — изделие из свежих техкарт (кроме выбранных руками).
    r["picked"] = loomplan.rematch(orders=nums) if nums else {}
    r["report_days"] = loomplan.rebuild_reports("0000", "9999", nums) if nums else []
    return {"success": True, "actionType": action, **r}


def pull_1c(cfg):
    """Забрать заказы из 1С по адресу из настроек и разобрать их."""
    req = urllib.request.Request(cfg["url"], headers={"Accept": "application/json"})
    if cfg.get("token"):
        req.add_header("Authorization", cfg["token"])
    with urllib.request.urlopen(req, timeout=int(cfg.get("timeout") or 60)) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    return handle_1c(payload, who="1С (опрос)")
