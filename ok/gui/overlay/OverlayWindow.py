import time

from PySide6.QtCore import QObject, Signal, Qt, QTimer

from ok import Logger
from ok import og
from ok.device.capture import HwndWindow
from ok.gui.Communicate import communicate
from ok.gui.debug.OverlayWidget import OverlayWidget

logger = Logger.get_logger(__name__)


class Communicate(QObject):
    speak = Signal(str)


class OverlayWindow(OverlayWidget):
    custom_draw_requested = Signal(str, object, object)
    custom_clear_requested = Signal(object)

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__()
        self._source_visible = False
        app = getattr(og, 'app', None)
        ok_config = getattr(app, 'ok_config', None)
        self._boxes_enabled = bool(ok_config.get('use_overlay', False) if ok_config is not None
                                   else getattr(app, 'debug', False))
        self._boxes_active = False
        self._boxes_until = 0
        self._custom_drawing_active = False
        self._custom_drawing_until = 0
        self.custom_painters = {}
        self._custom_painter_until = {}
        # Set translucent background
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Ensure mouse events are received properly
        self.setAttribute(Qt.WA_OpaquePaintEvent)

        # Set window flag to handle mouse events properly with translucent background
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        communicate.draw_box.connect(self.on_draw_box)
        communicate.clear_box.connect(self.clear_drawing)
        communicate.blur_overlay.connect(self.update_blur_patches)
        communicate.clear_blur_overlay.connect(self.clear_blur_overlay)
        self.custom_draw_requested.connect(self._set_custom_draw, Qt.QueuedConnection)
        self.custom_clear_requested.connect(self._clear_custom_draw, Qt.QueuedConnection)

        # self.update_overlay(hwnd_window.visible, hwnd_window.x, hwnd_window.y, hwnd_window.window_width,
        #                     hwnd_window.window_height, hwnd_window.width, hwnd_window.height, hwnd_window.scaling)

    def update_overlay(self, visible, x, y, window_width, window_height, width, height, scaling):
        logger.debug(f'update_overlay: {visible}, {x}, {y}, {width}, {height}, {scaling}')
        self._source_visible = visible
        if visible:
            self.setGeometry(x / scaling, y / scaling, width / scaling, height / scaling)
        self.refresh_visibility()

    def set_boxes_enabled(self, enabled):
        self._boxes_enabled = enabled
        if not enabled:
            self._boxes_active = False
            self._boxes_until = 0
        self.refresh_visibility()
        self.update()

    def request_show(self, duration=4.0):
        self._custom_drawing_active = True
        self._custom_drawing_until = time.monotonic() + duration
        self.refresh_visibility()
        self.update()
        QTimer.singleShot(int(duration * 1000) + 10, self.expire_custom_drawing)

    def draw(self, key, callback, duration=None):
        """Schedule arbitrary painting with callback(QPainter, OverlayWindow)."""
        if not callable(callback):
            raise TypeError('callback must be callable')
        self.custom_draw_requested.emit(str(key), callback, duration)

    def clear_draw(self, key=None):
        """Remove one custom painter, or all painters when key is None."""
        self.custom_clear_requested.emit(key)

    def _set_custom_draw(self, key, callback, duration):
        self.custom_painters[key] = callback
        if duration is None:
            self._custom_painter_until.pop(key, None)
        else:
            duration = max(0.0, float(duration))
            self._custom_painter_until[key] = time.monotonic() + duration
            QTimer.singleShot(int(duration * 1000) + 10, lambda: self._expire_custom_draw(key))
        self.refresh_visibility()
        self.update()

    def _clear_custom_draw(self, key):
        if key is None:
            self.custom_painters.clear()
            self._custom_painter_until.clear()
        else:
            key = str(key)
            self.custom_painters.pop(key, None)
            self._custom_painter_until.pop(key, None)
        self.refresh_visibility()
        self.update()

    def _expire_custom_draw(self, key):
        until = self._custom_painter_until.get(key)
        if until is not None and time.monotonic() >= until:
            self.custom_painters.pop(key, None)
            self._custom_painter_until.pop(key, None)
            self.refresh_visibility()
            self.update()

    def on_draw_box(self, key, boxes, color, frame, debug):
        if boxes and self._boxes_enabled:
            self._boxes_active = True
            self._boxes_until = time.monotonic() + 4.0
            self.refresh_visibility()
            self.update()
            QTimer.singleShot(4010, self.expire_boxes)

    def clear_drawing(self):
        self._boxes_active = False
        self._boxes_until = 0
        self.refresh_visibility()
        self.update()

    def expire_boxes(self):
        if self._boxes_active and time.monotonic() >= self._boxes_until:
            self._boxes_active = False
            self.refresh_visibility()
            self.update()

    def expire_custom_drawing(self):
        if self._custom_drawing_active and time.monotonic() >= self._custom_drawing_until:
            self._custom_drawing_active = False
            self.refresh_visibility()
            self.update()

    def update_blur_patches(self, patches):
        self.set_blur_patches(patches)
        self.refresh_visibility()

    def clear_blur_overlay(self):
        self.clear_blur_patches()
        self.refresh_visibility()

    def refresh_visibility(self):
        required = (self._boxes_active or self._custom_drawing_active
                    or bool(self.blur_images) or bool(self.custom_painters))
        if self._source_visible and required and not self.isVisible():
            self.show()
            return
        if (not self._source_visible or not required) and self.isVisible():
            self.hide()
