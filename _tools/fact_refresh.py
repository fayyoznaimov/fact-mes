"""Обновить зеркало FACT: скачать новые файлы и те, что изменились на FACT.

fact_mirror.py пропускает любой уже скачанный файл — даже если FACT его с тех
пор дописал (итоги недели и месяца, файлы станков, остановы за прошлые дни).
Здесь сравниваем время изменения из листинга Apache с локальным: файл новее —
качаем заново и ставим ему время FACT, чтобы следующий проход его не трогал.

    python fact_refresh.py                 всё дерево из fact_mirror.ROOTS и ещё EXTRA
    python fact_refresh.py factdata/loom   одна папка
"""
import html
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime

import fact_mirror as fm

EXTRA = ["factdata/shift/", "factdata/xlsdata/", "factdata/voicemsg/"]
ROW = re.compile(r'<a href="([^"]+)">.*?</a>\s*(?:</td>\s*<td[^>]*>)?\s*'
                 r'(\d{4}-\d\d-\d\d \d\d:\d\d|\d\d-[A-Za-z]{3}-\d{4} \d\d:\d\d)', re.I | re.S)


def _when(text):
    for fmt in ("%Y-%m-%d %H:%M", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            pass
    return None


def rows(url):
    """[(имя, время изменения на FACT или None)] из листинга Apache."""
    body = fm.fetch(url).decode("utf-8", "replace")
    out = {html.unescape(h): _when(w) for h, w in ROW.findall(body)
           if not fm.SKIP_HREF.match(html.unescape(h))}     # ?C=N;O=D — сортировка Apache
    for h in fm.LINK.findall(body):            # строки без даты — тоже берём
        h = html.unescape(h)
        if not fm.SKIP_HREF.match(h) and h != "../":
            out.setdefault(h, None)
    return list(out.items())


def refresh(rel, dest, st):
    url = fm.FACT + "/" + rel
    try:
        items = rows(url)
    except Exception as e:
        print("  ! не открылся каталог %s: %s" % (rel, e), flush=True)
        st["errors"] += 1
        return
    local_dir = os.path.join(dest, *rel.strip("/").split("/"))
    os.makedirs(local_dir, exist_ok=True)
    for name, remote in items:
        if name.endswith("/"):
            refresh(rel + name, dest, st)
            continue
        local = os.path.join(local_dir, urllib.parse.unquote(name))
        have = os.path.exists(local) and os.path.getsize(local) > 0
        # Листинг даёт время с точностью до минуты — сравниваем с запасом.
        if have and (remote is None or os.path.getmtime(local) >= remote - 60):
            st["same"] += 1
            continue
        try:
            data = fm.fetch(url + name)
            with open(local, "wb") as f:
                f.write(data)
            if remote:
                os.utime(local, (remote + 59, remote + 59))
            st["updated" if have else "new"] += 1
            st["bytes"] += len(data)
            n = st["updated"] + st["new"]
            if n % 200 == 0:
                print("  %d файлов, %.0f МБ … %s" % (n, st["bytes"] / 1e6, rel), flush=True)
        except Exception as e:
            print("  ! %s%s: %s" % (rel, name, e), flush=True)
            st["errors"] += 1


def main():
    roots = [a.strip("/") + "/" for a in sys.argv[1:]] or fm.ROOTS + EXTRA
    st = {"new": 0, "updated": 0, "same": 0, "bytes": 0, "errors": 0}
    t0 = time.time()
    for root in roots:
        before = st["new"] + st["updated"]
        print("[%s]" % root, flush=True)
        refresh(root, fm.DEST_DEFAULT, st)
        print("  +%d" % (st["new"] + st["updated"] - before), flush=True)
    print("ИТОГО: новых %d, обновлено %d, без изменений %d, %.1f МБ, ошибок %d, %.1f мин"
          % (st["new"], st["updated"], st["same"], st["bytes"] / 1e6, st["errors"],
             (time.time() - t0) / 60))


if __name__ == "__main__":
    main()
