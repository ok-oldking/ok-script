from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem


class SortingTableWidgetItem(QTableWidgetItem):

    def __init__(self, name=None):
        super().__init__()
        self.setFlags(self.flags() & ~Qt.ItemIsEditable)
        if name:
            self.setText(str(name))

    def __lt__(self, other):
        try:
            # Convert both items to comparable float values
            self_value = self.convert_to_float(self.text())
            other_value = other.convert_to_float(other.text())
            return self_value < other_value
        except ValueError:
            # If conversion fails, fall back to default string comparison
            return self.text() < other.text()

    @staticmethod
    def convert_to_float(value):
        """
        Convert the given value to float. Supports:
        - Float strings (e.g., "3.14")
        - Integer strings (e.g., "42")
        - Percentage strings (e.g., "45%")
        """
        if value.endswith('%'):
            return float(value.rstrip('%')) / 100
        else:
            return float(value)
