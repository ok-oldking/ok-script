from qfluentwidgets import SwitchButton

from ok.gui.tasks.LabelAndWidget import LabelAndWidget


class LabelAndSwitchButton(LabelAndWidget):

    def __init__(self, key: str, checked, config):
        super().__init__(key)
        self.key = key
        self.config = config
        self.switch_button = SwitchButton()
        self.switch_button.setChecked(checked)
        self.switch_button.checkedChanged.connect(self.check_changed)
        self.add_widget(self.switch_button)

    def check_changed(self, checked):
        self.config[self.key] = checked
