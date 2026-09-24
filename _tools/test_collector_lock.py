"""Сборщик один: второй процесс не захватывает блокировку, даже если отметка
«я жив» пропала или устарела (медленный проход FACT)."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_app")

CLAIM = textwrap.dedent("""
    import os, sys, time
    sys.path.insert(0, %r)
    import storage, collector, livestate
    storage.RUN_DIR = sys.argv[1]
    collector.STATUS_FILE = os.path.join(sys.argv[1], "collector.json")
    c = collector.Collector(livestate.MirrorSource(sys.argv[1]))
    ok = c.claim()
    if ok and os.path.exists(collector.STATUS_FILE):
        os.remove(collector.STATUS_FILE)      # отметки «я жив» больше нет
    print("claimed" if ok else "refused", flush=True)
    time.sleep(float(sys.argv[2]))
""" % APP)


class CollectorLockTests(unittest.TestCase):
    def test_second_process_refused_while_first_alive(self):
        with tempfile.TemporaryDirectory() as run:
            first = subprocess.Popen([sys.executable, "-c", CLAIM, run, "5"],
                                     stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(first.stdout.readline().strip(), "claimed")
                second = subprocess.run([sys.executable, "-c", CLAIM, run, "0"],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(second.stdout.strip(), "refused")
            finally:
                first.kill()
                first.wait()
                first.stdout.close()
            third = subprocess.run([sys.executable, "-c", CLAIM, run, "0"],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(third.stdout.strip(), "claimed")   # первый умер — блокировка свободна


if __name__ == "__main__":
    unittest.main()
