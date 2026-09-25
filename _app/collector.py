"""Сборщик данных FACT: живое состояние станков, свежие смены и остановы.

Единственный, кто пишет в базу станков. Работает сам, без людей:

    раз в минуту      FACT выкладывает новый снимок состояния. Сразу после
                      снимка спрашивать нечего — ждём ~50 с, дальше смотрим
                      каждые 5 секунд, пока не появится следующий. Новый снимок —
                      читаем стоящие станки (все — раз в 5 минут), пишем снимок
                      для мониторов, заводим и закрываем тикеты, шлём мастеру
                      станки без причины;
    каждые 2 минуты   забирает изменившиеся файлы смен и остановов (с
                      If-Modified-Since: неизменившийся файл FACT не отдаёт),
                      дописывает их в базу и пересчитывает свёртку остановов;
    раз в полчаса     забирает заказы и техкарты из 1С, если адрес задан.

Откуда брать — FACT по сети или папка зеркала. Код один и тот же, меняется
только источник: всё, что проверено на зеркале, так же работает на живом FACT.

    python collector.py --once                  один проход по зеркалу и отчёт
    python collector.py --fact http://172.0.30.9
    python collector.py --fact http://172.0.30.9 --once

По умолчанию сборщик запускается внутри приложения отдельным потоком. Можно
запустить и отдельным процессом — тогда приложение увидит его отметку в
`run/collector.json` и своего сборщика не поднимет: два сразу не работают.
"""
import argparse
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
from datetime import datetime

import ingest
import livestate
import logs
import storage

LOG = logs.get("collector")

LIVE_SEC = 5            # как часто спрашиваем FACT о новом снимке, когда его пора ждать
SNAPSHOT_SEC = 60       # FACT выкладывает новый снимок раз в минуту
FULL_SEC = 300          # файлы всех станков — раз в 5 минут, в остальные — только стоящих
INGEST_SEC = 120        # как часто дописываем смены и остановы
YESTERDAY_UNTIL_H = 3   # вчерашние остановы перечитываем только до 3 часов ночи
ONEC_MIN = 30           # как часто забираем заказы из 1С
BEAT_STALE_SEC = 30     # отметка старше — сборщика нет в живых
STATUS_FILE = os.path.join(storage.RUN_DIR, "collector.json")

DAY_DIR = re.compile(r"^\d{4}\.\d\d\.\d\d$")


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_status():
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def alive(status=None):
    """Жив ли сборщик — по его отметке, кто бы его ни запустил."""
    s = status if status is not None else read_status()
    return bool(s and s.get("beat") and time.time() - s["beat"] < BEAT_STALE_SEC)


def _pid_alive(pid):
    """Есть ли процесс с таким номером. На Windows нельзя спрашивать через
    os.kill(pid, 0): там это не проверка, а завершение процесса."""
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))    # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259           # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def other_alive(status=None):
    """Работает ли другой сборщик. Свежей отметки мало: после быстрого
    перезапуска службы отметка остановленного процесса ещё полминуты свежая,
    и новое приложение оставалось без сборщика. Поэтому на этой же машине
    проверяем, что процесс действительно есть."""
    s = status if status is not None else read_status()
    if not alive(s) or s.get("pid") == os.getpid():
        return False
    if s.get("host") == socket.gethostname():
        return _pid_alive(s.get("pid"))
    return True


_LOCK = None


def _take_lock():
    """Неблокирующий захват run/collector.lock на весь срок процесса."""
    global _LOCK
    if _LOCK is not None:
        return True
    os.makedirs(storage.RUN_DIR, exist_ok=True)
    f = open(os.path.join(storage.RUN_DIR, "collector.lock"), "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _LOCK = f
    return True


class Collector:
    def __init__(self, src, on_live=None, on_ingest=None):
        self.src = src
        self.on_live = on_live
        self.on_ingest = on_ingest
        self.last_dir = None
        self.fresh_at = None             # когда прочитали самый свежий снимок FACT
        self.full_at = None              # когда читали файлы всех станков
        self.snap_at = None              # когда пришёл последний новый снимок
        self.collect_checked = 0         # когда перечитывали журнал опроса FACT
        self.stuck_told = False          # о зависшем сборе FACT уже написали
        self.cache = {}                  # путь -> (время изменения, байты)
        self._lock = threading.Lock()
        self.next_onec = 0
        self.status = {
            "pid": os.getpid(), "host": socket.gethostname(), "source": src.kind,
            "url": getattr(src, "url", None), "started_at": _now_iso(), "beat": None,
            "live": {}, "ingest": {}, "onec": {}, "last_error": None,
        }

    # --- отметка «я жив» ---

    def claim(self):
        """Стать единственным сборщиком. Блокировка ОС держится, пока жив процесс:
        отметка «я жив» по времени её не заменяет — медленный проход FACT
        дольше 30 с выглядел смертью, и запускался второй писатель."""
        if other_alive() or not _take_lock():
            return False
        self.beat()
        return True

    def beat(self):
        with self._lock:
            self.status["beat"] = time.time()
            usage = getattr(self.src, "usage", None)
            if usage:
                self.status["fact_http"] = usage()
            tmp = STATUS_FILE + ".tmp"
            os.makedirs(storage.RUN_DIR, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.status, f, ensure_ascii=False)
            os.replace(tmp, STATUS_FILE)

    def _error(self, where, e):
        msg = "%s: %s: %s" % (where, type(e).__name__, e)
        # В журнал — только смену ошибки: за ночь молчания FACT одинаковых
        # строк было бы тысячи.
        if self.status.get("last_error") != msg:
            LOG.warning(msg)
        self.status["last_error"] = msg
        self.status["last_error_at"] = _now_iso()

    # --- живое состояние ---

    def live_once(self, force=False):
        dirs = livestate.state_dirs(self.src)
        d = dirs[0]
        if d == self.last_dir and not force:
            self._watch_stuck()
            return False
        t0 = time.perf_counter()
        # Раз в 5 минут — все станки; между ними — только стоящие, остальное из
        # прошлого снимка (он лежит в run/live.json).
        full = force or not self.full_at or time.time() - self.full_at >= FULL_SEC
        prev = None if full else livestate.load()
        if prev and prev.get("source") != self.src.kind:
            prev, full = None, True
        link = self._collect_links()     # что FACT ответил про каждый станок в опросе
        try:
            snap = livestate.snapshot(self.src, d, prev=prev, full=full, link=link)
        except urllib.error.HTTPError as e:
            # FACT раз в минуту пишет новую папку снимка: в первые секунды она
            # уже видна в списке, а файлов в ней ещё нет (раньше это давало
            # предупреждение в журнал каждую минуту). Берём предыдущую, целую,
            # а новую прочитаем через пять секунд.
            if e.code != 404 or len(dirs) < 2:
                raise
            if dirs[1] == self.last_dir and not force:
                self._watch_stuck()
                return False
            d = dirs[1]
            snap = livestate.snapshot(self.src, d, prev=prev, full=full, link=link)
        livestate.save(snap)
        import productionlog
        productionlog.archive_sample(snap)
        import loomstate
        try:
            loomstate.record(snap)
        except Exception as e:           # интервалы не должны останавливать доску
            self._error("интервалы состояний", e)
        if snap.get("full"):
            self.full_at = time.time()
        self.last_dir = d
        # Прочитали самый свежий — следующего ждать около минуты. Если взяли
        # предыдущий (свежий ещё не дописан), продолжаем спрашивать каждые 5 с.
        self.fresh_at = time.time() if d == dirs[0] else None
        stopped = sum(1 for st in snap["looms"].values() if not st["running"])
        self.status["live"] = {
            "dir": d, "at": _now_iso(), "looms": len(snap["looms"]), "stopped": stopped,
            "missing": snap["missing"], "read_ms": round((time.perf_counter() - t0) * 1000),
            "fact_time": snap.get("fact_time"), "files_read": snap.get("files_read"),
            "full": snap.get("full"),
        }
        if (self.status.get("last_error") or "").startswith("живое"):
            LOG.info("FACT снова отдаёт состояние")
            self.status["last_error"] = None
        # Время снимка — по FACT: после перезапуска первым читается и висящий
        # с ночи снимок, он не свежий.
        now = time.time()
        self.snap_at = min(now, snap.get("fact_time") or now) if self.src.kind == "fact" else now
        fresh = now - self.snap_at <= 180
        if self.stuck_told and fresh:
            self._tell("Данные FACT снова обновляются: снимок %s." % _now_iso()[11:16])
            self.stuck_told = False

        # Тикеты и андон — только по живым данным: по зеркалу или старому снимку
        # это завело бы тикеты на давно прошедшие остановы.
        if self.src.kind == "fact" and fresh:
            import tickets
            tickets.poll_once()
            self._escalate(tickets)
        if self.on_live:
            self.on_live()
        return True

    def _escalate(self, tickets):
        """Станок стоит без причины дольше порога — пишем мастеру один раз на
        останов. Сообщения уходят вне записи в базу: телеграм может отвечать
        секундами, а тикеты с мониторов в это время ждать не должны."""
        try:
            import notify
            if not notify.enabled():
                return
            rows = tickets.andon_candidates()
            sent = [r["ticket_id"] for r in rows if notify.send(notify.andon_text(r))]
            tickets.mark_escalated(sent)
            if rows:
                LOG.info("андон: мастеру отправлено %d из %d станков без причины",
                         len(sent), len(rows))
        except Exception as e:
            self._error("андон", e)

    def _next_wait(self):
        """Сколько ждать до следующего вопроса FACT: сразу после свежего снимка
        новому взяться неоткуда — до его срока (минута минус два шага) не спрашиваем."""
        if self.fresh_at:
            left = self.fresh_at + SNAPSHOT_SEC - 2 * LIVE_SEC - time.time()
            if left > LIVE_SEC:
                return left
        return LIVE_SEC

    # --- журнал опроса FACT: связь со станками и зависший сбор ---

    def _collect_log(self):
        """(текущий опрос, последний законченный) из opestate/collect_log*.txt."""
        read = lambda name: livestate.parse_collect_log(
            (self._fetch(livestate.OPESTATE + "/" + name)[0] or b"").decode("utf-8", "replace"))
        cur = read(livestate.COLLECT_LOG)
        done = cur if cur["completed"] else read("collect_log1.txt")
        self.status["fact_collect"] = {
            "started": cur["started"], "finished": cur["finished"], "completed": cur["completed"],
            "problems": {k: v for k, v in done["looms"].items() if v != "SUCCEED"}}
        return cur, done

    def _collect_links(self):
        """{станок: ответ FACT} последнего законченного опроса; нет журнала — {}."""
        try:
            return self._collect_log()[1]["looms"]
        except (OSError, ValueError, urllib.error.URLError):
            return {}

    def _watch_stuck(self):
        """Новых снимков нет: раз в минуту перечитать журнал опроса FACT, чтобы
        сказать почему (24.09: сбор FACT начался в 02:56 и не закончился — доска
        до полудня показывала снимок 02:55). Через 15 минут — одно сообщение."""
        now = time.time()
        if not self.snap_at or now - self.snap_at < 180 or now - self.collect_checked < 60:
            return
        self.collect_checked = now
        try:
            cur, _ = self._collect_log()
        except (OSError, ValueError, urllib.error.URLError):
            return
        if now - self.snap_at >= 900 and not self.stuck_told and self.src.kind == "fact":
            last = time.strftime("%H:%M", time.localtime(self.snap_at))
            why = ("сбор в FACT начался в %s и не закончился — перезапустите программу сбора на ПК FACT"
                   % cur["started"][11:16]) if cur["started"] and not cur["completed"] else "причина в журнале FACT не видна"
            self._tell("Данные FACT не обновляются с %s: %s." % (last, why))
            self.stuck_told = True

    def _tell(self, text):
        LOG.warning(text)
        try:
            import notify
            notify.send(text)
        except Exception as e:           # телеграм не должен ронять сборщик
            LOG.warning("не отправилось: %s", e)

    def run_live(self):
        while True:
            try:
                self.live_once()
            except Exception as e:
                self._error("живое состояние", e)
            # Отметку «жив» пишем каждые 5 секунд и во время ожидания: иначе при
            # паузе в 50 с приложение сочло бы сборщик остановленным.
            end = time.time() + self._next_wait()
            while True:
                try:
                    self.beat()
                except OSError as e:
                    LOG.warning("отметка сборщика не записалась: %s", e)
                rest = end - time.time()
                if rest <= 0:
                    break
                time.sleep(min(LIVE_SEC, rest))

    # --- смены и остановы ---

    def _fetch(self, rel):
        """(байты, изменился ли) — неизменившийся файл берём из памяти."""
        old = self.cache.get(rel)
        data, m = self.src.read(rel, since=old[0] if old else None)
        if data is None:
            return (old[1] if old else None), False
        self.cache[rel] = (m, data)
        if self.src.kind == "fact":
            self._save_mirror(rel, data, m)
        return data, True

    def _save_mirror(self, rel, data, mtime):
        """Скачанное с FACT кладём в зеркало: отчёты по файлам и скрипты
        пересборки видят те же данные, что и база."""
        path = os.path.join(storage.ROOT, *rel.split("/"))
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            os.utime(path, (mtime, mtime))
        except OSError as e:
            LOG.warning("зеркало: %s не записался: %s", rel, e)

    def ingest_once(self):
        t0 = time.perf_counter()
        st = {"shift_files": 0, "shift_rows": 0, "stop_days": 0, "stop_rows": 0}
        db = storage.fact_rw()
        try:
            # Смены: новые — все, уже известные — только три последние, их FACT
            # ещё дописывает (идущая смена обновляется каждые несколько минут).
            known = {r[0] for r in db.execute("SELECT DISTINCT shift FROM shift_full")}
            names = sorted(f for f in self.src.list("factdata/shift-shift")[1]
                           if ingest.SHIFT_FILE.match(f))
            # Последняя известная смена могла попасть в базу недописанной (с
            # зеркала или перед остановкой службы) — её перечитываем тоже.
            recent = set(names[-3:]) | ({max(known) + ".txt"} if known else set())
            shift_days = set()
            for fn in names:
                shift = fn[:-4]
                if shift in known and fn not in recent:
                    continue
                data, changed = self._fetch("factdata/shift-shift/" + fn)
                if not changed or data is None:
                    continue
                st["shift_rows"] += ingest.upsert_shift(db, shift, data.decode("utf-8", "replace"))
                st["shift_files"] += 1
                shift_days.add(shift[:10])
            db.commit()

            # Остановы: дни, которых нет в базе, последний, что есть (он мог
            # остаться недописанным), и сегодняшний — файл станка растёт весь
            # день. Вчерашний — только до 3 часов ночи: потом FACT его уже не
            # дописывает, а это ~46 лишних запросов каждые две минуты.
            days = sorted(d for d in self.src.list("factdata/stop_history")[0] if DAY_DIR.match(d))
            have = db.execute("SELECT MAX(day) FROM stop_log").fetchone()[0] or ""
            tail = days[-2:] if datetime.now().hour < YESTERDAY_UNTIL_H else days[-1:]
            todo = sorted({d for d in days if d >= have} | set(tail))
            for day in todo:
                files = sorted(f for f in self.src.list("factdata/stop_history/" + day)[1]
                               if f.endswith(".txt"))
                texts, changed = [], False
                for fn in files:
                    data, ch = self._fetch("factdata/stop_history/%s/%s" % (day, fn))
                    changed = changed or ch
                    if data:
                        texts.append(data.decode("utf-8", "replace"))
                if not changed:
                    continue
                rows = []
                for text in texts:
                    rows += ingest.stop_rows(text)[1]
                st["stop_rows"] += ingest.replace_stop_day(db, day, rows)
                st["stop_days"] += 1
                db.commit()
            # Память под файлы держим только за последние дни.
            keep = set(todo[-2:])
            for rel in [r for r in self.cache if r.startswith("factdata/stop_history/")]:
                if rel.split("/")[2] not in keep:
                    del self.cache[rel]

            if self.src.kind == "fact":
                self._small_files()
        finally:
            db.close()
        if shift_days:
            st["report_days"] = self.daily_reports(sorted(shift_days))
        st["ms"] = round((time.perf_counter() - t0) * 1000)
        st["at"] = _now_iso()
        self.status["ingest"] = st
        if (st["shift_files"] or st["stop_days"]) and self.on_ingest:
            self.on_ingest()
        return st

    def daily_reports(self, days):
        """Производственный отчёт (лист TOYOTA) за дни, по которым пришли смены.

        Раньше его собирали вручную скриптом из _tools, и вкладка «Производственный
        отчёт» стояла на последнем дне, когда кто-то его запускал."""
        try:
            import reports
            return reports.rebuild_daily_reports(days)
        except Exception as e:
            self._error("отчёт за день", e)
            return []

    def _shift_docs(self):
        """Три документа расстановки на сегодня (A, B, C) — как только начался день."""
        try:
            import people
            import tickets
            day = tickets.current_shift()[:10]
            made = people.ensure_shift_docs(day)
            if made:
                LOG.info("расстановка на %s: заведены документы смен %s", day, ", ".join(made))
        except Exception as e:
            self._error("расстановка", e)

    def _small_files(self):
        """Файлы, которые приложение читает прямо с диска: кто на каком станке
        и текущие рулоны."""
        try:
            ops = sorted(f for f in self.src.list("factdata/operator")[1]
                         if re.match(r"\d{4}\.\d\d\.\d\d\.txt$", f))
            for fn in ops[-2:]:
                self._fetch("factdata/operator/" + fn)
            for rel in ("factdata/current/current.txt", "factdata/cloth/current.txt"):
                self._fetch(rel)
        except Exception as e:
            self._error("файлы операторов", e)

    def _onec(self):
        cfg = (storage.config().get("onec") or {})
        if not cfg.get("url") or time.time() < self.next_onec:
            return
        self.next_onec = time.time() + 60 * int(cfg.get("every_min") or ONEC_MIN)
        try:
            import integration
            r = integration.pull_1c(cfg)
            self.status["onec"] = {**r, "at": _now_iso()}
            LOG.info("1С: %s", r)
        except Exception as e:
            self.status["onec"] = {"error": "%s: %s" % (type(e).__name__, e), "at": _now_iso()}
            self._error("1С", e)

    def run_ingest(self):
        while True:
            try:
                self.ingest_once()
            except Exception as e:
                self._error("смены и остановы", e)
            try:
                self._onec()
            except Exception as e:
                self._error("1С", e)
            self._shift_docs()
            time.sleep(INGEST_SEC)

    def run_states(self):
        """Интервалы состояний: дочитать архив снимков (в первый раз — весь)."""
        import loomstate
        while True:
            t0 = time.perf_counter()
            try:
                n = loomstate.catch_up()
                if n:
                    LOG.info("интервалы состояний: дочитано снимков %s за %.1f с", n, time.perf_counter() - t0)
                return
            except Exception as e:       # до успеха живые снимки в интервалы не пишутся
                self._error("интервалы состояний", e)
                time.sleep(300)

    def start(self):
        for target in (self.run_live, self.run_ingest, self.run_states):
            threading.Thread(target=target, name="collector:" + target.__name__,
                             daemon=True).start()
        return self


def start_in_app(src, on_live=None, on_ingest=None):
    """Запуск внутри приложения. Если отдельный сборщик уже работает — не мешаем,
    но присматриваем: остановился он — поднимаем свой, иначе доска замрёт."""
    def launch():
        # Захват не удался (второй процесс держит блокировку) — не запускаемся:
        # раньше результат claim() не проверялся, и писателей становилось два.
        c = Collector(src, on_live=on_live, on_ingest=on_ingest)
        return c.start() if c.claim() else None

    s = read_status()
    if not other_alive(s):
        started = launch()
        if started:
            return started
    LOG.info("сборщик уже работает отдельно (pid %s) — жду; остановится — запущу свой",
             s.get("pid"))

    def standby():
        while True:
            time.sleep(BEAT_STALE_SEC / 2)
            if not other_alive() and launch():
                LOG.info("отдельный сборщик остановился — сборщик запущен в приложении")
                return
    threading.Thread(target=standby, name="collector:standby", daemon=True).start()
    return None


def main():
    cfg = storage.config()
    ap = argparse.ArgumentParser(description="Сборщик данных FACT")
    ap.add_argument("--fact", metavar="URL", default=cfg.get("fact"),
                    help="адрес FACT, например http://172.0.30.9; без него — зеркало")
    ap.add_argument("--mirror", action="store_true", help="работать по зеркалу, даже если адрес задан")
    ap.add_argument("--once", action="store_true", help="один проход и отчёт — для проверки")
    args = ap.parse_args()

    logs.setup()
    storage.prepare()
    src = livestate.MirrorSource() if args.mirror or not args.fact \
        else livestate.HttpSource(args.fact)
    c = Collector(src)
    where = "FACT " + args.fact if src.kind == "fact" else "зеркало " + storage.FACTDATA

    if args.once:
        t0 = time.time()
        c.live_once(force=True)
        live = c.status["live"]
        print("Источник: %s" % where)
        print("  живое состояние: снимок %s, станков %d, стоит %d, прочитано за %d мс%s"
              % (live["dir"], live["looms"], live["stopped"], live["read_ms"],
                 (", нет файлов у " + ", ".join(live["missing"])) if live["missing"] else ""))
        st = c.ingest_once()
        print("  смены: файлов %d, строк %d; остановы: дней %d, строк %d; %d мс"
              % (st["shift_files"], st["shift_rows"], st["stop_days"], st["stop_rows"], st["ms"]))
        print("  всего %.1f с" % (time.time() - t0))
        return

    if not c.claim():
        s = read_status()
        raise SystemExit("Сборщик уже работает: pid %s на %s" % (s.get("pid"), s.get("host")))
    LOG.info("сборщик запущен: %s", where)
    print("Сборщик: %s. Остановить — Ctrl+C." % where)
    c.start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("остановлен")


if __name__ == "__main__":
    main()
