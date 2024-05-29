from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from qfluentwidgets import FluentIcon, NavigationItemPosition, MSFluentWindow, InfoBar, InfoBarPosition, MessageBox

import ok.gui
from ok.capture.windows.dump import dump_threads
from ok.gui.Communicate import communicate
from ok.gui.about.AboutTab import AboutTab
from ok.gui.start.StartTab import StartTab
from ok.gui.tasks.OneTimeTaskTab import OneTimeTaskTab
from ok.gui.tasks.TriggerTaskTab import TriggerTaskTab
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class Communicate(QObject):
    speak = Signal(str)


class MainWindow(MSFluentWindow):
    def __init__(self, icon, debug=False, about=None, exit_event=None):
        super().__init__()
        self.exit_event = exit_event
        self.start_tab = StartTab()
        self.second_tab = None
        self.onetime_tab = None
        self.trigger_tab = None
        self.addSubInterface(self.start_tab, FluentIcon.PLAY, self.tr('Start'))
        if len(ok.gui.executor.onetime_tasks) > 0:
            self.onetime_tab = OneTimeTaskTab()
            self.second_tab = self.onetime_tab
            self.addSubInterface(self.onetime_tab, FluentIcon.BOOK_SHELF, self.tr('Tasks'))
        if len(ok.gui.executor.trigger_tasks) > 0:
            self.trigger_tab = TriggerTaskTab()
            if self.second_tab is None:
                self.second_tab = self.trigger_tab
            self.addSubInterface(self.trigger_tab, FluentIcon.ROBOT, self.tr('Triggers'))
        # if debug:
        #     debug_tab = DebugTab()
        #     self.addSubInterface(debug_tab, FluentIcon.COMMAND_PROMPT, self.tr('Debug'))
        # ... Add other tabs similarly
        if about:
            about_tab = AboutTab(about)
            self.addSubInterface(about_tab, FluentIcon.QUESTION, self.tr('About'),
                                 position=NavigationItemPosition.BOTTOM)
        # Styling the tabs and content if needed, for example:
        self.setWindowTitle("Close Event Example")

        communicate.executor_paused.connect(self.executor_paused)
        communicate.tab.connect(self.navigate_tab)

        self.shortcut = QShortcut(QKeySequence("Ctrl+Alt+D"), self)
        self.shortcut.activated.connect(dump_threads)

        # Create a context menu for the tray
        menu = QMenu()
        exit_action = menu.addAction(self.tr("Exit"))
        exit_action.triggered.connect(ok.gui.ok.quit)

        self.tray = QSystemTrayIcon(icon)

        # Set the context menu and show the tray icon
        self.tray.setContextMenu(menu)
        self.tray.show()

        communicate.capture_error.connect(self.capture_error)
        communicate.notification.connect(self.show_notification)
        communicate.config_validation.connect(self.config_validation)

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

    def show_notification(self, message, title=None, error=None):
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
        if title is None:
            title = self.title
        self.tray.showMessage(title, message)

    def capture_error(self):
        self.show_notification(self.tr('Please check whether the game window is selected correctly!'),
                               self.tr('Capture Error'), error=True)

    def navigate_tab(self, index):
        if index == "start":
            self.switchTo(self.start_tab)
        elif index == "second":
            self.switchTo(self.second_tab)
        elif index == "onetime" and self.onetime_tab is not None:
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
        if ok.gui.ok.exit_event.is_set():
            event.accept()
            return
        title = self.tr('Exit')
        content = self.tr(
            "Are you sure you want to exit the app?")
        w = MessageBox(title, content, self.window())
        w.setContentCopyable(True)
        if w.exec():
            logger.info("Window closed")
            ok.gui.ok.quit()
            event.accept()
        else:
            event.ignore()
