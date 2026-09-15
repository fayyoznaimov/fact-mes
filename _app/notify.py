"""Телеграм: сводка после смены и тревога, когда FACT замолчал.

Два сценария, оба нужны мастеру, а не отчётности:

    после смены  — короткая сводка: КПД, выработка, куда ушёл простой,
                   пять худших станков и сколько тикетов остались без разбора;
    тревога      — приложение перестало получать данные от FACT дольше
                   получаса, и никто этого не видит, потому что доска показывает
                   последнее известное состояние.

Настройка — в `_app/config.json`:

    {
      "port": 8780,
      "fact": "http://172.0.30.9",
      "telegram": {
        "token": "123456:AA...",       у BotFather
        "chat_id": "-1001234567890",   куда слать: группа мастеров или личка
        "shift_report": true,
        "alerts": true,
        "after_shift_min": 15          через сколько минут после смены слать сводку
      }
    }

Проверить, не отправляя никому:

    python notify.py --dry --shift 2026.09.11.A     напечатать текст сводки
    python notify.py --test                         отправить пробное сообщение

Без настроек приложение работает как раньше: ничего не шлётся, ошибок нет.
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import logs
import reports
import storage
import tickets

LOG = logs.get("notify")
API = "https://api.telegram.org/bot%s/sendMessage"

# Смены цеха: A 07:00–15:00, B 15:00–23:00, C 23:00–07:00.
SHIFT_ENDS = {"A": 15, "B": 23, "C": 7}
SILENCE_MIN = 30          # столько молчит FACT, прежде чем это тревога


def settings():
    return (storage.config().get("telegram") or {})


def enabled():
    s = settings()
    return bool(s.get("token") and s.get("chat_id"))


def _say(text):
    """Печать в консоль, которая не падает на эмодзи: консоль Windows в cp1251."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, "replace").decode(enc, "replace"))


def send(text, dry=False):
    """Отправляет сообщение. Возвращает True, если ушло.

    Без настроенного бота ничего не печатает: из сборщика печать в консоль
    службы никому не видна, а на эмодзи консоль Windows падала."""
    s = settings()
    if dry or not enabled():
        if dry:
            _say(text)
        return False
    data = urllib.parse.urlencode({
        "chat_id": s["chat_id"], "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(API % s["token"], data, timeout=20) as r:
            ok = json.loads(r.read()).get("ok", False)
        if not ok:
            LOG.warning("телеграм не принял сообщение")
        return ok
    except Exception as e:
        # Молчание телеграма не должно ронять приложение: цех работает и без него.
        LOG.warning("не отправилось в телеграм: %s: %s", type(e).__name__, e)
        return False


# --- тексты ------------------------------------------------------------------

def shift_text(day, letter):
    """Сводка по смене. Читается с телефона за десять секунд."""
    s = reports.shift_summary(day, letter)
    head = "<b>Смена %s · %s</b>" % (letter, day.replace(".", "/"))
    if not s["loaded"]:
        return head + "\nДанных по смене ещё нет: FACT не выгрузился или зеркало не обновлено."

    lines = [head,
             "КПД <b>%s%%</b> · выработка %s тыс. пиков · станков %d"
             % (s["effic"], f"{s['kpicks']:,}".replace(",", " "), s["looms"]),
             "Простой %s ч, из них ожидание оператора %s ч" % (s["stop_h"], s["wait_h"])]

    if s["causes_h"]:
        lines.append("\n<b>Куда ушёл простой</b>")
        for name, h in list(s["causes_h"].items())[:5]:
            lines.append("  %s — %s ч" % (name, h))

    st = s["stops"]
    lines.append("\nОбрывы: уток %d · основа %d · ворс %d · ручные остановы %d"
                 % (st["уток"], st["основа"], st["ворс"], st["ручные"]))

    lines.append("\n<b>Куда идти в первую очередь</b>")
    for w in s["worst"]:
        extra = ", ручные %d мин" % w["manual_min"] if w["manual_min"] else ""
        lines.append("  %s (%s) — КПД %s%%, простой %d мин%s"
                     % (w["loom"], w["style"], w["eff"], w["stop_min"], extra))

    # Тикеты этой смены: сколько простоя объяснили и сколько осталось без причины.
    shift_key = "%s.%s" % (day, letter)
    conn = tickets.db()
    rows = conn.execute("SELECT category_id, duration_sec FROM ticket WHERE shift=?",
                        (shift_key,)).fetchall()
    conn.close()
    if rows:
        nameless = sum(1 for r in rows if not r["category_id"])
        mins = round(sum(r["duration_sec"] or 0 for r in rows) / 60)
        lines.append("\nТикетов за смену %d (%d мин); без причины %d"
                     % (len(rows), mins, nameless))
    return "\n".join(lines)


def day_text(day):
    """Итог за сутки — уходит утром, когда смена C закрыла день."""
    s = reports.day_summary(day)
    head = "<b>Итог за сутки · %s</b>" % day.replace(".", "/")
    if not s["loaded"]:
        return head + "\nДанных за сутки ещё нет: FACT не выгрузился или зеркало не обновлено."

    lines = [head,
             "КПД <b>%s%%</b> · выработка %s тыс. пиков · станков %d"
             % (s["effic"], f"{s['kpicks']:,}".replace(",", " "), s["looms"]),
             "Простой %s ч, из них ожидание оператора %s ч" % (s["stop_h"], s["wait_h"])]

    if s["by_shift"]:
        lines.append("\n<b>По сменам</b>")
        for sh in s["by_shift"]:
            lines.append("  %s — КПД %s%%, %s тыс. пиков"
                         % (sh["shift"], sh["effic"],
                            f"{sh['kpicks']:,}".replace(",", " ")))

    if s["causes_h"]:
        lines.append("\n<b>Куда ушёл простой за сутки</b>")
        for name, h in list(s["causes_h"].items())[:5]:
            lines.append("  %s — %s ч" % (name, h))

    st = s["stops"]
    lines.append("\nОбрывы: уток %d · основа %d · ворс %d · ручные остановы %d"
                 % (st["уток"], st["основа"], st["ворс"], st["ручные"]))

    lines.append("\n<b>Худшие станки за сутки</b>")
    for w in s["worst"]:
        extra = ", ручные %d мин" % w["manual_min"] if w["manual_min"] else ""
        lines.append("  %s — КПД %s%%, простой %d мин%s"
                     % (w["loom"], w["eff"], w["stop_min"], extra))

    conn = tickets.db()
    rows = conn.execute("SELECT category_id, duration_sec FROM ticket WHERE shift LIKE ?",
                        (day + ".%",)).fetchall()
    conn.close()
    if rows:
        nameless = sum(1 for r in rows if not r["category_id"])
        mins = round(sum(r["duration_sec"] or 0 for r in rows) / 60)
        lines.append("\nТикетов за сутки %d (%d мин); без причины %d"
                     % (len(rows), mins, nameless))
    return "\n".join(lines)


def alert_text(reason, last_at):
    last = ("последний снимок станков в " + last_at[11:16]) if last_at \
        else "снимков не было ни разу"
    return ("⚠️ <b>Нет связи с FACT</b>\n%s\n%s\n"
            "Доска в цехе показывает последнее известное состояние — ему нельзя верить."
            % (reason, last))


def recovered_text():
    return "✅ <b>FACT снова отвечает.</b> Данные на доске опять живые."


def andon_text(r):
    """Станок стоит без причины дольше порога — мастеру, один раз на останов."""
    return ("🟣 <b>%s стоит %d мин без причины</b>\n"
            "Станок сообщает: %s · артикул %s · смена %s\n"
            "Заведите тикет на доске или в приложении — иначе это время уйдёт "
            "в «причина не указана»."
            % (r["loom"], r["sec"] // 60, r["cause_ru"], r.get("style") or "—",
               (r.get("shift") or "")[-1:]))


# --- расписание --------------------------------------------------------------

def previous_shift(now):
    """Смена, которая только что закончилась к этому моменту, или None."""
    for letter, end_hour in SHIFT_ENDS.items():
        end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        if end > now:
            continue
        # Смена C кончается утром, а числится за прошлыми сутками.
        day = (end - timedelta(days=1)) if letter == "C" else end
        yield letter, day.strftime("%Y.%m.%d"), end


class Watcher:
    """Следит за молчанием FACT и за концом смены. Один поток, минутный шаг."""

    def __init__(self):
        self.sent_shifts = set()
        self.alerted = False

    def tick(self, now=None):
        now = now or datetime.now().astimezone()
        s = settings()

        if s.get("alerts", True):
            self._check_fact(now)
        if s.get("shift_report", True):
            self._check_shift(now, s.get("after_shift_min", 15))

    def _check_fact(self, now):
        if tickets.SOURCE["mode"] != "fact":
            return          # по зеркалу молчать нечему
        import collector
        s = collector.read_status() or {}
        running = collector.alive(s)
        live_at = (s.get("live") or {}).get("at")
        try:
            silent_min = (now - datetime.fromisoformat(live_at)).total_seconds() / 60 \
                if live_at else None
        except ValueError:
            silent_min = None
        # Снимок сборщика обновляется, только когда FACT выложил новый. Если
        # FACT отвечает, но снимков нет полчаса — это тоже «нет связи».
        broken = not running or silent_min is None or silent_min > SILENCE_MIN
        if broken and not self.alerted:
            reason = ("сборщик данных не работает" if not running
                      else s.get("last_error") or "FACT не выкладывает новые снимки")
            LOG.warning("тревога: FACT молчит (%s)", reason)
            send(alert_text(reason, live_at))
            self.alerted = True
        elif not broken and self.alerted:
            LOG.info("FACT снова отвечает — тревога снята")
            send(recovered_text())
            self.alerted = False

    def _check_shift(self, now, delay_min):
        for letter, day, end in previous_shift(now):
            key = "%s.%s" % (day, letter)
            if key in self.sent_shifts:
                continue
            if now < end + timedelta(minutes=delay_min):
                continue
            if now > end + timedelta(hours=2):
                self.sent_shifts.add(key)      # слишком поздно, не шлём вдогонку
                continue
            LOG.info("сводка по смене %s отправляется", key)
            send(shift_text(day, letter))
            self.sent_shifts.add(key)
            # Сутки закрывает смена C — следом уходит итог за весь день.
            if letter == "C" and settings().get("daily_digest", True):
                LOG.info("суточный итог за %s отправляется", day)
                send(day_text(day))

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as e:
                LOG.exception("наблюдатель: %s", e)
            time.sleep(60)


def start():
    """Запускает наблюдателя, если телеграм настроен."""
    import threading
    if not enabled():
        return False
    t = threading.Thread(target=Watcher().run, daemon=True)
    t.start()
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shift", metavar="ДЕНЬ.СМЕНА", help="например 2026.09.11.A")
    ap.add_argument("--day", metavar="ДЕНЬ", help="итог за сутки, например 2026.09.11")
    ap.add_argument("--dry", action="store_true", help="только напечатать, не отправлять")
    ap.add_argument("--test", action="store_true", help="отправить пробное сообщение")
    args = ap.parse_args()

    if args.test:
        ok = send("Проверка связи: приложение цеха на месте.", dry=args.dry)
        print("отправлено" if ok else "не отправлено (проверьте token и chat_id в config.json)")
        return
    if args.shift or args.day:
        if args.shift:
            day, letter = args.shift.rsplit(".", 1)
            text = shift_text(day, letter)
        else:
            text = day_text(args.day)
        print(text)
        if not args.dry:
            print("\n— отправлено" if send(text) else "\n— не отправлено")
        return
    print("Телеграм настроен." if enabled() else
          "Телеграм не настроен: добавьте token и chat_id в _app/config.json")
    now = datetime.now().astimezone()
    for letter, day, end in previous_shift(now):
        print("  последняя закончившаяся смена: %s.%s (в %s)" % (day, letter, end.strftime("%H:%M")))
        break


if __name__ == "__main__":
    main()
