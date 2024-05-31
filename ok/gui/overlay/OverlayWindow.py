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
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.FramelessWindowHint)  # Make the window frameless
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowTransparentForInput, True)
        self.setWindowFlag(Qt.Tool)
        communicate.window.connect(self.update_overlay)
        self.update_overlay(hwnd_window.visible, hwnd_window.x, hwnd_window.y, hwnd_window.border,
                            hwnd_window.title_height, hwnd_window.width, hwnd_window.height, hwnd_window.scaling)

    def update_overlay(self, visible, x, y, border, title_height, width, height, scaling):
        logger.debug(f'update_overlay: {visible}, {x}, {y}, {border}, {title_height} {width}, {height}, {scaling}')
        if visible:
            self.setGeometry((x + border) / scaling, (y + title_height) / scaling, width / scaling, height / scaling)
        if visible:
            self.show()
        else:
            self.hide()
