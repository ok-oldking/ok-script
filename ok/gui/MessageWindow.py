import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import BodyLabel, PushButton
from qframelesswindow import FramelessWindow, StandardTitleBar

import ok.gui
from ok.gui.common.style_sheet import StyleSheet
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class MessageWindow(FramelessWindow):
    def __init__(self, icon, title, message, exit_event=None):
        super().__init__()
        self.exit_event = exit_event
        self.message = message
        self.title_bar = StandardTitleBar(self)
        self.title_bar.maxBtn.hide()
        self.title_bar.minBtn.hide()
        self.setTitleBar(self.title_bar)
        self.setFixedSize(500, 200)
        self.setWindowTitle(title)
        self.setWindowIcon(icon)
        self.message_label = BodyLabel(message)
        self.message_label.setWordWrap(True)
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setAlignment(Qt.AlignCenter)
        self.setLayout(self.vBoxLayout)
        self.vBoxLayout.addWidget(self.message_label, 1, Qt.AlignVCenter)
        self.confirm_button = PushButton(self.tr('Confirm'))
        self.vBoxLayout.addWidget(self.confirm_button, 0, Qt.AlignCenter)
        self.confirm_button.clicked.connect(self.quit)
        self.confirm_button.setMaximumWidth(150)

        StyleSheet.MESSAGE_WINDOW.apply(self)
        self.activateWindow()

    def closeEvent(self, event):
        ok.gui.ok.quit()
        event.accept()

    def quit(self):
        ok.gui.ok.quit()
