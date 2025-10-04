from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from ok.gui.widget.UpdateConfigWidgetItem import UpdateConfigWidgetItem, value_to_string


class ListTableWidgetItem(UpdateConfigWidgetItem, QTableWidgetItem):

    def __init__(self, config, key, value, parent=None):
        UpdateConfigWidgetItem.__init__(self, config, key, value)
        QTableWidgetItem.__init__(self)
        self.setText(value_to_string(value))

    def setData(self, role, value):
        if role == Qt.EditRole:
            list_value = convert_to_list(value)
            self.set_value(list_value)
            self.setText(value_to_string(list_value))
        super().setData(role, value)


def convert_to_list(s):
    # Replace the Chinese comma with the English comma
    s = s.replace("，", ",")

    # Split the string by comma and strip the white spaces
    return [item.strip() for item in s.split(",")]
