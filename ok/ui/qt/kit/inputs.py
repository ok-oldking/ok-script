"""Input widgets.

Plain Qt inputs (QLineEdit, QCheckBox, QRadioButton, QTextEdit, ...) are
styled by the kit stylesheet and are used directly. This module adds the
inputs that need structure beyond a stylesheet.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QListView, QSpinBox

from ok.ui.qt.kit.buttons import Button


class ComboBox(QComboBox):
    """A combo box whose popup items can be styled (rounded, padded rows)."""

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self.setView(QListView(self))
        self.view().window().setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if items:
            self.addItems(list(items))


class NumberBox(QFrame):
    """A spin box with − and + buttons on either side.

    ``decimals`` > 0 makes it a floating point box. ``valueChanged`` carries
    an int or float accordingly.
    """

    valueChanged = Signal(object)

    def __init__(self, value=0, minimum=0, maximum=99, step=1, decimals: int = 0, parent=None):
        super().__init__(parent)
        self._spin = QDoubleSpinBox(self) if decimals else QSpinBox(self)
        if decimals:
            self._spin.setDecimals(decimals)
        self._spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin.setRange(minimum, maximum)
        self._spin.setSingleStep(step)
        self._spin.setValue(value)
        self._spin.setKeyboardTracking(False)

        self.minus_button = Button(icon="minus", variant="subtle")
        self.minus_button.setObjectName("numberMinus")
        self.plus_button = Button(icon="plus", variant="subtle")
        self.plus_button.setObjectName("numberPlus")
        for button in (self.minus_button, self.plus_button):
            button.setFixedSize(38, 34)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setAutoRepeat(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.minus_button)
        layout.addWidget(self._spin, 1)
        layout.addWidget(self.plus_button)
        self.setFixedHeight(36)

        self.minus_button.clicked.connect(self._spin.stepDown)
        self.plus_button.clicked.connect(self._spin.stepUp)
        self._spin.valueChanged.connect(self._on_value_changed)
        self._sync_buttons()

    @property
    def spin_box(self):
        return self._spin

    def value(self):
        return self._spin.value()

    def setValue(self, value) -> None:
        self._spin.setValue(value)

    def setRange(self, minimum, maximum) -> None:
        self._spin.setRange(minimum, maximum)
        self._sync_buttons()

    def _on_value_changed(self, value) -> None:
        self._sync_buttons()
        self.valueChanged.emit(value)

    def _sync_buttons(self) -> None:
        value = self._spin.value()
        self.minus_button.setEnabled(self.isEnabled() and value > self._spin.minimum())
        self.plus_button.setEnabled(self.isEnabled() and value < self._spin.maximum())

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.EnabledChange:
            self._sync_buttons()
