from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QRect, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from ok.ui.qt.kit.icons import icon as kit_icon
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.motion import SlidingIndicator, paint_rounded
from ok.ui.qt.kit.theme import set_style_property, theme

_GEOMETRY_EVENTS = (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide)
ICON_FILL_DURATION = 260
# Width of the soft edge of the icon color sweep, as a fraction of the diagonal.
ICON_FILL_EDGE = 0.35


def _diagonal_blend(base: QPixmap, top: QPixmap, progress: float) -> QPixmap:
    """``top`` revealed over ``base`` from the bottom-left corner, ``progress`` in 0..1."""

    width, height = top.width(), top.height()
    end = progress * (1.0 + ICON_FILL_EDGE)  # fully covered at progress 1

    def coverage(position: float) -> float:
        return min(1.0, max(0.0, (end - position) / ICON_FILL_EDGE))

    mask = QLinearGradient(0, height, width, 0)
    for position in sorted({0.0, 1.0, *(p for p in (end - ICON_FILL_EDGE, end) if 0.0 < p < 1.0)}):
        mask.setColorAt(position, QColor(0, 0, 0, round(255 * coverage(position))))

    # Paint in device pixels; the ratio is restored on the result.
    revealed = top.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    revealed.setDevicePixelRatio(1.0)
    painter = QPainter(revealed)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.fillRect(revealed.rect(), mask)
    painter.end()

    result = base.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    result.setDevicePixelRatio(1.0)
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    painter.fillRect(result.rect(), mask)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.drawImage(0, 0, revealed)
    painter.end()

    pixmap = QPixmap.fromImage(result)
    pixmap.setDevicePixelRatio(top.devicePixelRatio())
    return pixmap

EXPANDED_WIDTH = 216
COMPACT_WIDTH = 60
ICON_TEXT_SPACING = 8
COLLAPSE_DURATION = 180
# The sidebar highlight often travels far, so it moves faster than tab indicators.
NAV_INDICATOR_DURATION = 150
SIDEBAR_PADDING = 10
# Centers the 18px icon in a COMPACT_WIDTH rail, so the icon never moves.
ICON_LEFT = (COMPACT_WIDTH - 2 * SIDEBAR_PADDING - 18) // 2


class NavItem(QPushButton):
    """One navigation entry: icon, text and an optional attention dot."""

    def __init__(self, key: str, text: str, icon=None, parent=None):
        super().__init__(parent)
        self.key = key
        self._icon_source = icon
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(text)

        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(18, 18)
        self.text_label = QLabel(text, self)
        self.text_label.setObjectName("navText")
        self.dot = QLabel(self)
        self.dot.setObjectName("navDot")
        self.dot.setFixedSize(7, 7)
        self.dot.hide()
        for label in (self.icon_label, self.text_label, self.dot):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Fixed margins and a trailing spacer keep the icon in place while the
        # sidebar width animates and the label is hidden.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(ICON_LEFT, 0, 12, 0)
        layout.setSpacing(ICON_TEXT_SPACING)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label, 1)
        layout.addStretch(0)
        layout.addWidget(self.dot)

        # On selection the accent color sweeps across the icon from bottom left
        # to top right.
        self._fill_from = None
        self._fill_to = None
        self._fill = QVariantAnimation(self)
        self._fill.setDuration(ICON_FILL_DURATION)
        self._fill.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fill.setStartValue(0.0)
        self._fill.setEndValue(1.0)
        self._fill.valueChanged.connect(self._paint_fill)

        self.toggled.connect(self._on_toggled)
        theme.changed.connect(self._refresh_icon)
        self._refresh_icon()

    def text(self) -> str:
        return self.text_label.text()

    def setText(self, text: str) -> None:
        self.text_label.setText(text)
        self.setToolTip(text)

    def set_icon(self, icon) -> None:
        self._icon_source = icon
        self._refresh_icon()

    def set_badge(self, visible: bool) -> None:
        self.dot.setVisible(visible)

    def set_compact(self, compact: bool) -> None:
        self.text_label.setVisible(not compact)

    def _on_toggled(self, checked: bool) -> None:
        set_style_property(self.text_label, "selected", checked)
        source = self._icon_source
        if checked and isinstance(source, str) and self.isVisible() and self._fill.duration() > 0:
            # Bundled icons are single-color, so they can be recolored; app icons keep theirs.
            self._fill.stop()
            self._fill_from = self._icon_pixmap(False)
            self._fill_to = self._icon_pixmap(True)
            self._paint_fill(0.0)
            self._fill.start()
        else:
            self._refresh_icon()

    def _icon_pixmap(self, selected: bool):
        source = self._icon_source
        qicon = source if isinstance(source, QIcon) else kit_icon(source, "accent" if selected else "text_secondary", 1.7)
        return qicon.pixmap(QSize(18, 18), self.devicePixelRatioF())

    def _refresh_icon(self) -> None:
        self._fill.stop()
        self._fill_from = self._fill_to = None
        if self._icon_source is None:
            self.icon_label.clear()
            return
        self.icon_label.setPixmap(self._icon_pixmap(self.isChecked()))

    def _paint_fill(self, value) -> None:
        if self._fill_from is None:
            return
        progress = float(value)
        if progress >= 1.0:
            self.icon_label.setPixmap(self._fill_to)
            self._fill_from = self._fill_to = None
            return
        self.icon_label.setPixmap(_diagonal_blend(self._fill_from, self._fill_to, progress))


class NavigationView(QWidget):
    """A sidebar of titled sections plus pinned bottom items.

    ``current_changed`` carries the key of the item the user picked.
    ``compact_changed`` reports the collapsed (icon rail) state.
    """

    current_changed = Signal(str)
    compact_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kitSidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._items = {}
        self._sections = {}
        self._compact = False
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked.connect(lambda button: self.current_changed.emit(button.key))
        # The selection highlight is painted here, under the items, so it can
        # travel from the old item to the new one.
        self._indicator = SlidingIndicator(self, self._indicator_rect, NAV_INDICATOR_DURATION)
        self._group.buttonToggled.connect(self._on_item_toggled)
        theme.changed.connect(self.update)

        scroll = QScrollArea(self)
        self._scroll = scroll
        scroll.verticalScrollBar().valueChanged.connect(self.update)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contents = QWidget()
        contents.setObjectName("scrollContents")
        scroll.setWidget(contents)
        self._sections_layout = QVBoxLayout(contents)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(0)
        self._sections_layout.addStretch(1)

        self._bottom = QVBoxLayout()
        self._bottom.setContentsMargins(0, 0, 0, 0)
        self._bottom.setSpacing(2)
        separator = QFrame(self)
        separator.setObjectName("navSeparator")
        separator.setFixedHeight(1)

        self.collapse_button = NavItem("__collapse__", self.tr("Collapse"), "panel", self)
        self.collapse_button.setCheckable(False)
        self.collapse_button.clicked.connect(lambda: self.set_compact(not self._compact))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SIDEBAR_PADDING, 12, SIDEBAR_PADDING, 10)
        layout.setSpacing(6)
        layout.addWidget(scroll, 1)
        layout.addWidget(separator)
        layout.addLayout(self._bottom)
        layout.addWidget(self.collapse_button)
        self.setFixedWidth(EXPANDED_WIDTH)

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(COLLAPSE_DURATION)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(lambda width: self.setFixedWidth(int(width)))
        self._animation.finished.connect(self._finish_resize)

    def add_section(self, key: str, title: str = None) -> None:
        if key in self._sections:
            return
        box = QWidget()
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 10)
        box_layout.setSpacing(2)
        header = Label(title or "", "section", box)
        header.setContentsMargins(12, 6, 0, 6)
        header.setProperty("fullText", header.text())
        header.setVisible(bool(title))
        if title:
            # Keep the header's height when its text is hidden in the icon rail.
            header.setFixedHeight(header.sizeHint().height())
        box_layout.addWidget(header)
        box.hide()
        box.installEventFilter(self)
        self._sections[key] = (box, box_layout, header)
        self._sections_layout.insertWidget(self._sections_layout.count() - 1, box)

    def add_item(self, key: str, text: str, icon=None, section: str = None, bottom: bool = False) -> NavItem:
        if key in self._items:
            raise ValueError(f"duplicate navigation key: {key!r}")
        item = NavItem(key, text, icon, self)
        item.set_compact(self._compact)
        self._items[key] = item
        self._group.addButton(item)
        item.installEventFilter(self)
        if bottom:
            self._bottom.addWidget(item)
        else:
            if section not in self._sections:
                self.add_section(section)
            box, box_layout, _header = self._sections[section]
            box_layout.addWidget(item)
            box.show()
        return item

    def remove_item(self, key: str) -> None:
        item = self._items.pop(key, None)
        if item is None:
            return
        self._group.removeButton(item)
        if self._indicator.item() is item:
            self._indicator.set_item(self._group.checkedButton(), animate=False)
        container = item.parentWidget()
        item.setParent(None)
        item.deleteLater()
        for box, box_layout, _header in self._sections.values():
            if box is container:
                box.setVisible(box_layout.count() > 1)

    def item(self, key: str) -> NavItem:
        return self._items[key]

    def has_item(self, key: str) -> bool:
        return key in self._items

    def keys(self) -> list:
        return list(self._items)

    def current_key(self):
        button = self._group.checkedButton()
        return button.key if button else None

    def set_current(self, key: str) -> None:
        if key in self._items:
            self._items[key].setChecked(True)

    def set_badge(self, key: str, visible: bool) -> None:
        if key in self._items:
            self._items[key].set_badge(visible)

    def is_compact(self) -> bool:
        return self._compact

    def set_compact(self, compact: bool, animate: bool = True) -> None:
        """Switch between the full sidebar and the icon rail.

        Text is hidden before collapsing and shown after expanding, so it
        never squeezes while the width animates.
        """

        if compact == self._compact:
            return
        self._compact = compact
        self.collapse_button.setText(self.tr("Expand") if compact else self.tr("Collapse"))
        target = COMPACT_WIDTH if compact else EXPANDED_WIDTH
        self._animation.stop()
        if compact:
            self._show_text(False)
        if animate and self.isVisible():
            self._animation.setStartValue(self.width())
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self._finish_resize(target)
        self.compact_changed.emit(compact)

    def _finish_resize(self, width=None) -> None:
        self.setFixedWidth(width if width is not None else (COMPACT_WIDTH if self._compact else EXPANDED_WIDTH))
        if not self._compact:
            self._show_text(True)

    # --- selection highlight ----------------------------------------------------

    def _on_item_toggled(self, button, checked: bool) -> None:
        if checked:
            self._indicator.set_item(button)

    def _indicator_rect(self, item) -> QRectF:
        return QRectF(QRect(item.mapTo(self, QPoint(0, 0)), item.size()))

    def eventFilter(self, watched, event) -> bool:
        if event.type() in _GEOMETRY_EVENTS:
            self.update()
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        rect = self._indicator.rect()
        if rect is None:
            return
        viewport = self._scroll.viewport()
        top = viewport.mapTo(self, QPoint(0, 0)).y()
        item = self._indicator.item()
        if self._indicator.is_animating() or item.parentWidget() is self:
            # In flight it may cross into the pinned bottom items; only the
            # area above the list is off limits.
            clip = QRectF(0, top, self.width(), self.height() - top)
        else:
            clip = QRectF(0, top, self.width(), viewport.height())
        rect = rect.intersected(clip)
        if rect.isEmpty():
            return
        accent = theme.color("accent")
        fill = QColor(accent)
        fill.setAlphaF(0.14)
        border = QColor(accent)
        border.setAlphaF(0.35)
        paint_rounded(self, rect, 8, fill, border)

    def _show_text(self, visible: bool) -> None:
        for item in list(self._items.values()) + [self.collapse_button]:
            item.set_compact(not visible)
        for _box, _layout, header in self._sections.values():
            header.setText(header.property("fullText") if visible else "")
