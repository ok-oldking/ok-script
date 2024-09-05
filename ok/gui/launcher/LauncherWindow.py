from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import SplitTitleBar

from ok.gui.Communicate import communicate
from ok.gui.common.config import isWin11
from ok.gui.common.style_sheet import StyleSheet
from ok.gui.debug.LogWindow import LogWindow
from ok.gui.launcher.RunBar import RunBar
from ok.gui.launcher.UpdateBar import UpdateBar
from ok.gui.util.app import show_info_bar
from ok.logging.Logger import get_logger
from ok.update.GitUpdater import GitUpdater

logger = get_logger(__name__)

if isWin11():
    from qframelesswindow import AcrylicWindow as Window
else:
    from qframelesswindow import FramelessWindow as Window


class LauncherWindow(Window):

    def __init__(self, config, exit_event):
        super().__init__()
        self.exit_event = exit_event

        self.updater = GitUpdater(config, exit_event)

        self.setTitleBar(SplitTitleBar(self))
        self.titleBar.raise_()

        self.setWindowTitle(config.get('gui_title'))
        self.icon = QIcon(config.get('gui_icon') or ":/icon/icon.ico")
        self.setWindowIcon(self.icon)
        self.resize(1000, 650)
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(4, 40, 4, 4)
        self.log_window = LogWindow(floating=False)

        self.layout.addWidget(self.log_window)

        self.install_bar = UpdateBar(config, self.updater)
        self.layout.addWidget(self.install_bar)

        self.run_bar = RunBar(self.updater)
        self.layout.addWidget(self.run_bar)

        self.setLayout(self.layout)
        communicate.notification.connect(self.show_notification)
        StyleSheet.MESSAGE_WINDOW.apply(self)

    def show_notification(self, message, title=None, error=False, tray=False):
        show_info_bar(self.window(), message, title, error)

    def closeEvent(self, event):
        logger.info("Window closed set exit_event")
        self.exit_event.set()
        event.accept()
