"""The game connection popover opened from the run bar.

It replaces the old Capture page: pick the target window, refresh, take a
screenshot, choose the capture and interaction methods, and reach the log
and folder tools.
"""

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QMenu, QVBoxLayout, QWidget

from ok.core.capture_labels import capture_method_label
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.feedback import Pill
from ok.ui.qt.kit.inputs import ComboBox
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.options import OptionGroup
from ok.ui.qt.kit.popover import Popover
from ok.ui.qt.kit.switch import Switch
from ok.ui.qt.shell import diagnostics
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

POPOVER_WIDTH = 520


def _t(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


def _method_name(method) -> str:
    return method.__name__ if isinstance(method, type) else str(method)


def split_label(label: str):
    """Split a translated "Name - description" label into its two parts."""

    title, sep, description = label.partition(" - ")
    return (title.strip(), description.strip()) if sep else (label, "")


def device_label(device: dict) -> str:
    if device['device'] == "windows":
        kind = _t("StartTab", "PC")
    elif device.get('emulator'):
        kind = _t("StartTab", "Emulator")
    elif device['device'] == "browser":
        kind = _t("StartTab", "Browser")
    else:
        kind = _t("StartTab", "Android")
    parts = [kind, str(device.get('nick') or ''), str(device.get('address') or '')]
    return " · ".join(part for part in parts if part)


def device_details(device: dict) -> str:
    """Resolution and executable(s) of a device, e.g. "1920x1080 · Client.exe"."""

    exe = device.get('exe') or device.get('address') or ''
    if isinstance(exe, (list, tuple)):
        exe = ", ".join(str(item) for item in exe)
    parts = [str(device.get('resolution') or ''), str(exe)]
    return " · ".join(part for part in parts if part)


def capture_options(device_manager, device: dict):
    """``(options, current_index, method_names)`` for the device's capture methods."""

    if device['device'] == "windows":
        methods = device_manager.windows_capture_config.get('capture_method', [])
        if not methods:
            return [(_t("SelectCaptureListView", "Game Window"), "", None)], 0, [None]
        names = [_method_name(method) for method in methods]
        options = [split_label(_t("SelectCaptureListView", capture_method_label(name))) for name in names]
        current = device_manager.get_preferred_capture()
        index = names.index(current) if current in names else 0
        return [(title, description, None) for title, description in options], index, names
    if device['device'] == "browser":
        return [(_t("SelectCaptureListView", "Browser Capture"), "", None)], 0, ["browser"]
    adb = split_label(_t("SelectCaptureListView", "ADB(Supports Background, Slow, High Compatibility, High Latency)"))
    options, names = [(adb[0], adb[1], None)], ["adb"]
    emulator = device.get('emulator')
    if emulator:
        from ok.alas.emulator_windows import Emulator
        if emulator.type == Emulator.MuMuPlayer12 and "MuMuPlayerGlobal" not in emulator.path:
            options.append((_t("SelectCaptureListView", "Ipc (MuMuPlayer12 version >= 4.0)"), "", None))
            names.append("ipc")
            return options, 0 if device_manager.config.get('capture') == 'adb' else 1, names
    return options, 0, names


def interaction_options(device_manager, device: dict):
    """``(options, current_index, method_names)`` for the device's interaction methods."""

    if device['device'] == "windows":
        methods = device_manager.windows_capture_config.get('interaction', [])
        if isinstance(methods, str):
            methods = [methods]
        if not methods:
            return [(_t("SelectInteractionListView", "WindowsInteraction"), "", None)], 0, [None]
        names = [_method_name(method) for method in methods]
        options = [split_label(_t("SelectInteractionListView", name)) for name in names]
        current = device_manager.config.get("interaction")
        index = names.index(current) if current in names else 0
        return [(title, description, None) for title, description in options], index, names
    if device['device'] == "adb":
        return [(_t("SelectInteractionListView", "ADBInteraction"), "", None)], 0, [None]
    if device['device'] == "browser":
        return [(_t("SelectInteractionListView", "BrowserInteraction"), "", None)], 0, [None]
    return [(_t("SelectInteractionListView", "Default Interaction"), "", None)], 0, [None]


class ConnectionPopover(Popover):
    """Target window, capture and interaction settings plus diagnostics."""

    changed = Signal()
    capture_finished = Signal(object)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedWidth(POPOVER_WIDTH)
        self._devices = []
        self._capture_names = []
        self._interaction_names = []

        self.status_pill = Pill("", "neutral")
        close_button = Button(icon="x", variant="subtle", size="small")
        close_button.clicked.connect(self.close_popover)
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(Label(self.tr("Game window"), "subtitle"))
        header.addWidget(self.status_pill)
        header.addStretch(1)
        header.addWidget(close_button)

        self.window_combo = ComboBox()
        self.window_combo.activated.connect(self._on_window_picked)
        self.refresh_button = Button(icon="refresh")
        self.refresh_button.setToolTip(_t("StartTab", "Refresh"))
        self.refresh_button.clicked.connect(self._refresh_devices)
        pick_row = QHBoxLayout()
        pick_row.setSpacing(8)
        pick_row.addWidget(self.window_combo, 1)
        pick_row.addWidget(self.refresh_button)
        self.details_label = Label("", "caption")
        self.screenshot_button = Button(_t("StartCard", "Capture"), "camera", size="small")
        self.screenshot_button.clicked.connect(self._capture)
        self.capture_finished.connect(self._on_capture_finished)

        self.capture_group = OptionGroup()
        self.capture_group.selected.connect(self._on_capture_picked)
        self.interaction_group = OptionGroup()
        self.interaction_group.selected.connect(self._on_interaction_picked)

        export_button = Button(_t("StartTab", "Export Logs"), "export", "subtle", "small")
        export_button.clicked.connect(diagnostics.export_logs)
        folders_button = Button(self.tr("Open folder"), "folder", "subtle", "small")
        folders_menu = QMenu(folders_button)
        folders_menu.addAction(_t("StartTab", "Install Folder"), diagnostics.open_install_folder)
        folders_menu.addAction(_t("StartTab", "Screenshot Folder"), diagnostics.open_screenshot_folder)
        folders_menu.addAction(_t("StartTab", "Log Folder"), diagnostics.open_log_folder)
        folders_button.clicked.connect(lambda: folders_menu.exec(folders_button.mapToGlobal(
            folders_button.rect().bottomLeft())))
        log_button = Button(_t("StartTab", "View Log"), "file", "subtle", "small")
        log_button.clicked.connect(self._view_log)
        ocr_button = Button("OCR", "text", "subtle", "small")
        ocr_button.clicked.connect(diagnostics.ocr_log)
        tools = QHBoxLayout()
        tools.setSpacing(2)
        for button in (export_button, folders_button, log_button, ocr_button):
            tools.addWidget(button)
        tools.addStretch(1)

        self.boxes_switch = Switch()
        self.boxes_switch.toggled.connect(self._on_boxes_toggled)
        boxes_row = QHBoxLayout()
        boxes_row.addWidget(Label(_t("StartTab", "Enable Boxes"), "secondary"))
        boxes_row.addStretch(1)
        boxes_row.addWidget(self.boxes_switch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addLayout(pick_row)
        detail_row = QHBoxLayout()
        detail_row.addWidget(self.details_label, 1)
        detail_row.addWidget(self.screenshot_button)
        layout.addLayout(detail_row)
        layout.addSpacing(4)
        layout.addWidget(Label(_t("StartTab", "Capture Method"), "section"))
        layout.addWidget(self.capture_group)
        layout.addSpacing(4)
        layout.addWidget(Label(_t("StartTab", "Choose Interaction"), "section"))
        layout.addWidget(self.interaction_group)
        layout.addSpacing(4)
        layout.addLayout(boxes_row)
        layout.addLayout(tools)

    # --- state ----------------------------------------------------------------

    def refresh(self, finished: bool = True) -> None:
        from ok import og
        device_manager = og.device_manager
        self._devices = list(device_manager.get_devices())
        preferred = device_manager.config.get("preferred")
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        current = -1
        for row, device in enumerate(self._devices):
            self.window_combo.addItem(device_label(device))
            self.window_combo.setItemData(row, device_label(device), Qt.ItemDataRole.ToolTipRole)
            if device.get('imei') == preferred:
                current = row
        if current >= 0:
            self.window_combo.setCurrentIndex(current)
        self.window_combo.blockSignals(False)
        if finished:
            self.refresh_button.setEnabled(True)
        self._refresh_device_state()
        self.boxes_switch.blockSignals(True)
        self.boxes_switch.setChecked(bool(og.app.overlay_state()['boxes']))
        self.boxes_switch.blockSignals(False)

    def _refresh_device_state(self) -> None:
        from ok import og
        device_manager = og.device_manager
        device = device_manager.get_preferred_device()
        editable = og.executor.paused
        for widget in (self.window_combo, self.capture_group, self.interaction_group):
            widget.setEnabled(editable)
        if device is None:
            self.status_pill.setText(_t("StartTab", "Disconnected"))
            self.status_pill.set_tone("neutral")
            self.details_label.setText("")
            self.capture_group.set_options([])
            self.interaction_group.set_options([])
            return
        connected = bool(device.get('connected'))
        self.status_pill.setText(_t("StartTab", "Connected") if connected else _t("StartTab", "Disconnected"))
        self.status_pill.set_tone("success" if connected else "warning")
        self.details_label.setText(device_details(device))
        options, index, self._capture_names = capture_options(device_manager, device)
        self.capture_group.set_options(options, index)
        options, index, self._interaction_names = interaction_options(device_manager, device)
        self.interaction_group.set_options(options, index)
        if self.isVisible():
            self.reposition()

    # --- actions --------------------------------------------------------------

    def _on_window_picked(self, index: int) -> None:
        from ok import og
        if 0 <= index < len(self._devices):
            og.device_manager.set_preferred_device(index=index)
            self._refresh_device_state()
            self.changed.emit()

    def _refresh_devices(self) -> None:
        from ok import og
        self.refresh_button.setEnabled(False)
        og.device_manager.refresh()

    def _on_capture_picked(self, index: int) -> None:
        from ok import og
        if index < len(self._capture_names) and self._capture_names[index]:
            og.device_manager.set_capture(self._capture_names[index])
        elif index < len(self._capture_names):
            og.device_manager.set_capture("windows")
        self.changed.emit()

    def _on_interaction_picked(self, index: int) -> None:
        from ok import og
        if index < len(self._interaction_names) and self._interaction_names[index]:
            og.device_manager.set_interaction(self._interaction_names[index])
        self.changed.emit()

    def _view_log(self) -> None:
        from ok.ui.qt.Communicate import communicate
        self.close_popover()
        communicate.tab.emit("log")

    def _on_boxes_toggled(self, checked: bool) -> None:
        from ok import og
        og.app.set_overlay_setting('boxes', checked)

    def _capture(self) -> None:
        self.screenshot_button.setEnabled(False)
        diagnostics.capture_screenshot(done=self.capture_finished.emit)

    def _on_capture_finished(self, path) -> None:
        """Show a new screenshot on the Diagnosis page."""
        self.screenshot_button.setEnabled(True)
        page = getattr(self.window(), 'diagnosis_page', None)
        if not path or page is None:
            return
        from ok.ui.qt.Communicate import communicate
        self.close_popover()
        communicate.tab.emit("diagnosis")
        page.select_path(path)
