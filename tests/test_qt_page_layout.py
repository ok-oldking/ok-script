import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ok import og
from ok.ui.qt.common.design_system import DesignToken
from ok.ui.qt.tasks.EditTaskTab import EditTaskTab
from ok.ui.qt.widget.Tab import Tab


class TestQtPageLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def assert_page_layout(self, layout):
        margins = layout.contentsMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (DesignToken.PAGE_MARGIN,) * 4,
        )
        self.assertEqual(layout.spacing(), DesignToken.PAGE_SPACING)

    def test_standard_tab_uses_uniform_page_margins(self):
        tab = Tab()
        self.assert_page_layout(tab.vBoxLayout)
        tab.deleteLater()

    def test_script_tab_uses_standard_page_layout(self):
        old_task_manager = getattr(og, "task_manager", None)
        og.task_manager = SimpleNamespace(task_folder="", task_map={}, task_errors={})
        try:
            tab = EditTaskTab()
            self.assert_page_layout(tab.layout)
            tab.deleteLater()
        finally:
            og.task_manager = old_task_manager


if __name__ == "__main__":
    unittest.main()
