# window.py
import ctypes
import platform
import sys
import time

import psutil
import win32api
import win32con
import win32gui
import win32process

from ok.util.logger import Logger

MDT_EFFECTIVE_DPI = 0
user32 = ctypes.WinDLL('user32', use_last_error=True)
DWMWA_EXTENDED_FRAME_BOUNDS = 9
WGC_NO_BORDER_MIN_BUILD = 20348
WGC_MIN_BUILD = 19041

logger = Logger.get_logger("capture")

WINDOWS_BUILD_NUMBER = int(platform.version().split(".")[-1]) if sys.platform == "win32" else -1


def windows_graphics_available():
    logger.info(
        f"check available WINDOWS_BUILD_NUMBER:{WINDOWS_BUILD_NUMBER} >= {WGC_NO_BORDER_MIN_BUILD} {WINDOWS_BUILD_NUMBER >= WGC_NO_BORDER_MIN_BUILD}")
    if WINDOWS_BUILD_NUMBER >= WGC_NO_BORDER_MIN_BUILD:
        try:
            from ok.rotypes import idldsl
            from ok.rotypes.roapi import GetActivationFactory
            from ok.rotypes.Windows.Graphics.Capture import IGraphicsCaptureItemInterop
            GetActivationFactory('Windows.Graphics.Capture.GraphicsCaptureItem').astype(
                IGraphicsCaptureItemInterop)
            return True
        except Exception as e:
            logger.error(f'check available failed: {e}', exception=e)
            return False


def is_blank(image):
    return not image.any()


def is_window_minimized(hWnd):
    return user32.IsIconic(hWnd) != 0


def get_exe_by_hwnd(hwnd):
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid > 0:
            process = psutil.Process(pid)

            try:
                name = process.name()
            except psutil.AccessDenied as e:
                name = ""
                logger.error("get_exe_by_hwnd process.name() AccessDenied", e)

            try:
                exe = process.exe()
            except psutil.AccessDenied as e:
                exe = ""
                logger.error("get_exe_by_hwnd process.exe() AccessDenied", e)

            try:
                cmdline = process.cmdline()
            except psutil.AccessDenied as e:
                cmdline = ""
                logger.error("get_exe_by_hwnd process.cmdline() AccessDenied", e)

            return name, exe, cmdline
        else:
            return "", "", ""
    except Exception as e:
        logger.error('get_exe_by_hwnd error', e)
        return "", "", ""


def find_display(hmonitor, displays):
    for display in displays:
        if display.hmonitor == hmonitor:
            return display
    raise ValueError("Display not found")


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
        monitor = user32.MonitorFromWindow(hwnd, 2)

        dpiX = ctypes.c_uint()
        dpiY = ctypes.c_uint()
        ctypes.windll.shcore.GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, ctypes.byref(dpiX), ctypes.byref(dpiY))
        return client_x, client_y, window_width, window_height, client_width, client_height, dpiX.value / 96
    except Exception as e:
        logger.error(f'get_window_bounds exception', e)
        return 0, 0, 0, 0, 0, 0, 1


def is_foreground_window(hwnd):
    return win32gui.IsWindowVisible(hwnd) and win32gui.GetForegroundWindow() == hwnd


def show_title_bar(hwnd):
    try:
        current_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if current_style & win32con.WS_CAPTION:
            logger.info(f"Window '{hwnd}' already has a title bar.")
            return True
        new_style = current_style | win32con.WS_CAPTION
        new_style &= ~win32con.WS_POPUP
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
        win32gui.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                              win32con.SWP_FRAMECHANGED | win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        updated_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        time.sleep(0.01)
        if updated_style & win32con.WS_CAPTION:
            logger.info(f"Title bar shown for window '{hwnd}'.")
            return True
        else:
            logger.info(f"Failed to show title bar for window '{hwnd}'.")
            return False
    except Exception as e:
        print(f"Error showing title bar for window '{hwnd}': {e}")
        return False


def resize_window(hwnd, width, height):
    if not hwnd:
        logger.info("Invalid window handle provided.")
        return False
    try:
        SWP_SHOWWINDOW = 0x0040
        SWP_NOZORDER = 0x0004
        SWP_NOREPOSITION = 0x0002
        user32.SetWindowPos(hwnd, None, 0, 0, width, height, SWP_SHOWWINDOW | SWP_NOZORDER | SWP_NOREPOSITION)
        time.sleep(0.01)

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        window_width = right - left
        window_height = bottom - top
        screen_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

        center_x = (screen_width - window_width) // 2
        center_y = (screen_height - window_height) // 2
        SWP_NOSIZE = 0x0001

        user32.SetWindowPos(hwnd, None, center_x, center_y, 0, 0,
                            SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW)
        
        start_time = time.time()
        while time.time() - start_time < 5:
            n_left, n_top, n_right, n_bottom = win32gui.GetWindowRect(hwnd)
            n_width = n_right - n_left
            n_height = n_bottom - n_top
            if n_width == width and n_height == height and n_left == center_x and n_top == center_y:
                break
            time.sleep(0.1)
        
        time.sleep(0.5)
        
        logger.info(f"Window with handle {hwnd} resized to {width}x{height} and centered at ({center_x}, {center_y}).")
        return True
    except Exception as e:
        logger.error(f"Error resizing and centering window with handle {hwnd}: {e}")
        return False


def ratio_text_to_number(supported_ratio):
    supported_ratio_list = [int(i) for i in supported_ratio.split(':')]
    return supported_ratio_list[0] / supported_ratio_list[1]
