import os

from PySide6.QtCore import Qt, Signal
from qfluentwidgets import FluentIcon, SettingCard, PushButton, InfoBar, InfoBarPosition

import ok
from ok.gui.Communicate import communicate
from ok.gui.widget.StatusBar import StatusBar
from ok.interaction.Win32Interaction import is_admin
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class StartCard(SettingCard):
    show_choose_hwnd = Signal()

    def __init__(self):
        super().__init__(FluentIcon.PLAY, f'{self.tr("Start")} {ok.gui.app.title}', ok.gui.app.title)
        self.hBoxLayout.setAlignment(Qt.AlignVCenter)
        self.status_bar = StatusBar("test")
        self.status_bar.clicked.connect(self.status_clicked)
        self.hBoxLayout.addWidget(self.status_bar, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.start_button = PushButton(FluentIcon.PLAY, self.tr("Start"), self)
        self.hBoxLayout.addWidget(self.start_button, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.update_status()
        self.start_button.clicked.connect(self.clicked)
        communicate.executor_paused.connect(self.update_status)
        communicate.window.connect(self.update_status)
        communicate.task.connect(self.update_task)

    def status_clicked(self):
        if not ok.gui.executor.paused:
            if ok.gui.executor.current_task:
                communicate.tab.emit("onetime")
            elif ok.gui.executor.active_trigger_task_count():
                communicate.tab.emit("trigger")
            else:
                communicate.tab.emit("second")
            self.status_bar.show()

    def clicked(self):
        supported_ratio = ok.gui.app.config.get(
            'supported_screen_ratio')
        device = ok.gui.device_manager.get_preferred_device()
        ok.gui.device_manager.do_refresh(fast=True)
        if device and not device['connected'] and device.get('full_path'):
            path = ok.gui.device_manager.get_exe_path(device)
            if os.path.exists(path):
                start_exe_background(path)
                logger.info(f"start_exe_background path, full_path: {device.get('full_path')}")
                InfoBar.info(
                    title=self.tr('Info:'),
                    content=self.tr("Start Game {game}").format(game=device.get('full_path')),
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                    parent=self.parent()
                )
            else:
                InfoBar.error(
                    title=self.tr('Error:'),
                    content=self.tr("Game window path does not exist: {path}").format(path=path),
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                    parent=self.parent()
                )
            return
        if ok.gui.device_manager.capture_method is None:
            InfoBar.error(
                title=self.tr('Error:'),
                content=self.tr("Selected capture method is not supported by the game or your system!"),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self.parent()
            )
            return
        if not ok.gui.executor.connected():
            InfoBar.error(
                title=self.tr('Error:'),
                content=self.tr("Game window is not connected, please select the game window and capture method."),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self.parent()
            )
            self.show_choose_hwnd.emit()
            return
        supported, resolution = ok.gui.executor.supports_screen_ratio(supported_ratio)
        if not supported:
            InfoBar.error(
                title=self.tr('Error:'),
                content=self.tr(
                    "Window resolution {resolution} is not supported, the supported ratio is {supported_ratio}, check if game windows is minimized, resized or out of screen.",
                ).format(resolution=resolution, supported_ratio=supported_ratio),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self.window()
            )
            return
        if device and device['device'] == "windows" and not is_admin():
            InfoBar.error(
                title=self.tr('Error:'),
                content=self.tr(
                    f"PC version requires admin privileges, Please restart this app with admin privileges!"),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )
            return
        if ok.gui.executor.paused:
            ok.gui.executor.start()
        else:
            ok.gui.executor.pause()

    def update_task(self, task):
        self.update_status()

    def update_status(self):
        if ok.gui.executor.paused:
            device = ok.gui.device_manager.get_preferred_device()
            if device and not device['connected'] and device.get('full_path'):
                self.start_button.setText(self.tr("Start Game"))
            else:
                self.start_button.setText(self.tr("Start"))
            self.start_button.setIcon(FluentIcon.PLAY)
            self.status_bar.hide()
        else:
            self.start_button.setText(self.tr("Pause"))
            self.start_button.setIcon(FluentIcon.PAUSE)
            if not ok.gui.executor.connected():
                self.status_bar.setTitle(self.tr("Game Window Disconnected"))
                self.status_bar.setState(True)
            elif not ok.gui.executor.can_capture():
                self.status_bar.setTitle(self.tr('Paused: PC Game Window Must Be in Front!'))
                self.status_bar.setState(True)
            elif active_trigger_task_count := ok.gui.executor.active_trigger_task_count():
                self.status_bar.setTitle(
                    self.tr("Running") + ": " + str(active_trigger_task_count) + ' ' + self.tr("Trigger Tasks"))
                self.status_bar.setState(False)
            elif task := ok.gui.executor.current_task:
                self.status_bar.setTitle(self.tr("Running") + ": " + task.name)
                self.status_bar.setState(False)
            else:
                self.status_bar.setTitle(self.tr("Waiting for task to be enabled"))
                self.status_bar.setState(False)
            self.status_bar.show()


def start_exe_background(exe_path):
    # # Start the process in the background
    # try:
    #     process = subprocess.Popen(exe_path)
    #     return True  # Successfully started
    # except Exception as e:
    #     print(f"An error occurred: {e}")
    #     return False  # Failed to start
    os.startfile(exe_path)
