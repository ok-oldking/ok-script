"""Mica drawn by the app, for parts of a window whose DWM backdrop is another material.

DWM gives a window one backdrop. To show Mica in one area of an Acrylic
window, this module rebuilds Mica the way Windows composes it: the desktop
wallpaper under that area, blurred heavily, given the luminosity of the theme's
Mica tint and then mostly desaturated toward it (WinUI's MicaController
defaults). Like real Mica it ignores other windows and turns flat when the
window is inactive.
"""

import os
import sys
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

# The wallpaper is reduced to this many pixels across a screen; smooth scaling
# back up gives Mica's very wide blur.
SAMPLE_WIDTH = 48
# Wallpapers are kept at most this wide, so later per-screen work stays cheap.
CACHE_WIDTH = 640
# The blurred layer is cached at this fraction of the screen size. QPainter
# magnifies with blocky texels at large factors, so the sample is smoothly
# scaled up once here and painting only ever magnifies about 2x.
LAYER_SCALE = 0.5
# How often the wallpaper path, style and modification time are re-read.
RECHECK_SECONDS = 2.0

# Mica tint (gray level) and tint opacity, by dark mode.
MICA_TINT = {True: (0x20, 0.8), False: (0xF3, 0.5)}

SPI_GETDESKWALLPAPER = 0x0073


def tint_color(dark: bool) -> QColor:
    """The flat Mica color, used when the window is inactive."""

    level = MICA_TINT[dark][0]
    return QColor(level, level, level)


# --- color math (W3C compositing, non-separable blend modes) ------------------

def _lum(r: float, g: float, b: float) -> float:
    return 0.3 * r + 0.59 * g + 0.11 * b


def _set_lum(r: float, g: float, b: float, lum: float) -> tuple:
    delta = lum - _lum(r, g, b)
    r, g, b = r + delta, g + delta, b + delta
    lum = _lum(r, g, b)
    low, high = min(r, g, b), max(r, g, b)
    if low < 0:
        r, g, b = (lum + (c - lum) * lum / (lum - low) for c in (r, g, b))
    if high > 1:
        r, g, b = (lum + (c - lum) * (1 - lum) / (high - lum) for c in (r, g, b))
    return r, g, b


def _mica_pixel(color: QColor, tint: float, opacity: float) -> int:
    # Luminosity blend with the tint, then a Color blend with the (gray) tint
    # at ``opacity``, which pulls the result toward gray at its own luminosity.
    r, g, b = _set_lum(color.redF(), color.greenF(), color.blueF(), tint)
    lum = _lum(r, g, b)
    r, g, b = (c + (lum - c) * opacity for c in (r, g, b))
    return QColor.fromRgbF(min(1.0, max(0.0, r)), min(1.0, max(0.0, g)), min(1.0, max(0.0, b))).rgb()


# --- wallpaper ---------------------------------------------------------------

def _wallpaper_settings() -> tuple:
    """(path, modification time, style, tile, background RGB) of the desktop."""

    path, style, tile, background = "", "10", "0", (0, 0, 0)
    if sys.platform != "win32":
        return path, 0, style, tile, background
    import ctypes
    import winreg
    buffer = ctypes.create_unicode_buffer(520)
    if ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, len(buffer), buffer, 0):
        path = buffer.value
    if not path or not os.path.isfile(path):
        cached = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Themes\TranscodedWallpaper")
        path = cached if os.path.isfile(cached) else ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
            style = str(winreg.QueryValueEx(key, "WallpaperStyle")[0])
            tile = str(winreg.QueryValueEx(key, "TileWallpaper")[0])
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Colors") as key:
            background = tuple(int(part) for part in str(winreg.QueryValueEx(key, "Background")[0]).split()[:3])
    except (OSError, ValueError):
        pass
    mtime = os.path.getmtime(path) if path else 0
    return path, mtime, style, tile, background


class _MicaSampler:
    def __init__(self):
        self._settings = None
        self._checked_at = 0.0
        self._wallpaper = None  # QImage, at most CACHE_WIDTH wide, or None for a solid color
        self._samples = {}  # (screen width, height, dark) -> QImage of SAMPLE_WIDTH columns

    def _refresh(self) -> None:
        now = time.monotonic()
        if self._settings is not None and now - self._checked_at < RECHECK_SECONDS:
            return
        self._checked_at = now
        settings = _wallpaper_settings()
        if settings == self._settings:
            return
        self._settings = settings
        self._samples.clear()
        image = QImage(settings[0]) if settings[0] else QImage()
        if image.isNull():
            self._wallpaper = None
        else:
            if image.width() > CACHE_WIDTH:
                image = image.scaledToWidth(CACHE_WIDTH, Qt.TransformationMode.SmoothTransformation)
            self._wallpaper = image.convertToFormat(QImage.Format.Format_RGB32)

    def _screen_image(self, width: int, height: int) -> QImage:
        """The wallpaper as Windows places it on a screen, at sample size."""

        columns = SAMPLE_WIDTH
        rows = max(1, round(SAMPLE_WIDTH * height / width))
        _path, _mtime, style, tile, background = self._settings
        canvas = QImage(columns, rows, QImage.Format.Format_RGB32)
        canvas.fill(QColor(*background))
        image = self._wallpaper
        if image is None:
            return canvas
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = QRectF(0, 0, columns, rows)
        if style == "2":  # stretch
            painter.drawImage(target, image)
        elif style == "6":  # fit: letterboxed on the background color
            scale = min(columns / image.width(), rows / image.height())
            w, h = image.width() * scale, image.height() * scale
            painter.drawImage(QRectF((columns - w) / 2, (rows - h) / 2, w, h), image)
        else:  # fill, and an approximation for center, tile and span
            scale = max(columns / image.width(), rows / image.height())
            w, h = columns / scale, rows / scale
            painter.drawImage(target, image, QRectF((image.width() - w) / 2, (image.height() - h) / 2, w, h))
        painter.end()
        return canvas

    def sample(self, width: int, height: int, dark: bool) -> QImage:
        """The Mica layer for a whole screen of this size, at LAYER_SCALE of it."""

        self._refresh()
        key = (width, height, dark)
        if key not in self._samples:
            image = self._screen_image(width, height)
            level, opacity = MICA_TINT[dark]
            tint = level / 255
            for y in range(image.height()):
                for x in range(image.width()):
                    image.setPixel(x, y, _mica_pixel(image.pixelColor(x, y), tint, opacity))
            self._samples[key] = image.scaled(max(1, round(width * LAYER_SCALE)), max(1, round(height * LAYER_SCALE)),
                                              Qt.AspectRatioMode.IgnoreAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
        return self._samples[key]


_sampler = _MicaSampler()


def paint_mica(painter: QPainter, widget, rect, dark: bool) -> None:
    """Fill ``rect`` (``widget`` coordinates) with Mica as it would look there on screen."""

    if not widget.window().isActiveWindow():
        painter.fillRect(rect, tint_color(dark))
        return
    geometry = widget.screen().geometry()
    sample = _sampler.sample(geometry.width(), geometry.height(), dark)
    origin = widget.mapToGlobal(rect.topLeft())
    scale_x = sample.width() / geometry.width()
    scale_y = sample.height() / geometry.height()
    source = QRectF((origin.x() - geometry.x()) * scale_x, (origin.y() - geometry.y()) * scale_y,
                    rect.width() * scale_x, rect.height() * scale_y)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QRectF(rect), sample, source)
    painter.restore()
