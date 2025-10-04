from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QWidget


class TabWidget(QWidget):

    def __init__(self):
        super().__init__()
        color = self.get_palette_color(QPalette.Base)
        self.setStyleSheet(f"background-color:{color};")

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
