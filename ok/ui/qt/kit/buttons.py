from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy

from ok.ui.qt.kit.icons import icon as kit_icon
from ok.ui.qt.kit.theme import set_style_property, theme

VARIANTS = ("secondary", "primary", "tonal", "subtle", "danger")
SIZES = {"normal": (36, 14, 18), "small": (30, 10, 16)}

_ICON_COLOR = {"primary": "on_accent", "danger": "danger"}


class Button(QPushButton):
    """A push button with an optional icon and keyboard hint badge.

    ``icon`` is a bundled icon name or a QIcon. Text, icon and hint are laid
    out by the button itself so the hint can sit beside the text.
    """

    def __init__(self, text: str = "", icon=None, variant: str = "secondary", size: str = "normal",
                 hint: str = None, parent=None):
        super().__init__(parent)
        if variant not in VARIANTS:
            raise ValueError(f"unknown button variant: {variant!r}")
        if size not in SIZES:
            raise ValueError(f"unknown button size: {size!r}")
        self._variant = variant
        self._size = size
        self._icon_source = None
        self.setProperty("variant", variant)
        self.setProperty("size", size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self._icon_label = QLabel(self)
        self._icon_label.setObjectName("buttonIcon")
        self._text_label = QLabel(self)
        self._text_label.setObjectName("buttonText")
        self._hint_label = QLabel(self)
        self._hint_label.setProperty("role", "kbd")
        # A fixed box with centered text; padding alone sits the monospace glyphs high.
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setFixedHeight(20 if size == "normal" else 18)
        for label in (self._icon_label, self._text_label, self._hint_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        height, padding, _ = SIZES[size]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(padding, 0, padding, 0)
        # Glyphs leave a few pixels of air inside their box, so this reads wider than it is.
        layout.setSpacing(5)
        layout.addStretch(1)
        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label)
        layout.addWidget(self._hint_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        self.setFixedHeight(height)

        self.setText(text)
        self.set_hint(hint)
        self.set_icon(icon)
        theme.changed.connect(self._refresh_icon)

    @property
    def variant(self) -> str:
        return self._variant

    def set_variant(self, variant: str) -> None:
        if variant not in VARIANTS:
            raise ValueError(f"unknown button variant: {variant!r}")
        self._variant = variant
        set_style_property(self, "variant", variant)
        for label in (self._text_label, self._hint_label):
            label.style().unpolish(label)
            label.style().polish(label)
        self._refresh_icon()

    def text(self) -> str:
        return self._text_label.text()

    def setText(self, text: str) -> None:
        self._text_label.setText(text)
        self._text_label.setVisible(bool(text))
        self._update_icon_only()

    def hint(self) -> str:
        return self._hint_label.text()

    def set_hint(self, hint) -> None:
        self._hint_label.setText(hint or "")
        self._hint_label.setVisible(bool(hint))

    def set_icon(self, icon) -> None:
        """Set a bundled icon name, a QIcon, or ``None``."""

        self._icon_source = icon
        self._refresh_icon()
        self._update_icon_only()

    def setIcon(self, icon) -> None:
        self.set_icon(icon)

    def _resolved_icon(self) -> QIcon:
        if self._icon_source is None:
            return QIcon()
        if isinstance(self._icon_source, QIcon):
            return self._icon_source
        return kit_icon(self._icon_source, _ICON_COLOR.get(self._variant, "text"))

    def _refresh_icon(self) -> None:
        icon = self._resolved_icon()
        self._icon_label.setVisible(not icon.isNull())
        if icon.isNull():
            return
        side = SIZES[self._size][2]
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        self._icon_label.setPixmap(icon.pixmap(QSize(side, side), self.devicePixelRatioF(), mode))
        self._icon_label.setFixedSize(side, side)

    def _update_icon_only(self) -> None:
        icon_only = not self._text_label.text() and self._icon_source is not None
        if icon_only:
            self.setFixedWidth(self.height())
            self.layout().setContentsMargins(0, 0, 0, 0)
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            padding = SIZES[self._size][1]
            self.layout().setContentsMargins(padding, 0, padding, 0)

    def sizeHint(self) -> QSize:
        hint = self.layout().sizeHint()
        return QSize(max(hint.width(), self.height()), self.height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (event.Type.EnabledChange, event.Type.DevicePixelRatioChange):
            self._refresh_icon()
