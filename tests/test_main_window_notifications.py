import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok import og
from ok.gui.MainWindow import MainWindow


class _NotificationHarness:
    show_notification = MainWindow.show_notification

    def __init__(self):
        self.tray = SimpleNamespace(showMessage=Mock())
        self.navigate_tab = Mock()

    def window(self):
        return self


class _ExecutorPausedHarness:
    executor_paused = MainWindow.executor_paused

    def __init__(self):
        self.stackedWidget = SimpleNamespace(currentIndex=Mock(return_value=1))
        self.switchTo = Mock()
        self.show_notification = Mock()

    def startup_task_tab(self):
        return None

    def tr(self, message):
        return message


class TestMainWindowNotifications(unittest.TestCase):
    def test_task_name_notification_title_uses_app_translation(self):
        harness = _NotificationHarness()
        translate_task_name = Mock(return_value="Translated task name")
        original_app = getattr(og, "app", None)
        og.app = SimpleNamespace(tr=translate_task_name)
        self.addCleanup(setattr, og, "app", original_app)

        with (
            patch("ok.gui.MainWindow.QCoreApplication.translate", return_value="Translated status"),
            patch("ok.gui.util.app.show_info_bar") as show_info_bar,
        ):
            harness.show_notification("Stopped", "Original task name", tray=True)

        translate_task_name.assert_called_once_with("Original task name")
        show_info_bar.assert_called_once_with(
            harness,
            "Translated status",
            "Translated task name",
            False,
        )
        self.assertEqual("Translated task name", harness.tray.showMessage.call_args.args[0])

    def test_task_lifecycle_notifications_do_not_use_the_tray(self):
        harness = _ExecutorPausedHarness()

        harness.executor_paused(False)
        harness.executor_paused(True)

        self.assertEqual(
            [
                (("Start Success.",), {"tray": False}),
                (("Pause Success.",), {"tray": False}),
            ],
            harness.show_notification.call_args_list,
        )


if __name__ == "__main__":
    unittest.main()
