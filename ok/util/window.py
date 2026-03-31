# window.py
import ctypes
import os
import platform
import re
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


def compare_path_safe(str1, str2):
    if str1 is None and str2 is None:
        return True
    if str1 is None or str2 is None:
        return False
    return str1.replace('\\', '/').lower() == str2.replace('\\', '/').lower()


def get_player_id_from_cmdline(cmdline):
    for i in range(len(cmdline)):
        if i != 0:
            if cmdline[i].isdigit():
                return int(cmdline[i])
    for i in range(len(cmdline)):
        if i != 0:
            value = re.search(r'index=(\d+)', cmdline[i])
            if value is not None:
                return int(value.group(1))
    return 0


def _match_class_name(hwnd_class, patterns):
    if patterns is None:
        return -1
    if not isinstance(patterns, list):
        patterns = [patterns]
    for i, pattern in enumerate(patterns):
        if isinstance(pattern, str):
            if hwnd_class == pattern:
                return i
        elif re.search(pattern, hwnd_class):
            return i
    return -1


def enum_child_windows(biggest, frame_aspect_ratio, frame_width, frame_height):
    ratio_match = []

    def child_callback(hwnd, _):
        visible = win32gui.IsWindowVisible(hwnd)
        parent = win32gui.GetParent(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        real_width = rect[2] - rect[0]
        real_height = rect[3] - rect[1]
        if visible and real_height > 0:
            ratio = real_width / real_height
            difference = abs(ratio - frame_aspect_ratio)
            support = difference <= 0.01 * frame_aspect_ratio
            percent = (real_width * real_height) / (biggest[2] * biggest[3]) if biggest[2] * biggest[3] > 0 else 0
            x_offset = rect[0] - biggest[4]
            y_offset = rect[1] - biggest[5]
            if support and percent >= 0.7 or (frame_width == real_width and real_width >= frame_width) or (
                    frame_height == real_height and real_height >= frame_height):
                ratio_match.append((difference, (x_offset, y_offset, real_width, real_height)))
        return True

    win32gui.EnumChildWindows(biggest[0], child_callback, None)

    if ratio_match:
        ratio_match.sort(key=lambda x: x[0])
        return ratio_match[0][1]
    return None


def find_hwnd(title, exe_names, frame_width, frame_height, player_id=-1, class_name=None,
              selected_hwnd=0, top_hwnd_class=None, last_hwnd=0):
    if exe_names is None and title is None:
        return None, 0, None, 0, 0, 0, 0, []
    frame_aspect_ratio = frame_width / frame_height if frame_height != 0 else 0

    top_results = []

    def is_match(hwnd, results):
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowEnabled(hwnd):
            return True

        cname = win32gui.GetClassName(hwnd)
        is_main_class = class_name is None or _match_class_name(cname, class_name) >= 0
        if is_main_class and class_name is None and not win32gui.IsWindowVisible(hwnd):
            is_main_class = False

        t_idx = _match_class_name(cname, top_hwnd_class) if top_hwnd_class is not None else -1

        if not is_main_class and t_idx < 0:
            return True

        text = win32gui.GetWindowText(hwnd)
        if t_idx >= 0 and win32gui.IsWindowVisible(hwnd):
            name, full_path, cmdline = get_exe_by_hwnd(hwnd)
            tx, ty, _, _, tcw, tch, m_ts = get_window_bounds(hwnd)
            top_results.append((hwnd, full_path, tcw, tch, tx, ty, text, cname, m_ts, t_idx))

        if not is_main_class or (0 < selected_hwnd != hwnd):
            return True

        if title:
            if isinstance(title, str):
                if title != text:
                    return True
            elif not re.search(title, text):
                return True

        name, full_path, cmdline = get_exe_by_hwnd(hwnd)

        if exe_names:
            if not name or not any((compare_path_safe(name, exe_name) or compare_path_safe(exe_name, full_path)) for exe_name in exe_names):
                return True

        if player_id != -1 and player_id != get_player_id_from_cmdline(cmdline):
            logger.warning(f'player id check failed,cmdline {cmdline} {get_player_id_from_cmdline(cmdline)} != {player_id}')
            return True

        x, y, _, _, width, height, m_scaling = get_window_bounds(hwnd)
        if width <= 10 or height <= 10:
            return True
        # logger.debug(f'find_hwnd EnumWindows selected_hwnd {selected_hwnd} {results}')
        results.append((hwnd, full_path, width, height, x, y, text, cname, m_scaling))
        return True

    results = []
    win32gui.EnumWindows(is_match, results)
    # logger.debug(f'find_hwnd EnumWindows selected_hwnd {selected_hwnd} {results}')
    if not results:
        return None, 0, None, 0, 0, 0, 0, []

    w_biggest = max(results, key=lambda r: r[2] * r[3])
    w_last = next((r for r in results if 0 < last_hwnd == r[0]), None)

    biggest = w_biggest
    if w_last and w_biggest:
        if (w_biggest[2] * w_biggest[3]) <= (w_last[2] * w_last[3]) * 1.1:
            biggest = w_last

    results = [biggest]

    if top_hwnd_class is not None:
        bg_exe_path, bg_dir = biggest[1], None
        if bg_exe_path:
            bg_dir = os.path.dirname(os.path.normpath(bg_exe_path)).lower()

        filtered_top = []
        for result in top_results:
            top_exe_path = result[1]
            if top_exe_path and bg_exe_path:
                top_exe_path_norm = os.path.normpath(top_exe_path).lower()
                bg_exe_path_norm = os.path.normpath(bg_exe_path).lower()
                if top_exe_path_norm == bg_exe_path_norm or (bg_dir and top_exe_path_norm.startswith(bg_dir + os.sep)):
                    filtered_top.append(result)

        if filtered_top:
            for top_item in reversed(filtered_top):
                if top_item[0] != biggest[0] and not any(r[0] == top_item[0] for r in results):
                    results.insert(0, top_item[:9] if len(top_item) > 9 else top_item)

    x_offset, y_offset, real_width, real_height = 0, 0, biggest[2], biggest[3]
    if class_name is None and frame_aspect_ratio != 0:
        matching_child = enum_child_windows(biggest, frame_aspect_ratio, frame_width, frame_height)
        if matching_child is not None:
            x_offset, y_offset, real_width, real_height = matching_child
        if real_width < 10 or real_height < 10:
            logger.error(f'find_hwnd real_width, real_height too small return None {frame_width, frame_height} {biggest} {x_offset, y_offset, real_width, real_height}')
            return None, 0, None, 0, 0, 0, 0, []

    # logger.debug(f'find_hwnd {results}')

    return biggest[6], biggest[0], biggest[1], x_offset, y_offset, real_width, real_height, results

def find_all_visible_windows():
    windows = []
    
    def callback(hwnd, extra):
        if not win32gui.IsWindowVisible(hwnd):
            return True
            
        exStyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        WS_EX_TOOLWINDOW = 0x00000080
        if exStyle & WS_EX_TOOLWINDOW:
            return True
            
        title = win32gui.GetWindowText(hwnd)
        if not title or not str(title).strip():
            return True
            
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid <= 0:
                return True
            process = psutil.Process(pid)
            exe_name = process.name()
            exe_full_path = process.exe()
        except Exception:
            exe_name = ""
            exe_full_path = ""
            
        windows.append((hwnd, title, exe_name, exe_full_path))
        return True
        
    win32gui.EnumWindows(callback, None)
    return windows
