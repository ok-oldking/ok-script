# original https://github.com/dantmnf & https://github.com/hakaboom/winAuto
import re
import threading

from typing_extensions import override
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

    def __init__(self, title="", exit_event=threading.Event(), frame_width=0, frame_height=0):
        super().__init__()
        self.app_exit_event = exit_event
        self.stop_event = threading.Event()
        self.update_title_re(title)
        self.visible = False
        self.update_frame_size(frame_width, frame_height)
        self.do_update_window_size()
        self.thread = threading.Thread(target=self.update_window_size)
        self.thread.start()

    @override
    def close(self):
        self.app_exit_event.set()

    def stop(self):
        self.stop_event.set()

    def update_title_re(self, title):
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
        visible, x, y, border, title_height, width, height, scaling = self.visible, self.x, self.y, self.border, self.title_height, self.width, self.height, self.scaling
        if self.hwnd is None:
            self.hwnd = find_hwnd_by_title(self.title)
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

    def frame_ratio(self, size):
        if self.frame_width > 0 and self.width > 0:
            return int(size / self.frame_width * self.width)
        else:
            return size

    def title_text(self):
        if self.hwnd:
            return win32gui.GetWindowText(self.hwnd)
        return ""


def find_hwnd_by_title(title):
    hwnds = []

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
        return hwnds[0]
