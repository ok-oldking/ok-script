from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout


class FlowLayout(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flow Layout")

        # Main vertical layout
        self.vbox = QVBoxLayout()
        self.setLayout(self.vbox)

        # Add the first horizontal layout
        self.add_new_hbox()

    def add_new_hbox(self):
        # Create a new horizontal layout and add it to the vertical layout
        self.hbox = QHBoxLayout()
        self.hbox.setAlignment(Qt.AlignLeft)
        self.vbox.addLayout(self.hbox)
        self.current_width = 0

    def add_widget(self, widget):
        # Measure the width of the widget
        widget_width = widget.sizeHint().width()

        # Check if the current horizontal layout can accommodate the widget
        if self.current_width + widget_width > self.width():
            self.add_new_hbox()

        # Add the widget to the current horizontal layout
        self.hbox.addWidget(widget)
        self.current_width += widget_width
