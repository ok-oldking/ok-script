"""Explicit permission and window selection controls; never starts input."""

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget,
)
from qfluentwidgets import ComboBox as QComboBox, BodyLabel as QLabel, PushButton as QPushButton

from ok.device.services.permissions import PermissionKind
from ok.util.handler import Handler
from ok.core.events import communicate


class MacOSDevicePanel(QWidget):
    result_ready = Signal(object)
    stopped = Signal()

    def __init__(self, device_manager, exit_event, parent=None):
        super().__init__(parent)
        self.device_manager = device_manager
        self.exit_event = exit_event
        self._closed = False
        self._busy = False
        self._permissions = {}
        self.handler = Handler(exit_event, name='MacOSDevicePanel')
        self.result_ready.connect(self._apply_result, Qt.QueuedConnection)
        self.stopped.connect(self._show_stopped, Qt.QueuedConnection)
        exit_event.bind_stop(self)
        layout = QVBoxLayout(self)
        help_text = QLabel(
            'macOS 仅前台模式。请在系统设置 → 隐私与安全性中为本应用授权\n'
            '“屏幕与系统音频录制”和“辅助功能”，然后刷新。权限更改后可能需要重启本应用。'
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.permission_labels = {}
        self.permission_buttons = {}
        for kind, title in (
                (PermissionKind.SCREEN_RECORDING, '屏幕录制'),
                (PermissionKind.ACCESSIBILITY, '辅助功能')):
            row = QHBoxLayout()
            label = QLabel(f'{title}: 未检查')
            label.setWordWrap(True)
            button = QPushButton(f'请求 {title}')
            button.setEnabled(False)
            button.clicked.connect(lambda checked=False, k=kind: self.request_permission(k))
            row.addWidget(label, 1)
            row.addWidget(button)
            layout.addLayout(row)
            self.permission_labels[kind] = label
            self.permission_buttons[kind] = button
        row = QHBoxLayout()
        self.refresh_button = QPushButton('刷新权限与窗口')
        self.refresh_button.clicked.connect(self.refresh)
        self.windows = QComboBox()
        self.windows.addItem('请选择窗口（不自动选择）', None)
        self.windows.currentIndexChanged.connect(self._update_controls)
        self.bind_button = QPushButton('绑定并连接截图')
        self.bind_button.clicked.connect(self.bind_selected)
        row.addWidget(self.refresh_button)
        row.addWidget(self.windows, 1)
        row.addWidget(self.bind_button)
        layout.addLayout(row)
        self.status = QLabel('选择游戏主窗口后点击“绑定并连接截图”；任务需在任务页另行启动。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._update_controls()

    def _update_controls(self, *_):
        available = not self._closed and not self._busy and not self.exit_event.is_set()
        self.refresh_button.setEnabled(available)
        self.windows.setEnabled(available)
        self.bind_button.setEnabled(available and self.windows.currentData() is not None)
        for kind, button in self.permission_buttons.items():
            permission = self._permissions.get(kind)
            button.setEnabled(available and permission is not None and permission.can_request)

    def _submit(self, operation):
        if self._closed or self._busy or self.exit_event.is_set():
            return
        self._busy = True
        self.status.setText('正在检查，请稍候…')
        self._update_controls()

        def work():
            try:
                if self._closed or self.exit_event.is_set():
                    return
                result = operation()
            except Exception as error:
                result = {'error': str(error)}
            if not self._closed and not self.exit_event.is_set():
                self.result_ready.emit(result)

        if not self.handler.post(work):
            self._busy = False
            self.status.setText('已停止；不能执行检查。')
            self._update_controls()

    def _snapshot(self):
        permissions = self.device_manager.macos_permission_status()
        # Do not enumerate until capture permission is granted or request it implicitly.
        screen = next(p for p in permissions if p.kind == PermissionKind.SCREEN_RECORDING)
        selection = self.device_manager.discover_macos_windows() if screen.granted else None
        return {'permissions': permissions, 'selection': selection}

    @Slot()
    def refresh(self):
        self._submit(self._snapshot)

    def request_permission(self, kind):
        def request():
            permission = self.device_manager.request_macos_permission(kind)
            title = '屏幕录制' if kind == PermissionKind.SCREEN_RECORDING else '辅助功能'
            return {'permissions': self.device_manager.macos_permission_status(),
                    'message': f'{title}：请按系统提示完成授权后刷新。'}
        self._submit(request)

    @Slot()
    def bind_selected(self):
        window_id = self.windows.currentData()
        if window_id is None:
            return

        def bind():
            # Capture readiness is independent of foreground/input readiness.
            # Do not route this operation through StartController/executor.start.
            self.device_manager.prepare_macos_capture(timeout=8.0, manual_window_id=window_id)
            return {'connected': True, 'message': '窗口已绑定，截图已连接；未启动任务或输入。'}
        self._submit(bind)

    @Slot(object)
    def _apply_result(self, result):
        if self._closed or self.exit_event.is_set():
            return
        self._busy = False
        for permission in result.get('permissions', ()):
            self._permissions[permission.kind] = permission
            title = '屏幕录制' if permission.kind == PermissionKind.SCREEN_RECORDING else '辅助功能'
            state = '已授权' if permission.granted else '未授权或不可用'
            self.permission_labels[permission.kind].setText(
                f'{title}：{state}' + (f'\n{permission.detail}' if permission.detail else ''))
        if 'selection' in result:
            self.windows.clear()
            self.windows.addItem('请选择窗口（不自动选择）', None)
            selection = result['selection']
            if selection is not None:
                for candidate in selection.candidates:
                    geometry = candidate.outer_geometry
                    self.windows.addItem(
                        f'{candidate.application_name} — {candidate.title} '
                        f'[{geometry.width:g}×{geometry.height:g} 逻辑尺寸；窗口 {candidate.window_id}]',
                        userData=candidate.window_id)
            self.windows.setCurrentIndex(0)
            self.status.setText('请选择真正的主窗口；尺寸为窗口逻辑尺寸，不是内容帧分辨率。'
                                if self.windows.count() > 1 else '未发现窗口；检查屏幕录制权限、应用与窗口状态。')
        if 'message' in result:
            self.status.setText(result['message'])
        if 'error' in result:
            self.status.setText(f'检查失败：{result["error"]}')
        if result.get('connected'):
            communicate.adb_devices.emit(True)
        self._update_controls()

    def stop(self):
        """Stop panel jobs only; the application owns provider shutdown."""
        self._closed = True
        self.handler.stop()
        self.exit_event.unbind_stop(self)
        self.stopped.emit()

    @Slot()
    def _show_stopped(self):
        self.status.setText('已停止 / closed')
        self._update_controls()

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)
