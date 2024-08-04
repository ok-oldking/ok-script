import os
from ctypes import windll, wintypes

from PySide6.QtCore import Qt, Signal
from _ctypes import byref
from qfluentwidgets import FluentIcon, SettingCard, PushButton

import ok
from ok.gui.Communicate import communicate
from ok.gui.debug.DebugTab import capture
from ok.gui.widget.StatusBar import StatusBar
from ok.logging.Logger import get_logger
from ok.util.Handler import Handler

logger = get_logger(__name__)


class StartCard(SettingCard):
    show_choose_hwnd = Signal()

    def __init__(self, exit_event):
        super().__init__(FluentIcon.PLAY, f'{self.tr("Start")} {ok.gui.app.title}', ok.gui.app.title)
        self.hBoxLayout.setAlignment(Qt.AlignVCenter)
        self.status_bar = StatusBar("test")
        self.status_bar.clicked.connect(self.status_clicked)

        self.hBoxLayout.addWidget(self.status_bar, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.capture_button = PushButton(FluentIcon.ZOOM, self.tr("Test Capture"), self)
        self.hBoxLayout.addWidget(self.capture_button, 0, Qt.AlignRight)
        self.capture_button.clicked.connect(capture)

        self.hBoxLayout.addSpacing(16)

        self.start_button = PushButton(FluentIcon.PLAY, self.tr("Start"), self)
        self.hBoxLayout.addWidget(self.start_button, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.update_status()
        self.start_button.clicked.connect(self.clicked)
        communicate.executor_paused.connect(self.update_status)
        communicate.window.connect(self.update_status)
        communicate.task.connect(self.update_task)

        self.handler = Handler(exit_event, "StartCard")
        self.handler.post(self.bind_hot_keys)
        self.handler.post(self.check_hotkey, 0.1)

    def status_clicked(self):
        if not ok.gui.executor.paused:
            if ok.gui.executor.current_task:
                communicate.tab.emit("onetime")
            elif ok.gui.executor.active_trigger_task_count():
                communicate.tab.emit("trigger")
            else:
                communicate.tab.emit("start")
            self.status_bar.show()

    def clicked(self):
        if not ok.gui.executor.paused:
            ok.gui.executor.pause()
        else:
            ok.gui.app.start_controller.start()

    def update_task(self, task):
        self.update_status()

    def update_status(self):
        if ok.gui.executor.paused:
            device = ok.gui.device_manager.get_preferred_device()
            if device and not device['connected'] and device.get('full_path'):
                self.start_button.setText(self.tr("Start Game") + '(F9)')
            else:
                self.start_button.setText(self.tr("Start") + '(F9)')
            self.start_button.setIcon(FluentIcon.PLAY)
            self.status_bar.hide()
        else:
            self.start_button.setText(self.tr("Pause") + '(F9)')
            self.start_button.setIcon(FluentIcon.PAUSE)
            if not ok.gui.executor.connected():
                self.status_bar.setTitle(self.tr("Game Window Disconnected"))
                self.status_bar.setState(True)
            elif active_trigger_task_count := ok.gui.executor.active_trigger_task_count():
                if not ok.gui.executor.can_capture():
                    self.status_bar.setTitle(self.tr('Paused: PC Game Window Must Be in Front!'))
                    self.status_bar.setState(True)
                else:
                    self.status_bar.setTitle(
                        self.tr("Running") + ": " + str(active_trigger_task_count) + ' ' + self.tr("Trigger Tasks"))
                    self.status_bar.setState(False)
            elif task := ok.gui.executor.current_task:
                if not ok.gui.executor.can_capture():
                    self.status_bar.setTitle(self.tr('Paused: PC Game Window Must Be in Front!'))
                    self.status_bar.setState(True)
                else:
                    self.status_bar.setTitle(self.tr("Running") + ": " + task.name)
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
