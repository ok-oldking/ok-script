"""Icons for the kit: a small bundled stroke set plus app-provided files.

Bundled icons are drawn in a 24x24 box with ``currentColor`` strokes and are
tinted at paint time, so a QIcon made by :func:`icon` follows theme changes
without being recreated. Apps give their own tasks, groups and tabs an SVG or
PNG through :func:`load_icon`; those keep their own colors.
"""

import hashlib
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "play": '<path d="M7 3.5v17L20.5 12z" fill="currentColor" stroke="currentColor" stroke-width="1.5"/>',
    "pause": '<rect x="5.5" y="4" width="4.5" height="16" rx="1.25" fill="currentColor" stroke="none"/>'
             '<rect x="14" y="4" width="4.5" height="16" rx="1.25" fill="currentColor" stroke="none"/>',
    "stop": '<rect x="4.5" y="4.5" width="15" height="15" rx="2.5" fill="currentColor" stroke="none"/>',
    "power": '<path d="M12 3v9M6.3 6.8a8 8 0 1 0 11.4 0"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "chevron-up": '<path d="M6 15l6-6 6 6"/>',
    "chevron-right": '<path d="M9 6l6 6-6 6"/>',
    "chevron-left": '<path d="M15 6l-6 6 6 6"/>',
    "gear": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 '
            '0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 '
            '0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 '
            '2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 '
            '2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 '
            '2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
            '<circle cx="12" cy="12" r="3"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "alert": '<path d="M12 3 2 20h20zM12 10v4M12 17h.01"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v4.5h-4.5"/>',
    "reset": '<path d="M4 12a8 8 0 1 0 2.5-5.8M4 4v4h4"/>',
    "camera": '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "folder": '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 '
              '1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
    "export": '<path d="M12 15V3M7 8l5-5 5 5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    "file": '<path d="M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6"/>',
    "history": '<path d="M3 12a9 9 0 1 0 2.6-6.4M3 4v4h4M12 7v5l3 2"/>',
    "bolt": '<path d="M13 3 5 14h6l-1 7 8-11h-6z"/>',
    "timer": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 1.5M9 2h6"/>',
    "tasks": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/>'
             '<circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "code": '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.4 3.4-5 6.5-5s5.7 1.6 6.5 5M16 4.5a3.5 3.5 '
             '0 0 1 0 7M18 15c2 .6 3.2 2.3 3.5 5"/>',
    "gamepad": '<rect x="2" y="7" width="20" height="11" rx="5"/><path d="M7 11v3M5.5 12.5h3M15.5 12h.01M18 14h.01"/>',
    "bell": '<path d="M6 9a6 6 0 1 1 12 0c0 5 2 6.5 2 6.5H4S6 14 6 9zM10 19.5a2 2 0 0 0 4 0"/>',
    "pen": '<path d="M4 20h4L19 9l-4-4L4 16zM14 6l4 4"/>',
    "layers": '<path d="M12 3 3 8l9 5 9-5zM3 13l9 5 9-5"/>',
    "bug": '<rect x="7" y="8" width="10" height="12" rx="5"/><path d="M12 8V5M9 5.5 10.5 7M15 5.5 13.5 7M3 '
           '13h4M17 13h4M4 19l3-2M20 19l-3-2"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
    "grid": '<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" '
            'rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" '
            'width="7.5" height="7.5" rx="1.5"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
    "text": '<path d="M5 6V4h14v2M12 4v16M9 20h6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "trash":'<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "pulse":'<path d="M3 12h4l2.5-6 5 12 2.5-6h4"/>',
    "scan": '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 '
            '1-1-1v-3M8 10h8M8 14h5"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 '
            '5.7 5.7l1-1"/>',
    "heart": '<path d="M12 20s-7.5-4.6-9-9.3C2 7.5 4.2 5 7 5c2 0 3.3 1.2 5 3 1.7-1.8 3-3 5-3 2.8 0 5 2.5 4 5.7'
             '-1.5 4.7-9 9.3-9 9.3z"/>',
    "panel": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
    "download": '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    "share": '<path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7M16 6l-4-4-4 4M12 2v13"/>',
    "chat": '<path d="M21 11.5a8.5 8.5 0 0 1-12.6 7.4L3 20l1.2-5A8.5 8.5 0 1 1 21 11.5z"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01"/>',
    "palette": '<circle cx="12" cy="12" r="9"/><circle cx="8" cy="10" r="1.2"/><circle cx="12" cy="7.5" r="1.2"/>'
               '<circle cx="16" cy="10" r="1.2"/><path d="M12 21a3 3 0 0 1 0-6h2a3 3 0 0 0 3-3"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "github": '<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 '
              '0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.4 5.4 0 0 0 4 9c0 3.5 3 '
              '5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4M9 18c-4.51 2-5-2-7-2"/>',
    "window-minimize": '<path d="M6 12h12"/>',
    "window-maximize": '<rect x="6" y="6" width="12" height="12" rx="1"/>',
    "window-restore": '<rect x="6" y="8.5" width="9.5" height="9.5" rx="1"/><path d="M8.5 6H17a1 1 0 0 1 1 1v8.5"/>',
    "window-close": '<path d="M6 6l12 12M18 6 6 18"/>',
}

ICON_NAMES = tuple(_PATHS)


def svg_markup(name: str, color, stroke_width: float = 1.75) -> str:
    """Return the full SVG document for bundled icon ``name`` in ``color``."""

    try:
        body = _PATHS[name]
    except KeyError:
        raise KeyError(f"unknown kit icon: {name!r}") from None
    color = QColor(color).name()
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" '
            f'color="{color}">{body.replace("currentColor", color)}</svg>')


def icon_file(name: str, color, stroke_width: float = 1.75) -> str:
    """Write a tinted bundled icon to a cache file and return its path.

    Stylesheets can only reference images by path, e.g. combo box arrows.
    """

    markup = svg_markup(name, color, stroke_width)
    digest = hashlib.sha1(markup.encode()).hexdigest()[:12]
    folder = Path(tempfile.gettempdir()) / "ok-kit-icons"
    path = folder / f"{name}-{digest}.svg"
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(markup, encoding="utf-8")
        os.replace(tmp, path)
    return path.as_posix()


def _render(renderer: QSvgRenderer, size: QSize, dpr: float) -> QPixmap:
    image = QImage(round(size.width() * dpr), round(size.height() * dpr), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, _fit(renderer, QRectF(0, 0, image.width(), image.height())))
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def _fit(renderer: QSvgRenderer, rect: QRectF) -> QRectF:
    box = renderer.viewBoxF()
    if box.isEmpty():
        return rect
    scale = min(rect.width() / box.width(), rect.height() / box.height())
    w, h = box.width() * scale, box.height() * scale
    return QRectF(rect.x() + (rect.width() - w) / 2, rect.y() + (rect.height() - h) / 2, w, h)


class _TintedIconEngine(QIconEngine):
    """Paints a bundled icon in a theme color resolved at paint time."""

    def __init__(self, name: str, color=None, stroke_width: float = 1.75):
        super().__init__()
        if name not in _PATHS:
            raise KeyError(f"unknown kit icon: {name!r}")
        self.name = name
        self.color = color
        self.stroke_width = stroke_width

    def _resolve(self, mode) -> QColor:
        from ok.ui.qt.kit.theme import theme
        if mode == QIcon.Mode.Disabled:
            return theme.color("text_disabled")
        if self.color is None:
            return theme.color("text")
        if isinstance(self.color, str) and not self.color.startswith("#"):
            return theme.color(self.color)
        return QColor(self.color)

    def paint(self, painter, rect, mode, state):
        renderer = QSvgRenderer(QByteArray(svg_markup(self.name, self._resolve(mode), self.stroke_width).encode()))
        renderer.render(painter, QRectF(rect))

    def pixmap(self, size, mode, state):
        renderer = QSvgRenderer(QByteArray(svg_markup(self.name, self._resolve(mode), self.stroke_width).encode()))
        return _render(renderer, size, 1.0)

    def scaledPixmap(self, size, mode, state, scale):
        renderer = QSvgRenderer(QByteArray(svg_markup(self.name, self._resolve(mode), self.stroke_width).encode()))
        return _render(renderer, size, scale)

    def clone(self):
        return _TintedIconEngine(self.name, self.color, self.stroke_width)


class _SvgFileIconEngine(QIconEngine):
    """Renders an app SVG crisply at any size and device pixel ratio."""

    def __init__(self, data: bytes):
        super().__init__()
        self.data = data
        self.renderer = QSvgRenderer(QByteArray(data))

    def paint(self, painter, rect, mode, state):
        self.renderer.render(painter, _fit(self.renderer, QRectF(rect)))

    def pixmap(self, size, mode, state):
        return self._disabled(_render(self.renderer, size, 1.0), mode)

    def scaledPixmap(self, size, mode, state, scale):
        return self._disabled(_render(self.renderer, size, scale), mode)

    @staticmethod
    def _disabled(pixmap: QPixmap, mode) -> QPixmap:
        if mode != QIcon.Mode.Disabled:
            return pixmap
        image = pixmap.toImage()
        painter = QPainter(image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(image.rect(), QColor(0, 0, 0, 100))
        painter.end()
        result = QPixmap.fromImage(image)
        result.setDevicePixelRatio(pixmap.devicePixelRatio())
        return result

    def clone(self):
        return _SvgFileIconEngine(self.data)


class _RasterFileIconEngine(QIconEngine):
    """Fit raster artwork by its visible bounds, preserving its aspect ratio."""

    def __init__(self, image: QImage):
        super().__init__()
        self.image = image

    def paint(self, painter, rect, mode, state):
        scale = min(rect.width() / self.image.width(), rect.height() / self.image.height())
        width, height = self.image.width() * scale, self.image.height() * scale
        target = QRectF(rect.x() + (rect.width() - width) / 2,
                        rect.y() + (rect.height() - height) / 2, width, height)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if mode == QIcon.Mode.Disabled:
            painter.setOpacity(painter.opacity() * 0.4)
        painter.drawImage(target, self.image)
        painter.restore()

    def pixmap(self, size, mode, state):
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size, mode, state, scale):
        image = QImage(round(size.width() * scale), round(size.height() * scale),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        self.paint(painter, image.rect(), mode, state)
        painter.end()
        result = QPixmap.fromImage(image)
        result.setDevicePixelRatio(scale)
        return result

    def clone(self):
        return _RasterFileIconEngine(self.image)


class _ColorizedIconEngine(QIconEngine):
    """Tint an icon's alpha mask using a color resolved for the current theme."""

    def __init__(self, source: QIcon, color):
        super().__init__()
        self.source = source
        self.color = color

    def paint(self, painter, rect, mode, state):
        size = QSize(max(1, round(rect.width())), max(1, round(rect.height())))
        pixmap = self.scaledPixmap(size, mode, state, painter.device().devicePixelRatioF())
        painter.drawPixmap(rect, pixmap)

    def pixmap(self, size, mode, state):
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size, mode, state, scale):
        from ok.ui.qt.kit.theme import theme

        value = self.color
        if isinstance(value, dict):
            value = value.get("dark" if theme.is_dark() else "light", "text")
        color = theme.color(value) if isinstance(value, str) and not value.startswith("#") else QColor(value)
        if mode == QIcon.Mode.Disabled:
            color.setAlphaF(color.alphaF() * 0.4)
        image = self.source.pixmap(size, scale, QIcon.Mode.Normal, state).toImage()
        painter = QPainter(image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(image.rect(), color)
        painter.end()
        result = QPixmap.fromImage(image)
        result.setDevicePixelRatio(image.devicePixelRatio())
        return result

    def clone(self):
        return _ColorizedIconEngine(self.source, self.color)


def tinted_icon(source: QIcon, color) -> QIcon:
    """Recolor artwork at paint time; ``color`` can supply light/dark shades."""

    return QIcon(_ColorizedIconEngine(source, color))


def _trim_transparent(image: QImage) -> QImage:
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    # Ignore nearly invisible export fringes when measuring the artwork.
    occupied = [i for i, alpha in enumerate(bytes(rgba.constBits())[3::4]) if alpha >= 16]
    if not occupied:
        return image
    width = rgba.width()
    left = min(i % width for i in occupied)
    right = max(i % width for i in occupied)
    top, bottom = occupied[0] // width, occupied[-1] // width
    return image.copy(left, top, right - left + 1, bottom - top + 1)


def icon(name: str, color=None, stroke_width: float = 1.75) -> QIcon:
    """A bundled icon.

    ``color`` is a theme token name (``"text_secondary"``, ``"accent"``,
    ``"on_accent"``), a hex string or QColor; ``None`` uses the text color.
    """

    return QIcon(_TintedIconEngine(name, color, stroke_width))


@lru_cache(maxsize=256)
def _load_file_icon(path: str, mtime: float, trim_transparent: bool = False) -> QIcon:
    if path.lower().endswith(".svg"):
        data = Path(path).read_bytes()
        engine = _SvgFileIconEngine(data)
        if not engine.renderer.isValid():
            raise ValueError(f"invalid SVG icon: {path}")
        return QIcon(engine)
    if trim_transparent:
        image = QImage(path)
        if image.isNull():
            raise ValueError(f"unsupported icon file: {path}")
        return QIcon(_RasterFileIconEngine(_trim_transparent(image)))
    result = QIcon(path)
    if result.isNull():
        raise ValueError(f"unsupported icon file: {path}")
    return result


def load_icon(source, base_dir=None, *, trim_transparent: bool = False) -> QIcon:
    """Load an app-provided icon.

    ``source`` is a path to an ``.svg`` or raster file (relative paths are
    resolved against ``base_dir`` or the working directory), a ``QIcon``, or
    ``None`` for no icon.
    ``trim_transparent`` fits raster artwork by its alpha bounds at paint time;
    the source file stays unchanged.
    """

    if source is None:
        return QIcon()
    if isinstance(source, QIcon):
        return source
    path = Path(source)
    if not path.is_absolute() and base_dir is not None:
        path = Path(base_dir) / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"icon file not found: {path}")
    return _load_file_icon(str(path), path.stat().st_mtime, trim_transparent)
