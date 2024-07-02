import ctypes
import time

import numpy as np
import pywintypes
import win32con
import win32gui
import win32ui
from cv2.typing import MatLike
from typing_extensions import override

from ok.capture.windows.BaseWindowsCaptureMethod import BaseWindowsCaptureMethod
from ok.capture.windows.utils import try_delete_dc, BGRA_CHANNEL_COUNT
from ok.color.Color import is_close_to_pure_color
from ok.logging.Logger import get_logger

# This is an undocumented nFlag value for PrintWindow
PW_RENDERFULLCONTENT = 0x00000002

logger = get_logger(__name__)


def is_blank(image: MatLike):
    """
    BitBlt can return a balnk buffer. Either because the target is unsupported,
    or because there's two windows of the same name for the same executable.
    """
    return not image.any()


class BitBltCaptureMethod(BaseWindowsCaptureMethod):
    name = "BitBlt"
    short_description = "fastest, least compatible"
    description = (
            "\nThe best option when compatible. But it cannot properly record "
            + "\nOpenGL, Hardware Accelerated or Exclusive Fullscreen windows. "
            + "\nThe smaller the selected region, the more efficient it is. "
    )

    render_full = False

    @override
    def do_get_frame(self) -> MatLike | None:
        if self.hwnd_window.real_x_offset != 0 or self.hwnd_window.real_y_offset != 0:
            x = self.hwnd_window.real_x_offset
            y = self.hwnd_window.real_y_offset
        else:
            # x = self.hwnd_window.border
            # y = self.hwnd_window.title_height
            # rect = win32gui.GetWindowRect(self.hwnd_window.hwnd)
            # Calculate the width and height
            # window_width = rect[2] - rect[0]
            # window_height = rect[3] - rect[1]
            x, y = self.get_crop_point(self.hwnd_window.window_width, self.hwnd_window.window_height,
                                       self.hwnd_window.width, self.hwnd_window.height)
        return bit_blt_capture_frame(self.hwnd_window.hwnd, x,
                                     y,
                                     self.hwnd_window.real_width or self.hwnd_window.width,
                                     self.hwnd_window.real_height or self.hwnd_window.height,
                                     self.render_full)

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


def bit_blt_capture_frame(hwnd, border, title_height, width, height, _render_full_content=False):
    image: MatLike | None = None
    start = time.time()

    if hwnd is None:
        return image

    x, y, width, height = (border,
                           title_height, width, height)

    if width <= 0 or height <= 0:
        return None
    # If the window closes while it's being manipulated, it could cause a crash
    try:

        window_dc = win32gui.GetWindowDC(hwnd)
        dc_object = win32ui.CreateDCFromHandle(window_dc)

        # Causes a 10-15x performance drop. But allows recording hardware accelerated windows
        if _render_full_content:
            ctypes.windll.user32.PrintWindow(hwnd, dc_object.GetSafeHdc(), PW_RENDERFULLCONTENT)

        # On Windows there is a shadow around the windows that we need to account for.
        # left_bounds, top_bounds = 3, 0
        compatible_dc = dc_object.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(dc_object, width, height)

        compatible_dc.SelectObject(bitmap)
        compatible_dc.BitBlt(
            (0, 0),
            (width, height),
            dc_object,
            (x, y),
            win32con.SRCCOPY,
        )
        image = np.frombuffer(bitmap.GetBitmapBits(True), dtype=np.uint8)
    except (win32ui.error, pywintypes.error):
        # Invalid handle or the window was closed while it was being manipulated
        return None

    if is_blank(image):
        image = None
    else:
        image.shape = (height, width, BGRA_CHANNEL_COUNT)

    # Cleanup DC and handle
    try_delete_dc(dc_object)
    try_delete_dc(compatible_dc)
    win32gui.ReleaseDC(hwnd, window_dc)
    win32gui.DeleteObject(bitmap.GetHandle())
    # logger.debug(f'bit_blt capture {time.time() - start} {x, y}')
    return image


if __name__ == '__main__':
    print(bit_blt_capture_frame("MuMu模拟器12", None))
