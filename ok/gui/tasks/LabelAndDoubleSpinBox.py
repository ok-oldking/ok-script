from qfluentwidgets import DoubleSpinBox

from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class LabelAndDoubleSpinBox(LabelAndWidget):

    def __init__(self, key: str, value, config):
        super().__init__(key)
        self.key = key
        self.config = config
        self.spin_box = DoubleSpinBox()
        self.update_value()
        self.spin_box.valueChanged.connect(self.value_changed)
        self.add_widget(self.spin_box)

    def update_value(self):
        self.spin_box.setValue(self.config.get(self.key))

    def value_changed(self, value):
        self.config[self.key] = value
