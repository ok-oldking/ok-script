from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy


class FlowLayout(QWidget):
    def __init__(self, alignment=Qt.AlignLeft, max_columns=1):
        super().__init__()
        self.setWindowTitle("Flow Layout")
        self.alignment = alignment
        self.max_columns = max_columns

        # Main vertical layout
        self.vbox = QVBoxLayout()
        self.setLayout(self.vbox)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(2)
        self.vbox.setAlignment(Qt.AlignTop)
        self.widgets = []

        # Add the first horizontal layout
        self.add_new_hbox()

    def add_new_hbox(self):
        # Create a new horizontal layout and add it to the vertical layout
        self.hbox = QHBoxLayout()
        self.hbox.setAlignment(self.alignment | Qt.AlignTop)
        self.hbox.setContentsMargins(2, 0, 0, 0)
        self.hbox.setSpacing(16)
        self.vbox.addLayout(self.hbox)
        self.current_width = 0

    def add_widget(self, widget):
        # Rows are rebuilt whenever this widget is resized, after the parent
        # layout has assigned its real width.
        widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.widgets.append(widget)
        self._rebuild()

    def _rebuild(self):
        while self.vbox.count():
            layout = self.vbox.takeAt(0).layout()
            if layout is None:
                continue
            while layout.count():
                layout.takeAt(0)
            layout.deleteLater()

        self.add_new_hbox()
        available_width = max(1, self.width())
        for widget in self.widgets:
            widget.setMaximumWidth(16777215)
            widget_width = max(widget.sizeHint().width(), widget.minimumSizeHint().width())
            if self.hbox.count() and (
                self.current_width + widget_width > available_width
                or self.hbox.count() >= self.max_columns
            ):
                self.add_new_hbox()
            if widget_width > available_width:
                self.hbox.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.hbox.addWidget(widget)
            self.current_width += widget_width + self.hbox.spacing()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._rebuild()
