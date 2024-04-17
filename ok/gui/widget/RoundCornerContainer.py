from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QVBoxLayout, QLabel, QFrame, QSizePolicy, QLayout, QWidget, QHBoxLayout, QSpacerItem


class RoundCornerContainer(QFrame):
    def __init__(self, title, child=None, parent=None):
        super(RoundCornerContainer, self).__init__(parent)

        # Set the layout
        self.top_layout = QHBoxLayout()
        layout = QVBoxLayout(self)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 16px; margin:2px;")
        self.title_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.top_layout.addWidget(self.title_label)
        self.top_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        layout.addLayout(self.top_layout)
        if child is not None and isinstance(child, QWidget):
            child.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(child)
        elif child is not None and isinstance(child, QLayout):
            child.setSizeConstraint(QVBoxLayout.SetMaximumSize)
            layout.addLayout(child)
            layout.setStretchFactor(child, 1)
        layout.setStretchFactor(self.title_label, 0)

        self.setLayout(layout)

        self.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.setLineWidth(2)

        color = self.get_palette_color(QPalette.Base)
        self.setStyleSheet(f"background-color:{color};")

    def add_top_widget(self, widget):
        self.top_layout.addWidget(widget)

    def get_palette_color(self, palette_color):
        palette = self.palette()
        return color_to_hex(palette.color(palette_color))


def color_to_hex(color):
    """Converts a QColor object to a hex string representation.

    Args:
        color: The QColor object to convert.

    Returns:
        A string representing the hex code of the color (e.g., "#FF0000" for red).
    """
    red = color.red()
    green = color.green()
    blue = color.blue()
    hex_color = f"#{red:02X}{green:02X}{blue:02X}"
    return hex_color

# Usage:
# widget = RoundCornerContainer("Title")
# widget.show()
