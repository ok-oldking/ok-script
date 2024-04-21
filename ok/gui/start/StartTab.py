from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QPushButton
from qfluentwidgets import ListWidget, PushButton, FluentIcon

import ok
from ok.gui.Communicate import communicate
from ok.gui.start.SelectCaptureListView import SelectCaptureListView
from ok.gui.start.SelectHwndWindow import SelectHwndWindow
from ok.gui.start.StartCard import StartCard
from ok.gui.util.Alert import show_alert
from ok.gui.widget.Tab import Tab
from ok.interaction.Win32Interaction import is_admin
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class StartTab(Tab):
    def __init__(self):
        super().__init__()
        self.select_hwnd_window = None

        self.addWidget(StartCard())

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

        self.start_button = QPushButton(self.tr("Start"))
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.on_start_clicked)
        # layout.addWidget(self.start_button, alignment=Qt.AlignCenter)
        self.update_capture()
        self.refresh_clicked()

    def update_window_list(self):
        if self.device_list.currentRow() == -1:
            return
        data = ok.gui.device_manager.get_devices()[self.device_list.currentRow()]
        if data.get("device") == "windows":
            self.choose_window_button.setDisabled(True)
        else:
            self.choose_window_button.setDisabled(False)
        self.window_list.update_for_device(data.get("device"), data.get("hwnd"), data.get("capture"))

    def refresh_clicked(self):
        ok.gui.device_manager.refresh()
        self.refresh_button.setDisabled(True)
        self.refresh_button.setText(self.tr("Refreshing"))

    def on_start_clicked(self):
        i = self.device_list.currentRow()
        connected = ok.gui.device_manager.get_devices()[i]["connected"]
        if not connected:
            show_alert(self.tr("Error"), self.tr("Game Window is not detected, Please open game and refresh!"))
            return
        method = ok.gui.device_manager.get_devices()[i]["device"]
        if method == "windows" and not is_admin():
            show_alert(self.tr("Error"),
                       self.tr(f"PC version requires admin privileges, Please restart this app with admin privileges!"))
            return
        capture = ok.gui.device_manager.get_devices()[i].get("capture")
        if capture == "windows" and not ok.gui.device_manager.get_devices()[i].get("hwnd"):
            self.choose_window_clicked()
            return
        ok.gui.executor.start()

    def choose_window_clicked(self):
        self.select_hwnd_window = SelectHwndWindow(self.update_window_list, self.window())
        self.select_hwnd_window.show()

    def capture_index_changed(self):  # i is an index
        i = self.window_list.currentRow()
        if i == 1:
            self.choose_window_button.setDisabled(True)
            ok.gui.device_manager.set_capture("adb")
        elif i == 0:
            ok.gui.device_manager.set_capture("windows")
            device = ok.gui.device_manager.get_devices()[self.device_list.currentRow()]["device"]
            if device == "adb":
                self.choose_window_button.show()
                if not ok.gui.device_manager.get_hwnd_name():
                    self.choose_window_clicked()

    def device_index_changed(self):  # i is an index
        i = self.device_list.currentRow()
        if i == -1:
            return
        devices = ok.gui.device_manager.get_devices()
        if len(devices) > 0:
            imei = devices[i]["imei"]
            ok.gui.device_manager.set_preferred_device(imei)
            self.update_window_list()
            self.capture_index_changed()

    def update_capture(self):
        devices = ok.gui.device_manager.get_devices()
        preferred = ok.gui.device_manager.config.get("preferred")
        selected = self.device_list.currentRow()

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

        if selected != self.device_list.currentRow():
            self.device_list.setCurrentRow(selected)
        self.refresh_button.setDisabled(False)
        self.refresh_button.setText(self.tr("Refresh"))

    def update_progress(self, message):
        self.message = message

    def update_loading_animation(self):
        self.dot_count = (self.dot_count % 3) + 1  # Cycle through 1, 2, 3
        self.start_button.setText(f"{self.message}{'.' * self.dot_count}")

    def close(self):
        self.closed_by_finish_loading = True
        super().close()

    def closeEvent(self, event):
        self.timer.stop()
        if self.closed_by_finish_loading:
            super().closeEvent(event)
        else:
            # Create a message box that asks the user if they really want to close the window
            reply = QMessageBox.question(self, self.tr('Exit'), self.tr('Are you sure you want to exit the app?'),
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

            if reply == QMessageBox.Yes:
                self.exit_event.set()
                event.accept()
                self.app.quit()
                logger.info("Window closed")  # Place your code here
            else:
                event.ignore()
