import cv2
import win32api
import win32con

from ok.util.window import find_display

from ok.device.capture_methods.base import BaseWindowsCaptureMethod

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

    def __init__(self, hwnd_window: 'HwndWindow'):
        super().__init__(hwnd_window)
        import d3dshot
        self.desktop_duplication = d3dshot.create(capture_output="numpy")

    def do_get_frame(self):

        hwnd = self.hwnd_window.hwnd
        if hwnd == 0:
            return None

        hmonitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        if not hmonitor:
            return None

        self.desktop_duplication.display = find_display(hmonitor, self.desktop_duplication.displays)
        left = self.hwnd_window.x
        top = self.hwnd_window.y
        right = left + self.hwnd_window.width
        bottom = top + self.hwnd_window.height
        screenshot = self.desktop_duplication.screenshot((left, top, right, bottom))
        if screenshot is None:
            return None
        return cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)

    def close(self):
        if self.desktop_duplication is not None:
            self.desktop_duplication.stop()
