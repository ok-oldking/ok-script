# original https://github.com/dantmnf & https://github.com/hakaboom/winAuto
import re
import threading
import time

import psutil
import win32process
from win32 import win32gui

import ok.gui
from ok.capture.windows.window import is_foreground_window, get_window_bounds
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class HwndWindow:

    def __init__(self, exit_event, title, exe_name=None, frame_width=0, frame_height=0, player_id=-1):
        super().__init__()
        self.app_exit_event = exit_event
        self.exe_name = exe_name
        self.title = title
        self.stop_event = threading.Event()
        self.visible = False
        self.player_id = player_id
        self.window_width = 0
        self.window_height = 0
        self.visible = True
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.hwnd = None
        self.frame_width = 0
        self.frame_height = 0
        self.exists = False
        self.title = None
        self.exe_full_path = None
        self.real_width = 0
        self.real_height = 0
        self.real_x_offset = 0
        self.real_y_offset = 0
        self.scaling = 1.0
        self.frame_aspect_ratio = 0
        self.update_window(title, exe_name, frame_width, frame_height)
        self.thread = threading.Thread(target=self.update_window_size, name="update_window_size")
        self.thread.start()
        self._hwnd_title = ""

    def stop(self):
        self.stop_event.set()

    def update_window(self, title, exe_name, frame_width, frame_height, player_id=-1):
        self.player_id = player_id
        self.title = title
        self.exe_name = exe_name
        self.update_frame_size(frame_width, frame_height)

    def update_frame_size(self, width, height):
        logger.debug(f"update_frame_size:{self.frame_width}x{self.frame_height} to {width}x{height}")
        if width != self.frame_width or height != self.frame_height:
            self.frame_width = width
            self.frame_height = height
            if width > 0 and height > 0:
                self.frame_aspect_ratio = width / height
                logger.debug(f"HwndWindow: frame ratio: width: {width}, height: {height}")
        self.hwnd = None
        self.do_update_window_size()

    def update_window_size(self):
        while not self.app_exit_event.is_set() and not self.stop_event.is_set():
            self.do_update_window_size()
            time.sleep(0.2)

    def get_abs_cords(self, x, y):
        return self.x + x, self.y + y

    def do_update_window_size(self):
        try:
            visible, x, y, window_width, window_height, width, height, scaling = self.visible, self.x, self.y, self.window_width, self.window_height, self.width, self.height, self.scaling
            if self.hwnd is None:
                name, self.hwnd, self.exe_full_path, self.real_x_offset, self.real_y_offset, self.real_width, self.real_height = find_hwnd(
                    self.title,
                    self.exe_name,
                    self.frame_width, self.frame_height, player_id=self.player_id)
                if self.hwnd is not None:
                    logger.info(
                        f'found hwnd {self.hwnd} {self.exe_full_path} {win32gui.GetClassName(self.hwnd)} real:{self.real_x_offset},{self.real_y_offset},{self.real_width},{self.real_height}')
                self.exists = self.hwnd is not None
            if self.hwnd is not None:
                self.exists = win32gui.IsWindow(self.hwnd)
                if self.exists:
                    visible = is_foreground_window(self.hwnd)
                    x, y, window_width, window_height, width, height, scaling = get_window_bounds(
                        self.hwnd)
                    if self.frame_aspect_ratio != 0 and height != 0:
                        window_ratio = width / height
                        if window_ratio < self.frame_aspect_ratio:
                            cropped_window_height = int(width / self.frame_aspect_ratio)
                            height = cropped_window_height
                else:
                    ok.gui.executor.pause()
                    communicate.notification.emit('Paused because game exited', None, True, True)
                    self.hwnd = None
                changed = False
                if visible != self.visible:
                    self.visible = visible
                    changed = True
                if (window_width != self.window_width or window_height != self.window_height or
                    x != self.x or y != self.y or width != self.width or height != self.height or scaling != self.scaling) and (
                        (x >= -1 and y >= -1) or self.visible):
                    self.x, self.y, self.window_width, self.window_height, self.width, self.height, self.scaling = x, y, window_width, window_height, width, height, scaling
                    changed = True
                if changed:
                    logger.info(
                        f"do_update_window_size changed,visible:{self.visible} x:{self.x} y:{self.y} window:{self.width}x{self.height} self.window:{self.window_width}x{self.window_height} real:{self.real_width}x{self.real_height}")
                    communicate.window.emit(self.visible, self.x + self.real_x_offset, self.y + self.real_y_offset,
                                            self.window_width, self.window_height,
                                            self.width,
                                            self.height, self.scaling)
        except Exception as e:
            logger.error(f"do_update_window_size exception", e)

    def frame_ratio(self, size):
        if self.frame_width > 0 and self.width > 0:
            return int(size / self.frame_width * self.width)
        else:
            return size

    @property
    def hwnd_title(self):
        if not self._hwnd_title:
            if self.hwnd:
                self._hwnd_title = win32gui.GetWindowText(self.hwnd)
        return self._hwnd_title

    def __str__(self) -> str:
        return f"title_{self.title}_{self.exe_name}_{self.width}x{self.height}_{self.hwnd}_{self.exists}_{self.visible}"


def find_hwnd(title, exe_name, frame_width, frame_height, player_id=-1):
    results = []
    if exe_name is None and title is None:
        return None, None, None, 0, 0, 0, 0
    frame_aspect_ratio = frame_width / frame_height if frame_height != 0 else 0

    def callback(hwnd, lParam):
        if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if title:
                if isinstance(title, str):
                    if title != text:
                        return True
                elif not re.search(title, text):
                    return True
            name, full_path, cmdline = get_exe_by_hwnd(hwnd)
            if not name:
                return True
            x, y, _, _, width, height, scaling = get_window_bounds(
                hwnd)
            ret = (hwnd, full_path, width, height, x, y, text)
            if exe_name:
                if name != exe_name and exe_name != full_path:
                    return True
            if player_id != -1:
                if player_id != get_player_id_from_cmdline(cmdline):
                    logger.debug(
                        f'player id check failed,cmdline {cmdline} {get_player_id_from_cmdline(cmdline)} != {player_id}')
                    return True
            results.append(ret)
        return True

    win32gui.EnumWindows(callback, None)
    if len(results) > 0:
        biggest = None
        for result in results:
            if biggest is None or (result[2] * result[3]) > biggest[2] * biggest[3]:
                biggest = result
        x_offset = 0
        y_offset = 0
        real_width = 0
        real_height = 0
        if frame_aspect_ratio != 0:
            real_width, real_height = biggest[2], biggest[3]
            matching_child = enum_child_windows(biggest, frame_aspect_ratio)
            if matching_child is not None:
                x_offset, y_offset, real_width, real_height = matching_child
            logger.info(
                f'find_hwnd {frame_width, frame_height} {biggest} {x_offset, y_offset, real_width, real_height}')
        return biggest[6], biggest[0], biggest[1], x_offset, y_offset, real_width, real_height

    return None, None, None, 0, 0, 0, 0


def get_player_id_from_cmdline(cmdline):
    for i in range(len(cmdline)):
        if i != 0:
            if cmdline[i].isdigit():
                return int(cmdline[i])
    for i in range(len(cmdline)):
        if i != 0:
            value = re.search(r'index=(\d+)', cmdline[i])
            # Return the value if it exists, otherwise return None
            if value is not None:
                return int(value.group(1))
    return 0


def enum_child_windows(biggest, frame_aspect_ratio):
    ratio_match = []
    """
    A function to enumerate all child windows of the given parent window handle
    and print their handle and window title.
    """

    def child_callback(hwnd, _):
        visible = win32gui.IsWindowVisible(hwnd)
        parent = win32gui.GetParent(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        real_width = rect[2] - rect[0]
        real_height = rect[3] - rect[1]
        logger.info(f'find_hwnd child_callback {visible} {biggest[0]} {parent} {rect} {real_width} {real_height}')
        if visible and parent == biggest[0]:
            ratio = real_width / real_height
            difference = abs(ratio - frame_aspect_ratio)
            support = difference <= 0.01 * frame_aspect_ratio
            percent = (real_width * real_height) / (biggest[2] * biggest[3])
            if support and percent >= 0.7:
                x_offset = rect[0] - biggest[4]
                y_offset = rect[1] - biggest[5]
                ratio_match.append((x_offset, y_offset, real_width, real_height))
        return True

    win32gui.EnumChildWindows(biggest[0], child_callback, None)
    if len(ratio_match) > 0:
        return ratio_match[0]


def get_exe_by_hwnd(hwnd):
    # Get the process ID associated with the window
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        # Get the process name and executable path
        if pid > 0:
            process = psutil.Process(pid)
            return process.name(), process.exe(), process.cmdline()
        else:
            return None, None, None
    except Exception as e:
        logger.error('get_exe_by_hwnd error', e)
        return None, None, None


if __name__ == '__main__':
    print(find_hwnd("MuMu模拟器12", None))
    # hwnd_window = HwndWindow(threading.Event(), None, 'D:\\MuMuPlayer-12.0\\shell\\MuMuPlayer.exe', 16, 9)
    # from ok.capture.windows.BitBltCaptureMethod import BitBltCaptureMethod
    #
    # method = BitBltCaptureMethod(hwnd_window)
    # method.get_frame()
