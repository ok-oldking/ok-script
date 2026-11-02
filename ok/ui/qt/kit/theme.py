"""Theme state, color tokens and stylesheet installation for the kit.

A single :data:`theme` manager owns the current mode (light, dark or
following the system) and the accent color. Widgets read colors through
:meth:`ThemeManager.color` when they paint, and roots registered with
:meth:`ThemeManager.install` receive the generated stylesheet whenever the
theme changes. Installing on a root widget instead of the application keeps
the kit from restyling widgets that are not part of it.
"""

import weakref
from enum import Enum

import shiboken6
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette


class Theme(Enum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


DEFAULT_ACCENT = "#7C5CFF"

FONT_FAMILY = '"Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif'
MONO_FONT_FAMILY = '"Cascadia Mono", "JetBrains Mono", Consolas, monospace'

DARK_TOKENS = {
    "window": "#121218",
    "sidebar": "#101015",
    "surface": "#17171E",
    "surface_alt": "#1B1B23",
    "control": "#22222B",
    "control_hover": "#2A2A35",
    "control_pressed": "#1D1D25",
    "border": "#262630",
    "border_strong": "#33333F",
    "separator": "#22222B",
    "text": "#EDEDF2",
    "text_secondary": "#A6A6B3",
    "text_tertiary": "#8F8F9C",
    "text_disabled": "#6E6E7A",
    "switch_off": "#4A4A57",
    "scrim": "rgba(0, 0, 0, 140)",
    "shadow": "#000000",
    "success": "#4ADE80",
    "warning": "#F5B83D",
    "danger": "#F87171",
}

LIGHT_TOKENS = {
    "window": "#F7F7F8",
    "sidebar": "#EFEFF1",
    "surface": "#FFFFFF",
    "surface_alt": "#FAFAFB",
    "control": "#FFFFFF",
    "control_hover": "#F1F1F3",
    "control_pressed": "#E9E9EC",
    "border": "#E3E3E7",
    "border_strong": "#D4D4D8",
    "separator": "#EFEFF1",
    "text": "#18181B",
    "text_secondary": "#52525B",
    "text_tertiary": "#6B6B74",
    "text_disabled": "#A1A1AA",
    "switch_off": "#8E8E96",
    "scrim": "rgba(0, 0, 0, 90)",
    "shadow": "#000000",
    "success": "#1A7F37",
    "warning": "#9A6700",
    "danger": "#B42318",
}


def _channel(value: float) -> float:
    value /= 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: QColor) -> float:
    return 0.2126 * _channel(color.red()) + 0.7152 * _channel(color.green()) + 0.0722 * _channel(color.blue())


def contrast_ratio(a: QColor, b: QColor) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def readable_accent(accent: QColor, minimum: float = 4.5) -> QColor:
    """Darken ``accent`` until white text on it reaches ``minimum`` contrast."""

    white = QColor("#FFFFFF")
    color = QColor(accent)
    for _ in range(40):
        if contrast_ratio(color, white) >= minimum:
            return color
        h, s, l, a = color.getHslF()
        color = QColor.fromHslF(h, s, max(0.0, l - 0.025), a)
    return color


def rgba(color: QColor, alpha: float) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {round(alpha * 255)})"


class ThemeManager(QObject):
    """Current theme and accent, plus the roots that receive the stylesheet."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self._mode = Theme.AUTO
        self._accent = QColor(DEFAULT_ACCENT)
        self._roots = []
        self._watching_system = False

    @property
    def mode(self) -> Theme:
        return self._mode

    def set_theme(self, mode: Theme) -> None:
        mode = Theme(mode)
        if mode == self._mode:
            return
        self._mode = mode
        self._watch_system()
        self._refresh()

    def is_dark(self) -> bool:
        if self._mode == Theme.AUTO:
            hints = QGuiApplication.styleHints() if QGuiApplication.instance() else None
            return bool(hints and hints.colorScheme() == Qt.ColorScheme.Dark)
        return self._mode == Theme.DARK

    def accent(self) -> QColor:
        """The accent as used for fills behind white text in this theme."""

        return QColor(self._accent) if self.is_dark() else readable_accent(self._accent)

    def set_accent(self, color) -> None:
        color = QColor(color)
        if not color.isValid() or color == self._accent:
            return
        self._accent = color
        self._refresh()

    def tokens(self) -> dict:
        return dict(DARK_TOKENS if self.is_dark() else LIGHT_TOKENS)

    def color(self, name: str) -> QColor:
        if name == "accent":
            return self.accent()
        if name == "on_accent":
            return QColor("#FFFFFF")
        value = self.tokens()[name]
        if value.startswith("rgba"):
            r, g, b, a = (int(part) for part in value[5:-1].split(","))
            return QColor(r, g, b, a)
        return QColor(value)

    def install(self, root) -> None:
        """Apply the kit stylesheet to ``root`` now and on every theme change.

        ``root`` is a top-level kit widget, or the ``QApplication`` once the
        whole app uses the kit.
        """

        self._watch_system()
        if not any(ref() is root for ref in self._roots):
            self._roots.append(weakref.ref(root))
        self._apply(root)

    def uninstall(self, root) -> None:
        self._roots = [ref for ref in self._live_roots() if ref() is not root]

    def _live_roots(self) -> list:
        # A root's Python wrapper can outlive its deleted C++ widget.
        return [ref for ref in self._roots if ref() is not None and shiboken6.isValid(ref())]

    def stylesheet(self) -> str:
        from ok.ui.qt.kit.qss import build_stylesheet
        return build_stylesheet(self)

    def palette(self) -> QPalette:
        palette = QPalette()
        roles = {
            QPalette.ColorRole.Window: "window",
            QPalette.ColorRole.WindowText: "text",
            QPalette.ColorRole.Base: "control",
            QPalette.ColorRole.AlternateBase: "surface_alt",
            QPalette.ColorRole.Text: "text",
            QPalette.ColorRole.Button: "control",
            QPalette.ColorRole.ButtonText: "text",
            QPalette.ColorRole.ToolTipBase: "surface_alt",
            QPalette.ColorRole.ToolTipText: "text",
            QPalette.ColorRole.PlaceholderText: "text_tertiary",
        }
        for role, token in roles.items():
            palette.setColor(role, self.color(token))
        palette.setColor(QPalette.ColorRole.Highlight, self.accent())
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, self.color("text_disabled"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, self.color("text_disabled"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, self.color("text_disabled"))
        return palette

    def _apply(self, root) -> None:
        root.setPalette(self.palette())
        root.setStyleSheet(self.stylesheet())

    def _refresh(self) -> None:
        self._roots = self._live_roots()
        for ref in self._roots:
            self._apply(ref())
        self.changed.emit()

    def _watch_system(self) -> None:
        if self._watching_system or QGuiApplication.instance() is None:
            return
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)
        self._watching_system = True

    def _on_system_scheme_changed(self, _scheme) -> None:
        if self._mode == Theme.AUTO:
            self._refresh()


theme = ThemeManager()


def set_style_property(widget, name: str, value) -> None:
    """Set a property used by stylesheet selectors and re-evaluate the style."""

    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
