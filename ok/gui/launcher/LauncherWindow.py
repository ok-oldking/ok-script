from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import SplitTitleBar

from ok import Logger
from ok import get_path_relative_to_exe
from ok.gui.common.style_sheet import StyleSheet
from ok.gui.launcher.RunBar import RunBar
from ok.gui.launcher.UpdateBar import UpdateBar
from ok.gui.widget.BaseWindow import BaseWindow

logger = Logger.get_logger(__name__)


class LauncherWindow(BaseWindow):

    def __init__(self, config, updater, exit_event):
        super().__init__()
        self._lightBackgroundColor = QColor(240, 244, 249)
        self._darkBackgroundColor = QColor(32, 32, 32)
        self.exit_event = exit_event
        self.updater = updater
        self.setTitleBar(SplitTitleBar(self))
        self.titleBar.raise_()

        self.setWindowTitle(QCoreApplication.translate('app', '{} Launcher').format(config.get('gui_title')))
        self.icon = QIcon(get_path_relative_to_exe(config.get('gui_icon')) or ":/icon/icon.ico")
        self.setWindowIcon(self.icon)
        self.resize(600, 500)
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(4, 40, 4, 4)

        self.install_bar = UpdateBar(config, self.updater)
        self.layout.addWidget(self.install_bar)

        self.run_bar = RunBar(self.updater)
        self.layout.addWidget(self.run_bar)

        self.setLayout(self.layout)
        # FluentStyleSheet.FLUENT_WINDOW.apply(self)
        StyleSheet.TAB.apply(self)
        # StyleSheet.MESSAGE_WINDOW.apply(self)

    def closeEvent(self, event):
        logger.info("Window closed set exit_event")
        self.exit_event.set()
        event.accept()
