"""Толчок на мониторы: как только что-то поменялось, доска узнаёт сразу.

Монитор держит одно соединение (Server-Sent Events) и ждёт. Меняется состояние
станков или кто-то завёл тикет — номер версии растёт, и все ждущие просыпаются
одновременно. Ответ собирается один раз на версию, а не на каждый монитор:
двадцать экранов получают одну и ту же готовую строку.

Опрос раз в 15 секунд остаётся запасным путём — если соединение рвётся,
страница сама переходит на опрос и возвращается к толчкам, когда связь есть.
"""
import os
import threading
import time


class Hub:
    def __init__(self):
        self._cond = threading.Condition()
        self.version = 1
        self.changed_at = time.time()
        self.listeners = 0

    def bump(self):
        with self._cond:
            self.version += 1
            self.changed_at = time.time()
            self._cond.notify_all()

    def wait(self, seen, timeout):
        """Ждёт версии новее `seen` не дольше `timeout` секунд; возвращает текущую."""
        with self._cond:
            if self.version == seen:
                self._cond.wait(timeout)
            return self.version

    def join(self):
        with self._cond:
            self.listeners += 1

    def leave(self):
        with self._cond:
            self.listeners -= 1


HUB = Hub()


class PerVersion:
    """Значение, которое собирается один раз на версию хаба.

    Пока один поток собирает, остальные ждут на замке, а не собирают то же
    самое параллельно — иначе двадцать мониторов разом нагрузили бы базу.
    """

    def __init__(self, build):
        self.build = build
        self._lock = threading.Lock()
        self._ver = None
        self._data = None

    def get(self, ver):
        if self._ver == ver:
            return self._data
        with self._lock:
            if self._ver != ver:
                self._data = self.build()
                self._ver = ver
            return self._data


def watch_file(path, on_change, every=1.0):
    """Следит за временем изменения файла и зовёт on_change, когда оно сдвинулось.

    Так веб-сервер узнаёт о свежем снимке станков, который записал сборщик —
    даже если сборщик работает отдельным процессом.
    """
    def run():
        last = None
        while True:
            try:
                m = os.path.getmtime(path)
            except OSError:
                m = None
            if m != last:
                if last is not None or m is not None:
                    on_change()
                last = m
            time.sleep(every)

    t = threading.Thread(target=run, name="watch:" + os.path.basename(path), daemon=True)
    t.start()
    return t
