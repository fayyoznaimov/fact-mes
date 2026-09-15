"""Журнал работы приложения.

Пока приложение запускали руками, хватало вывода в консоль. На сервере консоли
нет, а вывод Python при перенаправлении в файл буферизуется — из-за этого
`app.log` оставался пустым даже после часов работы. Поэтому журнал пишется
через logging: сразу на диск, с ротацией, чтобы за год не вырос в гигабайты.

    logs.setup()                      # один раз при запуске
    log = logs.get("web")             # в любом модуле
    log.warning("FACT не отвечает")

Что писать обязательно: ошибки запросов, неудачные входы, сбои опроса FACT.
Обычные запросы не пишем — 30 мониторов за сутки дадут 170 тысяч строк ни о чём.
"""
import logging
import logging.handlers
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

MAX_BYTES = 2_000_000
KEEP_FILES = 10          # примерно месяц работы цеха

_ready = False


def setup(level=logging.INFO, to_console=True):
    global _ready
    if _ready:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)-8s %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    root = logging.getLogger("shop")
    root.setLevel(level)
    root.propagate = False

    fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES,
                                              backupCount=KEEP_FILES, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if to_console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)
    _ready = True


def get(name):
    if not _ready:
        setup()
    return logging.getLogger("shop." + name)


def tail(lines=200):
    """Последние строки журнала — чтобы смотреть их из приложения, а не по RDP."""
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()[-lines:]
