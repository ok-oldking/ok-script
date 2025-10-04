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
        self.add_widget(self.text_edit)

    def update_value(self):
        self.text_edit.setText(self.config.get(self.key))

    def value_changed(self):
        self.update_config(self.text_edit.toPlainText())
