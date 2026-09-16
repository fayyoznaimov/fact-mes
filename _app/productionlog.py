"""Неизменяемый журнал MES и архив минутных снимков FACT.

Записи журнала создаются триггерами в транзакции исходного изменения.
Прямым внешним писателям необходим register(connection); без него запись
блокируется, чтобы изменение не прошло без автора и времени.
"""
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
import json
import uuid
import zlib

ACTOR = ContextVar('production_actor', default='система')
TZ = timezone(timedelta(hours=5))
SCHEMA = '''
CREATE TABLE IF NOT EXISTS production_event (
 id INTEGER PRIMARY KEY, at TEXT NOT NULL, batch TEXT NOT NULL, actor TEXT NOT NULL,
 entity TEXT NOT NULL, action TEXT NOT NULL, before_json TEXT, after_json TEXT
);
CREATE INDEX IF NOT EXISTS pe_entity ON production_event(entity,id);
CREATE TABLE IF NOT EXISTS production_baseline(entity TEXT PRIMARY KEY, at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS pe_no_update BEFORE UPDATE ON production_event
 BEGIN SELECT RAISE(ABORT,'Журнал изменений нельзя редактировать'); END;
CREATE TRIGGER IF NOT EXISTS pe_no_delete BEFORE DELETE ON production_event
 BEGIN SELECT RAISE(ABORT,'Журнал изменений нельзя удалять'); END;
CREATE TABLE IF NOT EXISTS setup_document (
 id INTEGER PRIMARY KEY, loom TEXT NOT NULL, valid_from TEXT NOT NULL,
 created_at TEXT NOT NULL, author TEXT NOT NULL, snapshot_json TEXT NOT NULL,
 source TEXT NOT NULL DEFAULT 'document'
);
CREATE INDEX IF NOT EXISTS sd_loom ON setup_document(loom,valid_from,id);
CREATE TRIGGER IF NOT EXISTS sd_no_update BEFORE UPDATE ON setup_document
 BEGIN SELECT RAISE(ABORT,'Документ заправки неизменяем; создайте новую версию'); END;
CREATE TRIGGER IF NOT EXISTS sd_no_delete BEFORE DELETE ON setup_document
 BEGIN SELECT RAISE(ABORT,'Документ заправки нельзя удалять'); END;
CREATE TABLE IF NOT EXISTS machine_sample (
 snapshot TEXT PRIMARY KEY, at INTEGER NOT NULL, received_at TEXT NOT NULL, data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS ms_at ON machine_sample(at);
'''
TABLES = ('assignment','shift_master','shift_doc','loom_setup','loom_plan',
          'tech_card','tech_card_yarn','operator','ticket')


def now():
    return datetime.now(TZ).isoformat(timespec='microseconds')


def register(db):
    batch = uuid.uuid4().hex
    db.create_function('mes_actor', 0, lambda: ACTOR.get())
    db.create_function('mes_time', 0, now)
    db.create_function('mes_batch', 0, lambda: batch)
    db.execute('PRAGMA recursive_triggers=ON')


def install(db, tables=TABLES):
    db.executescript(SCHEMA)
    for table in tables:
        columns = [r[1] for r in db.execute('PRAGMA table_info(' + table + ')')]
        if not columns:
            continue
        def obj(prefix):
            result = 'json_object(' + ','.join("'%s',%s.\"%s\"" % (c,prefix,c) for c in columns) + ')'
            if table == 'assignment':
                result = "json_set(" + result + ", '$.operator_name',(SELECT name FROM operator WHERE id=" + prefix + ".operator_id), '$.operator_code',(SELECT code FROM operator WHERE id=" + prefix + ".operator_id))"
            return result
        if not db.execute('SELECT 1 FROM production_baseline WHERE entity=?',(table,)).fetchone():
            db.execute("INSERT INTO production_event(at,batch,actor,entity,action,after_json) "
                       "SELECT mes_time(),mes_batch(),'миграция',?,'BASELINE',"+obj('t')+' FROM '+table+' t',(table,))
            db.execute('INSERT INTO production_baseline VALUES (?,?)',(table,now()))
        for action in ('INSERT','UPDATE','DELETE'):
            before = obj('OLD') if action != 'INSERT' else 'NULL'
            after = obj('NEW') if action != 'DELETE' else 'NULL'
            condition = ''
            if action == 'UPDATE':
                watched = [c for c in columns if table != 'ticket' or c in
                           ('ended_at','category_id','comment','classified_by','classified_at','opened_by')]
                condition = ' WHEN ' + ' OR '.join('OLD."%s" IS NOT NEW."%s"' % (c,c) for c in watched)
            db.execute('CREATE TRIGGER IF NOT EXISTS pl_%s_%s AFTER %s ON %s%s BEGIN '
                       'INSERT INTO production_event(at,batch,actor,entity,action,before_json,after_json) '
                       "VALUES(mes_time(),mes_batch(),mes_actor(),'%s','%s',%s,%s); END"
                       % (table,action,action,table,condition,table,action,before,after))
    db.commit()


def sample_archive(start,end):
    import storage
    db=storage.shop_readonly()
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='machine_sample'").fetchone():return []
        result=[]
        for r in db.execute('SELECT at,data FROM machine_sample WHERE at BETWEEN ? AND ? ORDER BY at',(start-120,end)):
            values=json.loads(zlib.decompress(r['data']))
            result.append((r['at'],{name:{key:v.get(key) for key in ('state','cause','running','state_sec')}
                                    for name,v in values.items()}))
        return result
    finally:db.close()


def signal_history(loom, day, period='day'):
    from datetime import timedelta
    date=datetime.strptime(day.replace('.','-'),'%Y-%m-%d').replace(tzinfo=TZ)
    if period not in ('day','A','B','C'):raise ValueError('Неверный период')
    start=int((date+timedelta(hours={'day':0,'A':7,'B':15,'C':23}[period])).timestamp())
    end=start+(86400 if period=='day' else 28800)
    history=samples(loom,start,end)
    return {'loom':loom,'start':start,'end':end,'samples':history,
            'note':'Сохранённые снимки FACT. Между снимками изменения могли не попасть в архив.'}


def archive_sample(snap):
    if snap.get('source') != 'fact':
        return
    import storage
    db = storage.shop()
    try:
        payload = zlib.compress(json.dumps(snap['looms'],ensure_ascii=False).encode(),6)
        db.execute('INSERT OR IGNORE INTO machine_sample VALUES (?,?,?,?)',
                   (str(snap['dir']),int(snap.get('fact_time') or snap['read_at']),now(),payload))
        db.commit()
    finally:
        db.close()


def samples(loom, start, end):
    import storage
    db = storage.shop_readonly()
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='machine_sample'").fetchone():
            return []
        result=[]
        for row in db.execute('SELECT at,data FROM machine_sample WHERE at BETWEEN ? AND ? ORDER BY at',
                              (start-120,end)):
            value=json.loads(zlib.decompress(row['data'])).get(loom)
            if value:
                result.append(dict(at=row['at'],values=value))
        return result
    finally:
        db.close()


def events(entity, loom='', limit=200, record_id=None):
    if entity not in TABLES:
        raise ValueError('Неизвестный журнал')
    import storage
    db=storage.shop_readonly()
    try:
        where='entity=?';args=[entity]
        if loom:
            where+=" AND COALESCE(json_extract(after_json,'$.loom'),json_extract(before_json,'$.loom'))=?"
            args.append(loom)
        if record_id:
            where+=" AND COALESCE(json_extract(after_json,'$.id'),json_extract(before_json,'$.id'))=?"
            args.append(int(record_id))
        rows=db.execute('SELECT * FROM production_event WHERE '+where+' ORDER BY id DESC LIMIT ?',
                        (*args,min(max(int(limit),1),1000))).fetchall()
        return [dict(id=r['id'],at=r['at'],actor=r['actor'],action=r['action'],
                     before=json.loads(r['before_json']) if r['before_json'] else None,
                     after=json.loads(r['after_json']) if r['after_json'] else None) for r in rows]
    finally:db.close()


def assignment_periods(day, shift, loom=''):
    """Интервалы по времени сохранения; правки закрытой смены показаны отдельно.

    DELETE+INSERT в одном соединении — одно сохранение, а не уход оператора.
    Старые данные имеют только точность смены, не выдуманное время замены.
    """
    import storage
    date = datetime.strptime(day.replace('-', '.'), '%Y.%m.%d').replace(tzinfo=TZ)
    if shift not in ('A', 'B', 'C'):
        raise ValueError('Неверная смена')
    start = date + timedelta(hours={'A':7, 'B':15, 'C':23}[shift])
    end = start + timedelta(hours=8)
    db = storage.shop_readonly()
    try:
        rows = db.execute("SELECT * FROM production_event WHERE entity='assignment' AND "
                          "COALESCE(json_extract(after_json,'$.day'),json_extract(before_json,'$.day'))=? "
                          "AND COALESCE(json_extract(after_json,'$.shift'),json_extract(before_json,'$.shift'))=? ORDER BY id",
                          (date.strftime('%Y.%m.%d'), shift)).fetchall()
    finally:
        db.close()
    batches = {}
    for r in rows:
        before = json.loads(r['before_json']) if r['before_json'] else None
        after = json.loads(r['after_json']) if r['after_json'] else None
        machine = (after or before)['loom']
        if loom and machine != loom:
            continue
        key = (r['batch'], machine)
        if key not in batches:
            batches[key] = dict(loom=machine, at=r['at'], actor=r['actor'], action=r['action'], before=before)
        batches[key]['after'] = after
    periods, corrections, current = [], [], {}
    for event in batches.values():
        machine = event['loom']
        at = datetime.fromisoformat(event['at'])
        after = event['after']
        if event['action'] == 'BASELINE':
            current[machine] = dict(loom=machine,start=start.isoformat(),operator=after,
                                    actor=event['actor'],quality='legacy_shift')
            continue
        if at >= end:
            corrections.append(event)
            continue
        prior = current.get(machine)
        if prior and (prior['operator'] or {}).get('operator_id') == (after or {}).get('operator_id'):
            continue
        effective = max(start, at)
        if prior and datetime.fromisoformat(prior['start']) < effective:
            periods.append(dict(prior,end=effective.isoformat()))
        current[machine] = dict(loom=machine,start=effective.isoformat(),operator=after,
                                actor=event['actor'],quality='scheduled' if at < start else 'recorded')
    for value in current.values():
        periods.append(dict(value,end=end.isoformat()))
    return dict(day=day,shift=shift,periods=periods,corrections=corrections,
                note='Замены в текущей смене действуют с момента сохранения. Старые данные — только точность смены; поздние исправления показаны отдельно.')
