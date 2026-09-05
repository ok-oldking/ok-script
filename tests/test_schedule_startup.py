import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ok.ui.qt.tasks.ScheduleTaskTab import ScheduleTaskTab
from ok.util.windows_schedule import WindowsScheduleManager


class TestScheduleStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_constructor_and_cached_reads_do_not_connect_to_scheduler(self):
        with patch("ok.util.windows_schedule.WindowsScheduleCache") as cache, \
                patch.object(WindowsScheduleManager, "_init_com_service") as connect:
            manager = WindowsScheduleManager({"gui_title": "OK-Test"})
            manager.query_all_tasks()
            connect.assert_not_called()
            cache.return_value.get_all.assert_called_once()

    def test_com_is_created_and_released_on_query_thread_even_on_failure(self):
        calls = []
        com = SimpleNamespace(
            CoInitialize=lambda: calls.append(("init", threading.get_ident())),
            CoUninitialize=lambda: calls.append(("uninit", threading.get_ident())),
        )
        with patch("ok.util.windows_schedule.WindowsScheduleCache"), \
                patch.dict("sys.modules", {"pythoncom": com}):
            manager = WindowsScheduleManager({"gui_title": "OK-Test"})

            def connect():
                calls.append(("connect", threading.get_ident()))
                manager.SCHEDULE_SERVICE = object()

            with patch.object(manager, "_init_com_service", side_effect=connect), \
                    patch.object(manager, "_query_tasks_via_com", side_effect=RuntimeError("failed")):
                thread = threading.Thread(target=lambda: manager.query_all_tasks(force_sync=True))
                thread.start()
                thread.join(2)
                self.assertFalse(thread.is_alive())
            self.assertEqual(["init", "connect", "uninit"], [name for name, _ in calls])
            self.assertTrue(all(ident == thread.ident for _, ident in calls))
            self.assertIsNone(manager.SCHEDULE_SERVICE)
            self.assertIsNone(manager.SCHEDULE_FOLDER)

    def test_stalled_scheduler_does_not_block_qt_startup(self):
        entered = threading.Event()
        release = threading.Event()

        def stalled_connect():
            entered.set()
            release.wait(5)

        render = Mock()
        success = Mock()

        class TestTab(ScheduleTaskTab):
            def render_tasks(self, tasks):
                render(tasks)

            def show_success(self, message):
                success(message)

        with patch("ok.util.windows_schedule.WindowsScheduleCache") as cache, \
                patch.object(WindowsScheduleManager, "_init_com_service", side_effect=stalled_connect), \
                patch.object(WindowsScheduleManager, "_query_tasks_via_schtasks", return_value=[]):
            cache.return_value.get_all.return_value = []
            tab = TestTab({"gui_title": "OK-Test"})
            try:
                self.assertTrue(entered.wait(1))
                tab.show()
                heartbeat = Mock()
                QTimer.singleShot(0, heartbeat)
                QTest.qWait(30)
                heartbeat.assert_called_once()
                self.assertTrue(tab.isVisible())
                self.assertTrue(tab.refresh_thread.daemon)
                self.assertFalse(tab.isEnabled())
                original_thread = tab.refresh_thread
                tab.on_refresh()
                self.assertIs(original_thread, tab.refresh_thread)
                release.set()
                tab.refresh_thread.join(2)
                QTest.qWait(30)
                self.assertFalse(tab.refreshing)
                self.assertTrue(tab.isEnabled())
                self.assertEqual(2, render.call_count)
                success.assert_not_called()
            finally:
                release.set()
                tab.refresh_thread.join(2)
                tab.close()
                tab.deleteLater()


if __name__ == "__main__":
    unittest.main()
