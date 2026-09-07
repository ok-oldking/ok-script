import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from ok.device.services.permissions import PermissionKind, PermissionState, PermissionStatus
from ok.ui.qt.MacOSDevicePanel import MacOSDevicePanel
from ok.util.handler import ExitEvent


@pytest.fixture
def panel():
    app = QApplication.instance() or QApplication([])
    permissions = tuple(PermissionStatus(kind, PermissionState.GRANTED, False, 'System Settings')
                        for kind in PermissionKind)
    candidate = SimpleNamespace(application_name='Example', title='Main', window_id=42,
                                outer_geometry=SimpleNamespace(width=640, height=400))
    selection = SimpleNamespace(candidates=(candidate,), selected=candidate)
    manager = Mock()
    manager.macos_permission_status.return_value = permissions
    manager.discover_macos_windows.return_value = selection
    manager.bind_macos_window.return_value = selection
    event = ExitEvent()
    widget = MacOSDevicePanel(manager, event)
    yield widget, manager, app
    widget.stop()
    event.set()
    widget.handler.join(2)
    widget.close()
    app.processEvents()


def finish(widget, app):
    deadline = time.monotonic() + 2
    while widget._busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert not widget._busy


def test_refresh_background_does_not_select_bind_or_request(panel):
    widget, manager, app = panel
    caller_threads = []
    original = manager.macos_permission_status.return_value
    manager.macos_permission_status.side_effect = lambda: (
        caller_threads.append(threading.get_ident()) or original)
    widget.refresh()
    finish(widget, app)
    assert caller_threads == [widget.handler.thread.ident]
    assert caller_threads[0] != threading.get_ident()
    assert widget.windows.currentData() is None
    assert '640×400 逻辑尺寸' in widget.windows.itemText(1)
    assert not widget.bind_button.isEnabled()
    manager.bind_macos_window.assert_not_called()
    manager.request_macos_permission.assert_not_called()


def test_explicit_selection_prepares_provider_without_input(panel):
    widget, manager, app = panel
    widget.refresh()
    finish(widget, app)
    widget.windows.setCurrentIndex(1)
    widget.bind_selected()
    finish(widget, app)
    manager.prepare_macos_capture.assert_called_once_with(timeout=8.0, manual_window_id=42)
    manager.bind_macos_window.assert_not_called()
    manager.executor.start.assert_not_called()
    manager.interaction.on_run.assert_not_called()
    assert '未启动任务或输入' in widget.status.text()


def test_capture_connection_failure_does_not_report_success(panel):
    widget, manager, app = panel
    widget.refresh()
    finish(widget, app)
    widget.windows.setCurrentIndex(1)
    manager.prepare_macos_capture.side_effect = RuntimeError('capture unavailable')
    widget.bind_selected()
    finish(widget, app)
    assert 'capture unavailable' in widget.status.text()
    assert '截图已连接' not in widget.status.text()
    manager.interaction.on_run.assert_not_called()
    manager.executor.start.assert_not_called()


def test_connection_notifies_task_cards_without_manual_refresh(panel):
    from ok.core.events import communicate
    widget, manager, app = panel
    widget.refresh()
    finish(widget, app)
    widget.windows.setCurrentIndex(1)
    changed = Mock()
    with communicate.adb_devices.subscribed(changed):
        widget.bind_selected()
        finish(widget, app)
    changed.assert_called_once_with(True)


def test_missing_permission_does_not_enumerate_or_prompt(panel):
    widget, manager, app = panel
    manager.macos_permission_status.return_value = tuple(
        PermissionStatus(kind, PermissionState.REQUIRED, True, 'System Settings')
        for kind in PermissionKind)
    widget.refresh()
    finish(widget, app)
    manager.discover_macos_windows.assert_not_called()
    manager.request_macos_permission.assert_not_called()
    assert widget.permission_buttons[PermissionKind.SCREEN_RECORDING].isEnabled()
    manager.request_macos_permission.return_value = manager.macos_permission_status.return_value[0]
    widget.permission_buttons[PermissionKind.SCREEN_RECORDING].click()
    finish(widget, app)
    manager.request_macos_permission.assert_called_once_with(PermissionKind.SCREEN_RECORDING)


def test_bind_failure_is_actionable_and_does_not_prepare(panel):
    widget, manager, app = panel
    widget.refresh()
    finish(widget, app)
    widget.windows.setCurrentIndex(1)
    manager.prepare_macos_capture.side_effect = RuntimeError('MAC_TARGET_EXITED')
    widget.bind_selected()
    finish(widget, app)
    assert 'MAC_TARGET_EXITED' in widget.status.text()
    manager.prepare_macos_device.assert_not_called()


def test_stop_rejects_queries_and_queued_ui_results(panel):
    widget, manager, app = panel
    widget.stop()
    app.processEvents()
    widget.refresh()
    widget._apply_result({'message': 'stale'})
    assert widget.status.text() == '已停止 / closed'
    assert not widget.refresh_button.isEnabled()
    manager.macos_permission_status.assert_not_called()
