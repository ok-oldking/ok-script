from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView
from qfluentwidgets import ListWidget, PushButton, FluentIcon

import ok
from ok.gui.Communicate import communicate
from ok.gui.start.SelectCaptureListView import SelectCaptureListView
from ok.gui.start.SelectHwndWindow import SelectHwndWindow
from ok.gui.start.StartCard import StartCard
from ok.gui.widget.Tab import Tab
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class StartTab(Tab):
    def __init__(self):
        super().__init__()
        self.select_hwnd_window = None
        self.device_list_row = -1
        self.capture_list_row = -1
        self.start_card = StartCard()
        self.addWidget(self.start_card)

        self.device_list = ListWidget()
        # self.device_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.device_container = self.addCard(self.tr("Choose Window"), self.device_list)
        self.device_list.itemSelectionChanged.connect(self.device_index_changed)

        self.refresh_button = PushButton(FluentIcon.SYNC, self.tr("Refreshing"))
        self.refresh_button.clicked.connect(self.refresh_clicked)
        self.device_container.add_top_widget(self.refresh_button)
        communicate.adb_devices.connect(self.update_capture)

        self.choose_window_button = PushButton(FluentIcon.ZOOM, self.tr("Choose Window"))
        self.choose_window_button.clicked.connect(self.choose_window_clicked)

        self.window_list = SelectCaptureListView(self.capture_index_changed)
        self.interaction_container = self.addCard(self.tr("Capture Method"), self.window_list)
        self.interaction_container.add_top_widget(self.choose_window_button)

        self.closed_by_finish_loading = False
        self.message = "Loading"

        self.update_capture(True)
        self.refresh_clicked()
        self.update_selection()
        communicate.executor_paused.connect(self.update_selection)
        self.start_card.show_choose_hwnd.connect(self.choose_window_clicked)

    def update_window_list(self):
        if self.device_list_row == -1:
            return
        logger.debug(f"update_window_list {self.device_list_row}")
        data = ok.gui.device_manager.get_devices()[self.device_list_row]
        if data.get("device") == "windows":
            self.choose_window_button.setDisabled(True)
        else:
            self.choose_window_button.setDisabled(False)
        self.window_list.update_for_device(data.get("device"), data.get("hwnd"), data.get("capture"))

    def refresh_clicked(self):
        ok.gui.device_manager.refresh()
        self.refresh_button.setDisabled(True)
        self.refresh_button.setText(self.tr("Refreshing"))

    def choose_window_clicked(self):
        if self.choose_window_button.isEnabled():
            self.select_hwnd_window = SelectHwndWindow(self.update_window_list, self.window())
            self.select_hwnd_window.show()

    def capture_index_changed(self):  # i is an index
        i = self.window_list.currentRow()
        self.capture_list_row = i
        logger.debug(f"capture_index_changed {i}")
        if i == 1:
            self.choose_window_button.setDisabled(True)
            ok.gui.device_manager.set_capture("adb")
        elif i == 0:
            ok.gui.device_manager.set_capture("windows")
            device = ok.gui.device_manager.get_devices()[self.device_list_row]["device"]
            if device == "adb":
                self.choose_window_button.setEnabled(True)
        self.start_card.update_status()

    def device_index_changed(self):  # i is an index
        i = self.device_list.currentRow()
        self.device_list_row = i
        logger.debug(f"device_index_changed {i}")
        if i == -1:
            return
        devices = ok.gui.device_manager.get_devices()
        if len(devices) > 0:
            imei = devices[i]["imei"]
            ok.gui.device_manager.set_preferred_device(imei)
            self.update_window_list()
            self.capture_index_changed()
        self.start_card.update_status()

    def update_capture(self, finished):
        devices = ok.gui.device_manager.get_devices()
        preferred = ok.gui.device_manager.config.get("preferred")
        selected = self.device_list_row

        # Update the existing items in the device_list and ok.gui.device_manager.get_devices()
        for row, device in enumerate(devices):
            if device["imei"] == preferred:
                selected = row
            method = self.tr("PC") if device['device'] == "windows" else self.tr("Android")
            connected = self.tr("Connected") if device['connected'] else self.tr("Disconnected")
            item_text = f"{method} {connected}: {device['nick']} {device['address']} {device.get('resolution') or ''}"

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

    def update_selection(self):
        if ok.gui.executor.paused:
            self.device_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.window_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.update_window_list()
        else:
            self.device_list.setSelectionMode(QAbstractItemView.NoSelection)
            self.window_list.setSelectionMode(QAbstractItemView.NoSelection)
            self.choose_window_button.setDisabled(True)

    def update_progress(self, message):
        self.message = message
