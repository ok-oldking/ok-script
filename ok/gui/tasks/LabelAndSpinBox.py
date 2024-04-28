from qfluentwidgets import SpinBox

from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndSpinBox(ConfigLabelAndWidget):

    def __init__(self, config, config_desc, key: str):
        super().__init__(config_desc, key)
        self.key = key
        self.config = config
        self.spin_box = SpinBox()
        self.update_value()
        self.spin_box.valueChanged.connect(self.value_changed)
        self.add_widget(self.spin_box)

    def update_value(self):
        self.spin_box.setValue(self.config.get(self.key))

    def value_changed(self, value):
        self.config[self.key] = value
