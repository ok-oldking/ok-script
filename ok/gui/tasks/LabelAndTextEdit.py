from PySide6.QtGui import QFontMetrics
from qfluentwidgets import TextEdit

from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndTextEdit(ConfigLabelAndWidget):

    def __init__(self, config_desc, config, key: str):
        super().__init__(config_desc, config, key)
        self.key = key
        self.text_edit = TextEdit()
        font = self.text_edit.font()
        font_metrics = QFontMetrics(font)
        row_height = font_metrics.lineSpacing()
        self.text_edit.setFixedHeight(row_height * 6)
        self.update_value()
        self.text_edit.textChanged.connect(self.value_changed)
        self.add_widget(self.text_edit, stretch=0)

    def update_value(self):
        value = self.config.get(self.key)
        self.text_edit.setText(value)
        self._update_width(value)

    def value_changed(self):
        value = self.text_edit.toPlainText()
        self.update_config(value)
        self._update_width(value)

    def _update_width(self, value):
        font_metrics = QFontMetrics(self.text_edit.font())
        lines = value.splitlines() or ["M" * 16]
        content_width = max(font_metrics.horizontalAdvance(line) for line in lines)
        self.text_edit.setFixedWidth(content_width * 2)
