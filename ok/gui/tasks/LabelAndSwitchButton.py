from qfluentwidgets import SwitchButton

from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndSwitchButton(ConfigLabelAndWidget):

    def __init__(self, config_desc, config, key: str):
        super().__init__(config_desc, config, key)
        self.key = key
        self.switch_button = SwitchButton()
        self.switch_button.setOnText(self.tr('Yes'))
        self.switch_button.setOffText(self.tr('No'))
        self.update_value()
        self.switch_button.checkedChanged.connect(self.check_changed)
        self.add_widget(self.switch_button)

    def update_value(self):
        self.switch_button.setChecked(self.config.get(self.key))

    def check_changed(self, checked):
        self.update_config(checked)
