from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication
from qfluentwidgets import LineEdit

from ok.ui.qt.common.design_system import DesignToken, control_width
from ok.ui.qt.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


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


class LabelAndLineEdit(ConfigLabelAndWidget):
    MIN_INPUT_WIDTH = DesignToken.CONTROL_WIDTH
    HORIZONTAL_PADDING = 32

    def __init__(self, config_desc, config, key: str, options=None):
        super().__init__(config_desc, config, key)
        self.key = key
        options = options or {}
        self.minimum_input_width = options.get('minimum_width', self.MIN_INPUT_WIDTH)
        self.maximum_input_width = options.get('maximum_width')
        self.line_edit = LineEdit()
        self.line_edit.setMinimumWidth(self.minimum_input_width)
        self.line_edit._is_hotkey_input = True
        ensure_global_filter()
        self.update_value()
        self.line_edit.textChanged.connect(self.value_changed)
        self.add_widget(self.line_edit, stretch=0)

    def update_value(self):
        value = self.config.get(self.key)
        self.line_edit.setText(value)
        self._update_width(value)

    def value_changed(self, value):
        self.update_config(value)
        self._update_width(value)

    def _update_width(self, value):
        font_metrics = QFontMetrics(self.line_edit.font())
        content_width = font_metrics.horizontalAdvance(value or "") + self.HORIZONTAL_PADDING
        width = max(self.minimum_input_width, control_width(content_width))
        if self.maximum_input_width is not None:
            width = min(width, self.maximum_input_width)
        self.line_edit.setFixedWidth(width)
