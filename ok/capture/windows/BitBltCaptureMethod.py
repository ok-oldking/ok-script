import ctypes

import numpy as np
import pywintypes
import win32con
import win32gui
import win32ui
from cv2.typing import MatLike
from typing_extensions import override

from ok.capture.windows.BaseWindowsCaptureMethod import BaseWindowsCaptureMethod
from ok.capture.windows.utils import try_delete_dc, BGRA_CHANNEL_COUNT
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

    _render_full_content = False

    @override
    def do_get_frame(self) -> MatLike | None:

        image: MatLike | None = None

        hwnd = self.hwnd_window.hwnd
        if hwnd is None:
            return image

        x, y, width, height = self.hwnd_window.border + self.hwnd_window.ext_left_bounds, self.hwnd_window.title_height + self.hwnd_window.ext_top_bounds, self.hwnd_window.width, self.hwnd_window.height

        if width <= 0 or height <= 0:
            return None
        # If the window closes while it's being manipulated, it could cause a crash
        try:
            window_dc = win32gui.GetWindowDC(hwnd)
            dc_object = win32ui.CreateDCFromHandle(window_dc)

            # Causes a 10-15x performance drop. But allows recording hardware accelerated windows
            if self._render_full_content:
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
        return image

    def test_exclusive_full_screen(self):
        frame = self.do_get_frame()
        if frame is None:
            logger.error('Failed to test_exclusive_full_screen')
            return False
        return True
