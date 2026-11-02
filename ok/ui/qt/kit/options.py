from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QRadioButton, QVBoxLayout, QWidget

from ok.ui.qt.kit.feedback import Pill
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import set_style_property


class OptionCard(QFrame):
    """A selectable card with a radio mark, a title and a description."""

    clicked = Signal()

    def __init__(self, title: str, description: str = None, badge: str = None, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", False)
        self.radio = QRadioButton(self)
        self.radio.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.radio.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.title_label = Label(title, "strong", self)
        self.title_label.setWordWrap(True)
        self.badge = Pill(badge or "", "success", self)
        self.badge.setVisible(bool(badge))
        self.description_label = Label(description or "", "secondary", self, word_wrap=True)
        self.description_label.setVisible(bool(description))

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self.title_label)
        title_row.addWidget(self.badge)
        title_row.addStretch(1)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        text.addLayout(title_row)
        text.addWidget(self.description_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(self.radio, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)

    def is_selected(self) -> bool:
        return bool(self.property("selected"))

    def set_selected(self, selected: bool) -> None:
        self.radio.setChecked(selected)
        set_style_property(self, "selected", selected)

    def set_text(self, title: str, description: str = None) -> None:
        self.title_label.setText(title)
        self.description_label.setText(description or "")
        self.description_label.setVisible(bool(description))
        self.setToolTip(title if not description else f"{title}\n{description}")

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()) \
                and self.isEnabled():
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class OptionGroup(QWidget):
    """A vertical list of :class:`OptionCard`; exactly one is selected.

    ``selected`` fires with the index when the user picks a card.
    """

    selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

    def set_options(self, options, current: int = 0) -> None:
        """``options`` is a list of ``(title, description, badge)`` tuples."""

        while len(self.cards) > len(options):
            card = self.cards.pop()
            card.setParent(None)
            card.deleteLater()
        for index, (title, description, badge) in enumerate(options):
            if index >= len(self.cards):
                card = OptionCard(title, description, badge, self)
                card.clicked.connect(lambda i=index: self._pick(i))
                self.cards.append(card)
                self._layout.addWidget(card)
            card = self.cards[index]
            card.set_text(title, description)
            card.badge.setText(badge or "")
            card.badge.setVisible(bool(badge))
        self.set_current(current)

    def current(self) -> int:
        for index, card in enumerate(self.cards):
            if card.is_selected():
                return index
        return -1

    def set_current(self, index: int) -> None:
        for i, card in enumerate(self.cards):
            card.set_selected(i == index)

    def _pick(self, index: int) -> None:
        if index == self.current():
            return
        self.set_current(index)
        self.selected.emit(index)
