from typing import cast

import cv2
import d3dshot
import win32api
import win32con
from cv2.typing import MatLike
from typing_extensions import override

from ok.capture.HwndWindow import HwndWindow
from ok.capture.windows.BaseWindowsCaptureMethod import BaseWindowsCaptureMethod


# orignal https://github.com/Toufool/AutoSplit/blob/master/src/capture_method/DesktopDuplicationCaptureMethod.py
class DesktopDuplicationCaptureMethod(BaseWindowsCaptureMethod):
    name = "Direct3D Desktop Duplication"
    short_description = "slower, bound to display"
    description = (
            "\nDuplicates the desktop using Direct3D. "
            + "\nIt can record OpenGL and Hardware Accelerated windows. "
            + "\nAbout 10-15x slower than BitBlt. Not affected by window size. "
            + "\nOverlapping windows will show up and can't record across displays. "
            + "\nThis option may not be available for hybrid GPU laptops, "
            + "\nsee D3DDD-Note-Laptops.md for a solution. "
    )

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__(hwnd_window)
        self.desktop_duplication = d3dshot.create(capture_output="numpy")

    @override
    def do_get_frame(self) -> MatLike | None:

        image: MatLike | None = None

        hwnd = self.hwnd_window.hwnd
        if hwnd is None:
            return image

        hmonitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        if not hmonitor:
            return None

        self.desktop_duplication.display = next(
            display for display
            in self.desktop_duplication.displays
            if display.hmonitor == hmonitor
        )
        left = self.hwnd_window.x
        top = self.hwnd_window.y
        right = left + self.hwnd_window.width
        bottom = top + self.hwnd_window.height
        screenshot = cast(
            MatLike | None,
            self.desktop_duplication.screenshot((left, top, right, bottom)),
        )
        if screenshot is None:
            return None
        return cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)

    @override
    def close(self):
        if self.desktop_duplication is not None:
            self.desktop_duplication.stop()
