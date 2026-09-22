from ctypes import windll, wintypes

from PySide6.QtCore import Qt, Signal
from _ctypes import byref
from qfluentwidgets import FluentIcon, PrimaryPushButton, SettingCard, PushButton

from ok import Handler
from ok import Logger
from ok import og
from ok.ui.qt.Communicate import communicate
from ok.ui.qt.widget.StatusBar import StatusBar

logger = Logger.get_logger(__name__)


class StartCard(SettingCard):
    show_choose_hwnd = Signal()
    hotkey_changed = Signal()

    def __init__(self, exit_event):
        super().__init__(og.config.get('gui_icon'), og.app.title, og.app.version)
        self.basic_options = og.executor.basic_options

        self.iconLabel.setFixedSize(30, 30)
        self.hBoxLayout.setAlignment(Qt.AlignVCenter)
        self.status_bar = StatusBar("test")
        self.status_bar.clicked.connect(self.status_clicked)
        self.hBoxLayout.addWidget(self.status_bar, 0, Qt.AlignLeft)
        self.hBoxLayout.addSpacing(6)

        self.capture_button = PushButton(FluentIcon.ZOOM, self.tr("Capture"), self)
        self.hBoxLayout.addWidget(self.capture_button, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(6)

        self.refresh_button = PushButton(FluentIcon.SYNC, self.tr("Refresh"), self)
        self.hBoxLayout.addWidget(self.refresh_button, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(6)

        self.start_button = PrimaryPushButton(FluentIcon.PAUSE, self.tr("Pause"), self)
        self.hBoxLayout.addWidget(self.start_button, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(6)

        self.launch_button = PushButton(FluentIcon.PLAY, self.tr("Start Game"), self)
        self.hBoxLayout.addWidget(self.launch_button, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(20)

        self.hotkey_changed.connect(self.update_status)
        self.update_status()
        self.start_button.clicked.connect(self.toggle_pause)
        self.launch_button.clicked.connect(self.launch_clicked)
        communicate.executor_paused.connect(self.update_status)
        communicate.window.connect(self.update_status)
        communicate.adb_devices.connect(self.update_status)
        communicate.starting_emulator.connect(self.update_status)
        communicate.task.connect(self.update_task)

        self.handler = Handler(exit_event, "StartCard")
        self.current_hotkey = "UNINIT"
        self.handler.post(self.check_hotkey, 0.1)
        logger.debug('basic_options.start/stop: {}'.format(self.basic_options.get('Start/Stop')))

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
    def toggle_pause():
        if og.executor.paused:
            # Resume shares the full start flow: a silent fast-resume when the
            # game is already connected, launch+connect when it is not. Once
            # the game is up it never touches the game process again.
            og.app.start_controller.start()
        else:
            og.executor.pause()

    @staticmethod
    def launch_clicked():
        og.app.start_controller.start()

    def update_task(self, task):
        self.update_status()

    def update_status(self):
        hotkey = self.basic_options.get('Start/Stop')
        suffix = f'({hotkey})' if hotkey and hotkey != 'None' else ''
        starting = bool(getattr(og.app.start_controller, 'starting', False))

        device = og.device_manager.get_preferred_device()
        connected = bool(device) and bool(device.get('connected'))
        can_launch = bool(device) and not connected and bool(device.get('full_path'))

        # The pause/resume control belongs to the game session: it appears
        # once a game is connected and disappears when the game exits.
        # Launching is the pre-session action.
        self.start_button.setVisible(connected)
        self.launch_button.setVisible(not connected)
        self.launch_button.setEnabled(can_launch and not starting)

        if og.executor.paused:
            self.start_button.setText(self.tr("Resume") + suffix)
            self.start_button.setIcon(FluentIcon.PLAY)
            self.status_bar.hide()
        else:
            self.start_button.setText(self.tr("Pause") + suffix)
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
        new_hotkey = self.basic_options.get('Start/Stop')
        if new_hotkey != self.current_hotkey:
            self.rebind_hotkey(new_hotkey)
            self.current_hotkey = new_hotkey
            self.hotkey_changed.emit()

        msg = wintypes.MSG()
        if windll.user32.PeekMessageW(byref(msg), None, 0, 0, 1):
            if msg.message == 0x0312:  # WM_HOTKEY
                logger.debug(f'hotkey pressed {msg}')
                if msg.wParam == 999:
                    self.toggle_pause()

        self.handler.post(self.check_hotkey, 0.1)

    def rebind_hotkey(self, hotkey):
        windll.user32.UnregisterHotKey(None, 999)
        vk_map = {'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B}

        if hotkey and hotkey != 'None' and hotkey in vk_map:
            if not windll.user32.RegisterHotKey(None, 999, 0, vk_map[hotkey]):
                logger.error(f"Failed to register hotkey {hotkey}")
        else:
            logger.debug(f"Hotkey disabled or invalid: {hotkey}")
