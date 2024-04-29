# original https://github.com/dantmnf & https://github.com/hakaboom/winAuto
import ctypes
import re
import threading

import win32process
from win32 import win32gui

from ok.capture.windows.window import is_foreground_window, get_window_bounds
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class HwndWindow:
    visible = True
    x = 0
    y = 0
    width = 0
    height = 0
    title_height = 0
    border = 0
    scaling = 1
    top_cut = 0
    right_cut = 0
    bottom_cut = 0
    left_cut = 0
    window_change_listeners = []
    frame_aspect_ratio = 0
    hwnd = None
    frame_width = 0
    frame_height = 0
    exists = False
    title = None

    def __init__(self, exit_event, title="", exe_name=None, frame_width=0, frame_height=0):
        super().__init__()
        self.app_exit_event = exit_event
        self.exe_name = exe_name
        self.stop_event = threading.Event()
        self.update_title_re(title)
        self.visible = False
        self.update_frame_size(frame_width, frame_height)
        self.do_update_window_size()
        self.thread = threading.Thread(target=self.update_window_size)
        self.thread.start()

    def update_title_and_exe(self, title, exe):
        self.update_title_re(title)
        self.exe_name = exe
        self.hwnd = None
        self.visible = False
        self.exists = False
        self.width = 0
        self.height = 0
        self.do_update_window_size()

    def stop(self):
        self.stop_event.set()

    def update_title_re(self, title):
        if not title:
            self.title = None
        else:
            self.title = re.compile(title)

    def update_frame_size(self, width, height):
        logger.debug(f"update_frame_size:{self.frame_width}x{self.frame_height} to {width}x{height}")
        if width != self.frame_width or height != self.frame_height:
            self.frame_width = width
            self.frame_height = height
            if width > 0 and height > 0:
                self.frame_aspect_ratio = width / height
                logger.debug(f"HwndWindow: frame ratio:{self.frame_aspect_ratio} width: {width}, height: {height}")

    def update_window_size(self):
        while not self.app_exit_event.is_set() and not self.stop_event.is_set():
            self.do_update_window_size()
            self.app_exit_event.wait(0.1)

    def get_abs_cords(self, x, y):
        return int(self.x * self.scaling + (self.border * self.scaling + x)), int(
            self.y * self.scaling + (y + self.title_height * self.scaling))

    def get_top_left_frame_offset(self):
        return int(self.border * self.scaling), int(
            self.title_height * self.scaling)

    def do_update_window_size(self):
        try:
            visible, x, y, border, title_height, width, height, scaling = self.visible, self.x, self.y, self.border, self.title_height, self.width, self.height, self.scaling
            if self.hwnd is None:
                self.hwnd = find_hwnd_by_title_and_exe(self.title, self.exe_name)
                self.exists = self.hwnd is not None
            if self.hwnd is not None:
                self.exists = win32gui.IsWindow(self.hwnd)
                if self.exists:
                    visible = is_foreground_window(self.hwnd)
                    x, y, border, title_height, width, height, scaling = get_window_bounds(
                        self.hwnd)
                    if self.frame_aspect_ratio != 0:
                        window_ratio = width / height
                        if window_ratio < self.frame_aspect_ratio:
                            cropped_window_height = int(width / self.frame_aspect_ratio)
                            title_height += height - cropped_window_height
                            height = cropped_window_height
                    height = height
                    width = width
                    title_height = title_height
                else:
                    self.hwnd = None
                changed = False
                if visible != self.visible or self.scaling != scaling:
                    self.visible = visible
                    self.scaling = scaling
                    changed = True
                if (
                        x != self.x or y != self.y or border != self.border or title_height != self.title_height or width != self.width or height != self.height or scaling != self.scaling) and (
                        (x >= 0 and y >= 0) or self.visible):
                    self.x, self.y, self.border, self.title_height, self.width, self.height = x, y, border, title_height, width, height
                    changed = True
                if changed:
                    logger.debug(
                        f"do_update_window_size changed: {self.visible} {self.x} {self.y} {self.border} {self.width} {self.height} {self.scaling}")
                    communicate.window.emit(self.visible, self.x, self.y, self.border, self.title_height, self.width,
                                            self.height, self.scaling)
        except Exception as e:
            logger.error(f"do_update_window_size exception", e)

    def frame_ratio(self, size):
        if self.frame_width > 0 and self.width > 0:
            return int(size / self.frame_width * self.width)
        else:
            return size

    def title_text(self):
        if self.hwnd:
            return win32gui.GetWindowText(self.hwnd)
        return ""


def find_hwnd_by_title_and_exe(title, exe):
    if not title and not exe:
        return None
    hwnds = find_hwnds_by_title(title)
    if exe is not None:
        for hwnd in hwnds:
            exe_2 = get_exe_name_by_hwnd(hwnd)
            if exe_2 == exe:
                return hwnd
    if len(hwnds) > 0:
        return hwnds[0]


def find_hwnds_by_title(title):
    hwnds = []
    if not title:
        return hwnds

    def enum_windows_proc(hwnd, lParam):
        text = win32gui.GetWindowText(hwnd)
        if text and win32gui.IsWindowVisible(hwnd):
            if isinstance(title, str) and title == text:
                hwnds.append(hwnd)
            elif re.search(title, text):
                hwnds.append(hwnd)

    win32gui.EnumWindows(enum_windows_proc, None)
    if len(hwnds) > 0:
        if len(hwnds) > 1:
            logger.warning(f"Found multiple hwnds {len(hwnds)}")
    return hwnds


OpenProcess = ctypes.windll.kernel32.OpenProcess
CloseHandle = ctypes.windll.kernel32.CloseHandle
GetModuleFileNameExW = ctypes.windll.psapi.GetModuleFileNameExW

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010


def get_exe_name_by_hwnd(hwnd):
    # Get the process ID of the window
    _, pid = win32process.GetWindowThreadProcessId(hwnd)

    # Open the process
    h_process = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if h_process:
        # Get the executable name
        exe_name = ctypes.create_unicode_buffer(1024)
        GetModuleFileNameExW(h_process, None, exe_name, 1024)

        # Close the process handle
        CloseHandle(h_process)

        return exe_name.value
