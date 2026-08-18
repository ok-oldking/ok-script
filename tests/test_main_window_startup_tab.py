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

    def test_prefers_default_onetime_tab(self):
        onetime_tab = object()
        window = SimpleNamespace(
            onetime_tab=onetime_tab,
            grouped_task_tabs=[object()],
            imported_tabs={"tasks.okscript": object()},
            trigger_tab=object(),
        )

        self.assertIs(onetime_tab, MainWindow.startup_task_tab(window))

    def test_prefers_onetime_tabs_over_trigger_tab(self):
        trigger_tab = object()
        grouped_tab = object()
        window = SimpleNamespace(
            onetime_tab=None,
            grouped_task_tabs=[grouped_tab],
            imported_tabs={},
            trigger_tab=trigger_tab,
        )

        self.assertIs(grouped_tab, MainWindow.startup_task_tab(window))

    def test_uses_imported_onetime_tab_before_trigger_tab(self):
        trigger_tab = object()
        imported_tab = object()
        window = SimpleNamespace(
            onetime_tab=None,
            grouped_task_tabs=[],
            imported_tabs={"tasks.okscript": imported_tab},
            trigger_tab=trigger_tab,
        )

        self.assertIs(imported_tab, MainWindow.startup_task_tab(window))

    def test_falls_back_to_trigger_tab_without_onetime_tabs(self):
        trigger_tab = object()
        window = SimpleNamespace(
            onetime_tab=None,
            grouped_task_tabs=[],
            imported_tabs={},
            trigger_tab=trigger_tab,
        )

        self.assertIs(trigger_tab, MainWindow.startup_task_tab(window))


if __name__ == "__main__":
    unittest.main()
