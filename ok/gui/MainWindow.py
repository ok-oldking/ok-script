import os
import sys

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from qfluentwidgets import FluentIcon, NavigationItemPosition, MSFluentWindow, InfoBar, InfoBarPosition, MessageBox

import ok.gui
from ok.gui.Communicate import communicate
from ok.gui.about.AboutTab import AboutTab
from ok.gui.debug.DebugTab import DebugTab
from ok.gui.start.StartTab import StartTab
from ok.gui.tasks.OneTimeTaskTab import OneTimeTaskTab
from ok.gui.tasks.TriggerTaskTab import TriggerTaskTab
from ok.gui.util.Alert import alert_error
from ok.gui.widget.StartLoadingDialog import StartLoadingDialog
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class Communicate(QObject):
    speak = Signal(str)


class MainWindow(MSFluentWindow):
    def __init__(self, config, icon, title, version, debug=False, about=None, exit_event=None):
        super().__init__()
        self.original_layout = None
        self.exit_event = exit_event
        self.start_tab = StartTab()
        self.first_tab = None
        self.onetime_tab = None
        self.trigger_tab = None
        self.emulator_starting_dialog = None

        if len(ok.gui.executor.onetime_tasks) > 0:
            self.onetime_tab = OneTimeTaskTab()
            self.first_tab = self.onetime_tab
            self.addSubInterface(self.onetime_tab, FluentIcon.BOOK_SHELF, self.tr('Tasks'))
        if len(ok.gui.executor.trigger_tasks) > 0:
            self.trigger_tab = TriggerTaskTab()
            if self.first_tab is None:
                self.first_tab = self.trigger_tab
            self.addSubInterface(self.trigger_tab, FluentIcon.ROBOT, self.tr('Triggers'))
        # if debug:
        #     debug_tab = DebugTab()
        #     self.addSubInterface(debug_tab, FluentIcon.COMMAND_PROMPT, self.tr('Debug'))
        # ... Add other tabs similarly
        self.addSubInterface(self.start_tab, FluentIcon.PLAY, self.tr('Capture'))

        if debug:
            debug_tab = DebugTab(config, exit_event)
            self.addSubInterface(debug_tab, FluentIcon.DEVELOPER_TOOLS, self.tr('Debug'),
                                 position=NavigationItemPosition.BOTTOM)

        if about:
            about_tab = AboutTab(icon, title, version, debug, about)
            self.addSubInterface(about_tab, FluentIcon.QUESTION, self.tr('About'),
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

        if ok.gui.device_manager.get_preferred_device() is not None and self.onetime_tab is not None:
            self.switchTo(self.onetime_tab)

        communicate.capture_error.connect(self.capture_error)
        communicate.notification.connect(self.show_notification)
        communicate.config_validation.connect(self.config_validation)
        communicate.starting_emulator.connect(self.starting_emulator)

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
        bar = InfoBar.error if error else InfoBar.info
        if title is None:
            title = f"{self.tr('Error') if error else 'Info'}:"
        bar(
            title=title,
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,  # won't disappear automatically
            parent=self.window()
        )
        if tray:
            self.tray.showMessage(title, message)

    def capture_error(self):
        self.show_notification(self.tr('Please check whether the game window is selected correctly!'),
                               self.tr('Capture Error'), error=True)

    def navigate_tab(self, index):
        if index == "start":
            self.switchTo(self.start_tab)
        elif index == "first":
            self.switchTo(self.first_tab)
        elif index == "first" and self.onetime_tab is not None:
            self.switchTo(self.onetime_tab)
        elif index == "trigger" and self.trigger_tab is not None:
            self.switchTo(self.trigger_tab)

    def executor_paused(self, paused):
        if not paused:
            InfoBar.info(
                title="",
                content=self.tr(
                    "Start Success."),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,  # won't disappear automatically
                parent=self
            )

    def btn_clicked(self):
        self.comm.speak.emit("Hello, PySide6 with parameters!")

    def closeEvent(self, event):
        # Create a message box that asks the user if they really want to close the window
        if sys.platform == 'win32' and 'shutdown' in os.environ.get('SESSIONNAME', '').lower():
            logger.info("system shutting down")
            ok.gui.ok.quit()
            event.accept()
            return

        if ok.gui.ok.exit_event.is_set():
            event.accept()
            return
        title = self.tr('Exit')
        content = self.tr("Are you sure you want to exit the app?")
        w = MessageBox(title, content, self.window())
        if w.exec():
            logger.info("Window closed")
            ok.gui.ok.quit()
            event.accept()
        else:
            event.ignore()
