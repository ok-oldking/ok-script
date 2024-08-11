# original https://github.com/dantmnf & https://github.com/hakaboom/winAuto
import re
import threading
import time

import psutil
import win32api
import win32process
from pycaw.api.audioclient import ISimpleAudioVolume
from pycaw.utils import AudioUtilities
from qfluentwidgets import FluentIcon
from win32 import win32gui

import ok.gui
from ok.capture.windows.window import is_foreground_window, get_window_bounds
from ok.config.ConfigOption import ConfigOption
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)

mute_config_option = ConfigOption('Game Sound', {
    'Mute Game while in Background': False
}, icon=FluentIcon.MUTE)


class HwndWindow:

    def __init__(self, exit_event, title, exe_name=None, frame_width=0, frame_height=0, player_id=-1, hwnd_class=None,
                 global_config=None):
        super().__init__()
        self.app_exit_event = exit_event
        self.mute_option = global_config.get_config(mute_config_option)
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
        self.hwnd_class = hwnd_class
        self.pos_valid = False
        self._hwnd_title = ""
        self.monitors_bounds = get_monitors_bounds()
        self.update_window(title, exe_name, frame_width, frame_height)
        self.thread = threading.Thread(target=self.update_window_size, name="update_window_size")
        self.thread.start()

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
                    self.frame_width, self.frame_height, player_id=self.player_id, class_name=self.hwnd_class)
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
                    pos_valid = check_pos(x, y, width, height, self.monitors_bounds)
                    if not pos_valid and pos_valid != self.pos_valid and ok.gui.executor is not None:
                        if ok.gui.executor.pause():
                            logger.error(f'ok.gui.executor.pause pos_invalid: {x, y, width, height}')
                            communicate.notification.emit('Paused because game window is minimized or out of screen!',
                                                          None,
                                                          True, True)
                    if pos_valid != self.pos_valid:
                        self.pos_valid = pos_valid
                else:
                    ok.gui.executor.pause()
                    communicate.notification.emit('Paused because game exited', None, True, True)
                    self.hwnd = None
                changed = False
                if visible != self.visible:
                    self.visible = visible
                    changed = True
                    self.handle_mute()
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

    def handle_mute(self):
        if self.hwnd and self.mute_option.get('Mute Game while in Background'):
            set_mute_state(self.hwnd, 0 if self.visible else 1)

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


def check_pos(x, y, width, height, monitors_bounds):
    return width >= 0 and height >= 0 and is_window_in_screen_bounds(x, y, width, height, monitors_bounds)


def get_monitors_bounds():
    monitors_bounds = []
    monitors = win32api.EnumDisplayMonitors()
    for monitor in monitors:
        monitor_info = win32api.GetMonitorInfo(monitor[0])
        monitor_rect = monitor_info['Monitor']
        monitors_bounds.append(monitor_rect)
    return monitors_bounds


def is_window_in_screen_bounds(window_left, window_top, window_width, window_height, monitors_bounds):
    window_right, window_bottom = window_left + window_width, window_top + window_height

    for monitor_rect in monitors_bounds:
        monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_rect

        # Check if the window is within the monitor bounds
        if (window_left >= monitor_left and window_top >= monitor_top and
                window_right <= monitor_right and window_bottom <= monitor_bottom):
            return True

    return False


def find_hwnd(title, exe_name, frame_width, frame_height, player_id=-1, class_name=None):
    results = []
    if exe_name is None and title is None:
        return None, None, None, 0, 0, 0, 0
    frame_aspect_ratio = frame_width / frame_height if frame_height != 0 else 0

    def callback(hwnd, lParam):
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowEnabled(hwnd) and win32gui.IsWindowVisible(hwnd):
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
            if class_name is not None:
                if win32gui.GetClassName(hwnd) != class_name:
                    return True
            results.append(ret)
        return True

    win32gui.EnumWindows(callback, None)
    if len(results) > 0:
        logger.info(f'find_hwnd {results}')
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


# Function to get the mute state
def set_mute_state(hwnd, mute):
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        if session.Process and session.Process.pid == pid:
            volume = session._ctl.QueryInterface(ISimpleAudioVolume)
            volume.SetMute(mute, None)  # 0 to unmute, 1 to mute
            break


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
