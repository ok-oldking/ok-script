import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from ok import og
from ok.ui.qt.tasks.EditTaskTab import EditTaskTab
from ok.ui.qt.widget.Tab import PAGE_MARGINS as TAB_MARGINS, PAGE_SPACING as TAB_SPACING, Tab


class TestQtPageLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def assert_layout(self, layout, margins, spacing):
        actual = layout.contentsMargins()
        self.assertEqual(margins, (actual.left(), actual.top(), actual.right(), actual.bottom()))
        self.assertEqual(spacing, layout.spacing())

    def test_custom_tab_base_builds_titled_cards(self):
        tab = Tab()
        self.assert_layout(tab.vBoxLayout, TAB_MARGINS, TAB_SPACING)
        card = tab.add_card("Section", QLabel("content"))
        self.assertEqual("Section", card.titleLabel.text())
        self.assertIs(card.card, card.widget.parentWidget())
        tab.show_loading_dialog()
        self.assertTrue(tab.loading_dialog.isVisible() or not tab.isVisible())
        tab.hide_loading_dialog()
        self.assertFalse(tab.loading_dialog.isVisible())
        tab.deleteLater()

    def test_script_tab_uses_kit_page_layout(self):
        from ok.ui.qt.tasks.EditTaskTab import PAGE_MARGINS, PAGE_SPACING
        old_task_manager = getattr(og, "task_manager", None)
        og.task_manager = SimpleNamespace(task_folder="", task_map={}, task_errors={})
        try:
            tab = EditTaskTab()
            self.assert_layout(tab.layout(), PAGE_MARGINS, PAGE_SPACING)
            self.assertFalse(tab.empty_widget.isHidden())
            tab.deleteLater()
        finally:
            og.task_manager = old_task_manager


if __name__ == "__main__":
    unittest.main()
