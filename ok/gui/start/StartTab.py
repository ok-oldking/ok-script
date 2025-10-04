import os

import win32gui
import win32process
from PySide6.QtWidgets import QAbstractItemView
from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import ListWidget, PushButton, FluentIcon, SplitTitleBar


from ok.gui.Communicate import communicate
from ok.gui.start.SelectCaptureListView import SelectCaptureListView
from ok.gui.start.StartCard import StartCard
from ok.gui.util.Alert import alert_info
from ok.gui.widget.BaseWindow import BaseWindow
from ok.gui.widget.Tab import Tab



class StartTab(Tab):
    def __init__(self, config, exit_event):
        super().__init__()
        from ok import Logger
        self.logger = Logger.get_logger(__name__)
        self.select_hwnd_window = None
        self.device_list_row = -1
        self.capture_list_row = -1
        self.start_card = StartCard(exit_event)
        self.add_widget(self.start_card)

        self.device_list = ListWidget()

        self.device_container = self.add_card(self.tr("Choose Window"), self.device_list)
        self.device_list.itemSelectionChanged.connect(self.device_index_changed)

        self.refresh_button = PushButton(FluentIcon.SYNC, self.tr("Refreshing"))
        self.refresh_button.clicked.connect(self.refresh_clicked)
        self.device_container.add_top_widget(self.refresh_button)

        if config.get('windows') and (
                not config.get('windows').get('exe') and not config.get('windows').get('hwnd_class')):
            self.choose_window_button = PushButton(FluentIcon.VIEW, self.tr("Choose Window"))
            self.choose_window_button.clicked.connect(self.choose_window_clicked)
            self.device_container.add_top_widget(self.choose_window_button)

        communicate.adb_devices.connect(self.update_capture)

        self.capture_list = SelectCaptureListView(self.capture_index_changed)
        self.interaction_container = self.add_card(self.tr("Capture Method"), self.capture_list)

        self.closed_by_finish_loading = False
        self.message = "Loading"

        self.update_capture(True)
        self.refresh_clicked()
        self.update_selection()
        communicate.executor_paused.connect(self.update_selection)

    def update_window_list(self):
        if self.device_list_row == -1:
            return
        self.logger.debug(f"update_window_list {self.device_list_row}")
        self.capture_list.update_for_device()

    def choose_window_clicked(self):
        window = HwndChooser(None, self.winId())
        window.show()

    def refresh_clicked(self):
        from ok import og
        og.device_manager.refresh()
        self.refresh_button.setDisabled(True)
        self.refresh_button.setText(self.tr("Refreshing"))

    def capture_index_changed(self):  # i is an index
        i = self.capture_list.currentRow()
        self.capture_list_row = i
        from ok import og
        device = og.device_manager.get_preferred_device()
        self.logger.debug(f"capture_index_changed {i} {device}")
        if device is not None:
            if device.get('device') == 'adb':
                if i == 0:
                    og.device_manager.set_capture("adb")
                elif i == 1:
                    og.device_manager.set_capture("ipc")
            elif device.get('device') == 'windows':
                og.device_manager.set_capture("windows")
            self.start_card.update_status()

    def device_index_changed(self):  # i is an index
        i = self.device_list.currentRow()
        self.device_list_row = i
        self.logger.debug(f"device_index_changed {i}")
        if i == -1:
            return
        from ok import og
        og.device_manager.set_preferred_device(index=i)
        self.logger.debug(f"device_index_changed done {i}")

    def update_capture(self, finished):
        from ok import og
        devices = og.device_manager.get_devices()
        preferred = og.device_manager.config.get("preferred")
        selected = self.device_list_row

        self.logger.debug('update_capture')

        # Update the existing items in the device_list and og.device_manager.get_devices()
        for row, device in enumerate(devices):
            if device.get('imei') == preferred:
                selected = row
            if device['device'] == "windows":
                method = self.tr("PC")
            elif device.get('emulator'):
                method = self.tr("Emulator")
            else:
                method = self.tr("Android")
            connected = self.tr("Connected") if device['connected'] else self.tr("Disconnected")
            item_text = f"{method} {connected}: {device.get('nick')} {device['address']} {device.get('resolution') or ''}"

            if row < self.device_list.count():
                # Update the existing item
                item = self.device_list.item(row)
                item.setText(item_text)
            else:
                # Add a new item
                self.device_list.addItem(item_text)

        # Remove any extra items
        while self.device_list.count() > len(devices):
            self.device_list.takeItem(self.device_list.count() - 1)

        if selected != self.device_list_row:
            self.device_list.setCurrentRow(selected)
        if finished:
            self.refresh_button.setDisabled(False)
            self.refresh_button.setText(self.tr("Refresh"))
            self.capture_list.update_for_device()

    def update_selection(self):
        from ok import og
        if og.executor.paused:
            self.device_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.capture_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.update_window_list()

    def update_progress(self, message):
        self.message = message


def list_visible_hwnds(exclude_hwnd=None):
    hwnds = []

    def callback(hwnd, lParam):
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowEnabled(hwnd) and win32gui.IsWindowVisible(
                hwnd) and hwnd not in exclude_hwnd:
            title = win32gui.GetWindowText(hwnd)
            if title:
                hwnds.append((hwnd, title))
        return True

    win32gui.EnumWindows(callback, None)
    return hwnds


import psutil

black_list_process = ['NVIDIA Overlay.exe', 'explorer.exe', 'TextInputHost.exe', 'SystemSettings.exe',
                      'ApplicationFrameHost.exe']


class HwndChooser(BaseWindow):  # Assuming BaseWindow is defined elsewhere

    def __init__(self, parent=None, parent_id=None, icon=None):
        super().__init__()

        self.setTitleBar(SplitTitleBar(self))
        self.titleBar.raise_()

        self.setWindowTitle(self.tr("Choose Window"))

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 40, 12, 12)

        self.parent_id = parent_id

        self.list_widget = ListWidget(self)
        self.layout.addWidget(self.list_widget)
        self.hwnds = []
        self.load_hwnds()

        self.btn_confirm = PushButton(self.tr("Confirm"), self)
        self.btn_confirm.clicked.connect(self.confirm)
        self.layout.addWidget(self.btn_confirm)

        self.btn_cancel = PushButton(self.tr("Cancel"), self)
        self.btn_cancel.clicked.connect(self.cancel)
        self.layout.addWidget(self.btn_cancel)

    def load_hwnds(self):
        current_hwnd = int(self.winId()) if self.winId() else None
        hwnds = list_visible_hwnds([int(self.parent_id), int(current_hwnd)])
        current_pid = os.getpid()
        # Enhanced with process name retrieval using psutil
        self.hwnds.clear()
        for hwnd, title in hwnds:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            # Get the process name and executable path
            if 0 < pid != current_pid:
                try:
                    process = psutil.Process(pid)
                    exe_name = process.name()  # Get the executable name
                    if exe_name not in black_list_process:
                        self.list_widget.addItem(f"{title} ({exe_name})")
                        self.hwnds.append((hwnd, exe_name, process.exe()))
                except Exception as e:
                    self.logger.error('get process error', e)

    def confirm(self):
        row = self.list_widget.currentRow()
        if row > 0:
            alert_info(self.tr('{} Selected').format(self.list_widget.item(row).text()))
            from ok import og
            og.device_manager.select_hwnd(self.hwnds[row][2], self.hwnds[row][0])
        self.close()

    def cancel(self):
        self.close()
