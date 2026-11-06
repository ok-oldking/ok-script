import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok.ui.qt.MainWindow import (GAME_PROCESS_POLL_INTERVAL_MS, GAME_PROCESS_UPDATE_DELAY_MS,
                                 UPDATE_CHECK_GAME_PROCESS_CONFIG, MainWindow, game_process_exists,
                                 game_starting_or_started, request_pyappify_shutdown)


class TestMainWindowStartupTab(unittest.TestCase):
    def test_idle_game_allows_update_check(self):
        self.assertFalse(game_starting_or_started(
            start_controller=SimpleNamespace(starting=False), executor=SimpleNamespace(paused=True)))

    def test_auto_start_skips_update_check(self):
        self.assertTrue(game_starting_or_started(auto_start_enabled=True))

    def test_start_task_argument_skips_update_check(self):
        self.assertTrue(game_starting_or_started(start_task_requested=True))

    def test_starting_game_skips_update_check(self):
        self.assertTrue(game_starting_or_started(start_controller=SimpleNamespace(starting=True)))

    def test_started_executor_skips_update_check(self):
        self.assertTrue(game_starting_or_started(executor=SimpleNamespace(paused=False)))

    @staticmethod
    def _window(starting, config=None):
        about_tab = SimpleNamespace(update_card=object(), check_for_updates=Mock())
        return SimpleNamespace(about_tab=about_tab, config=config or {}, game_process_poll_timer=None,
                               _game_starting_or_started=lambda: starting,
                               _poll_game_process_for_update_check=Mock())

    def test_startup_update_check_runs_immediately_when_idle(self):
        window = self._window(starting=False, config={UPDATE_CHECK_GAME_PROCESS_CONFIG: True})

        MainWindow._startup_update_check(window)

        window.about_tab.check_for_updates.assert_called_once_with(automatic=True)
        self.assertIsNone(window.game_process_poll_timer)

    def test_startup_update_check_skipped_when_game_starting_and_config_off(self):
        window = self._window(starting=True)

        MainWindow._startup_update_check(window)

        window.about_tab.check_for_updates.assert_not_called()
        self.assertIsNone(window.game_process_poll_timer)

    def test_update_only_game_exit_config_key(self):
        self.assertEqual('update_only_game_exit', UPDATE_CHECK_GAME_PROCESS_CONFIG)

    @patch("ok.ui.qt.MainWindow.QTimer")
    def test_startup_update_check_waits_for_game_exit_when_configured(self, qtimer):
        window = self._window(starting=True, config={UPDATE_CHECK_GAME_PROCESS_CONFIG: True})

        MainWindow._startup_update_check(window)

        window.about_tab.check_for_updates.assert_not_called()
        qtimer.return_value.start.assert_called_once_with(GAME_PROCESS_POLL_INTERVAL_MS)

    @patch("ok.ui.qt.MainWindow.QTimer")
    def test_game_exit_schedules_check_after_ten_seconds(self, qtimer):
        poll_timer = Mock()
        running = [True]
        window = SimpleNamespace(game_process_poll_timer=poll_timer, update_check_timer=None,
                                 _game_running_or_launching=lambda: running[0],
                                 about_tab=SimpleNamespace(check_for_updates=Mock()))
        window._deferred_update_check = lambda: MainWindow._deferred_update_check(window)

        MainWindow._poll_game_process_for_update_check(window)
        poll_timer.stop.assert_not_called()
        qtimer.assert_not_called()

        running[0] = False
        MainWindow._poll_game_process_for_update_check(window)
        poll_timer.stop.assert_called_once_with()
        self.assertEqual(10_000, GAME_PROCESS_UPDATE_DELAY_MS)
        qtimer.return_value.start.assert_called_once_with(GAME_PROCESS_UPDATE_DELAY_MS)
        qtimer.return_value.timeout.connect.call_args.args[0]()
        window.about_tab.check_for_updates.assert_called_once_with(automatic=True)

    def test_deferred_check_keeps_waiting_if_game_restarted(self):
        poll_timer = Mock()
        window = SimpleNamespace(game_process_poll_timer=poll_timer, _game_running_or_launching=lambda: True,
                                 about_tab=SimpleNamespace(check_for_updates=Mock()))

        MainWindow._deferred_update_check(window)

        window.about_tab.check_for_updates.assert_not_called()
        poll_timer.start.assert_called_once_with(GAME_PROCESS_POLL_INTERVAL_MS)

    def test_game_running_or_launching(self):
        from ok import og
        with patch.object(og, 'app', SimpleNamespace(start_controller=SimpleNamespace(starting=True))), \
                patch.object(og, 'device_manager', None):
            self.assertTrue(MainWindow._game_running_or_launching())
        with patch.object(og, 'app', SimpleNamespace(start_controller=SimpleNamespace(starting=False))), \
                patch.object(og, 'device_manager', SimpleNamespace(hwnd_window=SimpleNamespace(exists=True))):
            self.assertTrue(MainWindow._game_running_or_launching())
        with patch.object(og, 'app', None), \
                patch.object(og, 'device_manager', SimpleNamespace(
                    hwnd_window=None, get_preferred_device=lambda: {'connected': False})):
            self.assertFalse(MainWindow._game_running_or_launching())

    def test_game_process_exists(self):
        self.assertFalse(game_process_exists(None))
        self.assertTrue(game_process_exists(SimpleNamespace(hwnd_window=SimpleNamespace(exists=True))))
        self.assertTrue(game_process_exists(SimpleNamespace(
            hwnd_window=None, get_preferred_device=lambda: {'connected': True})))
        self.assertFalse(game_process_exists(SimpleNamespace(
            hwnd_window=SimpleNamespace(exists=False), get_preferred_device=lambda: {'connected': False})))
        self.assertFalse(game_process_exists(SimpleNamespace(hwnd_window=None, get_preferred_device=lambda: None)))

    @patch("ok.ui.qt.MainWindow.pyappify.kill_pyappify")
    def test_pyappify_shutdown_does_not_block_gui_thread(self, kill_pyappify):
        thread = request_pyappify_shutdown()

        self.assertTrue(thread.daemon)
        thread.join(1)
        kill_pyappify.assert_called_once_with()

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
