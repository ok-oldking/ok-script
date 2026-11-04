"""Theme state, color tokens and stylesheet installation for the kit.

A single :data:`theme` manager owns the current mode (light, dark or
following the system) and the accent color. Widgets read colors through
:meth:`ThemeManager.color` when they paint, and roots registered with
:meth:`ThemeManager.install` receive the generated stylesheet whenever the
theme changes. Installing on a root widget instead of the application keeps
the kit from restyling widgets that are not part of it.
"""

import sys
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


class Backdrop(Enum):
    """The DWM material drawn behind kit windows."""

    NONE = "none"
    MICA = "mica"
    ACRYLIC = "acrylic"


# With a backdrop only the window frame (title bar, run bar, sidebar) shows the
# material, under one tint of the sidebar color at this opacity. Page content
# sits on an opaque layer (see ContentLayer), so cards, inputs and text keep
# their normal colors. Acrylic shows whatever is behind the window, so it gets
# a stronger tint than Mica to keep the frame readable.
BACKDROP_TINT = {
    (Backdrop.MICA, False): 0.35, (Backdrop.MICA, True): 0.45,
    (Backdrop.ACRYLIC, False): 0.8, (Backdrop.ACRYLIC, True): 0.65,
}

MICA_MIN_BUILD = 22000  # Windows 11 21H2, through an undocumented attribute
SYSTEMBACKDROP_MIN_BUILD = 22523  # DWMWA_SYSTEMBACKDROP_TYPE (Mica and Acrylic)


def _windows_build() -> int:
    return sys.getwindowsversion().build if sys.platform == "win32" else 0


def backdrop_supported(backdrop) -> bool:
    """Whether DWM on this system can draw ``backdrop``."""

    backdrop = Backdrop(backdrop)
    if backdrop == Backdrop.NONE:
        return True
    if backdrop == Backdrop.MICA:
        return _windows_build() >= MICA_MIN_BUILD
    return _windows_build() >= SYSTEMBACKDROP_MIN_BUILD


def supported_backdrops() -> list:
    return [backdrop for backdrop in Backdrop if backdrop_supported(backdrop)]


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
        self._backdrop = Backdrop.NONE

    @property
    def mode(self) -> Theme:
        return self._mode

    def backdrop(self) -> Backdrop:
        """The material kit windows draw on; NONE when unsupported."""

        return self._backdrop

    def set_backdrop(self, backdrop) -> None:
        backdrop = Backdrop(backdrop)
        if not backdrop_supported(backdrop):
            backdrop = Backdrop.NONE
        if backdrop == self._backdrop:
            return
        self._backdrop = backdrop
        self._refresh()

    def background(self, name: str) -> QColor:
        """The fill for a window-level background, adjusted for the backdrop.

        ``window``: the whole window (under the frame); ``sidebar``: the frame
        parts (sidebar, title bar, run bar); ``layer``: the panel page content
        sits on. Without a backdrop these are the plain tokens, and the layer is
        transparent so the window color shows.
        """

        if self._backdrop == Backdrop.NONE:
            return QColor(0, 0, 0, 0) if name == "layer" else self.color(name)
        if name == "layer":
            return self.color("window")
        if name == "sidebar":
            return QColor(0, 0, 0, 0)
        color = self.color("sidebar")
        color.setAlphaF(BACKDROP_TINT[(self._backdrop, self.is_dark())])
        return color

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
