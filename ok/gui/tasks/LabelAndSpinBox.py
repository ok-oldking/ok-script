from qfluentwidgets import SpinBox

from ok.gui.common.design_system import DesignToken
from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndSpinBox(ConfigLabelAndWidget):

    def __init__(self, config_desc, config, key: str, config_type=None):
        super().__init__(config_desc, config, key)
        self.key = key
        self.spin_box = SpinBox()
        default_value = config.get_default(key)
        if isinstance(config_type, dict) and 'min' in config_type:
            range_min = config_type['min']
        elif not default_value:
            range_min = 0
        elif default_value < 0:
            range_min = -999999
        else:
            range_min = 1
        range_max = config_type.get('max', 99999999) if isinstance(config_type, dict) else 99999999
        self.spin_box.setRange(range_min, range_max)
        self.spin_box.setFixedWidth(DesignToken.CONTROL_WIDTH)
        self.update_value()
        self.spin_box.valueChanged.connect(self.value_changed)
        self.add_widget(self.spin_box)

    def update_value(self):
        self.spin_box.setValue(self.config.get(self.key))

    def value_changed(self, value):
        self.update_config(value)
