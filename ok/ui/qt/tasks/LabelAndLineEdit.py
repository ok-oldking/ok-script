from PySide6.QtGui import QFontMetrics
from qfluentwidgets import LineEdit

from ok.gui.common.design_system import DesignToken, control_width
from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


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
