from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import set_style_property

CONTROL_COLUMN = 240
SUB_ROW_INDENT = 20


class Card(QFrame):
    """A rounded surface. ``look="inset"`` is the lighter card used inside pages."""

    def __init__(self, parent=None, look: str = "default"):
        super().__init__(parent)
        self.setProperty("look", look)


class SettingRow(QWidget):
    """Title and optional description on the left, a control on the right.

    The control sits in a right-aligned column of ``control_width`` pixels so
    controls line up across rows. ``indent`` marks a row that depends on the
    row above it.
    """

    def __init__(self, title: str, description: str = None, control: QWidget = None,
                 control_width: int = CONTROL_COLUMN, indent: bool = False, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("first", True)
        # Children get their parent up front: setVisible(True) on a parentless
        # widget shows it as a top-level window, which flashes on screen.
        self.title_label = Label(title, "strong", self, word_wrap=True)
        self.description_label = Label(description or "", "secondary", self, word_wrap=True)
        self.description_label.setVisible(bool(description))
        self.description_label.setMaximumWidth(560)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(3)
        text.addWidget(self.title_label)
        text.addWidget(self.description_label)

        self._control_box = QHBoxLayout()
        self._control_box.setContentsMargins(0, 0, 0, 0)
        self._control_box.addStretch(1)

        self._row_layout = QHBoxLayout(self)
        self._row_layout.setSpacing(24)
        self._row_layout.addLayout(text, 1)
        self._row_layout.addLayout(self._control_box)
        self.set_indent(indent)
        self._control_width = control_width
        self.control = None
        if control is not None:
            self.set_control(control)

    def set_control(self, control: QWidget) -> None:
        if self.control is not None:
            self._control_box.removeWidget(self.control)
            self.control.setParent(None)
        self.control = control
        expands = control.sizePolicy().horizontalPolicy() not in (
            control.sizePolicy().Policy.Fixed, control.sizePolicy().Policy.Maximum)
        if expands:
            control.setFixedWidth(self._control_width)
        self._control_box.addWidget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def set_first(self, first: bool) -> None:
        set_style_property(self, "first", first)

    def set_indent(self, indent: bool) -> None:
        """Indent a row that depends on the row above it."""

        self._row_layout.setContentsMargins(18 + (SUB_ROW_INDENT if indent else 0), 14, 18, 14)


class SettingGroup(QWidget):
    """A section label above an inset card of :class:`SettingRow` items."""

    def __init__(self, title: str = None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.title_label = Label(title or "", "section", self)
        self.title_label.setVisible(bool(title))
        layout.addWidget(self.title_label)
        self.card = Card(look="inset")
        self._rows = QVBoxLayout(self.card)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(0)
        layout.addWidget(self.card)
        self.rows = []

    def add_row(self, row: SettingRow) -> SettingRow:
        row.set_first(not self.rows)
        self.rows.append(row)
        self._rows.addWidget(row)
        return row
