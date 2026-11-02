import unittest
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok.ui.qt.MainWindow import MainWindow, request_pyappify_shutdown, update_check_delay_ms


class TestMainWindowStartupTab(unittest.TestCase):
    def test_pyappify_test_mode_checks_after_ten_seconds(self):
        with patch.dict(os.environ, {"PYAPPIFY_PYTHON_TEST": ""}):
            self.assertEqual(10_000, update_check_delay_ms())

    def test_normal_update_check_waits_thirty_seconds(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PYAPPIFY_PYTHON_TEST", None)
            self.assertEqual(30_000, update_check_delay_ms())

    @patch("ok.ui.qt.MainWindow.pyappify.kill_pyappify")
    def test_pyappify_shutdown_does_not_block_gui_thread(self, kill_pyappify):
        thread = request_pyappify_shutdown()

        self.assertTrue(thread.daemon)
        thread.join(1)
        kill_pyappify.assert_called_once_with()

    def test_started_check_cancels_pending_timer(self):
        timer = SimpleNamespace(isActive=lambda: True, stop=Mock())
        window = SimpleNamespace(update_check_timer=timer)

        MainWindow._cancel_scheduled_update_check(window)

        timer.stop.assert_called_once_with()

    def test_prefers_the_tasks_page(self):
        tasks_page = object()
        window = SimpleNamespace(tasks_page=tasks_page, imported_tabs={"tasks.okscript": object()})

        self.assertIs(tasks_page, MainWindow.startup_task_tab(window))

    def test_uses_imported_task_tab_without_tasks_page(self):
        imported_tab = object()
        window = SimpleNamespace(tasks_page=None, imported_tabs={"tasks.okscript": imported_tab})

        self.assertIs(imported_tab, MainWindow.startup_task_tab(window))

    def test_falls_back_to_imported_custom_page(self):
        page = object()
        window = SimpleNamespace(tasks_page=None, imported_tabs={},
                                 _imported_tab_controller=SimpleNamespace(custom_tabs={"demo": [page]}))

        self.assertIs(page, MainWindow.startup_task_tab(window))

    def test_nothing_to_start_on(self):
        window = SimpleNamespace(tasks_page=None, imported_tabs={})

        self.assertIsNone(MainWindow.startup_task_tab(window))


if __name__ == "__main__":
    unittest.main()
