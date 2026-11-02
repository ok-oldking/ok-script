import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from ok import og


def save_png(path, color="red", size=(64, 32)):
    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    image.save(path)
    return path


class TestListShots(unittest.TestCase):
    def test_pairs_original_and_boxed_newest_first(self):
        from ok.ui.qt.debug.diagnosis_page import list_shots
        with tempfile.TemporaryDirectory() as folder:
            save_png(os.path.join(folder, "2026-11-03_10-00-00-001_WGC_original.png"))
            save_png(os.path.join(folder, "2026-11-03_10-00-00-001_WGC_boxed.png"))
            newer = save_png(os.path.join(folder, "2026-11-03_10-00-05-001_ocr_original.png"))
            os.utime(newer, (time.time() + 5, time.time() + 5))
            open(os.path.join(folder, "notes.txt"), "w").close()
            shots = list_shots(folder)
            self.assertEqual(["ocr", "WGC"], [shot.title for shot in shots])
            self.assertEqual({"original", "boxed"}, set(shots[1].files))
            self.assertTrue(shots[1].path("boxed").endswith("_boxed.png"))
            self.assertTrue(shots[0].path("boxed").endswith("_original.png"))

    def test_missing_folder_is_empty(self):
        from ok.ui.qt.debug.diagnosis_page import list_shots
        self.assertEqual([], list_shots(None))
        self.assertEqual([], list_shots("does/not/exist"))


class TestDiagnosisPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._og_ok = getattr(og, "ok", None)
        # Image loads run on a worker thread and may still hold a file at cleanup.
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        og.ok = SimpleNamespace(screenshot=SimpleNamespace(screenshot_folder=self.folder.name))

    def tearDown(self):
        og.ok = self._og_ok
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.folder.cleanup()

    def make_page(self, debug=False):
        from ok.ui.qt.debug.diagnosis_page import DiagnosisPage
        page = DiagnosisPage(debug=debug)
        page.resize(1400, 800)
        page.show()
        QApplication.processEvents()
        self.addCleanup(page.deleteLater)
        return page

    def wait_for_image(self, page):
        deadline = time.time() + 5
        while page.view.image_size() is None and time.time() < deadline:
            QApplication.processEvents()
            time.sleep(0.01)

    def test_empty_folder_shows_placeholder(self):
        page = self.make_page()
        self.assertEqual(0, page.shot_list.count())
        self.assertIsNone(page.view.path)
        self.assertFalse(page.open_button.isEnabled())

    def test_shows_newest_and_toggles_boxes(self):
        save_png(os.path.join(self.folder.name, "a_original.png"), "red")
        boxed = save_png(os.path.join(self.folder.name, "a_boxed.png"), "blue")
        page = self.make_page()
        self.wait_for_image(page)
        self.assertEqual(boxed, page.view.path)
        self.assertFalse(page.kind_tabs.isHidden())
        page.kind_tabs.set_current("original")
        page.view.set_image(None)
        self.wait_for_image(page)
        self.assertTrue(page.view.path.endswith("a_original.png"))

    def test_refresh_follows_new_screenshots(self):
        save_png(os.path.join(self.folder.name, "old_original.png"))
        page = self.make_page()
        later = time.time() + 10
        new = save_png(os.path.join(self.folder.name, "new_original.png"))
        os.utime(new, (later, later))
        page.refresh()
        self.assertEqual("new", page.current_shot().title)

    def test_refresh_keeps_an_older_pick(self):
        first = save_png(os.path.join(self.folder.name, "first_original.png"))
        os.utime(first, (time.time() - 10, time.time() - 10))
        save_png(os.path.join(self.folder.name, "second_original.png"))
        page = self.make_page()
        page.shot_list.setCurrentRow(1)
        third = save_png(os.path.join(self.folder.name, "third_original.png"))
        os.utime(third, (time.time() + 10, time.time() + 10))
        page.refresh()
        self.assertEqual("first", page.current_shot().title)

    def test_select_path_after_capture(self):
        save_png(os.path.join(self.folder.name, "x_original.png"))
        path = save_png(os.path.join(self.folder.name, "y_original.png"))
        page = self.make_page()
        page.shot_list.setCurrentRow(1)
        page._on_capture_done(path)
        self.assertEqual("y", page.current_shot().title)
        self.assertTrue(page.capture_button.isEnabled())

    def test_developer_tools_only_in_debug(self):
        self.assertIsNone(self.make_page(debug=False).dev_button)
        with patch("ok.ui.qt.debug.diagnosis_page.og") as fake_og:
            fake_og.app.app.aboutToQuit.connect = lambda *_: None
            page = self.make_page(debug=True)
        actions = [action.text() for action in page.dev_menu.actions() if action.text()]
        self.assertEqual(["Reload tasks", "Generate i18n files", "Convert i18n files"], actions)


if __name__ == "__main__":
    unittest.main()
