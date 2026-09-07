import os
import time
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from qfluentwidgets import ExpandLayout
from shiboken6 import delete

from ok import og
from ok.ui.qt.Communicate import communicate
from ok.ui.qt.tasks.TaskCard import TaskCard
from ok.ui.qt.tasks.TaskTab import TaskTab
from ok.ui.qt.tasks.LabelAndWidget import LabelAndWidget
from ok.ui.qt.widget.ExpandCardLayout import ExpandCardLayout


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

    def test_config_row_uses_a_spacer_for_extra_width(self):
        row = LabelAndWidget(
            'Local Client Notification',
            'Send notifications through local QQ or WeChat clients')
        row.resize(640, 90)
        row.show()
        QApplication.processEvents()
        self.addCleanup(row.close)

        self.assertEqual(0, row.layout.stretch(0))
        self.assertEqual(2, row.layout.count())
        self.assertEqual(1, row.layout.stretch(1))
        self.assertIsNotNone(row.layout.itemAt(1).spacerItem())
        self.assertGreater(row.layout.itemAt(1).spacerItem().geometry().width(), 0)

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

    def test_task_card_shows_experimental_status_without_blocking_enablement(self):
        task = SimpleNamespace(
            name="Experimental task",
            description="",
            config=FakeConfig(),
            default_config={},
            config_description={},
            config_type={},
            icon=None,
            instructions=None,
            is_custom=False,
            show_create_shortcut=False,
            enabled=False,
            get_device_compatibility_state=lambda: {
                'status': 'experimental',
                'level': 'MAC_BASIC',
                'missing': (),
                'reason': 'Awaiting real-game validation',
            },
        )
        card = TaskCard(task, onetime=False)
        self.addCleanup(communicate.task.disconnect, card.update_buttons)
        self.addCleanup(card.close)

        self.assertEqual('[MAC_BASIC · experimental]', card.compatibility_label.text())
        import sys
        self.assertEqual(sys.platform == 'darwin', card.compatibility_label.isHidden())
        self.assertTrue(card.enable_button.isEnabled())
        self.assertEqual('Awaiting real-game validation', card.compatibility_label.toolTip())

    def test_task_card_blocks_unsupported_or_missing_capabilities(self):
        task = SimpleNamespace(
            name="Unsupported task",
            description="",
            config=FakeConfig(),
            default_config={},
            config_description={},
            config_type={},
            icon=None,
            instructions=None,
            is_custom=False,
            show_create_shortcut=False,
            enabled=False,
            get_device_compatibility_state=lambda: {
                'status': 'unsupported',
                'level': None,
                'missing': (),
                'reason': 'Unavailable on this provider',
            },
        )
        card = TaskCard(task, onetime=False)
        self.addCleanup(communicate.task.disconnect, card.update_buttons)
        self.addCleanup(card.close)

        self.assertEqual('[unsupported]', card.compatibility_label.text())
        self.assertFalse(card.enable_button.isEnabled())

        task.get_device_compatibility_state = lambda: {
            'status': 'missing-capabilities',
            'level': 'MAC_LOCKED_GAMEPLAY',
            'missing': ('keyboard_hold', 'mouse_middle'),
            'reason': 'Provider is incomplete',
        }
        card.update_buttons(task)

        self.assertEqual(
            '[MAC_LOCKED_GAMEPLAY · missing: keyboard_hold, mouse_middle]',
            card.compatibility_label.text(),
        )
        self.assertFalse(card.enable_button.isEnabled())

    def test_destroyed_task_card_disconnects_from_task_events(self):
        task = SimpleNamespace(
            name="Disposable task",
            description="",
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
        callback = card.update_buttons
        device_callback = card._on_device_changed
        self.assertIn(callback, communicate.task._subscribers)
        self.assertIn(device_callback, communicate.adb_devices._subscribers)

        delete(card)

        self.assertNotIn(callback, communicate.task._subscribers)
        self.assertNotIn(device_callback, communicate.adb_devices._subscribers)

    def test_device_refresh_recomputes_compatibility_state(self):
        states = iter((
            {'status': 'experimental', 'level': 'MAC_BASIC', 'missing': (), 'reason': ''},
            {'status': 'unsupported', 'level': None, 'missing': (), 'reason': 'Provider changed'},
        ))
        task = SimpleNamespace(
            name="Provider-sensitive task",
            description="",
            config=FakeConfig(),
            default_config={},
            config_description={},
            config_type={},
            icon=None,
            instructions=None,
            is_custom=False,
            show_create_shortcut=False,
            enabled=False,
            get_device_compatibility_state=lambda: next(states),
        )
        card = TaskCard(task, onetime=False)
        self.addCleanup(card.close)

        self.assertEqual('[MAC_BASIC · experimental]', card.compatibility_label.text())
        communicate.adb_devices.emit(True)

        self.assertEqual('[unsupported]', card.compatibility_label.text())
        self.assertFalse(card.enable_button.isEnabled())

    def test_task_cards_use_a_nested_expand_layout(self):
        tab = TaskTab()
        self.addCleanup(tab.close)

        self.assertIsInstance(tab.taskCardLayout, ExpandLayout)
        self.assertIs(tab.taskCardLayout, tab.task_cards_view.layout())
        self.assertIsNot(tab.taskCardLayout, tab.view.layout())
        margins = tab.taskCardLayout.contentsMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (0, 0, 0, 0),
        )

    def test_task_card_uses_native_expansion_state(self):
        values = {"Long text": "A configuration value long enough to use the multiline text editor"}
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
        tab = TaskTab()
        tab.add_task_card(card)
        tab.resize(1200, 800)
        tab.show()
        QApplication.processEvents()
        self.addCleanup(tab.close)
        self.addCleanup(communicate.task.disconnect, card.update_buttons)

        header_height = card.viewportMargins().top()

        card.setExpand(True)
        QTest.qWait(300)
        QApplication.processEvents()
        self.assertTrue(card.isExpand)

        card.setExpand(False)
        QTest.qWait(300)
        QApplication.processEvents()
        self.assertFalse(card.isExpand)
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
