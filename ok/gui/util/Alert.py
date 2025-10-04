from PySide6.QtWidgets import QMessageBox

from ok.gui.Communicate import communicate


def show_alert(title, message):
    # Create a QMessageBox
    msg = QMessageBox()

    # Set the title and message
    msg.setWindowTitle(title)
    msg.setText(message)

    from ok import og
    msg.setWindowIcon(og.app.icon)

    # Add a confirm button
    msg.setStandardButtons(QMessageBox.Ok)

    # Show the message box
    msg.exec()


def alert_info(message, tray=False, show_tab=None):
    communicate.notification.emit(None, message, False, tray, show_tab)


def alert_error(message, tray=False, show_tab=None):
    communicate.notification.emit(None, message, True, tray, show_tab)
