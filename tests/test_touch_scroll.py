import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget

from ok.gui.util.touch_scroll import enable_touch_scrolling


class TestTouchScrollLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_deleting_scroll_area_does_not_run_filter_on_deleted_object(self):
        scroll_area = QScrollArea()
        scroll_area.setWidget(QWidget())
        enable_touch_scrolling(scroll_area)

        scroll_area.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
