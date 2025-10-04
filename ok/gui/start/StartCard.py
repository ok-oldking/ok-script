import os
import subprocess
import zipfile
from ctypes import windll, wintypes
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget
from _ctypes import byref
from qfluentwidgets import FluentIcon, SettingCard, PushButton

from ok import Handler
from ok import Logger
from ok import og
from ok.gui.Communicate import communicate
from ok.gui.debug.DebugTab import capture
from ok.gui.widget.StatusBar import StatusBar

logger = Logger.get_logger(__name__)


class StartCard(SettingCard):
    show_choose_hwnd = Signal()

    def __init__(self, exit_event):
        super().__init__(og.config.get('gui_icon'), og.app.title, og.app.version)

        # while (item := self.hBoxLayout.takeAt(0)) is not None:
        #     if item.widget() and item.widget():
        #         item.widget().setParent(None)
        # self.hBoxLayout.setSpacing(8)
        self.iconLabel.setFixedSize(30, 30)
        # self.hBoxLayout.addWidget(self.iconLabel)
        self.hBoxLayout.setAlignment(Qt.AlignVCenter)
        self.status_bar = StatusBar("test")
        self.status_bar.clicked.connect(self.status_clicked)

        self.hBoxLayout.addWidget(self.status_bar, 0, Qt.AlignLeft)
        self.hBoxLayout.addSpacing(6)

        self.open_install_folder_button = PushButton(FluentIcon.FOLDER, self.tr("Install Folder"), self)
        self.hBoxLayout.addWidget(self.open_install_folder_button, 0, Qt.AlignRight)
        self.open_install_folder_button.clicked.connect(self.open_install_folder)
        self.hBoxLayout.addSpacing(6)

        self.export_log_button = PushButton(FluentIcon.FEEDBACK, self.tr("Export Logs"), self)
        self.hBoxLayout.addWidget(self.export_log_button, 0, Qt.AlignRight)
        self.export_log_button.clicked.connect(self.export_logs)
        self.hBoxLayout.addSpacing(6)

        self.capture_button = PushButton(FluentIcon.ZOOM, self.tr("Capture"), self)
        self.hBoxLayout.addWidget(self.capture_button, 0, Qt.AlignRight)
        self.capture_button.clicked.connect(self.capture)
        self.hBoxLayout.addSpacing(6)

        self.start_button = PushButton(FluentIcon.PLAY, self.tr("Start"), self)
        self.hBoxLayout.addWidget(self.start_button, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(6)
        self.update_status()
        self.start_button.clicked.connect(self.clicked)
        communicate.executor_paused.connect(self.update_status)
        communicate.window.connect(self.update_status)
        communicate.task.connect(self.update_task)

        self.handler = Handler(exit_event, "StartCard")
        self.handler.post(self.bind_hot_keys)
        self.handler.post(self.check_hotkey, 0.1)

    @staticmethod
    def capture():
        return capture(processor=og.config.get('screenshot_processor'))

    def status_clicked(self):
        if not og.executor.paused:
            if og.executor.current_task:
                communicate.tab.emit("onetime")
            elif og.executor.active_trigger_task_count():
                communicate.tab.emit("trigger")
            else:
                communicate.tab.emit("start")
            self.status_bar.show()

    @staticmethod
    def clicked():
        if not og.executor.paused:
            og.executor.pause()
        else:
            og.app.start_controller.start()

    @staticmethod
    def open_install_folder():
        cwd = os.getcwd()
        subprocess.Popen(f'explorer "{cwd}"')

    @staticmethod
    def export_logs():
        """
            Creates a zip file named "app-log.zip" in the user's Downloads folder.

            The zip file will contain the 'screenshots' and 'logs' folders from the
            current working directory. If the zip file already exists, it will be
            overwritten. After creation, Windows Explorer is opened to show the file.
            """
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

    def update_task(self, task):
        self.update_status()

    def update_status(self):
        if og.executor.paused:
            device = og.device_manager.get_preferred_device()
            if device and not device['connected'] and device.get('full_path'):
                self.start_button.setText(self.tr("Start Game") + '(F9)')
            else:
                self.start_button.setText(self.tr("Start") + '(F9)')
            self.start_button.setIcon(FluentIcon.PLAY)
            self.status_bar.hide()
        else:
            self.start_button.setText(self.tr("Pause") + '(F9)')
            self.start_button.setIcon(FluentIcon.PAUSE)
            if not og.executor.connected():
                self.status_bar.setTitle(self.tr("Game Window Disconnected"))
                self.status_bar.setState(True)
            elif active_trigger_task_count := og.executor.active_trigger_task_count():
                if not og.executor.can_capture():
                    self.status_bar.setTitle(self.tr('Paused: PC Game Window Must Be in Front!'))
                    self.status_bar.setState(True)
                else:
                    self.status_bar.setTitle(
                        self.tr("Running") + ": " + str(active_trigger_task_count) + ' ' + self.tr("Trigger Tasks"))
                    self.status_bar.setState(False)
            elif task := og.executor.current_task:
                if not og.executor.can_capture():
                    self.status_bar.setTitle(self.tr('Paused: PC Game Window Must Be in Front!'))
                    self.status_bar.setState(True)
                elif task.enabled:
                    self.status_bar.setTitle(self.tr("Running") + ": " + task.name)
                    self.status_bar.setState(False)
                else:
                    self.status_bar.setTitle(self.tr("Waiting for task to be enabled"))
                    self.status_bar.setState(False)
            else:
                self.status_bar.setTitle(self.tr("Waiting for task to be enabled"))
                self.status_bar.setState(False)
            self.status_bar.show()

    def check_hotkey(self):
        # Example event type, you should use the appropriate QEvent.Type for your case
        msg = wintypes.MSG()

        # PeekMessageW is used to check for a hotkey press
        if windll.user32.PeekMessageW(byref(msg), None, 0, 0, 1):
            if msg.message == 0x0312:  # WM_HOTKEY
                logger.debug(f'hotkey pressed {msg}')
                if msg.wParam == 999:
                    self.clicked()

        # Repost the check_hotkey method to be called after 100 ms
        self.handler.post(self.check_hotkey, 0.1)

    def bind_hot_keys(self):
        VK_F9 = 0x78

        if not windll.user32.RegisterHotKey(None, 999, 0, VK_F9):
            logger.error("start card Failed to register hotkey for VK_F9")
        logger.debug('start card bind_hot_keys')
