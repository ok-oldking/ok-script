from PySide6.QtWidgets import QLabel
from qfluentwidgets import PushButton

from ok.gui.tasks.ConfigLabelAndWidget import ConfigLabelAndWidget
from ok.gui.tasks.ModifyListDialog import ModifyListDialog
from ok.gui.widget.UpdateConfigWidgetItem import value_to_string


class ModifyListItem(ConfigLabelAndWidget):

    def __init__(self, config_desc, config, key: str):
        super().__init__(config_desc, config, key)
        self.switch_button = PushButton(self.tr('Modify'))
        self.switch_button.clicked.connect(self.clicked)
        self.list_text = QLabel("")
        self.update_value()
        self.add_widget(self.list_text)
        self.add_widget(self.switch_button)

    def update_value(self):
        items = self.config.get(self.key)
        total_length = sum(len(item) for item in items)

        if total_length > 30:
            display_text = "\n".join(items)
        else:
            display_text = value_to_string(items)

        self.list_text.setText(display_text)

    def clicked(self):
        dialog = ModifyListDialog(self.config.get(self.key), self.window())
        dialog.list_modified.connect(self.list_modified)
        dialog.exec()

    def list_modified(self, the_list):
        self.update_config(the_list)
        self.update_value()
