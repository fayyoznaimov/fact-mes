"""Изменения человеческим языком: что за объект, какой реквизит, было → стало.

Журнал production_event хранит строки таблиц целиком (JSON до и после). Читать
их как есть нельзя: «operator_id 23», «category_id toir», «2026-09-16T15:08:39…».
Здесь — как в истории версий 1С и журнале изменений SAP: операция (одно
сохранение: кто, когда), в ней объекты («Станок J9 · 16.09.2026 · смена C»),
у объекта — реквизиты с понятными названиями, старым и новым значением.
"""
import json
from datetime import datetime

YARN_RU = {"pile": "ворс", "ground": "грунт", "weft1": "уток", "weft2": "кромка",
           "hemply": "кромка кручёная", "hempoly": "кромка полиэстер", "weft3": "бордюр",
           "fancyply": "бордюр кручёная", "weft4": "бордюр полиэстер"}
SETUP = {"from_day": "Действует с", "gsm": "GSM", "weight_kg": "Вес штуки, кг", "ppt": "PPT — прокидки на ряд",
         "panels": "Панелей", "set_by": "Кто ввёл", "set_at": "Когда введено"}
for _slot, _ru in YARN_RU.items():
    SETUP[_slot + "_yarn"] = "Пряжа: " + _ru
    SETUP[_slot + "_lot"] = "Лот: " + _ru

LABELS = {
    "assignment": {"day": "День", "shift": "Смена", "loom": "Станок", "operator_id": "Оператор"},
    "shift_master": {"day": "День", "shift": "Смена", "operator_id": "Мастерица"},
    "shift_doc": {"day": "День", "shift": "Смена", "foreman_id": "Мастер смены", "status": "Статус",
                  "source": "Чем заполнено", "note": "Примечание", "created_at": "Создано",
                  "updated_by": "Изменил", "updated_at": "Когда изменено",
                  "confirmed_by": "Утвердил", "confirmed_at": "Когда утверждено"},
    "loom_setup": dict(SETUP, loom="Станок"),
    "loom_plan": {"loom": "Станок", "day": "День", "order_no": "Заказ", "product": "Изделие в плане",
                  "size": "Размер", "design": "Дизайн", "client": "Клиент", "gsm": "GSM",
                  "pile_yarn": "Ворс в плане", "note": "Пометка", "product_code": "Изделие 1С",
                  "pick": "Как выбрано изделие", "loaded_by": "Кто загрузил", "loaded_at": "Когда загружено"},
    "tech_card": {"order_number": "Заказ", "product_code": "Номенклатура", "uuid": "UUID 1С", "size": "Размер",
                  "size_cm": "Размер, см", "panels": "Панелей", "ppt": "PPT", "gsm": "GSM",
                  "weight_kg": "Вес штуки, кг", "seconds_per_row": "Секунд на ряд",
                  "seconds_per_pcs": "Секунд на штуку", "total_quantity": "Количество",
                  "total_rolls": "Рулонов", "has_spec": "Есть спецификация", "cloth_code": "Код ткани",
                  "due_day": "Срок", "loaded_at": "Когда получено из 1С"},
    "tech_card_yarn": {"order_number": "Заказ", "product_code": "Номенклатура", "slot": "Место пряжи",
                       "yarn_code": "Пряжа", "lot": "Лот", "grams": "Граммов", "description": "Описание 1С"},
    "tech_card_loom": {"order_number": "Заказ", "product_code": "Номенклатура", "loom": "Станок"},
    "operator": {"id": "№", "code": "Код", "name": "ФИО", "role": "Роль", "active": "Работает"},
    "ticket": {"id": "№", "loom": "Станок", "started_at": "Начало останова", "ended_at": "Окончание останова",
               "duration_sec": "Длительность", "fact_cause": "Сигнал станка", "style": "Артикул",
               "shift": "Смена", "category_id": "Причина", "comment": "Комментарий", "opened_by": "Кто завёл",
               "classified_by": "Кто указал причину", "classified_at": "Когда указана причина",
               "escalated_at": "Когда ушло мастеру"},
    "setting": {"key": "Параметр", "value": "Значение"},
    "rate_period": {"valid_from": "Действует с", "rate": "Ставка, сум", "unit": "За что",
                    "set_by": "Кто", "set_at": "Когда"},
    "cloth_map": {"cloth_norm": "Код ткани (ключ)", "cloth_code": "Код ткани на станке",
                  "product_code": "Артикул 1С", "set_by": "Кто", "set_at": "Когда"},
    "ppt_manual": {"key": "Код ткани / артикул", "ppt": "PPT", "panels": "Панелей", "source": "Источник",
                   "set_by": "Кто", "set_at": "Когда"},
    "yarn": {"id": "№", "name": "Пряжа", "key": "Ключ", "kind": "Вид", "active": "В справочнике",
             "created_at": "Добавлена"},
    "yarn_lot": {"code": "Код 1С", "name": "Наименование", "yarn": "Пряжа", "kind": "Вид", "lot": "Лот",
                 "supplier": "Поставщик", "color": "Цвет", "twist": "Крутка", "composition": "Состав",
                 "bag_kg": "Вес мешка, кг", "bobbins": "Бобин в мешке", "active": "Действует",
                 "loaded_by": "Кто загрузил", "loaded_at": "Когда загружено"},
    "loom_article": {"loom": "Станок", "product_code": "Артикул", "from_day": "С дня", "note": "Примечание",
                     "set_by": "Кто", "set_at": "Когда"},
    "plan_order": {"id": "№", "order_no": "Заказ", "product_code": "Артикул", "qty_towels": "Полотенец",
                   "due_day": "Срок", "source": "Источник", "note": "Примечание", "closed": "Закрыт"},
    "plan_loom": {"order_id": "Заказ №", "loom": "Станок", "from_day": "С дня", "qty_towels": "Доля станка, полотенец"},
    "doc": {"number": "Номер", "status": "Статус", "title": "Документ", "cancelled_by": "Отменил",
            "cancelled_at": "Когда отменён", "cancel_reason": "Причина отмены", "comment": "Комментарий"},
    "app_user": {"login": "Логин", "name": "Имя", "role": "Роль", "must_change": "Сменить пароль при входе",
                 "active": "Активен", "created_at": "Создан", "secret_changed": "Пароль"},
    "app_user_access": {"user_id": "Пользователь №", "access_json": "Разделы и права"},
    "app_user_employee": {"user_id": "Пользователь №", "operator_id": "Сотрудник"},
    "api_key": {"name": "Название", "prefix": "Начало ключа", "scopes": "Доступ", "active": "Действует",
                "created_by": "Кто создал", "created_at": "Создан", "last_used_at": "Последнее использование",
                "secret_changed": "Ключ"},
}
ENTITY = {"assignment": "Расстановка", "shift_master": "Мастерица смены", "shift_doc": "Документ смены",
          "loom_setup": "Заправка", "loom_plan": "План", "tech_card": "Техкарта 1С", "tech_card_yarn": "Пряжа техкарты",
          "tech_card_loom": "Станки техкарты", "operator": "Сотрудник", "ticket": "Тикет", "setting": "Настройка",
          "rate_period": "Ставка", "cloth_map": "Карта тканей", "ppt_manual": "PPT", "yarn": "Справочник пряжи",
          "yarn_lot": "Партия пряжи", "loom_article": "Артикул на станке", "plan_order": "Заказ плана",
          "plan_loom": "Станок заказа", "doc": "Документ", "app_user": "Пользователь",
          "app_user_access": "Права пользователя", "app_user_employee": "Сотрудник пользователя", "api_key": "Ключ API"}
ACTIONS = {"INSERT": "Добавлено", "UPDATE": "Изменено", "DELETE": "Удалено",
           "BASELINE": "Состояние на момент включения истории"}
SETTINGS = {"rate": "Ставка (до документов)", "rate_unit": "Единица ставки", "andon_warn_min": "«Нет тикета» через, мин",
            "andon_alarm_min": "Тревога на доске через, мин", "andon_notify_min": "Мастеру в телеграм через, мин",
            "weight_allowance_pct": "Надбавка к весу штуки, %"}
WORDS = {
    ("shift_doc", "status"): {"draft": "черновик", "confirmed": "утверждён"},
    ("doc", "status"): {"posted": "проведён", "cancelled": "отменён"},
    ("operator", "role"): {"operator": "оператор", "master": "мастерица"},
    ("app_user", "role"): {"admin": "администратор", "master": "мастерица смены", "operator": "оператор",
                           "viewer": "наблюдатель"},
    ("loom_plan", "pick"): {"auto": "подобрано автоматически", "manual": "выбрано вручную",
                            "ambiguous": "неоднозначно", "nomatch": "не найдено в 1С"},
    ("rate_period", "unit"): {"kpick": "за 1000 пиков", "pick": "за пик"},
    ("yarn", "kind"): {"pile": "ворс", "ground": "грунт", "weft": "уток", "": "—"},
    ("yarn_lot", "kind"): {"pile": "ворс", "ground": "грунт", "weft": "уток"},
    ("tech_card_yarn", "slot"): {"vors": "ворс", "karenoy": "грунт", "utog1": "уток", "utog2": "кромка",
                                 "utog2p": "кромка кручёная", "utog2x": "кромка полиэстер", "utog3": "бордюр",
                                 "utog3p": "бордюр кручёная", "utog4": "бордюр полиэстер"},
}
FLAGS = {"active", "closed", "must_change", "has_spec"}
# Служебные поля не показываются отдельной строкой: они уже в шапке операции.
SERVICE = {"operator_name", "operator_code", "built_at", "set_by", "set_at", "updated_by", "updated_at",
           "loaded_by", "loaded_at"}


def day_text(v):
    if isinstance(v, str) and len(v) == 10 and v[4] in ".-" and v[7] in ".-":
        return "%s.%s.%s" % (v[8:10], v[5:7], v[:4])
    return v


def time_text(v):
    if not isinstance(v, str) or len(v) < 16 or v[10] not in "T ":
        return day_text(v)
    try:
        d = datetime.fromisoformat(v.replace(" ", "T"))
    except ValueError:
        return v
    return d.strftime("%d.%m.%Y %H:%M") + (":%02d" % d.second if d.second else "")


def value_text(entity, field, value, row=None):
    """Значение так, как его понимает человек в цехе."""
    if value is None or value == "":
        return None
    row = row or {}
    if (entity, field) in WORDS:
        return WORDS[(entity, field)].get(value, value)
    if field == "secret_changed":
        return "изменён" if value else "не менялся"
    if field in FLAGS:
        return "да" if value in (1, "1", True) else "нет"
    if field in ("operator_id", "foreman_id") and row.get("operator_name"):
        return " — ".join(str(x) for x in (row.get("operator_code"), row.get("operator_name")) if x)
    if field == "category_id":
        import tickets
        c = tickets.CATEGORY_BY_ID.get(value)
        return c["name"] if c else value
    if field == "duration_sec" and isinstance(value, (int, float)):
        return "%d мин %02d с" % (value // 60, value % 60)
    if field == "access_json":
        try:
            a = json.loads(value)
            return "разделы: %s; действия: %s" % (", ".join(a.get("sections", [])) or "—",
                                                   ", ".join(a.get("permissions", [])) or "—")
        except (ValueError, AttributeError):
            return value
    if field.endswith("_at") or field in ("started_at", "ended_at"):
        return time_text(value)
    if field in ("day", "from_day", "valid_from", "due_day"):
        return day_text(value)
    if entity == "setting" and field == "key":
        return SETTINGS.get(value, value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def object_title(entity, row):
    """Какой объект изменён — его имя, а не первичный ключ."""
    r = row or {}
    d = day_text(r.get("day"))
    if entity == "assignment":
        return "Станок %s · %s · смена %s" % (r.get("loom"), d, r.get("shift"))
    if entity in ("shift_master", "shift_doc"):
        return "Смена %s · %s" % (r.get("shift"), d)
    if entity == "loom_setup":
        return "Станок %s · заправка с %s" % (r.get("loom"), day_text(r.get("from_day")))
    if entity == "loom_plan":
        return "План · станок %s · %s" % (r.get("loom"), d)
    if entity in ("tech_card", "tech_card_yarn", "tech_card_loom"):
        extra = {"tech_card_yarn": " · %s" % value_text(entity, "slot", r.get("slot")),
                 "tech_card_loom": " · станок %s" % r.get("loom")}.get(entity, "")
        return "Техкарта · заказ %s · %s%s" % (r.get("order_number") or "—", r.get("product_code"), extra)
    if entity == "operator":
        return "Сотрудник %s — %s" % (r.get("code"), r.get("name"))
    if entity == "ticket":
        return "Тикет № %s · станок %s · останов %s" % (r.get("id"), r.get("loom"), time_text(r.get("started_at")))
    if entity == "setting":
        return "Настройка: %s" % SETTINGS.get(r.get("key"), r.get("key"))
    if entity == "rate_period":
        return "Ставка с %s" % day_text(r.get("valid_from"))
    if entity == "cloth_map":
        return "Код ткани %s" % r.get("cloth_code")
    if entity == "ppt_manual":
        return "PPT · %s" % r.get("key")
    if entity == "yarn":
        return "Пряжа %s" % r.get("name")
    if entity == "yarn_lot":
        return "Партия %s · %s" % (r.get("code"), r.get("name"))
    if entity == "loom_article":
        return "Станок %s · артикул с %s" % (r.get("loom"), day_text(r.get("from_day")))
    if entity == "plan_order":
        return "Заказ %s · %s" % (r.get("order_no"), r.get("product_code"))
    if entity == "plan_loom":
        return "Заказ № %s · станок %s" % (r.get("order_id"), r.get("loom"))
    if entity == "doc":
        return "Документ %s" % r.get("number")
    if entity == "app_user":
        return "Пользователь %s (%s)" % (r.get("login"), r.get("name"))
    if entity in ("app_user_access", "app_user_employee"):
        return "Пользователь № %s" % r.get("user_id")
    if entity == "api_key":
        return "Ключ API «%s»" % r.get("name")
    return ENTITY.get(entity, entity)


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fields(entity, before, after, only_changed=True):
    """Реквизиты: [{field, label, before, after, delta, changed}] в порядке таблицы."""
    before, after = before or {}, after or {}
    labels = LABELS.get(entity, {})
    order = list(dict.fromkeys([*after.keys(), *before.keys()]))
    out = []
    for f in order:
        if f in SERVICE or f == "secret_changed" and not after.get(f) or f not in labels and f in ("id", "doc_id"):
            continue
        b, a = before.get(f), after.get(f)
        changed = (b if b != "" else None) != (a if a != "" else None)
        if only_changed and before and after and not changed:
            continue
        if not before or not after:          # добавлен или удалён: пустые реквизиты не нужны
            if (a if after else b) in (None, ""):
                continue
        row = dict(field=f, label=labels.get(f, f),
                   before=value_text(entity, f, b, before) if before else None,
                   after=value_text(entity, f, a, after) if after else None, changed=changed)
        if before and after and _number(b) and _number(a):
            row["delta"] = round(a - b, 4)
        out.append(row)
    return out


def describe(entity, event):
    """Событие журнала → запись «кто, когда, какой объект, что было и что стало»."""
    before, after = event.get("before"), event.get("after")
    return dict(id=event.get("id"), at=event.get("at"), at_text=time_text(event.get("at")),
                actor=event.get("actor"), action=event.get("action"), raw_before=before, raw_after=after,
                action_text=ACTIONS.get(event.get("action"), event.get("action")),
                entity=entity, entity_text=ENTITY.get(entity, entity),
                object=object_title(entity, after or before),
                fields=fields(entity, before, after))


def operations(events):
    """События одного сохранения (batch) — одна операция, как версия объекта в 1С."""
    ops, index = [], {}
    events = _merge_replace(events)
    for e in events:
        key = (e.get("batch"), e.get("actor"))
        if key not in index:
            index[key] = dict(batch=e.get("batch"), at=e["at"], at_text=e["at_text"], actor=e["actor"], items=[])
            ops.append(index[key])
        index[key]["items"].append(e)
    return ops


def _merge_replace(events):
    """Удаление и вставка того же объекта одним сохранением — это правка, а не два действия
    (так пишут INSERT OR REPLACE и «удалить расстановку смены и записать заново»)."""
    groups = {}
    for e in events:
        groups.setdefault((e.get("batch"), e["entity"], e["object"]), []).append(e)
    out, seen = [], set()
    for e in events:
        key = (e.get("batch"), e["entity"], e["object"])
        if key in seen:
            continue
        seen.add(key)
        group = groups[key]
        dels = [x for x in group if x["action"] == "DELETE"]
        ins = [x for x in group if x["action"] == "INSERT"]
        if len(dels) == 1 and len(ins) == 1 and len(group) == 2:
            before, after = dels[0]["raw_before"], ins[0]["raw_after"]
            merged = dict(ins[0], action="UPDATE", action_text=ACTIONS["UPDATE"], raw_before=before,
                          fields=fields(e["entity"], before, after))
            if merged["fields"]:
                out.append(merged)
            continue
        out.extend(group)
    for e in out:
        e.pop("raw_before", None)
        e.pop("raw_after", None)
    return out


def setup_fields(prev, cur):
    """Заправка: действующие значения до и после, с источником каждого значения.

    Пустое ручное поле берётся из техкарты 1С — поэтому показываем и само
    значение, и откуда оно: «вручную», «техкарта 1С», «план»."""
    def side(snap):
        if not snap:
            return {}, {}
        values, resolved = snap.get("values") or {}, snap.get("resolved") or snap.get("values") or {}
        source = {}
        for f in resolved:
            if values.get(f) not in (None, ""):
                source[f] = "вручную"
            elif resolved.get(f) not in (None, ""):
                source[f] = "техкарта 1С" if (snap.get("tech_card") or {}) else "план"
        return resolved, source
    b, bs = side(prev)
    a, as_ = side(cur)
    out = []
    for f in [k for k in SETUP if k not in ("from_day", "set_by", "set_at")]:
        bv, av = b.get(f), a.get(f)
        if bv in ("", None) and av in ("", None):
            continue
        changed = str(bv if bv is not None else "") != str(av if av is not None else "") or bs.get(f) != as_.get(f)
        row = dict(field=f, label=SETUP[f], before=value_text("loom_setup", f, bv) if prev else None,
                   before_source=bs.get(f), after=value_text("loom_setup", f, av), after_source=as_.get(f),
                   changed=changed if prev else True)
        if prev and _number(bv) and _number(av):
            row["delta"] = round(av - bv, 4)
        out.append(row)
    return out


def setup_context(snap):
    p, c = (snap or {}).get("plan") or {}, (snap or {}).get("tech_card") or {}
    return {k: v for k, v in (("Заказ", p.get("order_no") or c.get("order_number")),
                              ("Изделие 1С", p.get("product_code") or c.get("product_code")),
                              ("Изделие в плане", p.get("product")), ("Дизайн", p.get("design")),
                              ("Клиент", p.get("client")), ("Размер", c.get("size") or p.get("size"))) if v}
