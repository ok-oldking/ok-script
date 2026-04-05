import os
import subprocess
import zipfile
from pathlib import Path

import win32gui
import win32process
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QVBoxLayout, QHBoxLayout, QWidget, QListWidgetItem
from qfluentwidgets import ListWidget, PushButton, FluentIcon, SplitTitleBar, SwitchButton, SearchLineEdit

from ok.gui.Communicate import communicate
from ok.gui.start.SelectCaptureListView import SelectCaptureListView
from ok.gui.start.SelectInteractionListView import SelectInteractionListView
from ok.gui.start.StartCard import StartCard
from ok.gui.util.Alert import alert_info
from ok.gui.widget.BaseWindow import BaseWindow
from ok.gui.widget.Tab import Tab
from ok.gui.widget.Card import Card
from ok.gui.debug.DebugTab import capture


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

        self.start_card.refresh_button.clicked.connect(self.refresh_clicked)
        self.start_card.capture_button.clicked.connect(self.capture)

        horizontal_widget = QWidget()
        horizontal_layout = QHBoxLayout(horizontal_widget)
        horizontal_layout.setContentsMargins(0, 20, 0, 20)
        self.add_widget(horizontal_widget, 1)

        self.device_search_box = SearchLineEdit()
        self.device_search_box.setPlaceholderText(self.tr("Search title or exe..."))
        self.device_search_box.textChanged.connect(self.filter_devices)
        self.device_list = ListWidget()
        device_view_widget = QWidget()
        device_view_layout = QVBoxLayout(device_view_widget)
        device_view_layout.setContentsMargins(0, 0, 0, 0)
        device_view_layout.addWidget(self.device_search_box)
        device_view_layout.addWidget(self.device_list)
        self.device_container = Card(self.tr("Choose Window"), device_view_widget, stretch=1)
        horizontal_layout.addWidget(self.device_container, 2)
        self.device_list.itemSelectionChanged.connect(self.device_index_changed)

        communicate.adb_devices.connect(self.update_capture)

        self.capture_list = SelectCaptureListView(self.capture_index_changed)
        self.capture_container = Card(self.tr("Capture Method"), self.capture_list, stretch=1)
        horizontal_layout.addWidget(self.capture_container, 1)

        self.interaction_list = SelectInteractionListView(self.interaction_index_changed)
        self.interaction_container = Card(self.tr("Choose Interaction"), self.interaction_list, stretch=1)
        horizontal_layout.addWidget(self.interaction_container, 1)

        from ok import og

        self.debug_widget = QWidget()
        self.debug_layout = QHBoxLayout(self.debug_widget)
        self.debug_layout.setContentsMargins(0, 20, 0, 20)

        self.open_install_folder_button = PushButton(FluentIcon.FOLDER, self.tr("Install Folder"))
        self.open_install_folder_button.clicked.connect(self.open_install_folder)
        self.debug_layout.addWidget(self.open_install_folder_button)

        self.export_log_button = PushButton(FluentIcon.FEEDBACK, self.tr("Export Logs"))
        self.export_log_button.clicked.connect(self.export_logs)
        self.debug_layout.addWidget(self.export_log_button)

        self.ocr_button = PushButton(FluentIcon.SEARCH, "OCR")
        self.ocr_button.clicked.connect(self.ocr_log)
        self.debug_layout.addWidget(self.ocr_button)
        self.debug_layout.addStretch(1)

        self.add_card(self.tr("Debug"), self.debug_widget)

        self.overlay_widget = QWidget()
        self.overlay_layout = QHBoxLayout(self.overlay_widget)
        self.overlay_layout.setContentsMargins(0, 20, 0, 20)

        self.overlay_switch = SwitchButton()
        self.overlay_switch.setOnText(self.tr("Show Overlay"))
        self.overlay_switch.setOffText(self.tr("Hide Overlay"))
        self.overlay_switch.setChecked(og.app.ok_config.get('use_overlay', False))
        self.overlay_switch.checkedChanged.connect(self.on_overlay_toggled)
        self.overlay_layout.addWidget(self.overlay_switch)

        self.overlay_log_switch = SwitchButton()
        self.overlay_log_switch.setOnText(self.tr("Show Log on Overlay"))
        self.overlay_log_switch.setOffText(self.tr("Hide Log on Overlay"))
        self.overlay_log_switch.setChecked(og.app.ok_config.get('show_overlay_logs', True))
        self.overlay_log_switch.checkedChanged.connect(self.on_overlay_log_toggled)
        self.overlay_layout.addWidget(self.overlay_log_switch)
        self.overlay_layout.addStretch(1)

        self.add_card(self.tr("Debug Overlay"), self.overlay_widget)

        self.closed_by_finish_loading = False
        self.message = "Loading"

        self.update_capture(True)
        self.refresh_clicked()
        self.update_selection()
        communicate.executor_paused.connect(self.update_selection)

    def interaction_index_changed(self):
        i = self.interaction_list.currentRow()
        if i == -1: return
        from ok import og
        device = og.device_manager.get_preferred_device()
        self.logger.debug(f"interaction_index_changed {i} {device}")
        if device is not None:
            if device.get('device') == 'windows':
                methods = og.device_manager.windows_capture_config.get('interaction', [])
                if isinstance(methods, str):
                    methods = [methods]
                if methods and i < len(methods):
                    og.device_manager.set_interaction(methods[i])
            self.start_card.update_status()

    def on_overlay_toggled(self, checked):
        from ok import og
        og.app.ok_config['use_overlay'] = checked
        og.app.ok_config.save_file()
        if checked:
            if not og.app.overlay_window:
                from ok.gui.overlay.OverlayWindow import OverlayWindow
                og.app.overlay_window = OverlayWindow(og.device_manager.hwnd_window)
                communicate.window.connect(og.app.overlay_window.update_overlay)
        else:
            if og.app.overlay_window:
                communicate.window.disconnect(og.app.overlay_window.update_overlay)
                og.app.overlay_window.close()
                og.app.overlay_window = None

    def on_overlay_log_toggled(self, checked):
        from ok import og
        og.app.ok_config['show_overlay_logs'] = checked
        og.app.ok_config.save_file()
        if og.app.overlay_window:
            og.app.overlay_window.update()

    @staticmethod
    def capture():
        from ok import og
        return capture(processor=og.config.get('screenshot_processor'))

    @staticmethod
    def open_install_folder():
        cwd = os.getcwd()
        subprocess.Popen(f'explorer "{cwd}"')

    @staticmethod
    def export_logs():
        from ok import og
        app_name = og.config.get('gui_title')
        downloads_path = Path.home() / "Downloads"
        zip_path = downloads_path / f"{app_name}-log.zip"
        folders_to_archive = ["screenshots", "logs"]

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for folder in folders_to_archive:
                source_dir = Path.cwd() / folder
                if not source_dir.is_dir():
                    continue
                for file_path in source_dir.rglob("*"):
                    if file_path.is_file():
                        zipf.write(file_path, file_path.relative_to(Path.cwd()))

        subprocess.run(["explorer", f"/select,{zip_path}"])

    def ocr_log_bg(self):
        try:
            import os
            from ok import og
            from ok.gui.util.Alert import alert_error
            if og.executor.paused:
                alert_error(self.tr("Please Start First"))
                return
            result = og.executor.get_all_tasks()[0].ocr(log=True, screenshot=True)
            from ok.gui.util.Alert import alert_info
            alert_info(self.tr(f"OCR success (Logged): {result}"))
            folder = og.ok.screenshot.screenshot_folder
            if folder:
                folder_abs = os.path.abspath(folder)
                if result:
                    result_path = os.path.join(folder_abs, 'ocr_result.txt')
                    with open(result_path, 'w', encoding='utf-8') as f:
                        for box in result:
                            f.write(f"{box.name}, {box}, {box.confidence}\n")
                subprocess.Popen(f'explorer "{folder_abs}"')
        except Exception as e:
            self.logger.error('debug ocr_log exception', e)

    def ocr_log(self):
        import threading
        t = threading.Thread(target=self.ocr_log_bg)
        t.daemon = True
        t.start()

    def update_window_list(self):
        if self.device_list_row == -1:
            return
        self.logger.debug(f"update_window_list {self.device_list_row}")
        self.capture_list.update_for_device()
        self.interaction_list.update_for_device()

    def refresh_clicked(self):
        from ok import og
        og.device_manager.refresh()
        self.start_card.refresh_button.setDisabled(True)
        self.start_card.refresh_button.setText(self.tr("Refreshing"))

    def capture_index_changed(self):  # i is an index
        i = self.capture_list.currentRow()
        self.capture_list_row = i
        if i == -1:
            return
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
                methods = og.device_manager.windows_capture_config.get('capture_method', [])
                if methods and i < len(methods):
                    og.device_manager.set_capture(methods[i])
                else:
                    og.device_manager.set_capture("windows")
            elif device.get('device') == 'browser':
                og.device_manager.set_capture("browser")
            self.start_card.update_status()

    def device_index_changed(self):  # i is an index
        i = self.device_list.currentRow()
        self.device_list_row = i
        self.logger.debug(f"device_index_changed {i}")
        if i == -1:
            return
        from ok import og
        og.device_manager.set_preferred_device(index=i)
        self.capture_list.update_for_device()
        self.interaction_list.update_for_device()
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
            elif device['device'] == "browser":
                method = self.tr("Browser")
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
                item = QListWidgetItem(item_text)
                self.device_list.addItem(item)
            item.setData(Qt.UserRole, device)

        # Remove any extra items
        while self.device_list.count() > len(devices):
            self.device_list.takeItem(self.device_list.count() - 1)

        self.filter_devices()

        if selected != self.device_list_row:
            self.device_list.setCurrentRow(selected)
        if finished:
            self.start_card.refresh_button.setDisabled(False)
            self.start_card.refresh_button.setText(self.tr("Refresh"))
            self.capture_list.update_for_device()
            self.interaction_list.update_for_device()

    def filter_devices(self, text=None):
        if text is None:
            text = self.device_search_box.text()
        search_text = text.lower()
        for i in range(self.device_list.count()):
            item = self.device_list.item(i)
            device = item.data(Qt.UserRole)
            if not device:
                continue
            nick = (device.get('nick') or "").lower()
            exe = (device.get('exe') or "").lower()
            address = (device.get('address') or "").lower()
            if search_text in nick or search_text in exe or search_text in address:
                item.setHidden(False)
            else:
                item.setHidden(True)

    def update_selection(self):
        from ok import og
        if og.executor.paused:
            self.device_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.capture_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.interaction_list.setSelectionMode(QAbstractItemView.SingleSelection)
            self.update_window_list()

    def update_progress(self, message):
        self.message = message
