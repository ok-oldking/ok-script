from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtWidgets import QApplication


class GlobalMouseButtonFilter(QObject):
    """
    Application-level event filter for XButton1 / XButton2 (mouse4 / mouse5).
    Routes mouse4/mouse5 exclusively to the widget that currently holds keyboard focus,
    preventing accidental input via hover or triggering OS/browser navigation actions.
    """

    def eventFilter(self, watched, event):
        evt_type = event.type()
        if evt_type in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.NonClientAreaMouseButtonPress,
            QEvent.Type.NonClientAreaMouseButtonRelease,
        ):
            btn = event.button()
            if btn in (Qt.MouseButton.XButton1, Qt.MouseButton.XButton2):
                focused = QApplication.focusWidget()
                if focused is not None and getattr(focused, '_is_hotkey_input', False):
                    if evt_type == QEvent.Type.MouseButtonPress:
                        key_name = 'mouse4' if btn == Qt.MouseButton.XButton1 else 'mouse5'
                        focused.setText(key_name)
                        focused.setFocus(Qt.FocusReason.MouseFocusReason)
                    event.accept()
                    return True
        return super().eventFilter(watched, event)


_global_mouse_filter = None


def ensure_global_filter():
    global _global_mouse_filter
    app = QApplication.instance()
    if app is not None and _global_mouse_filter is None:
        _global_mouse_filter = GlobalMouseButtonFilter(app)
        app.installEventFilter(_global_mouse_filter)
