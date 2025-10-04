from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QVBoxLayout, QApplication
from qfluentwidgets import BodyLabel, PushButton, SplitTitleBar
from qframelesswindow import StandardTitleBar

from ok import Logger, og
from ok.gui.Communicate import communicate
from ok.gui.common.style_sheet import StyleSheet
from ok.gui.widget.BaseWindow import BaseWindow

logger = Logger.get_logger(__name__)


class MessageWindow(BaseWindow):
    def __init__(self, icon, title, message, exit_event=None):
        super().__init__()
        self.exit_event = exit_event
        self.message = message
        self.setTitleBar(SplitTitleBar(self))
        self.titleBar.raise_()
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

        # StyleSheet.MESSAGE_WINDOW.apply(self)
        # self.activateWindow()
        logger.info(f'MessageWindow init {message}')

    def closeEvent(self, event):
        logger.info('closeEvent')
        og.app.quit()

    def quit(self):
        logger.info('quit')
        og.app.quit()
        QApplication.quit()

    def showEvent(self, event):
        if event.type() == QEvent.Show:
            logger.info("MessageWindow has fully displayed")
            communicate.start_success.emit()
        super().showEvent(event)
