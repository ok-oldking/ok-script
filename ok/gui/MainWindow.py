from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMessageBox
from qfluentwidgets import FluentIcon, NavigationItemPosition, MSFluentWindow, InfoBar, InfoBarPosition

import ok.gui
from ok.gui.Communicate import communicate
from ok.gui.about.AboutTab import AboutTab
from ok.gui.debug.DebugTab import DebugTab
from ok.gui.start.StartTab import StartTab
from ok.gui.tasks.TaskTab import TaskTab
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
        self.addSubInterface(self.start_tab, FluentIcon.PLAY, self.tr('Start'))
        if len(ok.gui.executor.onetime_tasks) > 0:
            task_tab = TaskTab()
            self.second_tab = task_tab
            self.addSubInterface(task_tab, FluentIcon.BOOK_SHELF, self.tr('OneTimeTask'))
        if len(ok.gui.executor.trigger_tasks) > 0:
            trigger_task_tab = TriggerTaskTab()
            if self.second_tab is None:
                self.second_tab = trigger_task_tab
            self.addSubInterface(trigger_task_tab, FluentIcon.ROBOT, self.tr('TriggerTask'))
        if debug:
            debug_tab = DebugTab()
            self.addSubInterface(debug_tab, FluentIcon.COMMAND_PROMPT, self.tr('Debug'))
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
        if index == 0:
            self.switchTo(self.start_tab)
        elif index == 1:
            self.switchTo(self.second_tab)

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
