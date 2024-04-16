from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QMessageBox, QHBoxLayout, QListWidget, QPushButton

import ok
from ok.gui.Communicate import communicate
from ok.gui.loading.SelectHwndWindow import SelectHwndWindow
from ok.gui.util.Alert import show_alert
from ok.gui.widget.RoundCornerContainer import RoundCornerContainer
from ok.interaction.Win32Interaction import is_admin
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class LoadingWindow(QWidget):
    def __init__(self, app, exit_event):
        super().__init__()
        self.app = app
        self.exit_event = exit_event
        self.dot_count = 0
        self.initUI()
        self.select_hwnd_window = None
        layout = QVBoxLayout()
        top_layout = QHBoxLayout()
        layout.addLayout(top_layout)
        self.setLayout(layout)
        self.capture_list = QListWidget()
        self.capture_list.itemSelectionChanged.connect(self.capture_index_changed)
        self.capture_list_data = []
        capture_container = RoundCornerContainer(self.tr("Choose Window"), self.capture_list)

        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.refresh_button.clicked.connect(self.refresh_clicked)
        capture_container.add_top_widget(self.refresh_button)
        communicate.adb_devices.connect(self.update_capture)
        top_layout.addWidget(capture_container)

        self.window_list = QListWidget()
        self.window_list.addItem(self.tr("Windows (Supports Background, Low Compatibility, Low Latency)"))
        self.window_list.addItem(self.tr("ADB (Supports Background, High Compatibility, High Latency)"))
        self.window_list.itemSelectionChanged.connect(self.window_index_changed)
        interaction_container = RoundCornerContainer(self.tr("Capture Method"), self.window_list)
        top_layout.addWidget(interaction_container)

        # self.start_button = StartButton()
        self.closed_by_finish_loading = False
        self.message = "Loading"

        self.start_button = QPushButton(self.tr("Start"))
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button, alignment=Qt.AlignCenter)
        self.update_capture()

    def refresh_clicked(self):
        ok.gui.device_manager.refresh()
        self.refresh_button.setDisabled(True)
        self.refresh_button.setText(self.tr("Refreshing"))

    def on_start_clicked(self):
        i = self.capture_list.currentRow()
        connected = self.capture_list_data[i]["connected"]
        if not connected:
            show_alert(self.tr("Error"), self.tr("Game Window is not detected, Please open game and refresh!"))
            return
        method = self.capture_list_data[i]["method"]
        if method == "windows" and not is_admin():
            show_alert(self.tr("Error"),
                       self.tr(f"PC version requires admin privileges, Please restart this app with admin privileges!"))
            return
        ok.gui.device_manager.start()
        self.app.show_main_window()

    def window_index_changed(self):  # i is an index
        i = self.window_list.currentRow()
        if i == 1:
            ok.gui.device_manager.set_hwnd_name(None)
        elif i == 0:
            self.select_hwnd_window = SelectHwndWindow()
            self.select_hwnd_window.show()

    def capture_index_changed(self):  # i is an index
        i = self.capture_list.currentRow()
        imei = self.capture_list_data[i]["imei"]
        ok.gui.device_manager.set_preferred_device(imei)

    def update_capture(self):
        devices = ok.gui.device_manager.get_devices()
        selected = self.capture_list.currentRow()
        self.capture_list.clear()
        self.capture_list_data.clear()
        if len(devices) > 0:
            for row, device in enumerate(devices):
                if device["imei"] == ok.gui.device_manager.config.get("preferred"):
                    selected = row
                method = self.tr("PC") if device['method'] == "windows" else self.tr("Android")
                connected = self.tr("Connected") if device['connected'] else self.tr("Disconnected")
                self.capture_list.addItem(
                    f"{method} {connected}: {device['nick']} {device['address']} {device.get('resolution') or ''}")
                item = self.capture_list.item(row)
                if not device['connected']:
                    item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                self.capture_list_data.append(device)
            if selected == -1:
                selected = 0
            self.capture_list.setCurrentRow(selected)
        self.refresh_button.setDisabled(False)
        self.refresh_button.setText(self.tr("Refresh"))

    def initUI(self):
        self.setWindowTitle(self.app.title)
        self.setWindowIcon(self.app.icon)

        communicate.loading_progress.connect(self.update_progress)
        # self.setLayout(layout)
        self.update_progress("Loading, please wait...")
        # Start the timer for the loading animation
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_loading_animation)
        self.timer.start(1000)  # Update every 500 ms

    def update_progress(self, message):
        self.message = message

    def loading_done(self):
        self.start_button.setEnabled(True)
        self.timer.stop()
        self.start_button.setText(self.tr("Start"))

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
