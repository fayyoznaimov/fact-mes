"""Дашборд по станкам: что заправлено, кто работает, с какой скоростью и что рвётся.

Сводит в одну строку четыре разных источника:

    FACT (смена)   скорость, выработка, обрывы утка, основы, ворса, простой;
    FACT (сейчас)  работает станок или стоит, и по какой причине;
    тикеты         открытый тикет и что по нему указали;
    цех            какое изделие заправлено и кто из операторов на станке.

Что на станке должно ткаться — из плана цеха на этот день (loom_plan): заказ,
изделие, дизайн/клиент, GSM; пряжа и лоты — из техкарты 1С этого изделия.
Артикул, поставленный мастером руками (loom_article), — запасной вариант для
станков без плана.

Расхождения показываем, а не прячем: код ткани, набранный на станке
(«3050X7360»), сверяется с изделием по плану — размер, дизайн, GSM; артикул
мастера — с изделием плана. Каждое расхождение — строка в списке на дашборде.
"""
import re
import time
from datetime import datetime, timedelta

import cache
import logs
import metrics
import people
import tickets
import workcal
from storage import fact, shop

LOG = logs.get("dash")

# Остаток основы и длина навоя приходят от станка в десятых долях метра:
# Beam_length_meter=50000 — это навой на 5 000 м, а не на 50 км.
BEAM_SCALE = 10.0

YARN_TITLES = {"vors": "ворс", "karenoy": "основа", "utog1": "уток",
               "utog2": "кромка", "utog2p": "кромка кручёная", "utog2x": "кромка полиэстер",
               "utog3": "бордюр", "utog3p": "бордюр кручёная", "utog4": "бордюр полиэстер"}


def design_of(product_code):
    """«5080 D152 320» -> «D152». Из кода изделия убираем размер и плотность."""
    if not product_code:
        return ""
    parts = product_code.split()
    mid = [p for p in parts if not re.fullmatch(r"\d{2,6}", p)]
    return " ".join(mid) or product_code


def plan_for_day(day):
    """План цеха на день: {станок: клетка} — заказ, изделие, размер, дизайн, GSM."""
    db = shop()
    try:
        rows = db.execute(
            "SELECT loom, order_no, product, size, design, client, gsm, pile_yarn, note,"
            " product_code, pick FROM loom_plan WHERE day=?", (day,)).fetchall()
    except Exception:            # таблицы плана ещё нет
        rows = []
    finally:
        db.close()
    return {r["loom"]: dict(r) for r in rows}


def shown_code(code):
    """Код ткани для экрана: FACT хранит пробел как «%20» («220100tc%20390»).
    В базе код не меняем — по нему ищутся панели, отчёты и план."""
    return (code or "").replace("%20", " ")


def cloth_parts(cloth):
    """Код ткани со станка (набирают руками) -> (размер, дизайн, GSM).

        «70140D272600» -> ('70140', 'D272', 600)    буквы, номер дизайна, GSM
        «3050X7360»    -> ('3050', 'X7', 360)       цифр после букв 4+ — последние три GSM
        «5090D272»     -> ('5090', 'D272', None)    три цифры — это номер дизайна
        «70140HOTEL500»-> ('70140', None, None)     слово — дизайн и GSM не разобрать надёжно
    Чего не разобрали — None: такое расхождением не считаем."""
    s = re.sub(r"[^A-Z0-9]", "", (cloth or "").replace("%20", "").upper())
    m = re.match(r"^(\d{4,6})([A-Z]*)(\d*)", s)
    if not m:
        return None, None, None
    size, letters, digits = m.groups()
    if 1 <= len(letters) <= 2 and digits:
        if len(digits) >= 4:
            # Номер дизайна — не длиннее трёх цифр: «J03815430» — J038, 430.
            return size, letters + digits[:-3][:3], int(digits[-3:])
        return size, letters + digits, None
    return size, None, None


def _code_design(d):
    """Дизайн вида «D272», «J401-SH» — такие сравниваем; «Terry», «Hotel» — нет."""
    return bool(re.fullmatch(r"[A-Z]{1,2}\d{1,4}(-?[A-Z]+)?", re.sub(r"\s", "", str(d or "")).upper()))


GSM_TOLERANCE = 10       # 307 на станке и 300 в плане — одно и то же


def plan_mismatch(plan, cloth, master=None, split=False):
    """Чем станок расходится с планом — список фраз. Сравниваем только то, что
    известно с обеих сторон: неразобранный код ткани расхождением не считаем.

    split=True — (расхождения, подсказки): на станке не тот размер или дизайн —
    это тревога; GSM в пределах одного изделия и выбор мастера — подсказка.
    Раньше всё шло одним списком, и ⚠ горел у трёх четвертей станков."""
    if not plan or not plan.get("order_no"):
        return ([], []) if split else []
    import loomplan
    out = []
    size, design, gsm = cloth_parts(cloth)
    want = (plan.get("size") or "").replace("x", "")
    diff = []
    if size and want and size != want:
        diff.append("размер")
    if (design and _code_design(plan.get("design"))
            and not loomplan._same_design(design, plan["design"])):
        diff.append("дизайн")
    if gsm and plan.get("gsm") and abs(int(gsm) - int(plan["gsm"])) > GSM_TOLERANCE:
        diff.append("GSM")
    text = lambda what: ("на станке «%s», по плану %s (заказ %s) — не совпадает %s"
                         % (shown_code(cloth), plan.get("product") or "—", plan["order_no"], what))
    serious = [d for d in diff if d != "GSM"]
    notes = []
    if serious:
        out.append(text(", ".join(diff)))
    elif diff:
        notes.append(text("GSM"))
    if master and plan.get("product_code") and master != plan["product_code"]:
        notes.append("мастер поставил «%s», по плану «%s»" % (master, plan["product_code"]))
    if split:
        return out, notes
    return out + notes


def current_articles(day=None):
    """Что заправлено на станках на указанный день: {станок: строка учёта}."""
    day = day or datetime.now().strftime("%Y.%m.%d")
    db = shop()
    rows = db.execute(
        "SELECT loom, product_code, from_day, note, set_by FROM loom_article a"
        " WHERE from_day <= ? AND from_day = ("
        "   SELECT MAX(from_day) FROM loom_article b"
        "   WHERE b.loom = a.loom AND b.from_day <= ?)", (day, day)).fetchall()
    db.close()
    return {r["loom"]: dict(r) for r in rows}


def set_article(loom, product_code, day=None, who="", note=""):
    day = day or datetime.now().strftime("%Y.%m.%d")
    db = shop()
    db.execute("INSERT OR REPLACE INTO loom_article (loom, product_code, from_day, note, set_by,"
               " set_at) VALUES (?,?,?,?,?,?)",
               (loom, product_code, day, (note or "").strip()[:200], who,
                datetime.now().astimezone().isoformat(timespec="seconds")))
    db.commit()
    db.close()


def clear_article(loom, day=None):
    day = day or datetime.now().strftime("%Y.%m.%d")
    db = shop()
    db.execute("DELETE FROM loom_article WHERE loom=? AND from_day=?", (loom, day))
    db.commit()
    db.close()


def _tech_cards():
    """Техкарты 1С: изделие -> размер, плотность, пряжа; и станки-претенденты."""
    return cache.get(("tech_cards",), 120, _read_tech_cards)


def _read_tech_cards():
    cards, yarn, candidates = {}, {}, {}
    # Техкарты живут в цеховой базе: это данные 1С, а не FACT.
    # Ключ — (заказ, номенклатура); по одной номенклатуре — последняя по времени
    # техкарта, для станков, где артикул поставил мастер без заказа.
    with shop() as db:
        for r in db.execute("SELECT * FROM tech_card ORDER BY loaded_at"):
            cards[(r["order_number"] or "", r["product_code"])] = dict(r)
            cards[r["product_code"]] = dict(r)
        last = {}
        for r in db.execute("SELECT y.*, t.loaded_at FROM tech_card_yarn y LEFT JOIN tech_card t"
                            " ON t.order_number = y.order_number AND t.product_code = y.product_code"
                            " ORDER BY t.loaded_at"):
            v = {"yarn": r["yarn_code"], "lot": r["lot"], "grams": r["grams"]}
            yarn.setdefault((r["order_number"] or "", r["product_code"]), {})[r["slot"]] = v
            if last.get(r["product_code"]) not in (None, r["order_number"]):
                yarn[r["product_code"]] = {}       # пришла техкарта новее — пряжа только её
            last[r["product_code"]] = r["order_number"]
            yarn.setdefault(r["product_code"], {})[r["slot"]] = v
        for r in db.execute("SELECT loom, product_code FROM tech_card_loom"):
            candidates.setdefault(r["loom"], []).append(r["product_code"])
    return cards, yarn, candidates


def _shift_stats(day, letter):
    """Итоги смены по станкам. Монитор с карточками спрашивает их на каждое
    изменение доски, а меняются они раз в пару минут — держим минуту."""
    return cache.get(("shift_stats", day, letter), 60, lambda: _read_shift_stats(day, letter))


def _read_shift_stats(day, letter):
    with fact() as db:
        if letter:
            rows = db.execute(
                "SELECT * FROM shift_full WHERE day=? AND letter=? AND run_min > 5", (day, letter))
        else:
            rows = db.execute(
                "SELECT loom, style, cloth, AVG(rpm) rpm, AVG(effic_pct) effic_pct,"
                " SUM(picks) picks, SUM(meters) meters, SUM(pieces) pieces,"
                " SUM(run_min) run_min, SUM(stop_min) stop_min,"
                " SUM(weft_ct) weft_ct, SUM(warp_ct) warp_ct, SUM(top_ct) top_ct,"
                " SUM(manual_ct) manual_ct, SUM(weft_fix_min) weft_fix_min,"
                " SUM(warp_fix_min) warp_fix_min, SUM(top_fix_min) top_fix_min,"
                " SUM(wait_total_min) wait_total_min"
                " FROM shift_full WHERE day=? AND run_min > 5 GROUP BY loom", (day,))
        return {r["loom"]: dict(r) for r in rows}


def _operators(day, letter):
    db = shop()
    if letter:
        rows = db.execute(
            "SELECT a.loom, o.code, o.name FROM assignment a JOIN operator o ON o.id=a.operator_id"
            " WHERE a.day=? AND a.shift=?", (day, letter)).fetchall()
    else:
        rows = db.execute(
            "SELECT a.loom, o.code, o.name FROM assignment a JOIN operator o ON o.id=a.operator_id"
            " WHERE a.day=? GROUP BY a.loom", (day,)).fetchall()
    db.close()
    return {r["loom"]: {"code": r["code"], "name": r["name"]} for r in rows}


def loom_details(max_age=20):
    """Подробности прямо со станка: модель, код ткани, остаток основы, обороты,
    прогнозы съёма и схода навоев.

    Раньше каждый запрос карточек перечитывал сорок файлов станков; теперь их
    раз в минуту читает сборщик, а здесь берётся готовый снимок.
    """
    try:
        _, live = tickets.state_now(max_age)
    except Exception as e:
        # Карточки рисуются и без этих полей, но молчать нельзя: именно
        # проглоченная ошибка однажды скрыла неверное имя файла станка.
        LOG.warning("подробности станков не прочитались: %s: %s", type(e).__name__, e)
        return {}
    out = {}
    for loom, st in live.items():
        d = st.get("details") or {}
        out[loom] = {**d, "model": d.get("model") or st.get("type", ""),
                     "rpm": d.get("rpm") or st.get("rpm")}
    return out


# Что показывать в прогнозе: съём ткани и сход навоя основы — у всех,
# навой ворса — только у станков, где он заправлен отдельно.
FORECAST_KINDS = (("doff", "doff_min", "съём ткани"),
                  ("beam", "beam_out_min", "сход навоя основы"),
                  ("top", "top_beam_out_min", "сход навоя ворса"))


def forecast(horizon_min=12 * 60):
    """Что случится в ближайшие часы: съём ткани и сход навоев по всем станкам.

    Станок сам считает, через сколько минут кончится рулон и навой. Сход навоя —
    это узловязка или перезаправка: два-четыре часа простоя, если навой и
    бригада не готовы заранее. В LDS это отдельная колонка простоев («Knotting»),
    у нас — список, по которому бригада готовится до того, как станок встал.
    """
    try:
        snap = tickets.snapshot_now()
        _, live = tickets.state_now()
    except Exception as e:
        return {"events": [], "stale": True, "snapshot_at": None,
                "error": "%s: %s" % (type(e).__name__, e)}
    # Минуты станок посчитал в момент снимка — от него и отсчитываем, а не от
    # «сейчас». Иначе без связи с FACT (ноутбук ушёл из сети цеха) старые минуты
    # прибавлялись бы к текущему времени, и сроки уезжали бы вперёд.
    read_at = snap.get("read_at") or time.time()
    base = datetime.fromtimestamp(read_at) - timedelta(seconds=livestate_lag(snap, read_at))
    mirror = snap.get("source") == "mirror"
    # По зеркалу «сейчас» — время снимка: иначе позавчерашний съём показался бы
    # через шесть минут.
    now = base if mirror else datetime.now()
    stale = not mirror and time.time() - read_at > STALE_FORECAST_SEC
    events = []
    for loom, st in live.items():
        d = st.get("details") or {}
        for kind, key, label in FORECAST_KINDS:
            if kind == "top" and not (d.get("top_beam_use") or st.get("top_beam_use")):
                continue
            mins = d.get(key) or st.get(key) or 0
            if not mins:
                continue
            # Минуты — работы станка, а в выходной (вс 07:00 → пн 07:00) станки
            # стоят: съём, посчитанный в субботнюю ночь, будет в понедельник.
            at = workcal.add_working_minutes(base, mins)
            left = (at - now).total_seconds() / 60
            if left <= 0 or left > horizon_min:
                continue
            ahead = (at.date() - now.date()).days
            events.append({"loom": loom, "label_loom": loom_label(loom), "kind": kind,
                           "what": label, "in_min": int(left), "at": at.strftime("%H:%M"),
                           "tomorrow": ahead == 1,
                           "when": "" if ahead <= 0 else "завтра" if ahead == 1
                                   else "пн вт ср чт пт сб вс".split()[at.weekday()] + at.strftime(" %d.%m"),
                           "remaining_m": d.get("remaining_m"), "style": st.get("style")})
    events.sort(key=lambda e: e["in_min"])
    return {"events": events, "horizon_min": horizon_min,
            "stale": stale, "snapshot_at": datetime.fromtimestamp(read_at).strftime("%d.%m %H:%M"),
            "counts": {k: sum(1 for e in events if e["kind"] == k) for k, _, _ in FORECAST_KINDS}}


STALE_FORECAST_SEC = 300      # снимок старше 5 минут — связи с FACT нет, прогноз помечаем


def livestate_lag(snap, now=None):
    import livestate
    return livestate.lag_sec(snap, now)


def _picks_by_shift(day):
    """Выработка по сменам за день: {станок: {'A': тыс. пиков, ...}}."""
    return cache.get(("picks_by_shift", day), 60, lambda: _read_picks_by_shift(day))


def _read_picks_by_shift(day):
    out = {}
    with fact() as db:
        for r in db.execute(
                "SELECT loom, letter, SUM(picks) picks FROM shift_full"
                " WHERE day=? AND run_min > 5 GROUP BY loom, letter", (day,)):
            out.setdefault(r["loom"], {})[r["letter"]] = round((r["picks"] or 0) / 1000, 1)
    return out


def loom_label(loom):
    """D1 -> D-01: так станки подписаны на мониторах в цехе."""
    m = re.match(r"^([A-Za-z]+)(\d+)$", loom or "")
    return "%s-%02d" % (m.group(1).upper(), int(m.group(2))) if m else loom


def cards(day="", letter=""):
    """Карточка на каждый станок — то, что висит на мониторе в цехе."""
    if not day and not letter:
        day, letter = tickets.current_shift().rsplit('.', 1)
    day = day or tickets.current_shift()[:10]
    with fact() as db:
        selected = db.execute('SELECT * FROM shift_full WHERE day=?' +
                              (' AND letter=?' if letter else ''),
                              (day, letter) if letter else (day,)).fetchall()
    stats = {}
    fields = ('run_min', 'stop_min', 'picks', 'pieces', 'stops_total', 'weft_ct',
              'warp_ct', 'top_ct', 'weft_stop_min', 'warp_stop_min', 'top_stop_min')
    for item in selected:
        total = stats.setdefault(item['loom'], dict.fromkeys(fields, 0))
        for field in fields:
            total[field] += item[field] or 0
    board = tickets.board()
    live = {r['loom']: r for r in board['looms']}
    base = rows(day, letter)
    details = loom_details()
    picks = _picks_by_shift(day)
    fact_ops = people.fact_operators(day)
    cats = {c["id"]: c for c in tickets.categories()}

    out = []
    for r in base["rows"]:
        stat = stats.get(r['loom'])
        state = live.get(r['loom'], {})
        run = stat['run_min'] if stat else 0
        elapsed = run + (stat['stop_min'] if stat else 0)
        d = details.get(r["loom"], {})
        op = r["operator"]
        if not op and fact_ops.get(r["loom"], {}).get("name"):
            f = fact_ops[r["loom"]]
            op = {"name": f["name"], "code": f["code"], "source": "FACT"}
        elif op:
            op = {**op, "source": "назначен"}

        cause = r["cause_ru"] or "—"
        p = picks.get(r["loom"], {})
        t = r["ticket"]
        cat = cats.get((t or {}).get("category") or "")
        out.append({
            'rpm_avg': round(stat['picks'] / run, 1) if stat and run > 0 else None,
            'efficiency_pct': round(100 * run / elapsed, 1) if elapsed else None,
            'towels_per_hour': round(stat['pieces'] * r['panels'] * 60 / elapsed, 1) if elapsed else None,
            'stops_total': stat['stops_total'] if stat else None,
            'stop_min': round(stat['stop_min'], 1) if stat else None,
            'weft_stop_min': round(stat['weft_stop_min'], 1) if stat else None,
            'warp_stop_min': round(stat['warp_stop_min'], 1) if stat else None,
            'pile_stop_min': round(stat['top_stop_min'], 1) if stat else None,
            # Ровно то, что доска просит объяснить тикетом (tickets.andon_level):
            # не только ручной останов, но и обесточенный или «прочее» без причины.
            'awaiting_ticket': bool(not board.get('stale') and not board.get('error')
                                    and state.get('needs_ticket')),
            "loom": r["loom"], "label": loom_label(r["loom"]),
            "model": ("Toyota " + d["model"]) if d.get("model") and d["model"] != "none" else "",
            "state": r["state"], "state_min": r["state_min"],
            "cause_ru": cause,
            "cause_en": tickets.CAUSE_EN.get(
                next((k for k, v in tickets.CAUSE_RU.items() if v == cause), ""), "Undefined"),
            "reason": r["reason"], "reason_from": r["reason_from"],
            "ticket": {"ru": cat["name"], "en": cat["en"]} if cat else None,
            "operator": op,
            "oee_shift": d.get("oee_shift"), "oee_24h": d.get("oee_24h"),
            "rpm": r["rpm_now"] if r['state'] == 'run' else 0,
            "design": r["design"], "article": r["article"],
            "cloth_name": shown_code(d.get("cloth_name") or r["style_fact"]),
            "weft_ct": stat['weft_ct'] if stat else None,
            "warp_p_ct": stat['top_ct'] if stat else None,
            "warp_g_ct": stat['warp_ct'] if stat else None,
            "remaining_m": d.get("remaining_m"), "beam_length_m": d.get("beam_length_m"),
            "picks_total": round(stat['picks'] / 1000, 1) if stat else None,
            "towels": round(stat['pieces'] * r['panels']) if stat else None,
            "panels": r["panels"], "rows_woven": stat['pieces'] if stat else None,
            "shift_a": p.get("A"), "shift_b": p.get("B"), "shift_c": p.get("C"),
        })

    return {"day": day, "shift": letter, "rows": out,
            'source': board['source'], 'snapshot_age_sec': board.get('snapshot_age_sec'),
            'stale': board.get('stale') or bool(board.get('error')),
            'ticket_wait_min': board['andon']['warn_min'],
            "totals": base["totals"],
            "operators_from_fact": sum(1 for r in out
                                       if (r["operator"] or {}).get("source") == "FACT")}


def rows(day, letter=""):
    """Строки дашборда: станок, состояние, скорость, дизайн, пряжа, утки, оператор."""
    stats = _shift_stats(day, letter)
    ops = _operators(day, letter)
    cards, yarn, candidates = _tech_cards()
    articles = current_articles(day)
    plan = plan_for_day(day)
    # Код ткани «сейчас» — из снимка станка; за прошлый день — из итогов смены.
    det = loom_details() if day == datetime.now().strftime("%Y.%m.%d") else {}
    # Сверка PPT за день: счётчики станка против 1С. Расхождение кода ткани с
    # планом и так покажет plan_mismatch — здесь добавляем только сам PPT.
    import pptcheck
    ppt_notes = {}
    for d in pptcheck.loom_days(day, day):
        if d["verdict"] in ("ppt", "diff") or (d["verdict"] == "other" and not d["cloth_mismatch"]):
            ppt_notes[d["loom"]] = ["PPT: " + d["text"]]
    # Счётчик Toyota считает ряды: полотенец в ряду столько, сколько панелей.
    panels = metrics.panels_by_cloth()

    live = {}
    board = tickets.board()
    for l in board["looms"]:
        live[l["loom"]] = l

    out = []
    for loom in sorted(set(stats) | set(live), key=lambda x: (x[0], int(re.sub(r"\D", "", x) or 0))):
        s = stats.get(loom, {})
        l = live.get(loom, {})

        p = plan.get(loom)
        art = articles.get(loom)
        master = art["product_code"] if art else None
        # Сначала план цеха (изделие 1С в клетке), потом артикул мастера; станок
        # без плана и без артикула — единственное изделие 1С для него, если оно одно.
        code, source = None, None
        if p and p.get("product_code"):
            code, source = p["product_code"], "план"
        elif master:
            code, source = master, "мастер"
        elif not p:
            cand = candidates.get(loom, [])
            if len(cand) == 1:
                code, source = cand[0], "1С"
        # Техкарта изделия по плану — именно этого заказа; артикул мастера — последняя.
        key = (str((p or {}).get("order_no") or ""), code) if source == "план" else code or ""
        card = cards.get(key) or cards.get(code or "", {})
        y = yarn.get(key) or yarn.get(code or "", {})
        cloth = (det.get(loom) or {}).get("cloth_name") or s.get("cloth") or ""
        mism, notes = plan_mismatch(p, cloth, master, split=True)
        # Дизайн и клиент — раздельно: в плане «D327/64» — дизайн D327, клиент 64.
        design = p["design"] if p and p.get("design") else design_of(code)
        client = (p or {}).get("client")
        yarns = {slot: (y.get(slot) or {}).get("yarn") for slot in YARN_TITLES if y.get(slot)}
        if not yarns and p and p.get("pile_yarn"):
            yarns = {"vors": p["pile_yarn"]}

        ticket = None
        if l.get("ticket_id"):
            ticket = {"id": l["ticket_id"], "category": l.get("ticket_category"),
                      "reason": l.get("reason"), "minutes": round(l.get("state_sec", 0) / 60)}

        out.append({
            "loom": loom,
            # Цвет на дашборде: зелёный — работает, красный — стоит.
            "state": "run" if l.get("running") else ("stop" if l else "—"),
            "cause_ru": l.get("cause_ru"),
            "reason": l.get("reason"),
            "reason_from": l.get("reason_from"),
            "state_min": round(l.get("state_sec", 0) / 60) if l else None,
            "ticket": ticket,

            "rpm_now": l.get("rpm"),
            "rpm_shift": round(s["rpm"]) if s.get("rpm") else None,
            "effic": round(s["effic_pct"], 1) if s.get("effic_pct") is not None else None,

            "article": code or "",
            "article_from": source,
            "candidates": candidates.get(loom, []),
            "design": design,
            "client": client,
            "size": (p or {}).get("size") or card.get("size") or "",
            "gsm": card.get("gsm") or (p or {}).get("gsm"),
            "yarn": yarns,
            "lots": {slot: (y.get(slot) or {}).get("lot") for slot in YARN_TITLES
                     if (y.get(slot) or {}).get("lot")},
            "order_no": (p or {}).get("order_no"),
            "plan_product": (p or {}).get("product") or (p or {}).get("note"),
            "plan_pick": (p or {}).get("pick"),
            "cloth": shown_code(cloth),
            "mismatch": mism,
            "notes": notes + ppt_notes.get(loom, []),
            "style_fact": s.get("style") or l.get("style") or "",

            "kpicks": round((s.get("picks") or 0) / 1000, 1),
            "meters": round(s.get("meters") or 0, 1),
            "pieces": round(s.get("pieces") or 0),
            "panels": panels.get(s.get("cloth") or "", 1),
            "towels": int((s.get("pieces") or 0) * panels.get(s.get("cloth") or "", 1)),

            "operator": ops.get(loom),

            "weft_ct": int(s.get("weft_ct") or 0),
            "warp_ct": int(s.get("warp_ct") or 0),
            "top_ct": int(s.get("top_ct") or 0),
            "manual_ct": int(s.get("manual_ct") or 0),
            "weft_fix_min": round(s.get("weft_fix_min") or 0),
            "warp_fix_min": round(s.get("warp_fix_min") or 0),
            "top_fix_min": round(s.get("top_fix_min") or 0),
            "stop_min": round(s.get("stop_min") or 0),
        })

    known = sum(1 for r in out if r["article"] or r["design"])
    return {
        "day": day, "shift": letter, "rows": out,
        "mismatches": [{"loom": r["loom"], "text": t} for r in out for t in r["mismatch"]],
        "articles": sorted(k for k in cards if isinstance(k, str)),
        "yarn_titles": YARN_TITLES,
        "totals": {
            "looms": len(out),
            "running": sum(1 for r in out if r["state"] == "run"),
            "stopped": sum(1 for r in out if r["state"] == "stop"),
            "with_ticket": sum(1 for r in out if r["ticket"]),
            "kpicks": round(sum(r["kpicks"] for r in out)),
            "weft_ct": sum(r["weft_ct"] for r in out),
            "warp_ct": sum(r["warp_ct"] for r in out),
            "top_ct": sum(r["top_ct"] for r in out),
            "with_article": known,
            "with_plan": sum(1 for r in out if r["order_no"]),
            "with_product": sum(1 for r in out if r["article_from"] == "план"),
            "mismatch": sum(1 for r in out if r["mismatch"]),
            "with_operator": sum(1 for r in out if r["operator"]),
            "towels": sum(r["towels"] for r in out),
            "rows_woven": sum(r["pieces"] for r in out),
        },
    }
