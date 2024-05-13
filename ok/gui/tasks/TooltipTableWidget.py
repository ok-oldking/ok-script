from PySide6.QtWidgets import QHeaderView
from qfluentwidgets import TableWidget


class TooltipTableWidget(TableWidget):

    def __init__(self, width_percentages=None):
        super().__init__()
        self.verticalHeader().setVisible(False)
        self.width_percentages = width_percentages

        # Set the QTableWidget to fill the width of its parent
        self.horizontalHeader().setStretchLastSection(True)

        # Set the columns to resize to fill the width of the QTableWidget
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setWordWrap(True)

    def setItem(self, row, column, item):
        super().setItem(row, column, item)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.width_percentages is not None:
            width = self.width() - self.verticalScrollBar().width()
            for i, percentage in enumerate(self.width_percentages):
                self.setColumnWidth(i, int(width * percentage))
