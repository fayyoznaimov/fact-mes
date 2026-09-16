"""Заправка станка, введённая вручную: GSM, вес штуки, PPT, панели, пряжа и лот.

Часть этих данных пока не приходит ни из FACT, ни из 1С: вес штуки и лот
пряжи знает только цех. Запись действует с указанного дня, пока станок не
перезаправят. Пустое поле значит «как в справочнике»: берётся значение из
справочника артикулов или техкарты 1С.

Вводить можно по одному станку (щелчок по номеру станка в отчёте) или таблицей
на все станки сразу — вкладка «Заправка», как раньше в Excel. Пряжа проверяется
по справочнику (yarns.py): одно написание на одну пряжу.

Отчёт (лист TOYOTA, `_tools/make_excel_report.py`) читает эту таблицу сам;
после сохранения отчёт пересобирается за все дни, начиная с дня заправки.
"""
import json
import re
from datetime import datetime

import yarns
from storage import fact, shop

NUMBERS = {"gsm": (100, 1500), "weight_kg": (0.01, 5), "ppt": (200, 9000), "panels": (1, 12)}
# Места пряжи — как типы компонентов в техкарте 1С, у каждого свой лот:
# weft1 — уток, weft2 — кромка, weft3 — бордюр, weft4 — бордюр полиэстер.
YARNS = ("pile", "ground", "weft1", "weft2", "hemply", "hempoly", "weft3", "fancyply", "weft4")
TEXTS = tuple("%s_%s" % (y, k) for y in YARNS for k in ("yarn", "lot"))
FIELDS = tuple(NUMBERS) + TEXTS
YARN_RU = {"pile": "ворс", "ground": "грунт", "weft1": "уток", "weft2": "кромка",
           "hemply": "кромка кручёная", "hempoly": "кромка полиэстер", "weft3": "бордюр",
           "fancyply": "бордюр кручёная", "weft4": "бордюр полиэстер"}
NAMES = {"gsm": "GSM", "weight_kg": "вес штуки", "ppt": "PPT", "panels": "панели"}
MAX_DAYS = 62           # дальше назад отчёт при сохранении не пересобираем


def effective(day):
    """{станок: заправка, действующая в этот день} — только введённое вручную."""
    db = shop()
    rows = db.execute(
        "SELECT * FROM loom_setup s WHERE from_day <= ? AND from_day = ("
        " SELECT MAX(from_day) FROM loom_setup b WHERE b.loom = s.loom AND b.from_day <= ?)",
        (day, day)).fetchall()
    db.close()
    return {r["loom"]: dict(r) for r in rows}


def _number(field, raw):
    s = str(raw if raw is not None else "").strip().replace(",", ".").replace(" ", "")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        raise ValueError("%s: «%s» — не число" % (NAMES[field], raw))
    # Вес штуки часто пишут в граммах: 635 — это 0,635 кг.
    if field == "weight_kg" and v > NUMBERS["weight_kg"][1]:
        v = v / 1000.0
    lo, hi = NUMBERS[field]
    if not lo <= v <= hi:
        raise ValueError("%s: %s — вне разумных границ %s–%s" % (NAMES[field], raw, lo, hi))
    return int(round(v)) if field == "panels" else round(v, 4)


def _clean(values):
    """Проверенная строка заправки: числа в границах, пряжа — из справочника."""
    row = {f: _number(f, values.get(f, "")) for f in NUMBERS}
    for y in YARNS:
        try:
            row[y + "_yarn"] = yarns.resolve(values.get(y + "_yarn"))
        except ValueError as e:
            raise ValueError("%s: %s" % (YARN_RU[y], e))
        lot = re.sub(r"\s+", " ", str(values.get(y + "_lot") or "").strip().upper())
        row[y + "_lot"] = lot[:40] or None
    return row


def _check_day(from_day):
    try:
        datetime.strptime(from_day or "", "%Y.%m.%d")
    except ValueError:
        raise ValueError("день заправки: нужна дата вида 2026.09.14")


def _write(pairs, from_day, who, effective_at=None):
    """Записать [(станок, строка)] и пересобрать отчёт с дня заправки."""
    import productionlog
    now = productionlog.now()
    valid = datetime.strptime(from_day, '%Y.%m.%d').replace(tzinfo=productionlog.TZ)
    if effective_at:
        try:
            valid = datetime.fromisoformat(effective_at)
            valid = valid.replace(tzinfo=productionlog.TZ) if valid.tzinfo is None else valid.astimezone(productionlog.TZ)
            if valid.strftime('%Y.%m.%d') != from_day:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Время начала заправки должно относиться к выбранному дню') from None
    db = shop()
    token = productionlog.ACTOR.set(who or 'система')
    try:
        db.execute('BEGIN IMMEDIATE')
        documents = [(loom, document_snapshot(db, loom, from_day, row)) for loom,row in pairs]
        db.executemany(
            "INSERT OR REPLACE INTO loom_setup (loom, from_day, %s, set_by, set_at) VALUES (%s)"
            % (", ".join(FIELDS), ",".join("?" * (len(FIELDS) + 4))),
            [(loom, from_day, *[row[f] for f in FIELDS], who, now) for loom, row in pairs])
        for loom, snap in documents:
            snap['precision'] = 'minute' if effective_at else 'day'
            db.execute('INSERT INTO setup_document(loom,valid_from,created_at,author,snapshot_json) VALUES (?,?,?,?,?)',
                       (loom,valid.isoformat(),now,who,json.dumps(snap,ensure_ascii=False)))
        db.commit()
    finally:
        db.close()
        productionlog.ACTOR.reset(token)
    with fact() as f:
        days = [r[0] for r in f.execute(
            "SELECT DISTINCT day FROM shift_full WHERE day >= ? ORDER BY day LIMIT ?",
            (from_day, MAX_DAYS))]
    import reports
    return reports.rebuild_daily_reports(days)


def document_snapshot(db, loom, day, values):
    """Полный снимок источников, без изменяемых ссылок на справочники."""
    plan = db.execute('SELECT * FROM loom_plan WHERE loom=? AND day=?',(loom,day)).fetchone()
    plan = dict(plan) if plan else {}
    card = db.execute('SELECT * FROM tech_card WHERE order_number=? AND product_code=?',
                      (plan.get('order_no') or '',plan.get('product_code') or '')).fetchone()
    card = dict(card) if card else {}
    yarn_rows = [dict(r) for r in db.execute('SELECT * FROM tech_card_yarn WHERE order_number=? AND product_code=?',
                 (card.get('order_number') or '',card.get('product_code') or ''))]
    setting = db.execute("SELECT value FROM setting WHERE key='weight_allowance_pct'").fetchone()
    resolved = dict(values)
    # PPT остаётся только явно введённым: плановые секунды 1С не равны прокидкам.
    for key in ('gsm', 'panels'):
        if resolved.get(key) in (None, ''):
            resolved[key] = card.get(key) or plan.get(key)
    slots = {'vors':'pile','karenoy':'ground','utog1':'weft1','utog2':'weft2','utog2p':'hemply',
             'utog2x':'hempoly','utog3':'weft3','utog3p':'fancyply','utog4':'weft4'}
    for yarn in yarn_rows:
        slot = slots.get(yarn.get('slot'))
        if slot:
            for suffix, source in (('_yarn','yarn_code'),('_lot','lot')):
                if resolved.get(slot+suffix) in (None, ''):
                    resolved[slot+suffix] = yarn.get(source)
    return {'schema_version':1,'loom':loom,'day':day,'precision':'day',
            'plan':plan,'tech_card':card,'tech_card_yarns':yarn_rows,'values':values,
            'resolved':resolved,'weight_allowance_pct':setting[0] if setting else None,
            'warning':None if card else 'Техкарта по плану не найдена; сохранены введённые значения'}


def documents(loom='', limit=100, before=None):
    db=shop()
    try:
        conditions, args = [], []
        if loom:conditions.append('loom=?');args.append(loom)
        if before:conditions.append('id<?');args.append(int(before))
        rows=db.execute('SELECT * FROM setup_document'+(' WHERE '+' AND '.join(conditions) if conditions else '')+
                        ' ORDER BY id DESC LIMIT ?', (*args,min(max(int(limit),1),500))).fetchall()
        return [dict(id=r['id'],loom=r['loom'],valid_from=r['valid_from'],created_at=r['created_at'],
                     author=r['author'],source=r['source'],snapshot=json.loads(r['snapshot_json'])) for r in rows]
    finally:db.close()


def yarn_analysis(from_day, to_day):
    """Сравнение только полных смен, целиком покрытых одним документом.

    Без счётчиков на границе заправки нельзя пропорционально делить выпуск.
    Смешанные смены и время до первого документа явно исключены.
    """
    from datetime import timedelta
    from productionlog import TZ
    first = datetime.strptime(from_day.replace('-','.'),'%Y.%m.%d').replace(tzinfo=TZ)
    last = datetime.strptime(to_day.replace('-','.'),'%Y.%m.%d').replace(tzinfo=TZ)
    if not 0 <= (last-first).days <= 366:
        raise ValueError('Выберите период до 366 дней')
    db=shop()
    try:
        docs={}
        for row in db.execute('SELECT * FROM setup_document WHERE valid_from<? ORDER BY valid_from,id',
                              ((last+timedelta(days=2)).isoformat(),)):
            doc=dict(row)
            doc['snapshot']=json.loads(doc['snapshot_json'])
            docs.setdefault(doc['loom'],{})[doc['valid_from']]=doc
    finally:db.close()
    groups={}; excluded={'no_document':0,'mixed_setup':0,'unfinished':0,'no_yarn':0,'incomplete':0};included=0
    with fact() as db:
        rows=db.execute('SELECT * FROM shift_full WHERE day BETWEEN ? AND ?',
                        (first.strftime('%Y.%m.%d'),last.strftime('%Y.%m.%d'))).fetchall()
    now=datetime.now(TZ)
    for row in rows:
        r=dict(row)
        hour={'A':7,'B':15,'C':23}.get(r.get('letter'))
        if hour is None:continue
        start=datetime.strptime(r['day'],'%Y.%m.%d').replace(tzinfo=TZ)+timedelta(hours=hour)
        end=start+timedelta(hours=8)
        if end>now:excluded['unfinished']+=1;continue
        if not 479 <= (r.get('run_min') or 0)+(r.get('stop_min') or 0) <= 481:
            excluded['incomplete']+=1;continue
        candidates=list(docs.get(r['loom'],{}).values())
        active=[d for d in candidates if datetime.fromisoformat(d['valid_from'])<=start]
        if not active:excluded['no_document']+=1;continue
        if any(start<datetime.fromisoformat(d['valid_from'])<end for d in candidates):
            excluded['mixed_setup']+=1;continue
        doc=active[-1];s=doc['snapshot'];v=s.get('resolved') or s['values'];p=s.get('plan') or {}
        yarns_found=[(slot,v.get(slot+'_yarn'),v.get(slot+'_lot')) for slot in YARNS if v.get(slot+'_yarn')]
        if not yarns_found:excluded['no_yarn']+=1;continue
        included+=1
        for slot,yarn,lot in yarns_found:
            key=(slot,yarn,lot,p.get('design'),v.get('gsm'))
            g=groups.setdefault(key,dict(slot=YARN_RU[slot],yarn=yarn,lot=lot,design=p.get('design'),gsm=v.get('gsm'),
                                         shifts=0,run_min=0,stop_min=0,picks=0,stops=0,rows=0,towels=0,panels_known=True,documents=set()))
            g['shifts']+=1;g['documents'].add(doc['id'])
            for field in ('run_min','stop_min','picks'):g[field]+=r.get(field) or 0
            g['rows']+=r.get('pieces') or 0
            if v.get('panels'):
                g['towels']+=(r.get('pieces') or 0)*v['panels']
            else:g['panels_known']=False
            g['stops']+=r.get({'pile':'top_ct','ground':'warp_ct'}.get(slot,'weft_ct')) or 0
    out=[]
    for g in groups.values():
        run=g['run_min'];total=run+g['stop_min']
        g.update(rpm=round(g['picks']/run,1) if run else None,
                 efficiency=round(100*run/total,1) if total else None,
                 stops_per_run_hour=round(g['stops']*60/run,2) if run else None,
                 documents=sorted(g['documents']))
        out.append(g)
    return dict(from_day=from_day,to_day=to_day,groups=out,included_shifts=included,excluded=excluded,
                note='Сравнение по сохранённым заправкам: отдельно дизайн и GSM. Обрывы утка общие для всех его компонентов; это не доказательство причины в конкретной пряже. Смены со сменой заправки исключены, поскольку нет точного выпуска на границе.')


def save(looms, from_day, values, who="", effective_at=None):
    """Одна заправка на один или несколько станков (окно по номеру станка)."""
    looms = sorted({(l or "").strip().upper() for l in looms if (l or "").strip()})
    if not looms:
        raise ValueError("не указан станок")
    _check_day(from_day)
    row = _clean(values)
    days = _write([(loom, row) for loom in looms], from_day, who, effective_at)
    return {"looms": looms, "from_day": from_day, "days": days}


def save_many(rows, from_day, who="", effective_at=None):
    """Таблица заправки: у каждого станка своя строка. Либо сохраняется всё,
    либо ничего — с перечнем, что поправить: половина сохранённой таблицы
    путает больше, чем ошибка."""
    _check_day(from_day)
    pairs, errors = [], []
    for r in rows or []:
        loom = (r.get("loom") or "").strip().upper()
        if not loom:
            continue
        try:
            pairs.append((loom, _clean(r.get("values") or {})))
        except ValueError as e:
            errors.append("%s — %s" % (loom, e))
    if errors:
        more = " и ещё %d" % (len(errors) - 10) if len(errors) > 10 else ""
        raise ValueError("ничего не сохранено: " + "; ".join(errors[:10]) + more)
    if not pairs:
        raise ValueError("изменений нет")
    if len({loom for loom, _ in pairs}) != len(pairs):
        raise ValueError('Станок повторяется в документе')
    days = _write(pairs, from_day, who, effective_at)
    return {"looms": [p[0] for p in pairs], "from_day": from_day, "days": days}


def _loom_key(loom):
    m = re.match(r"^([A-Za-z]+)(\d+)$", loom or "")
    return (m.group(1), int(m.group(2))) if m else (loom or "", 0)


def grid(day):
    """Все станки на день для таблицы заправки: что действует и что введено вручную.

    Справочные значения берутся из отчёта за этот день (или ближайший прошлый),
    пряжа — в справочном написании, чтобы таблица не пестрела «ошибками»
    из-за пробелов."""
    import reports
    days = reports.report_days()
    rd = next((d for d in days if d <= day), days[0] if days else None)
    rows = reports.report_day(rd) if rd else []
    setups = effective(day)
    out = []
    for r in sorted(rows, key=lambda x: _loom_key(x["loom"])):
        s = setups.get(r["loom"]) or {}
        ref = {"gsm": r.get("gsm"), "weight_kg": r.get("weight_kg"), "ppt": r.get("ppt"),
               "panels": r.get("panels")}
        # Пряжа и лоты — по местам, как их собрал отчёт (из техкарты 1С изделия по плану).
        try:
            for y in json.loads(r.get("yarns") or "[]"):
                ref[y["slot"] + "_yarn"], ref[y["slot"] + "_lot"] = y.get("yarn"), y.get("lot")
        except (ValueError, TypeError, KeyError):
            pass
        values, manual = {}, {}
        for f in FIELDS:
            if s.get(f) not in (None, ""):
                values[f], manual[f] = s[f], True
            else:
                v = ref.get(f)
                if f.endswith("_yarn"):
                    v = yarns.canon(v) if v not in (None, "", "0") else ""
                values[f] = v
        out.append({"loom": r["loom"], "cloth": r.get("cloth"), "design": r.get("design"),
                    "values": values,
                    "manual": manual, "from_day": s.get("from_day"), "set_by": s.get("set_by")})
    return {"day": day, "report_day": rd, "rows": out}
