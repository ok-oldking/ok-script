from qfluentwidgets import SpinBox, PushButton

from ok import communicate
from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndGlobal(ConfigLabelAndWidget):

    def __init__(self, config_desc, config, key: str):
        super().__init__(config_desc, config, key)
        self.key = key
        self.config = config
        self.config_button = PushButton(self.tr('Go to Config'))
        self.config_button.clicked.connect(self.value_changed)
        self.add_widget(self.config_button, stretch=0)

    def value_changed(self):
        communicate.global_config.emit(self.key)
