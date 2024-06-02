from qfluentwidgets import ComboBox

from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget


class LabelAndDropDown(ConfigLabelAndWidget):

    def __init__(self, task, options, key: str):
        super().__init__(task, key)
        self.key = key
        self.combo_box = ComboBox()
        self.combo_box.addItems(options)
        self.combo_box.setCurrentIndex(find_string_index(options, self.config.get(self.key)))
        self.combo_box.setMinimumWidth(210)
        self.combo_box.currentTextChanged.connect(self.text_changed)
        self.add_widget(self.combo_box)

    def text_changed(self, text):
        self.update_config(text)

    def update_value(self):
        self.combo_box.setText(self.config.get(self.key))


def find_string_index(my_list, target_string):
    try:
        index = my_list.index(target_string)
        return index
    except ValueError:
        return 0
