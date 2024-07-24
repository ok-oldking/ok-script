import ctypes
import ctypes.wintypes

import win32gui

from ok.logging.Logger import get_logger

MDT_EFFECTIVE_DPI = 0
user32 = ctypes.WinDLL('user32', use_last_error=True)

DWMWA_EXTENDED_FRAME_BOUNDS = 9

logger = get_logger(__name__)


def is_window_minimized(hWnd):
    return user32.IsIconic(hWnd) != 0


def get_window_bounds(hwnd):
    try:
        extended_frame_bounds = ctypes.wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(extended_frame_bounds),
            ctypes.sizeof(extended_frame_bounds),
        )
        client_x, client_y, client_width, client_height = win32gui.GetClientRect(hwnd)
        window_left, window_top, window_right, window_bottom = win32gui.GetWindowRect(hwnd)
        window_width = window_right - window_left
        window_height = window_bottom - window_top
        client_x, client_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
        monitor = user32.MonitorFromWindow(hwnd, 2)  # 2 = MONITOR_DEFAULTTONEAREST

        # Get the DPI
        dpiX = ctypes.c_uint()
        dpiY = ctypes.c_uint()
        ctypes.windll.shcore.GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, ctypes.byref(dpiX), ctypes.byref(dpiY))
        return client_x, client_y, window_width, window_height, client_width, client_height, dpiX.value / 96
    except Exception as e:
        logger.error(f'get_window_bounds exception', e)
        return 0, 0, 0, 0, 0, 0, 1


def is_foreground_window(hwnd):
    return win32gui.IsWindowVisible(hwnd) and win32gui.GetForegroundWindow() == hwnd
