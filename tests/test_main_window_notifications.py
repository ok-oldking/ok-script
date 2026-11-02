import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok import og
from ok.ui.qt.MainWindow import MainWindow


class _NotificationHarness:
    show_notification = MainWindow.show_notification

    def __init__(self):
        self.tray = SimpleNamespace(showMessage=Mock())
        self.notification_manager = Mock()
        self.navigate_tab = Mock()

    def window(self):
        return self


class _NavigateHarness:
    navigate_tab = MainWindow.navigate_tab

    def __init__(self):
        self.run_bar = SimpleNamespace(open_popover=Mock())
        self.switch_to = Mock()
        self.tasks_page = SimpleNamespace(set_filter=Mock())
        self.schedule_tab = None
        self.about_tab = None


class TestMainWindowNotifications(unittest.TestCase):
    def test_task_name_notification_title_uses_app_translation(self):
        harness = _NotificationHarness()
        translate_task_name = Mock(return_value="Translated task name")
        original_app = getattr(og, "app", None)
        og.app = SimpleNamespace(tr=translate_task_name)
        self.addCleanup(setattr, og, "app", original_app)

        with (
            patch("ok.ui.qt.MainWindow.QCoreApplication.translate", return_value="Translated status"),
            patch("ok.ui.qt.MainWindow.show_toast") as show_toast,
        ):
            harness.show_notification("Stopped", "Original task name", tray=True)

        translate_task_name.assert_called_once_with("Original task name")
        show_toast.assert_called_once_with(
            harness, "Translated status", "Translated task name", "neutral", duration=8000)
        harness.notification_manager.notify_system.assert_called_once_with(
            "Translated task name", "Translated status", False, True)

    def test_error_notification_uses_danger_toast(self):
        harness = _NotificationHarness()
        original_app = getattr(og, "app", None)
        og.app = SimpleNamespace(tr=lambda text: text)
        self.addCleanup(setattr, og, "app", original_app)

        with patch("ok.ui.qt.MainWindow.show_toast") as show_toast:
            harness.show_notification("Failed", error=True)

        self.assertEqual("danger", show_toast.call_args.args[3])
        self.assertIsNone(show_toast.call_args.args[2])

    def test_start_tab_requests_open_the_connection_popover(self):
        harness = _NavigateHarness()

        harness.navigate_tab("start")
        harness.navigate_tab("trigger")

        harness.run_bar.open_popover.assert_called_once_with()
        harness.switch_to.assert_called_once_with(harness.tasks_page)
        harness.tasks_page.set_filter.assert_called_once_with("trigger")


if __name__ == "__main__":
    unittest.main()
