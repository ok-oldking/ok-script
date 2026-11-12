import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok.ui.qt.MainWindow import MainWindow, game_starting_or_started, request_pyappify_shutdown


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
    def _window(starting):
        about_tab = SimpleNamespace(update_card=object(), check_for_updates=Mock())
        return SimpleNamespace(about_tab=about_tab, _game_starting_or_started=lambda: starting)

    def test_startup_update_check_runs_immediately_when_idle(self):
        window = self._window(starting=False)

        MainWindow._startup_update_check(window)

        window.about_tab.check_for_updates.assert_called_once_with(automatic=True)

    def test_startup_update_check_skipped_when_game_starting(self):
        window = self._window(starting=True)

        MainWindow._startup_update_check(window)

        window.about_tab.check_for_updates.assert_not_called()

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
