import math

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF, QIcon
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy

from ok.ui.qt.kit.icons import icon as kit_icon
from ok.ui.qt.kit.motion import SlidingIndicator, paint_rounded
from ok.ui.qt.kit.theme import set_style_property, theme

LOOKS = ("pill", "underline")
UNDERLINE_HEIGHT = 2


class _TabText(QLabel):
    """A label sized for its selected (semibold) text, so selecting a tab never
    changes its width and shifts its neighbors."""

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold)
        margins = self.contentsMargins()
        # Measured like QLabel measures its own text, plus the fractional advance.
        metrics = QFontMetrics(font)
        text_width = max(metrics.boundingRect(QRect(0, 0, 4000, 4000), int(self.alignment()), self.text()).width(),
                         math.ceil(QFontMetricsF(font).horizontalAdvance(self.text())))
        width = text_width + margins.left() + margins.right()
        return QSize(max(hint.width(), width), hint.height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


class TabItem(QPushButton):
    """One tab: optional icon, text and count badge."""

    def __init__(self, key: str, text: str, count=None, icon=None, look: str = "pill", parent=None):
        super().__init__(parent)
        self.key = key
        self._icon_source = icon
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("look", look)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(30 if look == "pill" else 40)

        self.icon_label = QLabel(self)
        self.text_label = _TabText(text, self)
        self.text_label.setObjectName("tabText")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label = QLabel(self)
        self.count_label.setObjectName("tabCount")
        for label in (self.icon_label, self.text_label, self.count_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12 if look == "pill" else 10, 0, 12 if look == "pill" else 10, 0)
        layout.setSpacing(8)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.set_count(count)
        self._refresh_icon()
        self.toggled.connect(self._on_toggled)
        theme.changed.connect(self._refresh_icon)

    def text(self) -> str:
        return self.text_label.text()

    def set_count(self, count) -> None:
        self.count_label.setText("" if count is None else str(count))
        self.count_label.setVisible(count is not None)

    def _refresh_icon(self) -> None:
        source = self._icon_source
        if source is None:
            self.icon_label.hide()
            return
        icon = source if isinstance(source, QIcon) else kit_icon(source, "text" if self.isChecked() else "text_secondary")
        size = 20 if isinstance(source, QIcon) else 16
        self.icon_label.setPixmap(icon.pixmap(QSize(size, size), self.devicePixelRatioF()))
        self.icon_label.setFixedSize(size, size)
        self.icon_label.show()

    def _on_toggled(self, checked: bool) -> None:
        set_style_property(self.text_label, "selected", checked)
        set_style_property(self.count_label, "selected", checked)
        self._refresh_icon()

    def sizeHint(self) -> QSize:
        return QSize(self.layout().sizeHint().width(), self.height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


class TabStrip(QFrame):
    """A row of mutually exclusive tabs.

    ``look="pill"`` is the segmented filter style; ``look="underline"`` is
    the page-tab style. ``current_changed`` carries the selected key.
    """

    current_changed = Signal(str)

    def __init__(self, look: str = "pill", parent=None):
        super().__init__(parent)
        if look not in LOOKS:
            raise ValueError(f"unknown tab look: {look!r}")
        self._look = look
        self.setProperty("look", look)
        # The underline strip spans its row so the bottom border runs full width.
        horizontal = QSizePolicy.Policy.Maximum if look == "pill" else QSizePolicy.Policy.Preferred
        self.setSizePolicy(horizontal, QSizePolicy.Policy.Fixed)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._items = {}
        layout = QHBoxLayout(self)
        margin = 3 if look == "pill" else 0
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(4 if look == "pill" else 6)
        if look == "underline":
            layout.addStretch(1)
        self._group.buttonToggled.connect(self._on_toggled)
        self._indicator = SlidingIndicator(self, self._indicator_rect)
        theme.changed.connect(self.update)

    def _indicator_rect(self, item) -> QRectF:
        rect = QRectF(item.geometry())
        if self._look == "underline":
            return QRectF(rect.left(), rect.bottom() + 1 - UNDERLINE_HEIGHT, rect.width(), UNDERLINE_HEIGHT)
        return rect

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        rect = self._indicator.rect()
        if rect is None:
            return
        fill = QColor(theme.color("accent"))
        if self._look == "underline":
            paint_rounded(self, rect, 1, fill)
        else:
            fill.setAlphaF(0.18)
            paint_rounded(self, rect, 7, fill)

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide):
            self.update()
        return super().eventFilter(watched, event)

    def _insert(self, widget, alignment=Qt.AlignmentFlag(0)) -> None:
        layout = self.layout()
        index = layout.count() - 1 if self._look == "underline" else layout.count()
        layout.insertWidget(index, widget, 0, alignment)

    def add_tab(self, key: str, text: str, count=None, icon=None) -> TabItem:
        if key in self._items:
            raise ValueError(f"duplicate tab key: {key!r}")
        item = TabItem(key, text, count, icon, self._look, self)
        self._items[key] = item
        self._group.addButton(item)
        item.installEventFilter(self)
        self._insert(item)
        if len(self._items) == 1:
            item.setChecked(True)
        return item

    def add_separator(self) -> None:
        line = QFrame(self)
        line.setObjectName("tabSeparator")
        line.setFixedSize(1, 18)
        self._insert(line, Qt.AlignmentFlag.AlignVCenter)

    def clear(self) -> None:
        """Remove every tab and separator."""

        for item in self._items.values():
            self._group.removeButton(item)
        self._items.clear()
        # Rebuilt tabs start at their selection rather than flying in.
        self._indicator.set_item(None, animate=False)
        layout = self.layout()
        for index in reversed(range(layout.count())):
            widget = layout.itemAt(index).widget()
            if widget is not None:
                layout.takeAt(index)
                widget.deleteLater()

    def item(self, key: str) -> TabItem:
        return self._items[key]

    def keys(self) -> list:
        return list(self._items)

    def set_count(self, key: str, count) -> None:
        self._items[key].set_count(count)

    def current_key(self):
        button = self._group.checkedButton()
        return button.key if button else None

    def set_current(self, key: str) -> None:
        self._items[key].setChecked(True)

    def _on_toggled(self, button, checked: bool) -> None:
        if checked:
            self._indicator.set_item(button)
            self.current_changed.emit(button.key)
