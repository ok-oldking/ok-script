import threading

from ok.util.color import is_close_to_pure_color
from ok.util.logger import Logger

from ok.device.capture_methods.base import BaseWindowsCaptureMethod
from ok.device.capture_methods.bitblt_utils import (
    capture_by_bitblt,
    capture_desktop_by_bitblt,
    clean_up_desktop_bitblt,
    composite_hwnds,
    get_crop_point,
)

logger = Logger.get_logger(__name__)

render_full = False


class BitBltCaptureMethod(BaseWindowsCaptureMethod):
    name = "BitBlt"
    short_description = "fastest, least compatible"
    description = (
            "\nThe best option when compatible. But it cannot properly record "
            + "\nOpenGL, Hardware Accelerated or Exclusive Fullscreen windows. "
            + "\nThe smaller the selected region, the more efficient it is. "
    )

    def __init__(self, hwnd_window: 'HwndWindow'):
        super().__init__(hwnd_window)
        self.dc_object = None
        self.bitmap = None
        self.window_dc = None
        self.compatible_dc = None
        self.last_hwnd = 0
        self.last_width = 0
        self.last_height = 0
        self.lock = threading.Lock()
        self.contexts = {}

    def do_get_frame(self):
        with self.lock:
            if self.hwnd_window.real_x_offset != 0 or self.hwnd_window.real_y_offset != 0:
                x = self.hwnd_window.real_x_offset
                y = self.hwnd_window.real_y_offset
            else:
                x, y = get_crop_point(self.hwnd_window.window_width, self.hwnd_window.window_height,
                                      self.hwnd_window.width, self.hwnd_window.height)

            width = self.hwnd_window.real_width or self.hwnd_window.width
            height = self.hwnd_window.real_height or self.hwnd_window.height

            bg = capture_by_bitblt(self, self.hwnd_window.hwnd, width, height, x, y, render_full)
            bg = composite_hwnds(bg, self.hwnd_window, self.contexts, render_full)

            return bg

    def get_name(self):
        return f'BitBlt_{render_full}'

    def test_exclusive_full_screen(self):
        frame = self.do_get_frame()
        if frame is None:
            logger.error(f'Failed to test_exclusive_full_screen {self.hwnd_window}')
            return False
        return True

    def test_is_not_pure_color(self):
        frame = self.do_get_frame()
        if frame is None:
            logger.error(f'Failed to test_is_not_pure_color frame is None {self.hwnd_window}')
            return False
        else:
            if is_close_to_pure_color(frame):
                logger.error(f'Failed to test_is_not_pure_color failed {self.hwnd_window}')
                return False
            else:
                return True



class ForegroundBitBltCaptureMethod(BaseWindowsCaptureMethod):
    name = "ForegroundBitBlt"
    short_description = "fastest, foreground only"
    description = (
            "\nCaptures the desktop pixels at the game window position. "
            + "\nThis is designed for foreground-only overlays and upscalers. "
            + "\nIt is very fast, but the game window must be in front and unobscured. "
    )

    def __init__(self, hwnd_window: 'HwndWindow'):
        super().__init__(hwnd_window)
        self.window_dc = None
        self.dc_object = None
        self.compatible_dc = None
        self.bitmap = None
        self.last_width = 0
        self.last_height = 0
        self.lock = threading.Lock()

    def do_get_frame(self):
        if not self.hwnd_window.is_foreground():
            return None

        with self.lock:
            x = self.hwnd_window.x + self.hwnd_window.real_x_offset
            y = self.hwnd_window.y + self.hwnd_window.real_y_offset
            width = self.hwnd_window.real_width or self.hwnd_window.width
            height = self.hwnd_window.real_height or self.hwnd_window.height
            return capture_desktop_by_bitblt(self, width, height, x, y)

    def close(self):
        with self.lock:
            clean_up_desktop_bitblt(self)
