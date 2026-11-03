from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QVBoxLayout, QApplication

from ok import Logger, og
from ok.ui.qt.Communicate import communicate
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import theme
from ok.ui.qt.kit.window import KitWindow

logger = Logger.get_logger(__name__)


class MessageWindow(KitWindow):
    """A small window that shows one message and quits the app on Confirm."""

    def __init__(self, icon, title, message, exit_event=None):
        super().__init__()
        self.exit_event = exit_event
        self.message = message
        self.setFixedSize(520, 240)
        self.setWindowTitle(title)
        self.setWindowIcon(icon)
        self.message_label = Label(message, "body", word_wrap=True)
        self.message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.confirm_button = Button(self.tr('Confirm'), variant="primary")
        self.confirm_button.clicked.connect(self.quit)
        self.vBoxLayout = QVBoxLayout(self.body)
        self.vBoxLayout.setContentsMargins(28, 16, 28, 24)
        self.vBoxLayout.setSpacing(16)
        self.vBoxLayout.addWidget(self.message_label, 1, Qt.AlignVCenter)
        self.vBoxLayout.addWidget(self.confirm_button, 0, Qt.AlignRight)
        theme.install(self)
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
