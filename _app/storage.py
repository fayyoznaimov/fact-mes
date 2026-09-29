"""Где лежат данные и как к ним подключаться.

Единственное место, где создаются соединения с базами. Когда цеховая база
переедет с SQLite на MS SQL, менять придётся этот файл, а не всё приложение.

Две базы, и они разные по смыслу:

    fact.db  — то, что пересчитывается из зеркала FACT (смены, отчёты).
               Потеряли — собрали заново скриптом rebuild_db.py. Читается только.
    shop.db  — то, что вводят люди: операторы, назначения, тикеты, пользователи,
               ставка. Это терять нельзя, её и надо переносить в настоящую СУБД.
"""
import json
import os
import sqlite3

import ingest

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
ROOT = os.path.dirname(HERE)
FACT_DB = os.path.join(ROOT, "_tools", "fact.db")
SHOP_DB = os.path.join(HERE, "shop.db")
TOOLS_DIR = os.path.join(ROOT, "_tools")
REPORTS_DIR = os.path.join(ROOT, "reports")
FACTDATA = os.path.join(ROOT, "factdata")
MIRROR_OPERATOR = os.path.join(FACTDATA, "operator")
# Файлы работающей службы: снимок станков от сборщика и отметка, что он жив.
RUN_DIR = os.path.join(HERE, "run")
LIVE_FILE = os.path.join(RUN_DIR, "live.json")

SHIFT_LETTERS = ["A", "B", "C"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS operator (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator',   -- operator | master
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE (code, role)
);
CREATE TABLE IF NOT EXISTS assignment (
    day TEXT NOT NULL, shift TEXT NOT NULL, loom TEXT NOT NULL,
    operator_id INTEGER NOT NULL REFERENCES operator(id),
    PRIMARY KEY (day, shift, loom)
);
CREATE TABLE IF NOT EXISTS shift_master (
    day TEXT NOT NULL, shift TEXT NOT NULL,
    operator_id INTEGER NOT NULL REFERENCES operator(id),
    PRIMARY KEY (day, shift, operator_id)
);
CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_assign_shift ON assignment(day, shift);

-- Что сейчас заправлено на станке. 1С знает только «изделие делается на этих
-- станках» — на один станок претендует несколько изделий, и по дате различить
-- их нельзя. Поэтому артикул ставит мастер при заправке, а всё остальное
-- (дизайн, пряжа, размер) подтягивается к нему из техкарты.
CREATE TABLE IF NOT EXISTS loom_article (
    loom TEXT NOT NULL,
    product_code TEXT NOT NULL,
    from_day TEXT NOT NULL,          -- с какого дня заправлено
    note TEXT,
    set_by TEXT,
    set_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (loom, from_day)
);
CREATE INDEX IF NOT EXISTS idx_loom_article ON loom_article(loom, from_day DESC);

-- Планирование: заказ приходит из 1С (или заводится руками), внутри заказа
-- изделие, и заказ ставится на станки. Факт считается по счётчикам станка.
CREATE TABLE IF NOT EXISTS plan_order (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL,
    product_code TEXT NOT NULL,
    qty_towels INTEGER NOT NULL,
    due_day TEXT,                    -- к какому дню нужно закончить
    source TEXT,                     -- «1С» или «вручную»
    note TEXT,
    closed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (order_no, product_code)
);
CREATE TABLE IF NOT EXISTS plan_loom (
    order_id INTEGER NOT NULL REFERENCES plan_order(id),
    loom TEXT NOT NULL,
    from_day TEXT NOT NULL,          -- с какого дня станок делает этот заказ
    qty_towels INTEGER,              -- доля станка; пусто — делим поровну
    PRIMARY KEY (order_id, loom)
);
CREATE INDEX IF NOT EXISTS idx_plan_loom ON plan_loom(loom, from_day);

-- Пиков на изделие: значение из 1С или введённое руками. Оно главнее
-- расчётного по счётчикам — расчёт остаётся запасным вариантом.
CREATE TABLE IF NOT EXISTS ppt_manual (
    key TEXT PRIMARY KEY,            -- код ткани на станке или артикул 1С
    ppt REAL NOT NULL,
    panels INTEGER,
    source TEXT,                     -- «1С» или «вручную»
    set_by TEXT,
    set_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Связка кода ткани на станке с артикулом 1С. Код ткани набирают на станке
-- руками («3050X7360»), артикул живёт в 1С («3060  D152 320»): без этой связки
-- план из 1С не видит, что станок уже ткёт заказ.
CREATE TABLE IF NOT EXISTS cloth_map (
    cloth_norm TEXT PRIMARY KEY,     -- код ткани без пробелов, знаков и регистра
    cloth_code TEXT NOT NULL,        -- как набран на станке
    product_code TEXT NOT NULL,      -- артикул 1С
    set_by TEXT,
    set_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Ключи для внешних систем (1С, бот, BI). Хранится только хэш: сам ключ
-- показывается один раз при создании.
CREATE TABLE IF NOT EXISTS api_key (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,            -- начало ключа, чтобы узнать его в списке
    key_hash TEXT NOT NULL UNIQUE,
    scopes TEXT NOT NULL,            -- read write tickets — через пробел
    active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    last_used_at TEXT
);

-- Техкарты 1С. Раньше лежали в базе станков, но это данные 1С, а не FACT:
-- базу станков можно стереть и собрать заново, техкарты при этом терять нельзя.
-- Техкарты 1С (tech_card, tech_card_yarn, tech_card_loom) — в TECH_CARD_SCHEMA ниже.

-- Расстановка на смену: три документа на каждый день (A, B, C) — кто мастер
-- смены, кто мастерицы, какой оператор на каком станке. Операторы и мастерицы
-- лежат в assignment и shift_master, здесь — шапка документа и его статус.
CREATE TABLE IF NOT EXISTS shift_doc (
    day TEXT NOT NULL, shift TEXT NOT NULL,
    foreman_id INTEGER REFERENCES operator(id),   -- мастер смены
    status TEXT NOT NULL DEFAULT 'draft',          -- draft — черновик, confirmed — утверждён
    source TEXT,                                   -- чем заполнен: прошлая смена, FACT, вручную
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_by TEXT, updated_at TEXT,
    confirmed_by TEXT, confirmed_at TEXT,
    PRIMARY KEY (day, shift)
);

-- Заправка станка, введённая вручную: GSM, вес штуки, PPT, пряжа и её лот.
-- Действует с from_day до следующей записи по этому станку — вводится один раз
-- при заправке, а не каждый день. Пустое поле — берём из справочника.
CREATE TABLE IF NOT EXISTS loom_setup (
    loom TEXT NOT NULL, from_day TEXT NOT NULL,
    gsm REAL, weight_kg REAL, ppt REAL, panels INTEGER, design TEXT,
    pile_yarn TEXT, pile_lot TEXT, ground_yarn TEXT, ground_lot TEXT,
    weft1_yarn TEXT, weft1_lot TEXT, weft2_yarn TEXT, weft2_lot TEXT,
    weft3_yarn TEXT, weft3_lot TEXT, weft4_yarn TEXT, weft4_lot TEXT,
    -- weft1 — уток, weft2 — кромка, weft3 — бордюр, weft4 — бордюр полиэстер;
    -- кромка кручёная, кромка полиэстер и бордюр кручёная — отдельно, как в 1С.
    hemply_yarn TEXT, hemply_lot TEXT, hempoly_yarn TEXT, hempoly_lot TEXT,
    fancyply_yarn TEXT, fancyply_lot TEXT,
    set_by TEXT, set_at TEXT,
    PRIMARY KEY (loom, from_day)
);

-- План цеха по станкам (Excel «TOYOTA - LOOM PLAN»): на каждый станок и день —
-- изделие, номер производственного заказа и ворс. Главное, чего нет ни в FACT,
-- ни в 1С: какой станок в какой день делает какой заказ.
CREATE TABLE IF NOT EXISTS loom_plan (
    loom TEXT NOT NULL, day TEXT NOT NULL,
    order_no TEXT,                   -- производственный заказ 1С
    product TEXT,                    -- как записано в плане: 70x140 J301/6 (420GSM)
    size TEXT, design TEXT, client TEXT, gsm INTEGER,
    pile_yarn TEXT,                  -- строка «Ворс» плана
    note TEXT,                       -- пометки: «Praborka 35 sm», «23 рулон берасиз»
    product_code TEXT,               -- изделие заказа: техкарта 1С
    pick TEXT,                       -- как выбрано изделие: auto, manual, ambiguous
    loaded_by TEXT, loaded_at TEXT,
    PRIMARY KEY (loom, day)
);
CREATE INDEX IF NOT EXISTS idx_loom_plan_order ON loom_plan(order_no);
CREATE INDEX IF NOT EXISTS idx_loom_plan_day ON loom_plan(day);

-- Кто и когда менял план цеха в приложении (перетаскиванием или вручную).
CREATE TABLE IF NOT EXISTS loom_plan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, who TEXT,
    loom TEXT NOT NULL, day TEXT NOT NULL,
    old_order TEXT, new_order TEXT, old_note TEXT, new_note TEXT
);

-- Всё, что прислала 1С, как есть: разбор можно повторить, спор — проверить.
-- Разобранное лежит в tech_card, tech_card_yarn, tech_card_loom и plan_order.
CREATE TABLE IF NOT EXISTS onec_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT, received_at TEXT NOT NULL, who TEXT,
    action TEXT, orders INTEGER, order_numbers TEXT, ok INTEGER NOT NULL,
    error TEXT, result TEXT, payload TEXT NOT NULL
);

-- Заказы 1С последней версией — ровно так, как их прислала 1С (JSON заказа).
-- Отдаются обратно через GET /api/v1/1c в том же формате.
CREATE TABLE IF NOT EXISTS onec_order (
    order_key TEXT PRIMARY KEY,      -- uuid заказа, без него — номер
    order_number TEXT, product_code TEXT,
    received_at TEXT NOT NULL, message_id INTEGER,
    versions INTEGER NOT NULL DEFAULT 1,   -- сколько раз 1С присылала заказ
    raw TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_onec_order_number ON onec_order(order_number);
CREATE INDEX IF NOT EXISTS idx_onec_order_received ON onec_order(received_at);

-- Справочник пряжи: одно написание на одну пряжу. key — название без пробелов,
-- по нему «16/1 SPUN», «16/1SPUN» и «16/1 spun» считаются одной пряжей.
CREATE TABLE IF NOT EXISTS yarn (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- как пишется в отчёте: 12/1, 16/1 SPUN, 300 DEN
    key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT '',   -- pile, ground, weft — подсказка, не ограничение
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""

# Документ: всё, что меняет учёт (заправка, ведомость, ставка, утверждённый
# отчёт), сначала проверяется, показывается человеку и только после его
# подтверждения проводится. Проведённый документ не меняется: исправляют
# новым документом (supersedes_id), отменяют с причиной. Кто и когда —
# в самом документе, построчная история — в production_event.
DOC_SCHEMA = """
CREATE TABLE IF NOT EXISTS doc (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted','cancelled')),
    title TEXT NOT NULL,
    period_from TEXT, period_to TEXT,
    comment TEXT,
    supersedes_id INTEGER REFERENCES doc(id),
    created_by TEXT NOT NULL, created_at TEXT NOT NULL,
    cancelled_by TEXT, cancelled_at TEXT, cancel_reason TEXT,
    payload_json TEXT NOT NULL,      -- что ввёл человек
    result_json TEXT NOT NULL,       -- что он видел и подтвердил: итоги, изменения, предупреждения
    checksum TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS doc_type_period ON doc(type, period_from, period_to);
CREATE TRIGGER IF NOT EXISTS doc_no_delete BEFORE DELETE ON doc
 BEGIN SELECT RAISE(ABORT,'Документ нельзя удалить: его можно только отменить с причиной'); END;
CREATE TRIGGER IF NOT EXISTS doc_only_cancel BEFORE UPDATE ON doc
 WHEN OLD.status <> 'posted' OR NEW.status <> 'cancelled'
   OR NEW.cancelled_by IS NULL OR NEW.cancelled_at IS NULL OR trim(COALESCE(NEW.cancel_reason,'')) = ''
   OR NEW.type IS NOT OLD.type OR NEW.number IS NOT OLD.number OR NEW.title IS NOT OLD.title
   OR NEW.period_from IS NOT OLD.period_from OR NEW.period_to IS NOT OLD.period_to
   OR NEW.comment IS NOT OLD.comment OR NEW.supersedes_id IS NOT OLD.supersedes_id
   OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at
   OR NEW.payload_json IS NOT OLD.payload_json OR NEW.result_json IS NOT OLD.result_json
   OR NEW.checksum IS NOT OLD.checksum
 BEGIN SELECT RAISE(ABORT,'Проведённый документ неизменяем: его можно только отменить с причиной'); END;

-- Ставка действует с даты. Новая ставка не пересчитывает прошлые смены;
-- строка отменённого документа не действует.
CREATE TABLE IF NOT EXISTS rate_period (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valid_from TEXT NOT NULL,        -- 2026.09.16
    rate REAL NOT NULL,
    unit TEXT NOT NULL CHECK (unit IN ('kpick','pick')),
    doc_id INTEGER REFERENCES doc(id),
    set_by TEXT NOT NULL, set_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS rate_period_from ON rate_period(valid_from, id);
CREATE TRIGGER IF NOT EXISTS rate_no_update BEFORE UPDATE ON rate_period
 BEGIN SELECT RAISE(ABORT,'Ставку меняют новым документом'); END;
CREATE TRIGGER IF NOT EXISTS rate_no_delete BEFORE DELETE ON rate_period
 BEGIN SELECT RAISE(ABORT,'Ставку меняют новым документом'); END;
"""

# Причины простоя — справочник в базе, а не список в коде: цех добавляет свои,
# у каждой причины категория (плановый / внеплановый простой), цвет и место,
# где её разрешено ставить. Так же устроено в DPA, и без этого не построить
# аналитику простоев: «плановые» не должны попадать в потери.
STOP_REASON_SCHEMA = """
CREATE TABLE IF NOT EXISTS stop_reason (
    id TEXT PRIMARY KEY,             -- короткий код: electrical, toir
    name TEXT NOT NULL,              -- как выбирают в списке
    name_en TEXT,
    reason TEXT NOT NULL,            -- как причина называется в отчёте
    applies TEXT NOT NULL DEFAULT 'any' CHECK (applies IN ('any','stop','off')),
    is_call INTEGER NOT NULL DEFAULT 0,      -- вызов человека, а не вид работы
    category TEXT NOT NULL DEFAULT 'unscheduled'
        CHECK (category IN ('scheduled','unscheduled','undefined')),
    color TEXT,
    sort INTEGER NOT NULL DEFAULT 100,
    in_operator INTEGER NOT NULL DEFAULT 1,  -- предлагать на мониторе в цеху
    in_analytics INTEGER NOT NULL DEFAULT 1, -- предлагать при разборе простоев
    important INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    builtin INTEGER NOT NULL DEFAULT 0       -- пришла из первой версии приложения
);
"""

# Справочник партий пряжи из 1С создаётся вместе с базой: так он сразу под журналом.
YARN_LOT_SCHEMA = """
CREATE TABLE IF NOT EXISTS yarn_lot (
    code TEXT PRIMARY KEY,           -- код номенклатуры 1С
    name TEXT NOT NULL,              -- полное название в 1С
    yarn TEXT,                       -- пряжа в справочном написании: «16/1 RING»
    kind TEXT,                       -- pile / ground / weft — «Тип основа пряжи»
    lot TEXT,
    supplier TEXT, color TEXT, twist TEXT, composition TEXT,
    bag_kg REAL, bobbins INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    loaded_by TEXT, loaded_at TEXT
);
CREATE INDEX IF NOT EXISTS yarn_lot_yarn ON yarn_lot(yarn);
"""
# Ставка до первого документа — из прежней настройки; дата раньше любых данных.
RATE_START = "2000.01.01"

DEFAULTS = {
    "rate": "287", "rate_unit": "kpick",   # kpick = за 1000 пиков, pick = за один пик
    # Андон: станок стоит, а причины нет. Через сколько минут он становится
    # «нет тикета», через сколько — тревогой на доске и через сколько уходит
    # мастеру в телеграм.
    "andon_warn_min": "2", "andon_alarm_min": "10", "andon_notify_min": "15",
    # Вес штуки считаем сами: ширина × длина × GSM и надбавка на угар краски, %.
    "weight_allowance_pct": "10",
}


def config():
    """Настройки запуска из config.json рядом с приложением: порт и адрес FACT.

    Нужен, чтобы служба на сервере запускалась одной и той же командой, а
    адрес FACT правился в файле, а не в задании планировщика.
    """
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except ValueError as e:
        raise SystemExit(f"Ошибка в {CONFIG_PATH}: {e}")


# Техкарта 1С — по производственному заказу и номенклатуре. Одна номенклатура
# бывает в нескольких заказах («220100 TerryCloth 390» — в 1484 и 1708), и у
# каждого свои количество, срок и лоты пряжи: с ключом по одной номенклатуре
# заказ, пришедший позже, затирал техкарту прежнего. order_number '' — техкарта
# без заказа (старые выгрузки).
TECH_CARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS tech_card (
    order_number TEXT NOT NULL DEFAULT '',   -- производственный заказ 1С
    product_code TEXT NOT NULL,              -- номенклатура
    uuid TEXT,
    size TEXT, size_cm INTEGER, panels INTEGER,
    ppt REAL,                        -- weftPerOneRow
    gsm INTEGER,
    weight_kg REAL,
    seconds_per_row REAL, seconds_per_pcs REAL,
    total_quantity REAL, total_rolls INTEGER,
    has_spec INTEGER,
    cloth_code TEXT,                 -- код ткани на станке, если 1С его присылает
    due_day TEXT,
    loaded_at TEXT,
    PRIMARY KEY (order_number, product_code)
);
CREATE TABLE IF NOT EXISTS tech_card_yarn (
    order_number TEXT NOT NULL DEFAULT '', product_code TEXT NOT NULL, slot TEXT NOT NULL,
    yarn_code TEXT, lot TEXT, grams REAL, description TEXT,
    PRIMARY KEY (order_number, product_code, slot)
);
CREATE TABLE IF NOT EXISTS tech_card_loom (
    order_number TEXT NOT NULL DEFAULT '', product_code TEXT NOT NULL, loom TEXT NOT NULL,
    PRIMARY KEY (order_number, product_code, loom)
);
CREATE INDEX IF NOT EXISTS idx_tcl_loom ON tech_card_loom(loom);
"""


_SCHEMA_READY = set()


def shop():
    """Цеховая база. WAL: чтение не ждёт запись — иначе тикет, записанный
    с монитора, на секунду запирает всех, кто в это время открыл отчёт.

    Схема и настройки по умолчанию — один раз на процесс (WAL тоже хранится в
    самом файле): раньше это делалось при каждом соединении, и страница плана
    открывала базу 400 раз по 3–5 мс."""
    db = sqlite3.connect(SHOP_DB, timeout=10)
    db.row_factory = sqlite3.Row
    import productionlog
    productionlog.register(db)
    db.execute("PRAGMA synchronous=NORMAL")
    if SHOP_DB not in _SCHEMA_READY:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA + TECH_CARD_SCHEMA + DOC_SCHEMA + YARN_LOT_SCHEMA + STOP_REASON_SCHEMA)
        for k, v in DEFAULTS.items():
            db.execute("INSERT OR IGNORE INTO setting (key, value) VALUES (?,?)", (k, v))
        db.commit()
        _migrate_documents(db)
        productionlog.install(db)
        productionlog.register(db)
        _SCHEMA_READY.add(SHOP_DB)
    return db


def _migrate_documents(db):
    """Ставка из настройки становится первым периодом; заправка знает свой документ."""
    import productionlog
    if not db.execute("SELECT 1 FROM rate_period LIMIT 1").fetchone():
        db.execute("INSERT INTO rate_period (valid_from, rate, unit, set_by, set_at) VALUES (?,?,?,?,?)",
                   (RATE_START, float(setting(db, "rate")), setting(db, "rate_unit"), "миграция",
                    productionlog.now()))
    if not db.execute("SELECT 1 FROM stop_reason LIMIT 1").fetchone():
        import tickets
        db.executemany(
            "INSERT INTO stop_reason (id, name, name_en, reason, applies, is_call, category, sort, builtin)"
            " VALUES (?,?,?,?,?,?,?,?,1)",
            [(c["id"], c["name"], c["en"], c["reason"], c["applies"], int(c["call"]),
              "scheduled" if c["id"] in ("toir", "naladka", "zapravka") else "unscheduled", i * 10)
             for i, c in enumerate(tickets.DEFAULT_CATEGORIES)])
    db.executescript(productionlog.SCHEMA)
    if "doc_id" not in [r[1] for r in db.execute("PRAGMA table_info(setup_document)")]:
        db.execute("ALTER TABLE setup_document ADD COLUMN doc_id INTEGER")
    db.commit()


def rate_for(db, day):
    """(ставка, единица), действующие в этот день, — по проведённым документам."""
    r = db.execute(
        "SELECT r.rate, r.unit FROM rate_period r LEFT JOIN doc d ON d.id = r.doc_id"
        " WHERE r.valid_from <= ? AND (r.doc_id IS NULL OR d.status = 'posted')"
        " ORDER BY r.valid_from DESC, r.id DESC LIMIT 1", (day,)).fetchone()
    if r:
        return float(r["rate"]), r["unit"]
    return float(setting(db, "rate")), setting(db, "rate_unit")


def shop_readonly():
    """Чтение истории цеха без создания таблиц и изменения настроек базы."""
    db = sqlite3.connect(f"file:{SHOP_DB}?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    return db


class ReadConnection(sqlite3.Connection):
    """Read scopes own their connection; leaving a scope releases the file."""

    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def fact():
    """База станков для отчётов — только чтение: пишет в неё один сборщик."""
    db = sqlite3.connect(f"file:{FACT_DB}?mode=ro", uri=True, timeout=10,
                         factory=ReadConnection)
    db.row_factory = sqlite3.Row
    return db


def fact_rw():
    """База станков на запись — для сборщика и скриптов пересборки."""
    db = sqlite3.connect(FACT_DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db


def _move_tech_cards(conn):
    """Разово переносит техкарты из базы станков в цеховую, если здесь их ещё нет."""
    if conn.execute("SELECT 1 FROM tech_card LIMIT 1").fetchone():
        return 0
    conn.execute("ATTACH DATABASE ? AS f", (FACT_DB,))
    try:
        has = conn.execute("SELECT name FROM f.sqlite_master WHERE name='tech_card'").fetchone()
        if not has:
            return 0
        cols = ("product_code, uuid, size, size_cm, panels, ppt, gsm, weight_kg,"
                " seconds_per_row, seconds_per_pcs, total_quantity, total_rolls, has_spec, loaded_at")
        n = conn.execute("INSERT OR IGNORE INTO tech_card (order_number, %s)"
                         " SELECT COALESCE(order_number, ''), %s FROM f.tech_card"
                         % (cols, cols)).rowcount
        conn.execute("INSERT OR IGNORE INTO tech_card_yarn (order_number, product_code, slot,"
                     " yarn_code, lot, grams) SELECT COALESCE(t.order_number, ''), y.product_code,"
                     " y.slot, y.yarn_code, y.lot, y.grams FROM f.tech_card_yarn y"
                     " LEFT JOIN f.tech_card t ON t.product_code = y.product_code")
        conn.execute("INSERT OR IGNORE INTO tech_card_loom (order_number, product_code, loom)"
                     " SELECT COALESCE(t.order_number, ''), l.product_code, l.loom"
                     " FROM f.tech_card_loom l LEFT JOIN f.tech_card t ON t.product_code = l.product_code")
        conn.commit()
        return n
    finally:
        conn.execute("DETACH DATABASE f")


def _tech_card_by_order(conn):
    """Разово: техкарты со старым ключом (одна номенклатура) — на ключ «заказ +
    номенклатура». Старые таблицы переименовываем, создаём новые, переносим."""
    pk = [r[1] for r in sorted(conn.execute("PRAGMA table_info(tech_card)"), key=lambda r: r[5])
          if r[5]]
    if pk != ["product_code"]:
        return False
    if "description" not in [r[1] for r in conn.execute("PRAGMA table_info(tech_card_yarn)")]:
        conn.execute("ALTER TABLE tech_card_yarn ADD COLUMN description TEXT")
    conn.executescript(
        "ALTER TABLE tech_card RENAME TO tech_card_old;"
        "ALTER TABLE tech_card_yarn RENAME TO tech_card_yarn_old;"
        "ALTER TABLE tech_card_loom RENAME TO tech_card_loom_old;"
        "DROP INDEX IF EXISTS idx_tcl_loom;")
    conn.executescript(TECH_CARD_SCHEMA)
    cols = ("uuid, size, size_cm, panels, ppt, gsm, weight_kg, seconds_per_row, seconds_per_pcs,"
            " total_quantity, total_rolls, has_spec, cloth_code, due_day, loaded_at")
    conn.execute("INSERT OR REPLACE INTO tech_card (order_number, product_code, %s)"
                 " SELECT COALESCE(order_number, ''), product_code, %s FROM tech_card_old"
                 % (cols, cols))
    conn.execute("INSERT OR REPLACE INTO tech_card_yarn (order_number, product_code, slot, yarn_code,"
                 " lot, grams, description) SELECT COALESCE(t.order_number, ''), y.product_code,"
                 " y.slot, y.yarn_code, y.lot, y.grams, y.description FROM tech_card_yarn_old y"
                 " LEFT JOIN tech_card_old t ON t.product_code = y.product_code")
    conn.execute("INSERT OR REPLACE INTO tech_card_loom (order_number, product_code, loom)"
                 " SELECT COALESCE(t.order_number, ''), l.product_code, l.loom"
                 " FROM tech_card_loom_old l LEFT JOIN tech_card_old t ON t.product_code = l.product_code")
    conn.executescript("DROP TABLE tech_card_old; DROP TABLE tech_card_yarn_old;"
                       " DROP TABLE tech_card_loom_old;")
    conn.commit()
    return True


def prepare():
    """Разовая подготовка при запуске: схемы, WAL, свёртка остановов."""
    os.makedirs(RUN_DIR, exist_ok=True)
    # WAL нужен и базе станков: иначе запись сборщика блокирует всех, кто
    # смотрит отчёты.
    w = fact_rw()
    ingest.ensure_schema(w)
    built = ingest.ensure_rollup(w)
    w.commit()
    w.close()
    conn = shop()
    # Техкарты — по заказу и номенклатуре (раньше — по одной номенклатуре).
    rekeyed = _tech_card_by_order(conn)
    moved = _move_tech_cards(conn)
    # Клетка плана знает изделие заказа (техкарту 1С), а не только номер заказа:
    # в одном заказе 1С бывает под три десятка изделий с разными PPT и пряжей.
    # pick — как выбрано: auto (подобрано по размеру/GSM/дизайну), manual, ambiguous.
    have = [r[1] for r in conn.execute("PRAGMA table_info(loom_plan)")]
    for col in ("product_code", "pick"):
        if col not in have:
            conn.execute("ALTER TABLE loom_plan ADD COLUMN %s TEXT" % col)
    # Места пряжи ручной заправки — как типы компонентов 1С (кручёная, полиэстер).
    have = [r[1] for r in conn.execute("PRAGMA table_info(loom_setup)")]
    for col in ("hemply_yarn", "hemply_lot", "hempoly_yarn", "hempoly_lot",
                "fancyply_yarn", "fancyply_lot", "design"):
        if col not in have:
            conn.execute("ALTER TABLE loom_setup ADD COLUMN %s TEXT" % col)
    conn.commit()
    import productionlog
    productionlog.install(conn)      # добавленные колонки сразу попадают в журнал
    conn.close()
    info = {"rollup_built": built, "tech_cards_moved": moved, "tech_cards_rekeyed": rekeyed}
    # Справочник пряжи при первом запуске собирается из того, что уже есть в
    # отчётах и техкартах. Сбой здесь не должен мешать запуску приложения.
    try:
        import yarns
        info["yarns_seeded"] = yarns.seed_if_empty()
    except Exception as e:
        info["yarns_error"] = "%s: %s" % (type(e).__name__, e)
    return info


def setting_int(key):
    """Число из настроек цеха; пустое или испорченное значение — значение по умолчанию."""
    db = shop()
    try:
        v = setting(db, key)
    finally:
        db.close()
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return int(float(DEFAULTS.get(key, 0)))


def setting(db, key):
    r = db.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
    return r["value"] if r else DEFAULTS.get(key)


def all_settings():
    db = shop()
    s = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM setting")}
    db.close()
    return s


# Ставка меняется только документом «Ставка» — с датой начала действия.
DOCUMENT_SETTINGS = ("rate", "rate_unit")


def save_settings(values, who=""):
    """Прочие настройки. Изменение попадает в журнал с автором; UPSERT, а не
    REPLACE, — иначе журнал видел бы удаление и вставку вместо правки."""
    import productionlog
    db = shop()
    token = productionlog.ACTOR.set(who or "система")
    try:
        for k in DOCUMENT_SETTINGS:
            if k in values and str(values[k]) != str(setting(db, k)):
                raise ValueError("ставка меняется документом «Ставка» с датой начала — "
                                 "прошлые смены не пересчитываются")
        for k, v in values.items():
            if k not in DOCUMENT_SETTINGS:
                db.execute("INSERT INTO setting (key, value) VALUES (?,?)"
                           " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
        db.commit()
    finally:
        db.close()
        productionlog.ACTOR.reset(token)
