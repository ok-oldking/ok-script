from ok.core.events import communicate


def alert_info(message, tray=False, show_tab=None):
    communicate.notification.emit(message, None, False, tray, show_tab, None, None)


def alert_error(message, tray=False, show_tab=None):
    communicate.notification.emit(message, None, True, tray, show_tab, None, None)
