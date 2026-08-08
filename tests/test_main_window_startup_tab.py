import unittest
from types import SimpleNamespace

from ok.gui.MainWindow import MainWindow


class TestMainWindowStartupTab(unittest.TestCase):
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
