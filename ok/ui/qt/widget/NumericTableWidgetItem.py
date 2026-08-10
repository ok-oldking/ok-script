from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator, QDoubleValidator
from PySide6.QtWidgets import QTableWidgetItem

from ok.gui.widget.UpdateConfigWidgetItem import UpdateConfigWidgetItem, value_to_string


class NumericTableWidgetItem(UpdateConfigWidgetItem, QTableWidgetItem):

    def __init__(self, config, key, value, parent=None):
        UpdateConfigWidgetItem.__init__(self, config, key, value)
        QTableWidgetItem.__init__(self)

        # Determine if the original value is int or float
        if isinstance(value, int):
            self.validator = QIntValidator(0, 999999, self.tableWidget())
        elif isinstance(value, float):
            self.validator = QDoubleValidator(0, 999999, 2, self.tableWidget())
        else:
            raise ValueError("Value must be an int or float")
        self.setText(value_to_string(value))

    def setData(self, role, value):
        if role == Qt.EditRole:
            state, _, _ = self.validator.validate(str(value), 0)
            if state != QIntValidator.Acceptable:
                return
            if isinstance(self.value, int):
                value = int(value)
            else:
                value = float(value)
            self.set_value(value)
        super().setData(role, value)
