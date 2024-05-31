import ctypes
import ctypes.wintypes

import win32gui

user32 = ctypes.WinDLL('user32', use_last_error=True)

DWMWA_EXTENDED_FRAME_BOUNDS = 9


def is_window_minimized(hWnd):
    return user32.IsIconic(hWnd) != 0


def get_window_bounds(hwnd):
    extended_frame_bounds = ctypes.wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd,
        DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(extended_frame_bounds),
        ctypes.sizeof(extended_frame_bounds),
    )
    scaling = user32.GetDpiForWindow(hwnd) / 96
    client_x, client_y, client_width, client_height = win32gui.GetClientRect(hwnd)
    window_width = extended_frame_bounds.right - extended_frame_bounds.left
    window_height = extended_frame_bounds.bottom - extended_frame_bounds.top
    border = int((window_width - client_width) / 2)
    title = window_height - client_height - border
    window_rect = win32gui.GetWindowRect(hwnd)
    ext_left_bounds = extended_frame_bounds.left - window_rect[0]
    ext_top_bounds = extended_frame_bounds.top - window_rect[1]
    return extended_frame_bounds.left, extended_frame_bounds.top, border, title, client_width, client_height, scaling, ext_left_bounds, ext_top_bounds


def is_foreground_window(hwnd):
    return win32gui.IsWindowVisible(hwnd) and win32gui.GetForegroundWindow() == hwnd
