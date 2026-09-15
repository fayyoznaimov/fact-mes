"""Согласованные копии SQLite и конфигурации. Источники открываются mode=ro.

Каталог completed публикуется переименованием только после проверки обеих баз.
Хранение без автоматического удаления; место проверяет администратор сервера.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile


def backup(data, config, destination):
    data, config, destination = map(Path, (data, config, destination))
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    stage = Path(tempfile.mkdtemp(prefix=".partial-", dir=destination))
    try:
        for name in ("shop.db", "fact.db"):
            source = sqlite3.connect((data / name).resolve().as_uri() + "?mode=ro", uri=True)
            target = sqlite3.connect(stage / name)
            try:
                source.backup(target, pages=1024, sleep=0.1)
                if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("Не прошла проверка копии " + name)
            finally:
                target.close()
                source.close()
            os.chmod(stage / name, 0o600)
        for name in ("config.json", "service.env"):
            if (config / name).is_file():
                shutil.copyfile(config / name, stage / name)
                os.chmod(stage / name, 0o600)
        (stage / "manifest.json").write_text(json.dumps({
            "created_utc": stamp, "databases": ["shop.db", "fact.db"],
            "consistency": "SQLite backup per database; not a cross-database transaction",
            "code_release": str(Path("/opt/fact-mes/current").resolve()),
        }, indent=2), encoding="utf-8")
        completed = destination / stamp
        stage.rename(completed)
        return completed
    except BaseException:
        shutil.rmtree(stage)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/var/lib/fact-mes")
    parser.add_argument("--config", default="/etc/fact-mes")
    parser.add_argument("--destination", default="/var/backups/fact-mes")
    args = parser.parse_args()
    print(backup(args.data, args.config, args.destination))
