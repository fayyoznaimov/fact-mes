"""Запустить все автономные test_*.py отдельными процессами. Без рабочего сервера.

python _tools/check.py
Код выхода 0 — все наборы прошли; 1 — ошибка, тайм-аут или тесты не найдены.
Сквозной e2e_test.py запускается отдельно на подготовленной песочнице.
"""
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    root = Path(__file__).resolve().parents[1]
    tests = sorted((root / "_tools").glob("test_*.py"))
    if not tests:
        print("ERROR: no test suites found", flush=True)
        return 1
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    failed = []
    started = time.monotonic()
    for test in tests:
        print("\n== " + test.name, flush=True)
        try:
            result = subprocess.run([sys.executable, str(test)], cwd=root, env=env,
                                    timeout=180, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
            print(result.stdout, end="", flush=True)
            if result.returncode:
                failed.append(test.name)
        except subprocess.TimeoutExpired:
            print("ERROR: suite exceeded 180 seconds", flush=True)
            failed.append(test.name)
        except OSError as exc:
            print("ERROR: " + str(exc), flush=True)
            failed.append(test.name)
    print("\n== %d/%d suites passed in %.1fs" %
          (len(tests) - len(failed), len(tests), time.monotonic() - started), flush=True)
    if failed:
        print("FAILED: " + ", ".join(failed), flush=True)
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
