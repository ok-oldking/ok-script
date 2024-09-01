from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from ok.gui.common.style_sheet import StyleSheet
from ok.gui.debug.LogWindow import LogWindow
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class InstallBar(QWidget):

    def __init__(self, config):
        super().__init__()

        self.layout = QHBoxLayout()
        self.version_label = QLabel(self.tr("Current Version:") + "v1.8.7")
        self.log_window = LogWindow(floating=False)

        self.layout.addWidget(self.log_window)
        self.setLayout(self.layout)
        StyleSheet.MESSAGE_WINDOW.apply(self)
