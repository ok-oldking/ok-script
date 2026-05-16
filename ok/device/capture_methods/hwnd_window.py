import threading
import time

import win32api
import win32con
import win32gui
import win32process

from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_info
from ok.util.GlobalConfig import basic_options
from ok.util.logger import Logger
from ok.util.window import show_title_bar, get_window_bounds, resize_window, is_foreground_window, find_hwnd

from ok.device.capture_methods.base import BaseWindowsCaptureMethod

logger = Logger.get_logger(__name__)

class HwndWindow:

    def __init__(self, exit_event, title, exe_name=None, frame_width=0, frame_height=0, player_id=-1, hwnd_class=None,
                 global_config=None, device_manager=None, top_hwnd_class=None):
        super().__init__()
        logger.info(
            f'HwndWindow init title:{title} player_id:{player_id} exe_name:{exe_name} hwnd_class:{hwnd_class} top_hwnd_class:{top_hwnd_class}')
        self.app_exit_event = exit_event
        self.exe_names = None
        self.visible_monitors = []
        self.device_manager = device_manager
        self.to_handle_mute = True
        self.title = title
        self.stop_event = threading.Event()
        self.visible = False
        self.player_id = player_id
        self.window_width = 0
        self.window_height = 0
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.hwnd = 0
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
        self.last_mute_check = 0
        self.hwnds = []
        self.top_hwnd = 0
        self.top_offset_x = 0
        self.top_offset_y = 0

        self.hwnd_class = hwnd_class
        self.top_hwnd_class = top_hwnd_class
        self.pos_valid = False
        self._hwnd_title = ""
        self.monitors_bounds = get_monitors_bounds()
        self.mute_option = global_config.get_config(basic_options)
        self.global_config = global_config
        self.mute_option.validator = self.validate_mute_config
        self.update_window(title, exe_name, frame_width, frame_height, player_id, hwnd_class, top_hwnd_class)
        self.thread = threading.Thread(target=self.update_window_size, name="update_window_size")
        self.thread.start()

    def validate_mute_config(self, key, value):
        if key == 'Mute Game while in Background' and self.hwnd:
            logger.info(f'validate_mute_config {value}')
            if value:
                self.handle_mute(value)
            else:
                logger.info(f'config changed unmute set_mute_state {value}')
                set_mute_state(self.hwnd, 0)
        return True, None

    def stop(self):
        self.stop_event.set()

    def _front_hwnd_candidates(self):
        return list(dict.fromkeys(hwnd for hwnd in (self.top_hwnd, self.hwnd) if hwnd))

    def bring_to_front(self):
        errors = []
        for refreshed in (False, True):
            hwnds = self._front_hwnd_candidates()
            if not hwnds:
                if not refreshed:
                    self.do_update_window_size()
                    continue
                logger.warning('bring_to_front failed: no hwnd found')
                return False

            invalid_hwnds = []
            for hwnd in hwnds:
                try:
                    if not win32gui.IsWindow(hwnd):
                        invalid_hwnds.append(hwnd)
                        continue
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.BringWindowToTop(hwnd)
                    win32gui.SetForegroundWindow(hwnd)
                    return True
                except Exception as e:
                    errors.append(f'{hwnd}: {e}')

            if invalid_hwnds and len(invalid_hwnds) == len(hwnds) and not refreshed:
                self.do_update_window_size()
                continue
            if invalid_hwnds:
                errors.append(f'invalid hwnds: {invalid_hwnds}')
            break

        logger.warning(f'bring_to_front failed: {", ".join(errors)}')
        return False

    def try_resize_to(self, resize_to):
        if not self.global_config.get_config('Basic Options').get('Auto Resize Game Window'):
            return False
        if self.hwnd and self.window_width > 0:
            show_title_bar(self.hwnd)
            screen_width = win32api.GetSystemMetrics(0)
            screen_height = win32api.GetSystemMetrics(1)
            x, y, window_width, window_height, width, height, scaling = get_window_bounds(self.hwnd)
            title_height = window_height - height
            logger.info(f'try_resize_to {x, y, window_width, window_height, width, height, scaling} ')
            border = window_width - width
            resize_width = 0
            resize_height = 0
            for resolution in resize_to:
                if screen_width >= border + resolution[0] and screen_height >= title_height + resolution[
                    1]:
                    resize_width = resolution[0] + border
                    resize_height = resolution[1] + title_height
                    break
            if resize_width > 0:
                resize_window(self.hwnd, resize_width, resize_height)
                self.do_update_window_size()
                if self.window_height == resize_height and self.window_width == resize_width:
                    logger.info(f'resize hwnd success to {self.width}x{self.height}')
                    return True
                else:
                    logger.error(f'resize hwnd failed: {self.width}x{self.height}')

    def update_window(self, title, exe_name, frame_width, frame_height, player_id=-1, hwnd_class=None,
                      top_hwnd_class=None):
        self.player_id = player_id
        self.title = title
        if isinstance(exe_name, str):
            self.exe_names = [exe_name]
        else:
            self.exe_names = exe_name
        self.update_frame_size(frame_width, frame_height)
        self.hwnd_class = hwnd_class
        self.top_hwnd_class = top_hwnd_class

    def update_frame_size(self, width, height):
        logger.debug(f"update_frame_size:{self.frame_width}x{self.frame_height} to {width}x{height}")
        if width != self.frame_width or height != self.frame_height:
            self.frame_width = width
            self.frame_height = height
            if width > 0 and height > 0:
                self.frame_aspect_ratio = width / height
                logger.debug(f"HwndWindow: frame ratio: width: {width}, height: {height}")
        self.hwnd = 0
        self.do_update_window_size()

    def update_window_size(self):
        while not self.app_exit_event.is_set() and not self.stop_event.is_set():
            self.do_update_window_size()
            time.sleep(0.2)
        if self.hwnd and self.mute_option.get('Mute Game while in Background'):
            logger.info(f'exit reset mute state to 0')
            set_mute_state(self.hwnd, 0)

    def get_abs_cords(self, x, y):
        return self.x + x, self.y + y

    def get_top_window_cords(self, x, y):
        return x - self.top_offset_x, y - self.top_offset_y

    def do_update_window_size(self):
        if self.device_manager and getattr(self.device_manager, 'capture_method', None):
            from ok.device.capture_methods.browser import BrowserCaptureMethod
            if isinstance(self.device_manager.capture_method, BrowserCaptureMethod):
                return
        try:
            changed = False
            exists = False
            visible, x, y, window_width, window_height, width, height, scaling = self.visible, self.x, self.y, self.window_width, self.window_height, self.width, self.height, self.scaling
            name, find_hwnd_res, exe_full_path, real_x_offset, real_y_offset, real_width, real_height, hwnds = find_hwnd(
                self.title,
                self.exe_names or self.device_manager.config.get('selected_exe'),
                self.frame_width, self.frame_height, player_id=self.player_id, class_name=self.hwnd_class,
                selected_hwnd=self.device_manager.config.get('selected_hwnd'),
                top_hwnd_class=self.top_hwnd_class, last_hwnd=self.hwnd)

            if find_hwnd_res > 0 and self.hwnd != find_hwnd_res:
                old_hwnd = self.hwnd
                self.hwnd = find_hwnd_res
                self.exe_full_path = exe_full_path
                self._hwnd_title = ""
                logger.info(
                    f'do_update_window_size hwnd changed from {old_hwnd} to {self.hwnd} top {hwnds[0][0] if hwnds else self.hwnd} {self.exe_full_path} {win32gui.GetClassName(self.hwnd)} real:{real_x_offset},{real_y_offset},{real_width},{real_height}')
                changed = True

            if find_hwnd_res > 0:
                self.hwnds = hwnds
                self.real_x_offset = real_x_offset
                self.real_y_offset = real_y_offset
                self.real_width = real_width
                self.real_height = real_height
                self.top_hwnd = hwnds[0][0] if hwnds else self.hwnd
                self.top_offset_x = 0
                self.top_offset_y = 0
                if hwnds and len(hwnds) > 0:
                    bg_hwnd_info = next((w for w in hwnds if w[0] == self.hwnd), None)
                    if bg_hwnd_info:
                        self.top_offset_x = hwnds[0][4] - bg_hwnd_info[4]
                        self.top_offset_y = hwnds[0][5] - bg_hwnd_info[5]

            exists = self.hwnd > 0
            if self.hwnd > 0:
                exists = win32gui.IsWindow(self.hwnd)
                if exists:
                    visible = self.is_foreground()
                    x, y, window_width, window_height, width, height, scaling = get_window_bounds(
                        self.hwnd)
                    if self.frame_aspect_ratio != 0 and height != 0:
                        window_ratio = width / height
                        if window_ratio < self.frame_aspect_ratio:
                            cropped_window_height = int(width / self.frame_aspect_ratio)
                            height = cropped_window_height
                    pos_valid = check_pos(x, y, width, height, self.monitors_bounds)
                    if isinstance(self.device_manager.capture_method,
                                  BaseWindowsCaptureMethod) and not pos_valid and pos_valid != self.pos_valid and self.device_manager.executor is not None:
                        if self.device_manager.executor.pause():
                            logger.error(f'og.executor.pause pos_invalid: {x, y, width, height}')
                            communicate.notification.emit('Paused because game window is minimized or out of screen!',
                                                          None,
                                                          True, True, "start", None)
                    if pos_valid != self.pos_valid:
                        self.pos_valid = pos_valid
                else:
                    if self.global_config.get_config('Basic Options').get(
                            'Exit App when Game Exits') and self.device_manager.executor is not None and self.device_manager.executor.pause():
                        alert_info('Auto exit because game exited', True)
                        communicate.quit.emit()
                    else:
                        communicate.notification.emit('Game Exited', None, True, True, None, None)
                    self.hwnd = 0
                    visible = False
                if visible != self.visible:
                    self.visible = visible
                    for visible_monitor in self.visible_monitors:
                        visible_monitor.on_visible(visible)
                    changed = True

                if changed or (time.time() - self.last_mute_check > 2):
                    self.handle_mute()
                    self.last_mute_check = time.time()

                if (window_width != self.window_width or window_height != self.window_height or
                    x != self.x or y != self.y or width != self.width or height != self.height or scaling != self.scaling) and (
                        (x >= -1 and y >= -1) or self.visible):
                    self.x, self.y, self.window_width, self.window_height, self.width, self.height, self.scaling = x, y, window_width, window_height, width, height, scaling
                    changed = True
                if self.exists != exists:
                    self.exists = exists
                    changed = True
                if changed:
                    device = self.device_manager.get_preferred_device()
                    if device:
                        logger.info(f"hwnd changed,connected:{self.exists}")
                        device['connected'] = self.exists
                        device['width'] = width
                        device['height'] = height
                        device['resolution'] = f"{width}x{height}"
                        communicate.adb_devices.emit(True)
                    logger.info(
                        f"do_update_window_size changed,visible:{self.visible},exists:{self.exists} x:{self.x} y:{self.y} window:{self.width}x{self.height} self.window:{self.window_width}x{self.window_height} real:{self.real_width}x{self.real_height}")
                    communicate.window.emit(self.visible, self.x + self.real_x_offset, self.y + self.real_y_offset,
                                            self.window_width, self.window_height,
                                            self.width,
                                            self.height, self.scaling)
        except Exception as e:
            logger.error(f"do_update_window_size exception", e)

    def is_foreground(self):
        if is_foreground_window(self.hwnd):
            return True
        for w in self.hwnds:
            if is_foreground_window(w[0]):
                return True
        return False

    def handle_mute(self, mute=None):
        if mute is None:
            mute = self.mute_option.get('Mute Game while in Background')
        if self.hwnd and self.to_handle_mute and mute:
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
        return str(
            f"title_{self.title}_{self.exe_names}_{self.width}x{self.height}_{self.hwnd}_{self.exists}_{self.visible}")



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

        # Allow a 20 pixel boundary tolerance for maximized windows which often leak outside monitor bounds by 8-13 pixels.
        if (window_left >= monitor_left - 20 and window_top >= monitor_top - 20 and
                window_right <= monitor_right + 20 and window_bottom <= monitor_bottom + 20):
            return True

    return False



def get_mute_state(hwnd):
    try:
        from pycaw.api.audioclient import ISimpleAudioVolume
        from pycaw.utils import AudioUtilities
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            if session.Process and session.Process.pid == pid:
                volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                return volume.GetMute()
        return 0
    except Exception as e:
        logger.warning(f"get_mute_state exception: {e}")
        return 0



def set_mute_state(hwnd, mute):
    try:
        from pycaw.api.audioclient import ISimpleAudioVolume
        from pycaw.utils import AudioUtilities
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            if session.Process and session.Process.pid == pid:
                volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                volume.SetMute(mute, None)
                break
    except Exception as e:
        logger.warning(f"No default audio endpoint, skip mute. Exception: {e}")
