from PySide6.QtWidgets import QLabel
from qfluentwidgets import PushButton

from ok.gui.tasks.LabelAndWidget import LabelAndWidget
from ok.gui.tasks.ModifyListDialog import ModifyListDialog
from ok.gui.widget.UpdateConfigWidgetItem import value_to_string


class ModifyListItem(LabelAndWidget):

    def __init__(self, key: str, the_list, config):
        super().__init__(key)
        self.key = key
        self.config = config
        self.list = the_list
        self.switch_button = PushButton(self.tr('Modify'))
        self.switch_button.clicked.connect(self.clicked)
        self.list_text = QLabel(value_to_string(self.list))
        self.add_widget(self.list_text)
        self.add_widget(self.switch_button)

    def clicked(self):
        dialog = ModifyListDialog(self.list, self.window())
        dialog.list_modified.connect(self.list_modified)
        dialog.exec()

    def list_modified(self, the_list):
        self.list = the_list
        self.config[self.key] = the_list
        self.list_text.setText(value_to_string(self.list))
