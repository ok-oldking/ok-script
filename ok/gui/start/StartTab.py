from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView
from qfluentwidgets import ListWidget, PushButton, FluentIcon

import ok
from ok.gui.Communicate import communicate
from ok.gui.start.SelectCaptureListView import SelectCaptureListView
from ok.gui.start.StartCard import StartCard
from ok.gui.widget.Tab import Tab
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class StartTab(Tab):
    def __init__(self, exit_event):
        super().__init__()
        self.select_hwnd_window = None
        self.device_list_row = -1
        self.capture_list_row = -1
        self.start_card = StartCard(exit_event)
        self.addWidget(self.start_card)

        self.device_list = ListWidget()
        # self.device_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.device_container = self.addCard(self.tr("Choose Window"), self.device_list)
        self.device_list.itemSelectionChanged.connect(self.device_index_changed)

        self.refresh_button = PushButton(FluentIcon.SYNC, self.tr("Refreshing"))
        self.refresh_button.clicked.connect(self.refresh_clicked)
        self.device_container.add_top_widget(self.refresh_button)
        communicate.adb_devices.connect(self.update_capture)

        self.capture_list = SelectCaptureListView(self.capture_index_changed)
        self.interaction_container = self.addCard(self.tr("Capture Method"), self.capture_list)

        self.closed_by_finish_loading = False
        self.message = "Loading"

        self.update_capture(True)
        self.refresh_clicked()
        self.update_selection()
        communicate.executor_paused.connect(self.update_selection)

    def update_window_list(self):
        if self.device_list_row == -1:
            return
        logger.debug(f"update_window_list {self.device_list_row}")
        self.capture_list.update_for_device()

    def refresh_clicked(self):
        ok.gui.device_manager.refresh()
        self.refresh_button.setDisabled(True)
        self.refresh_button.setText(self.tr("Refreshing"))

    def capture_index_changed(self):  # i is an index
        i = self.capture_list.currentRow()
        self.capture_list_row = i
        device = ok.gui.device_manager.get_preferred_device()
        logger.debug(f"capture_index_changed {i} {device}")
        if device is not None:
            if device.get('device') == 'adb':
                if i == 0:
                    ok.gui.device_manager.set_capture("adb")
                elif i == 1:
                    ok.gui.device_manager.set_capture("windows")
                elif i == 2:
                    ok.gui.device_manager.set_capture("ipc")
            elif device.get('device') == 'windows':
                ok.gui.device_manager.set_capture("windows")
            self.start_card.update_status()

    def device_index_changed(self):  # i is an index
        i = self.device_list.currentRow()
        self.device_list_row = i
        logger.debug(f"device_index_changed {i}")
        if i == -1:
            return
        ok.gui.device_manager.set_preferred_device(index=i)
        logger.debug(f"device_index_changed done {i}")

    def update_capture(self, finished):
        devices = ok.gui.device_manager.get_devices()
        preferred = ok.gui.device_manager.config.get("preferred")
        selected = self.device_list_row

        logger.debug('update_capture')

        # Update the existing items in the device_list and ok.gui.device_manager.get_devices()
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
        if ok.gui.executor.paused:
            self.device_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.capture_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.update_window_list()
        else:
            self.device_list.setSelectionMode(QAbstractItemView.NoSelection)
            self.capture_list.setSelectionMode(QAbstractItemView.NoSelection)

    def update_progress(self, message):
        self.message = message
