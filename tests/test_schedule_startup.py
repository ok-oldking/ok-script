import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from qt_helpers import wait
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
        self._assert_stalled_scheduler_does_not_block_qt_startup(False)

    def test_stalled_migration_does_not_block_qt_startup(self):
        self._assert_stalled_scheduler_does_not_block_qt_startup(True)

    def _assert_stalled_scheduler_does_not_block_qt_startup(self, block_migration):
        entered = threading.Event()
        release = threading.Event()

        def stalled_connect(*args, **kwargs):
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
                patch("ok.ui.qt.tasks.schedule_index_sync.sync_schedule_task_indexes",
                      side_effect=stalled_connect if block_migration else None) as migrate, \
                patch.object(WindowsScheduleManager, "_init_com_service",
                             side_effect=None if block_migration else stalled_connect), \
                patch.object(WindowsScheduleManager, "_query_tasks_via_schtasks", return_value=[]):
            cache.return_value.get_all.return_value = []
            tab = TestTab({"gui_title": "OK-Test"})
            try:
                self.assertTrue(entered.wait(1))
                tab.show()
                heartbeat = Mock()
                QTimer.singleShot(0, heartbeat)
                wait(30)
                heartbeat.assert_called_once()
                self.assertTrue(tab.isVisible())
                self.assertTrue(tab.refresh_thread.daemon)
                self.assertFalse(tab.isEnabled())
                original_thread = tab.refresh_thread
                tab.on_refresh()
                self.assertIs(original_thread, tab.refresh_thread)
                release.set()
                tab.refresh_thread.join(2)
                wait(30)
                self.assertFalse(tab.refreshing)
                migrate.assert_called_once_with(rewrite_argv=False)
                cache.return_value.load_cache.assert_called_once()
                self.assertTrue(tab.isEnabled())
                self.assertEqual(2, render.call_count)
                success.assert_not_called()
            finally:
                release.set()
                tab.refresh_thread.join(2)
                tab.close()
                tab.deleteLater()


class TestSchedulePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_tab(self):
        from ok import og
        from ok.util.windows_schedule import ScheduleTaskInfo
        self._og_app = getattr(og, "app", None)
        og.app = SimpleNamespace(tr=lambda text: text)
        self.addCleanup(setattr, og, "app", self._og_app)
        patches = [patch("ok.util.windows_schedule.WindowsScheduleCache"),
                   patch("ok.ui.qt.tasks.schedule_index_sync.sync_schedule_task_indexes"),
                   patch.object(WindowsScheduleManager, "_init_com_service"),
                   patch.object(WindowsScheduleManager, "query_all_tasks", return_value=[])]
        mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        mocks[0].return_value.get_all.return_value = []
        tab = ScheduleTaskTab({"gui_title": "OK-Test"})
        tab.refresh_thread.join(2)
        wait(10)
        self.addCleanup(tab.deleteLater)
        own = tab._own_app_name()
        tasks = [
            ScheduleTaskInfo("Daily", path=f"\\{own}\\Daily", enabled=True, status="Ready", trigger_type="Daily",
                             next_run_time="2026-11-04 09:00:00"),
            ScheduleTaskInfo("Other", path="\\ok-other\\Other", enabled=False, status="Disabled",
                             trigger_type="Weekly", read_only=True),
        ]
        return tab, tasks, own

    def test_groups_rows_by_app_and_reuses_rows(self):
        tab, tasks, own = self.make_tab()
        self.assertFalse(tab.empty_widget.isHidden())
        tab.render_tasks(tasks)
        self.assertEqual([own, "ok-other"], list(tab.groups))
        self.assertTrue(tab.empty_widget.isHidden())
        row = tab.groups[own].rows[tasks[0].path]
        self.assertTrue(row.enabled_switch.isChecked())
        self.assertIn("Daily", row.detail_label.text())
        other = tab.groups["ok-other"].rows[tasks[1].path]
        self.assertFalse(other.view_button.isEnabled())
        self.assertFalse(other.enabled_switch.isEnabled())

        tasks[0].enabled = False
        tab.render_tasks(tasks[:1])
        self.assertIs(row, tab.groups[own].rows[tasks[0].path])
        self.assertFalse(row.enabled_switch.isChecked())
        self.assertNotIn("ok-other", tab.groups)

    def test_switch_toggles_the_scheduled_task(self):
        tab, tasks, own = self.make_tab()
        tab.render_tasks(tasks)
        tab.schedule_manager = Mock()
        tab.groups[own].rows[tasks[0].path].enabled_switch.click()
        tab.schedule_manager.disable_task.assert_called_once_with(tasks[0].path)


if __name__ == "__main__":
    unittest.main()
