from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMessageBox
from qfluentwidgets import FluentIcon, NavigationItemPosition, MSFluentWindow, InfoBar, InfoBarPosition

import ok.gui
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
    def __init__(self, debug=False, about=None, exit_event=None):
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
        reply = QMessageBox.question(self, 'Window Close', 'Are you sure you want to close the window?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.exit_event.set()
            event.accept()
            logger.info("Window closed")  # Place your code here
        else:
            event.ignore()
