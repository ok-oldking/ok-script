from PySide6.QtCore import QEasingCurve, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from ok.ui.qt.kit.icons import icon as kit_icon
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import set_style_property, theme

EXPANDED_WIDTH = 216
COMPACT_WIDTH = 60
ICON_TEXT_SPACING = 8
COLLAPSE_DURATION = 180
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
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        source = self._icon_source
        if source is None:
            self.icon_label.clear()
            return
        if isinstance(source, QIcon):
            qicon = source
        else:
            qicon = kit_icon(source, "text" if self.isChecked() else "text_secondary", 1.7)
        self.icon_label.setPixmap(qicon.pixmap(QSize(18, 18), self.devicePixelRatioF()))


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

        scroll = QScrollArea(self)
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
        self._sections[key] = (box, box_layout, header)
        self._sections_layout.insertWidget(self._sections_layout.count() - 1, box)

    def add_item(self, key: str, text: str, icon=None, section: str = None, bottom: bool = False) -> NavItem:
        if key in self._items:
            raise ValueError(f"duplicate navigation key: {key!r}")
        item = NavItem(key, text, icon, self)
        item.set_compact(self._compact)
        self._items[key] = item
        self._group.addButton(item)
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

    def _show_text(self, visible: bool) -> None:
        for item in list(self._items.values()) + [self.collapse_button]:
            item.set_compact(not visible)
        for _box, _layout, header in self._sections.values():
            header.setText(header.property("fullText") if visible else "")
