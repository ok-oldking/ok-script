from PySide6.QtWidgets import QMessageBox

import ok
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


def show_alert(title, message):
    # Create a QMessageBox
    msg = QMessageBox()

    # Set the title and message
    msg.setWindowTitle(title)
    msg.setText(message)

    msg.setWindowIcon(ok.gui.app.icon)

    # Add a confirm button
    msg.setStandardButtons(QMessageBox.Ok)

    # Show the message box
    msg.exec()


def alert_info(message, tray=False):
    communicate.notification.emit(None, message, False, tray)


def alert_error(message, tray=False):
    logger.error(message)
    communicate.notification.emit(None, message, True, tray)
