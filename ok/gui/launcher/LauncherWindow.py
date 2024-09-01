from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import SplitTitleBar

from ok.gui.common.config import isWin11
from ok.gui.common.style_sheet import StyleSheet
from ok.gui.debug.LogWindow import LogWindow
from ok.gui.launcher.InstallBar import InstallBar
from ok.logging.Logger import get_logger

logger = get_logger(__name__)

if isWin11():
    from qframelesswindow import AcrylicWindow as Window
else:
    from qframelesswindow import FramelessWindow as Window


class LauncherWindow(Window):

    def __init__(self, config):
        super().__init__()

        self.setTitleBar(SplitTitleBar(self))
        self.titleBar.raise_()

        self.setWindowTitle(config.get('gui_title'))
        self.icon = QIcon(config.get('gui_icon') or ":/icon/icon.ico")
        self.setWindowIcon(self.icon)
        self.resize(1000, 650)
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(4, 40, 4, 4)
        self.log_window = LogWindow(floating=False)

        self.install_bar = InstallBar(config)
        self.layout.addWidget(self.install_bar)

        self.layout.addWidget(self.log_window)
        self.setLayout(self.layout)
        StyleSheet.MESSAGE_WINDOW.apply(self)
