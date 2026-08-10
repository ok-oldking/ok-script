import os
import time
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ok import og
from ok.gui.Communicate import communicate
from ok.gui.tasks.TaskCard import TaskCard
from ok.gui.tasks.TaskTab import TaskTab
from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class FakeConfig(dict):
    def get_default(self, key):
        return None

    def has_user_config(self):
        return False


class PopulatedFakeConfig(dict):
    def get_default(self, key):
        return self.get(key)

    def has_user_config(self):
        return True


class TestTaskUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.original_app = getattr(og, "app", None)
        self.original_executor = getattr(og, "executor", None)
        og.app = SimpleNamespace(tr=lambda text: text)
        og.executor = SimpleNamespace(current_task=None)

    def tearDown(self):
        og.app = self.original_app
        og.executor = self.original_executor

    def test_config_description_column_uses_available_row_width(self):
        row = LabelAndWidget(
            'Local Client Notification',
            'Send notifications through local QQ or WeChat clients')
        row.resize(640, 90)
        row.show()
        QApplication.processEvents()
        self.addCleanup(row.close)

        self.assertEqual(1, row.layout.stretch(0))
        self.assertEqual(1, row.layout.count())
        self.assertGreater(row.title_layout.geometry().width(), 400)

    def test_task_card_uses_single_line_compact_header(self):
        task = SimpleNamespace(
            name="Task name",
            description="Task description",
            config=FakeConfig(),
            default_config={},
            config_description={},
            config_type={},
            icon=None,
            instructions=None,
            is_custom=False,
            show_create_shortcut=False,
            enabled=False,
        )
        card = TaskCard(task, onetime=False)
        card.resize(800, card.height())
        card.show()
        QApplication.processEvents()
        self.addCleanup(communicate.task.disconnect, card.update_buttons)
        self.addCleanup(card.close)

        self.assertEqual(50, card.card.height())
        self.assertEqual(50, card.height())
        self.assertTrue(card.card.iconLabel.isHidden())
        self.assertIs(card.card.vBoxLayout, card.card.hBoxLayout.itemAt(1).layout())
        self.assertEqual(1, card.card.vBoxLayout.count())
        self.assertLess(card.card.titleLabel.x(), card.card.contentLabel.x())
        self.assertEqual(
            card.card.titleLabel.geometry().center().y(),
            card.card.contentLabel.geometry().center().y(),
        )

    def test_task_card_with_long_text_collapses_to_header_height(self):
        values = {f"Option {index}": False for index in range(20)}
        values["Long text"] = "A configuration value long enough to use the multiline text editor"
        task = SimpleNamespace(
            name="Long text task",
            description="Collapse regression test",
            config=PopulatedFakeConfig(values),
            default_config=values,
            config_description={},
            config_type={},
            icon=None,
            instructions=None,
            is_custom=False,
            show_create_shortcut=False,
            enabled=False,
        )
        card = TaskCard(task, onetime=False)
        card.resize(1200, card.height())
        card.show()
        QApplication.processEvents()
        self.addCleanup(communicate.task.disconnect, card.update_buttons)
        self.addCleanup(card.close)

        header_height = card.viewportMargins().top()
        card.setExpand(True)
        QTest.qWait(300)
        QApplication.processEvents()
        self.assertGreater(card.height(), header_height)

        card.setExpand(False)
        QTest.qWait(300)
        QApplication.processEvents()
        self.assertEqual(header_height, card.height())

    def test_status_panel_stays_closed_until_a_different_task_starts(self):
        first_task = SimpleNamespace(
            enabled=True,
            start_time=time.time() - 3,
            name="First task",
            info={},
        )
        second_task = SimpleNamespace(
            enabled=True,
            start_time=time.time() - 3,
            name="Second task",
            info={},
        )
        tab = TaskTab()
        tab.show()
        self.addCleanup(tab.close)

        og.executor.current_task = first_task
        tab.update_info_table()
        self.assertFalse(tab.task_info_container.isHidden())

        tab.close_info_button.click()
        tab.update_info_table()
        self.assertTrue(tab.task_info_container.isHidden())

        first_task.start_time = time.time() - 3
        tab.update_info_table()
        self.assertFalse(tab.task_info_container.isHidden())

        tab.close_info_button.click()
        og.executor.current_task = second_task
        tab.update_info_table()
        self.assertFalse(tab.task_info_container.isHidden())


if __name__ == "__main__":
    unittest.main()
