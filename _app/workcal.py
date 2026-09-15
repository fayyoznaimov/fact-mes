"""Рабочий календарь цеха: когда станки работают по расписанию.

Так же, как в DPA (Структура предприятия → Расписание, «наследуется от SRT»):
смены A 07:00, B 15:00, C 23:00 с понедельника по субботу; воскресенье —
выходной с 07:00 воскресенья до 07:00 понедельника (ночная смена C с субботы
дорабатывает до 07:00 воскресенья). Производственные сутки — с 07:00 до 07:00,
как в планёрке и в «WARP & WEFT 7:00-6:59».

Праздники — HOLIDAYS: производственные сутки, в которые цех не работает.
"""
from datetime import date, datetime, time, timedelta

DAY_START_H = 7                  # производственные сутки: 07:00 → 07:00 следующего дня
OFF_WEEKDAYS = {6}               # воскресенье (понедельник = 0)
HOLIDAYS = set()                 # {"2026.12.31", ...} — сутки без работы, как «YYYY.MM.DD»


def production_day(dt):
    """Производственные сутки, к которым относится момент: 03:00 воскресенья —
    это ещё суббота (ночная смена C)."""
    return (dt - timedelta(hours=DAY_START_H)).date()


def is_working_day(d):
    """Работает ли цех в эти производственные сутки (date или «YYYY.MM.DD»)."""
    if isinstance(d, str):
        d = datetime.strptime(d, "%Y.%m.%d").date()
    return d.weekday() not in OFF_WEEKDAYS and d.strftime("%Y.%m.%d") not in HOLIDAYS


def is_working(dt):
    return is_working_day(production_day(dt))


def _day_end(d):
    return datetime.combine(d + timedelta(days=1), time(DAY_START_H))


def add_working_minutes(start, minutes):
    """Когда станок наработает ещё minutes минут, если в выходные он стоит.

    Станок сообщает «до съёма 180 мин работы»; в субботу в 06:00 это не
    воскресенье 09:00, а понедельник 08:00 — выходной пропускаем."""
    t, left = start, max(0.0, float(minutes))
    for _ in range(400):                        # больше года выходных подряд не бывает
        d = production_day(t)
        end = _day_end(d)
        if not is_working_day(d):
            t = end
            continue
        room = (end - t).total_seconds() / 60
        if left <= room:
            return t + timedelta(minutes=left)
        left -= room
        t = end
    return t + timedelta(minutes=left)


def last_working_day(day=None):
    """Последние рабочие производственные сутки не позже day («YYYY.MM.DD»):
    в понедельник на планёрке — суббота, а не пустое воскресенье."""
    d = datetime.strptime(day, "%Y.%m.%d").date() if day else production_day(datetime.now())
    for _ in range(400):
        if is_working_day(d):
            return d.strftime("%Y.%m.%d")
        d -= timedelta(days=1)
    return d.strftime("%Y.%m.%d")
