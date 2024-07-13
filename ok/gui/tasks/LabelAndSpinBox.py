from qfluentwidgets import SpinBox

from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndSpinBox(ConfigLabelAndWidget):

    def __init__(self, config_desc, config, key: str):
        super().__init__(config_desc, config, key)
        self.key = key
        self.spin_box = SpinBox()
        self.spin_box.setRange(1, 99999999)
        self.spin_box.setFixedWidth(180)
        self.update_value()
        self.spin_box.valueChanged.connect(self.value_changed)
        self.add_widget(self.spin_box)

    def update_value(self):
        self.spin_box.setValue(self.config.get(self.key))

    def value_changed(self, value):
        self.update_config(value)
