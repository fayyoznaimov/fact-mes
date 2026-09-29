"""Prepare and run the full HTTP E2E on an isolated copy, never on production.

python _tools/run_e2e.py --data-root PATH --mxl PATH --order PATH --result PATH
Local source databases are read through SQLite backup; credentials are replaced.
On Windows the existing Excel template and installed Excel are also required.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request


def backup(source, destination):
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--mxl", type=Path, required=True)
    parser.add_argument("--order", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    for path in (args.data_root / "_app/shop.db", args.data_root / "_tools/fact.db",
                 args.mxl, args.order):
        if not path.is_file():
            parser.error("Missing fixture: " + str(path))
    # Refuse to run against a server already occupying the reserved test port.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8790))
    args.result.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    with tempfile.TemporaryDirectory(prefix="fact_e2e_") as temporary:
        root = Path(temporary)
        print("Preparing isolated E2E copy", flush=True)
        for folder in ("_app", "_tools"):
            (root / folder).mkdir()
            for source in (repo / folder).iterdir():
                if source.is_file() and source.suffix in {".py", ".html", ".ps1", ".js", ".css", ".svg"}:
                    shutil.copy2(source, root / folder / source.name)
        for relative in ("_app/shop.db", "_tools/fact.db"):
            backup(args.data_root / relative, root / relative)
        mirror = args.data_root / "factdata"
        if mirror.is_dir():
            shutil.copytree(mirror, root / "factdata")
        (root / "_tools/fixtures").mkdir()
        shutil.copy2(args.mxl, root / "_tools/fixtures/13.mxl")
        (root / "postman").mkdir()
        shutil.copy2(args.order, root / "postman/order_1557.json")
        if (repo / "frontend/dist").is_dir():
            shutil.copytree(repo / "frontend/dist", root / "frontend/dist")
        # Fail closed on any accidental FACT or other external-network fallback.
        # PYTHONPATH propagates this guard to the report-building subprocess too.
        (root / "sitecustomize.py").write_text(
            "import socket\n"
            "_connect = socket.socket.connect\n"
            "def local_connect(self, address):\n"
            "    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):\n"
            "        raise OSError('E2E blocks external network')\n"
            "    return _connect(self, address)\n"
            "socket.socket.connect = local_connect\n", encoding="utf-8")
        env["PYTHONPATH"] = str(root)
        provision = """
import json, secrets
import storage, productionlog
with storage.shop() as db:
    productionlog.register(db)
    for table in ('app_session', 'api_key', 'login_fail'):
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            db.execute('DELETE FROM ' + table)
    db.execute("UPDATE app_user SET active=0, pwd_hash='', pwd_salt=''")
    db.commit()
import auth, api
password = secrets.token_urlsafe(32)
login = 'e2e_' + secrets.token_hex(8)
auth.create_user(login, 'E2E administrator', 'admin', password)
token = auth.login(login, password)
key = api.create_key('E2E local only', ['read', 'write'])['key']
with open('e2e_secrets.json', 'w', encoding='utf-8') as f:
    json.dump({'admin': {'token': token}, 'key_1c': key}, f)
"""
        subprocess.run([sys.executable, "-c", provision], cwd=root / "_app", env=env, check=True)
        with (args.result / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "app.py", "--host", "127.0.0.1",
                                       "--port", "8790", "--mirror", "--no-collector"],
                                      cwd=root / "_app", env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 90
                while True:
                    if server.poll() is not None:
                        raise RuntimeError("Sandbox startup failed; see server.log")
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:8790/api/health", timeout=2):
                            break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Sandbox readiness timed out")
                        time.sleep(.25)
                print("Running full e2e_test.py on 127.0.0.1:8790", flush=True)
                with (args.result / "e2e.log").open("w", encoding="utf-8") as output:
                    test = subprocess.run([sys.executable, "e2e_test.py"], cwd=root / "_tools",
                                          env=env, stdout=output, stderr=subprocess.STDOUT, timeout=1200)
                result = root / "_tools/e2e_result.json"
                if result.is_file():
                    shutil.copy2(result, args.result / result.name)
                    report = json.loads(result.read_text(encoding="utf-8"))
                    failed = [r for r in report["results"] if not r[2]]
                    print("Checks: %d; failures: %d" % (len(report["results"]), len(failed)))
                    for area, name, _, note in failed:
                        print(area, name, note)
                else:
                    print("No result JSON; see e2e.log")
                return test.returncode
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    raise SystemExit(main())
