import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon
from ok import og
from ok.ui.qt.Communicate import communicate
from ok.ui.qt.start.StartCard import StartCard
from ok.ui.qt.tasks.TaskCard import TaskCard
from ok.util.handler import ExitEvent


class DummyTask:
    def __init__(self, name="DummyTask"):
        self.name = name
        self.description = "Dummy Task Description"
        self.default_config = {}
        self.config_description = {}
        self.config_type = {}
        self.icon = None
        self.enabled = True
        self.running = False
        self._paused = False
        self.first_run_alert = None
        self.config = {}
        self.show_create_shortcut = False
        self.tab = "onetime"

    @property
    def paused(self):
        return self._paused

    def disable(self):
        self.enabled = False

    def unpause(self):
        self._paused = False

    def pause(self):
        self._paused = True


class TestUIStateSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.orig_app = getattr(og, "app", None)
        self.orig_executor = getattr(og, "executor", None)
        self.orig_config = getattr(og, "config", None)
        self.orig_device = getattr(og, "device_manager", None)

        og.config = {"gui_icon": FluentIcon.PLAY}
        og.app = SimpleNamespace(
            title="TestApp",
            version="1.0.0",
            tr=lambda text: text,
            start_controller=SimpleNamespace(start=lambda *args: None)
        )
        self.basic_options = {"Start/Stop": "F9", "Stop Task": "F10"}
        og.device_manager = SimpleNamespace(
            get_preferred_device=lambda: {"connected": True}
        )
        og.executor = SimpleNamespace(
            basic_options=self.basic_options,
            paused=True,
            current_task=None,
            active_trigger_task_count=lambda: 0,
            can_capture=lambda: True,
            connected=lambda: True,
            lock=threading.Lock(),
            onetime_task_queue=set(),
            onetime_tasks=[],
            pause=lambda: setattr(og.executor, "paused", True),
            stop_current_task=lambda: None,
            waiting_for_task=lambda t: None
        )

    def tearDown(self):
        og.app = self.orig_app
        og.executor = self.orig_executor
        og.config = self.orig_config
        og.device_manager = self.orig_device

    def test_start_card_has_stop_button_and_rescan_guard(self):
        exit_event = ExitEvent()
        card = StartCard(exit_event)
        self.addCleanup(exit_event.set)
        self.addCleanup(card.handler.stop)
        self.addCleanup(card.close)

        self.assertEqual(card.refresh_button.text(), "Rescan Window")
        self.assertTrue(card.refresh_button.isEnabled())
        self.assertIn("F10", card.stop_button.text())

        # When task is running, refresh button is disabled and tooltip updated
        running_task = DummyTask()
        running_task.running = True
        og.executor.current_task = running_task
        card.update_status()

        self.assertFalse(card.refresh_button.isEnabled())
        self.assertTrue(card.stop_button.isEnabled())
        self.assertEqual(card.refresh_button.toolTip(), "Cannot rescan window while a task is running")

        # When task finishes
        og.executor.current_task = None
        card.update_status()
        self.assertTrue(card.refresh_button.isEnabled())

    def test_start_card_stop_clicked(self):
        exit_event = ExitEvent()
        card = StartCard(exit_event)
        self.addCleanup(exit_event.set)
        self.addCleanup(card.handler.stop)
        self.addCleanup(card.close)

        task = DummyTask()
        task.running = True
        og.executor.current_task = task
        og.executor.onetime_tasks = [task]

        card.stop_clicked()
        self.assertFalse(task.enabled)
        self.assertFalse(task.running)
        self.assertIsNone(og.executor.current_task)
        self.assertTrue(og.executor.paused)

    def test_task_card_shows_resume_when_executor_paused(self):
        task = DummyTask()
        task.enabled = True
        task.running = True
        card = TaskCard(task, onetime=True)
        card.show()
        self.addCleanup(card.close)

        # Running normally
        og.executor.paused = False
        card.update_buttons(task)
        QApplication.processEvents()
        self.assertTrue(card.start_button.isHidden())
        self.assertFalse(card.pause_button.isHidden())

        # Executor paused
        og.executor.paused = True
        communicate.executor_paused.emit(True)
        QApplication.processEvents()
        self.assertFalse(card.start_button.isHidden())
        self.assertEqual(card.start_button.text(), "Resume")
        self.assertTrue(card.pause_button.isHidden())


if __name__ == "__main__":
    unittest.main()
