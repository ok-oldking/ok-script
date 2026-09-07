from types import SimpleNamespace
from unittest.mock import Mock

from ok.ui.qt.widget.StartLoadingDialog import StartLoadingDialog
from ok.ui.qt.MainWindow import MainWindow
from ok import og


def test_actual_preparation_seconds_are_displayed():
    dialog = SimpleNamespace(loading_label=Mock())
    StartLoadingDialog.set_macos_status(dialog, 'preparation', 8)
    assert '8 秒' in dialog.loading_label.setText.call_args.args[0]
    assert '30' not in dialog.loading_label.setText.call_args.args[0]
    StartLoadingDialog.set_macos_status(dialog, 'preparation', 7)
    assert '7 秒' in dialog.loading_label.setText.call_args.args[0]


def test_updates_do_not_reshow_or_activate_dialog(monkeypatch):
    token = object()
    monkeypatch.setattr(og, 'app', SimpleNamespace(start_controller=SimpleNamespace(_start_cancel=token)))
    dialog = Mock()
    dialog.isVisible.return_value = True
    window = SimpleNamespace(emulator_starting_dialog=dialog)
    for phase, seconds in [('foreground', 29), ('preparation', 8), ('preparation', 7)]:
        MainWindow.macos_start_status(window, token, phase, seconds)
    dialog.show.assert_not_called()
    dialog.activateWindow.assert_not_called()
    MainWindow.macos_start_status(window, object(), 'done', 0)
    dialog.close.assert_not_called()
    MainWindow.macos_start_status(window, token, 'done', 0)
    dialog.close.assert_called_once()
