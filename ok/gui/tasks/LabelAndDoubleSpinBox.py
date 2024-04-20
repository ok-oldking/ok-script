from qfluentwidgets import DoubleSpinBox

from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class LabelAndDoubleSpinBox(LabelAndWidget):

    def __init__(self, key: str, value, config):
        super().__init__(key)
        self.key = key
        self.config = config
        self.spin_box = DoubleSpinBox()
        self.spin_box.setValue(value)
        self.spin_box.valueChanged.connect(self.value_changed)
        self.add_widget(self.spin_box)

    def value_changed(self, value):
        self.config[self.key] = value
