import os

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from qfluentwidgets import FluentIcon, NavigationItemPosition, MSFluentWindow, InfoBar, InfoBarPosition

import ok.gui
from ok.config.Config import Config
from ok.gui.Communicate import communicate
from ok.gui.about.AboutTab import AboutTab
from ok.gui.debug.DebugTab import DebugTab
from ok.gui.settings.SettingTab import SettingTab
from ok.gui.start.StartTab import StartTab
from ok.gui.tasks.OneTimeTaskTab import OneTimeTaskTab
from ok.gui.tasks.TriggerTaskTab import TriggerTaskTab
from ok.gui.util.Alert import alert_error
from ok.gui.util.app import show_info_bar
from ok.gui.widget.StartLoadingDialog import StartLoadingDialog
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class Communicate(QObject):
    speak = Signal(str)


class MainWindow(MSFluentWindow):
    def __init__(self, config, icon, title, version, debug=False, about=None, exit_event=None):
        super().__init__()
        logger.info('main window __init__')
        self.main_window_config = Config('main_window', {'last_version': 'v0.0.0'})
        self.original_layout = None
        self.exit_event = exit_event
        self.start_tab = StartTab(exit_event)
        self.onetime_tab = None
        self.trigger_tab = None
        self.emulator_starting_dialog = None

        self.addSubInterface(self.start_tab, FluentIcon.PLAY, self.tr('Capture'))

        if len(ok.gui.executor.onetime_tasks) > 0:
            self.onetime_tab = OneTimeTaskTab()
            self.first_task_tab = self.onetime_tab
            self.addSubInterface(self.onetime_tab, FluentIcon.BOOK_SHELF, self.tr('Tasks'))
        if len(ok.gui.executor.trigger_tasks) > 0:
            self.trigger_tab = TriggerTaskTab()
            if self.first_task_tab is None:
                self.first_task_tab = self.trigger_tab
            self.addSubInterface(self.trigger_tab, FluentIcon.ROBOT, self.tr('Triggers'))

        if debug:
            debug_tab = DebugTab(config, exit_event)
            self.addSubInterface(debug_tab, FluentIcon.DEVELOPER_TOOLS, self.tr('Debug'),
                                 position=NavigationItemPosition.BOTTOM)

        if about:
            self.about_tab = AboutTab(icon, title, version, debug, about)
            self.addSubInterface(self.about_tab, FluentIcon.QUESTION, self.tr('About'),
                                 position=NavigationItemPosition.BOTTOM)
        else:
            self.about_tab = None

        setting_tab = SettingTab()
        self.addSubInterface(setting_tab, FluentIcon.SETTING, self.tr('Settings'),
                             position=NavigationItemPosition.BOTTOM)

        # Styling the tabs and content if needed, for example:
        dev = self.tr('Debug')
        release = self.tr('Release')
        self.setWindowTitle(f'{title} {version} {dev if debug else release}')

        communicate.executor_paused.connect(self.executor_paused)
        communicate.tab.connect(self.navigate_tab)

        # Create a context menu for the tray
        menu = QMenu()
        exit_action = menu.addAction(self.tr("Exit"))
        exit_action.triggered.connect(ok.gui.ok.quit)

        self.tray = QSystemTrayIcon(icon)

        # Set the context menu and show the tray icon
        self.tray.setContextMenu(menu)
        self.tray.show()

        # if ok.gui.device_manager.config.get("preferred") is None or self.onetime_tab is None:
        #     self.switchTo(self.start_tab)

        communicate.capture_error.connect(self.capture_error)
        communicate.notification.connect(self.show_notification)
        communicate.config_validation.connect(self.config_validation)
        communicate.starting_emulator.connect(self.starting_emulator)
        if self.about_tab is not None and version != self.main_window_config.get('last_version'):
            logger.info(f'first run show about tab last version:{self.main_window_config.get("last_version")}')
            self.main_window_config['last_version'] = version
            self.switchTo(self.about_tab)
        logger.info('main window __init__ done')

    def starting_emulator(self, done, error, seconds_left):
        if error:
            self.switchTo(self.start_tab)
            alert_error(error, True)
        if done:
            self.emulator_starting_dialog.close()
            return
        else:
            if self.emulator_starting_dialog is None:
                self.emulator_starting_dialog = StartLoadingDialog(seconds_left,
                                                                   self)
            else:
                self.emulator_starting_dialog.set_seconds_left(seconds_left)
            self.emulator_starting_dialog.show()

    def config_validation(self, message):
        title = self.tr('Error')
        InfoBar.error(
            title=title,
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,  # won't disappear automatically
            parent=self.window()
        )
        self.tray.showMessage(title, message)

    def show_notification(self, message, title=None, error=False, tray=False):
        show_info_bar(self.window(), message, title, error)

        if tray:
            self.tray.showMessage(title, message, QSystemTrayIcon.Critical if error else QSystemTrayIcon.Information,
                                  5000)

    def capture_error(self):
        self.show_notification(self.tr('Please check whether the game window is selected correctly!'),
                               self.tr('Capture Error'), error=True)

    def navigate_tab(self, index):
        logger.debug(f'navigate_tab {index}')
        if index == "start":
            self.switchTo(self.start_tab)
        elif index == "onetime" and self.onetime_tab is not None:
            self.switchTo(self.onetime_tab)
        elif index == "trigger" and self.trigger_tab is not None:
            self.switchTo(self.trigger_tab)

    def executor_paused(self, paused):
        self.show_notification(self.tr("Start Success.") if not paused else self.tr("Pause Success."))

    def btn_clicked(self):
        self.comm.speak.emit("Hello, PySide6 with parameters!")

    def closeEvent(self, event):
        if ok.gui.ok.exit_event.is_set():
            logger.info("Window closed exit_event.is_set")
            event.accept()
            return
        else:
            logger.info("Window closed exit_event.is not set")
            ok.gui.ok.quit()
            event.accept()
