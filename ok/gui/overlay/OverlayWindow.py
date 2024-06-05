from PySide6.QtCore import QObject, Signal, Qt

from ok.capture.HwndWindow import HwndWindow
from ok.gui.Communicate import communicate
from ok.gui.debug.FrameWidget import FrameWidget
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class Communicate(QObject):
    speak = Signal(str)


class OverlayWindow(FrameWidget):
    def __init__(self, hwnd_window: HwndWindow):
        super().__init__()
        # Set translucent background
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Ensure mouse events are received properly
        self.setAttribute(Qt.WA_OpaquePaintEvent)

        # Set window flag to handle mouse events properly with translucent background
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        communicate.window.connect(self.update_overlay)
        self.update_overlay(hwnd_window.visible, hwnd_window.x, hwnd_window.y, hwnd_window.border,
                            hwnd_window.title_height, hwnd_window.width, hwnd_window.height, hwnd_window.scaling)

        self.setMouseTracking(True)

    def update_overlay(self, visible, x, y, border, title_height, width, height, scaling):
        logger.debug(f'update_overlay: {visible}, {x}, {y}, {border}, {title_height} {width}, {height}, {scaling}')
        if visible:
            self.setGeometry((x + border) / scaling, (y + title_height) / scaling, width / scaling, height / scaling)
        if visible:
            self.show()
        else:
            self.hide()
