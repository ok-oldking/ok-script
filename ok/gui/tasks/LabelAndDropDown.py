from qfluentwidgets import ComboBox

from ok import find_index_in_list, og
from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndDropDown(ConfigLabelAndWidget):

    def __init__(self, config_desc, options, config, key: str):
        super().__init__(config_desc, config, key)
        self.key = key
        self.tr_dict = {}
        self.tr_options = []
        for option in options:
            tr = og.app.tr(option)
            self.tr_options.append(tr)
            self.tr_dict[tr] = option
        self.combo_box = ComboBox()
        self.combo_box.addItems(self.tr_options)
        self.combo_box.setCurrentIndex(find_index_in_list(options, self.config.get(self.key), -1))
        self.combo_box.setMinimumWidth(210)
        self.combo_box.currentTextChanged.connect(self.text_changed)
        self.add_widget(self.combo_box)

    def text_changed(self, text):
        option = self.tr_dict.get(text)
        self.update_config(option)

    def update_value(self):
        self.combo_box.setText(og.app.tr(self.config.get(self.key)))
