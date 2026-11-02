import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from ok.util.config import Config


def log_line(i, level="INFO"):
    return f"2026-11-03 10:00:{i % 60:02d},{i % 1000:03d} {level} ok.module: message number {i}"


class TestLogBuffer(unittest.TestCase):
    def test_continuation_lines_follow_their_record(self):
        from ok.ui.qt.shell.log_page import LogBuffer, LEVELS
        buffer = LogBuffer(100)
        buffer.append(log_line(1))
        buffer.append(log_line(2, "ERROR"))
        buffer.append("Traceback (most recent call last):")
        buffer.append('  File "x.py", line 1')
        buffer.append(log_line(3))
        text = buffer.filtered_text(LEVELS["ERROR"], "")
        self.assertEqual([log_line(2, "ERROR"), "Traceback (most recent call last):", '  File "x.py", line 1'],
                         text.split("\n"))
        # A text match inside a traceback keeps the whole record.
        self.assertEqual(3, len(buffer.filtered_text(0, "x.py").split("\n")))

    def test_keeps_only_max_lines(self):
        from ok.ui.qt.shell.log_page import LogBuffer
        buffer = LogBuffer(10)
        for i in range(25):
            buffer.append(log_line(i))
        self.assertEqual(10, len(buffer))
        self.assertTrue(buffer.filtered_text(0, "").endswith("message number 24"))


class TestLogPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self._config_folder = Config.config_folder
        Config.config_folder = self._folder.name
        self.log_file = Path(self._folder.name) / "ok-script.log"

    def tearDown(self):
        Config.config_folder = self._config_folder
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self._folder.cleanup()

    def write(self, lines, mode="a"):
        with self.log_file.open(mode, encoding="utf-8") as file:
            file.write("".join(line + "\n" for line in lines))

    def make_page(self):
        from ok.ui.qt.shell.log_page import LogPage
        page = LogPage(self.log_file)
        page.resize(1200, 700)
        page.show()
        QApplication.processEvents()
        self.addCleanup(page.deleteLater)
        return page

    def test_loads_tail_and_appends(self):
        self.write([log_line(i) for i in range(5)], "w")
        page = self.make_page()
        self.assertEqual(5, page.view.blockCount())
        self.write([log_line(5, "WARNING")])
        page.poll()
        self.assertEqual(6, page.view.blockCount())
        self.assertIn("message number 5", page.view.document().lastBlock().text())

    def test_partial_lines_wait_for_their_newline(self):
        self.write([log_line(0)], "w")
        page = self.make_page()
        with self.log_file.open("a", encoding="utf-8") as file:
            file.write("2026-11-03 10:00:01,000 INFO half")
        page.poll()
        self.assertEqual(1, page.view.blockCount())
        with self.log_file.open("a", encoding="utf-8") as file:
            file.write(" done\n")
        page.poll()
        self.assertEqual("2026-11-03 10:00:01,000 INFO half done", page.view.document().lastBlock().text())

    def test_level_filter_applies_to_new_lines(self):
        self.write([log_line(0), log_line(1, "ERROR")], "w")
        page = self.make_page()
        page.level_combo.setCurrentText("ERROR")
        page._apply_filter()
        self.assertEqual(1, page.view.blockCount())
        self.write([log_line(2), log_line(3, "CRITICAL")])
        page.poll()
        self.assertEqual(2, page.view.blockCount())
        self.assertEqual("ERROR", Config("log_window", {"level": "ALL", "filter_text": ""})["level"])

    def test_rotation_restarts_from_the_new_file(self):
        self.write([log_line(i) for i in range(5)], "w")
        page = self.make_page()
        self.write([log_line(100)], "w")
        page.poll()
        self.assertIn("message number 100", page.view.document().lastBlock().text())

    def test_paused_page_does_not_read(self):
        self.write([log_line(0)], "w")
        page = self.make_page()
        page.toggle_pause()
        self.write([log_line(1)])
        page.poll()
        self.assertEqual(1, page.view.blockCount())
        page.toggle_pause()
        self.assertEqual(2, page.view.blockCount())

    def test_large_log_stays_fast(self):
        from ok.ui.qt.shell.log_page import MAX_LINES
        levels = ("INFO", "DEBUG", "WARNING", "ERROR")
        self.write([log_line(i, levels[i % 4]) for i in range(MAX_LINES)], "w")
        start = time.perf_counter()
        page = self.make_page()
        load = time.perf_counter() - start
        self.assertEqual(MAX_LINES, page.view.blockCount())

        start = time.perf_counter()
        page.level_combo.setCurrentText("ERROR")
        page._apply_filter()
        QApplication.processEvents()
        refilter = time.perf_counter() - start

        page.level_combo.setCurrentIndex(0)
        page._apply_filter()
        QApplication.processEvents()
        self.write([log_line(i) for i in range(500)])
        start = time.perf_counter()
        page.poll()
        QApplication.processEvents()
        append = time.perf_counter() - start
        self.assertEqual(MAX_LINES, page.view.blockCount())
        print(f"\nlog page: load {load * 1000:.0f}ms, refilter {refilter * 1000:.0f}ms, "
              f"append 500 {append * 1000:.0f}ms")
        self.assertLess(load, 3)
        self.assertLess(refilter, 1.5)
        self.assertLess(append, 0.3)


if __name__ == "__main__":
    unittest.main()
