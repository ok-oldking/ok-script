import time

from PySide6.QtCore import QObject

import ok.gui
from ok.alas.platform_windows import execute
from ok.capture.windows.BaseWindowsCaptureMethod import BaseWindowsCaptureMethod
from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_error
from ok.logging.Logger import get_logger
from ok.util.Handler import Handler
from ok.util.win import is_admin

logger = get_logger(__name__)


class StartController(QObject):
    def __init__(self, app_config, exit_event):
        super().__init__()
        self.config = app_config
        self.exit_event = exit_event
        self.handler = Handler(exit_event, __name__)
        self.start_timeout = app_config.get('start_timeout', 60)

    def start(self, task=None):
        self.handler.post(lambda: self.do_start(task))

    def do_start(self, task=None):
        communicate.starting_emulator.emit(False, None, self.start_timeout)
        try:
            ok.gui.device_manager.do_refresh(True)
        except Exception as e:
            communicate.starting_emulator.emit(True, self.tr(str(e)), 0)
            return

        device = ok.gui.device_manager.get_preferred_device()

        if device and not device['connected'] and device.get('full_path'):
            path = ok.gui.device_manager.get_exe_path(device)
            if path:
                logger.info(f"starting game {path}")
                if not execute(path):
                    communicate.starting_emulator.emit(True, self.tr("Start game failed, please start game first"), 0)
                    return
                wait_until = time.time() + self.start_timeout
                while not self.exit_event.is_set():
                    ok.gui.device_manager.do_refresh(True)
                    error = self.check_device_error()
                    if error is None:
                        break
                    logger.error(f'waiting for game to start error {error}')
                    remaining_time = wait_until - time.time()
                    if remaining_time <= 0:
                        communicate.starting_emulator.emit(True, self.tr('Start game timeout!'), 0)
                        return
                    communicate.starting_emulator.emit(False, None, int(remaining_time))
                    time.sleep(2)
            else:
                communicate.starting_emulator.emit(True,
                                                   self.tr('Game path does not exist, Please open game manually!'), 0)
                return
        else:
            error = self.check_device_error()
            if error:
                communicate.starting_emulator.emit(True, error, 0)
                return
        if task:
            task.enable()
            task.unpause()
        ok.gui.executor.start()
        communicate.starting_emulator.emit(True, None, 0)

    def check_device_error(self):
        try:
            device = ok.gui.device_manager.get_preferred_device()
            if not device:
                return self.tr('No game selected!')
            if ok.gui.device_manager.capture_method is None:
                return self.tr("Selected capture method is not supported by the game or your system!")
            if not ok.gui.device_manager.device_connected():
                logger.error(f'Emulator is not connected {ok.gui.device_manager.device}')
                return self.tr("Emulator is not connected, start the emulator first!")
            if not ok.gui.device_manager.capture_method.connected():
                logger.error(f'Game window is not connected {ok.gui.device_manager.capture_method}')
                return self.tr("Game window is not connected, please select the game window and capture method.")
            if isinstance(ok.gui.device_manager.capture_method, BaseWindowsCaptureMethod):
                if self.config.get('windows', {}).get('check_hdr', False):
                    logger.info(f'start checking for hdr and night light')
                    from ok.display.display import is_hdr_enabled
                    if is_hdr_enabled():
                        if self.config.get('windows', {}).get('force_no_hdr', False):
                            return self.tr(f'Windows HDR is enabled, please turn it off first.')
                        else:
                            alert_error(self.tr('Windows HDR is enabled, tasks might not work correctly!'), True)
                if self.config.get('windows', {}).get('check_night_light', False):
                    logger.info(f'start checking for night light')
                    from ok.display.display import is_night_light_enabled
                    if is_night_light_enabled():
                        if self.config.get('windows', {}).get('force_no_night_light', False):
                            return self.tr(f'Windows night light is enabled, please turn it off first.')
                        else:
                            alert_error(self.tr('Windows night light is enabled, tasks might not work correctly!'),
                                        True)
                if not ok.gui.device_manager.capture_method.hwnd_window.pos_valid:
                    return self.tr(f'Game window is minimized or out of screen, please restore it first!')
            frame = self.try_capture_a_frame()
            if frame is None:
                return self.tr('Capture failed, please check game window')
            if ok.gui.executor.feature_set is not None and not ok.gui.executor.feature_set.check_size(frame):
                return self.tr(
                    'Image resource load failed, please try install again.(Don\'t put the app in Downloads folder)')
            supported_resolution = self.config.get(
                'supported_resolution', {})
            supported_ratio = supported_resolution.get('ratio')
            min_size = supported_resolution.get('min_size')
            supported, resolution = ok.gui.executor.check_frame_and_resolution(supported_ratio, min_size)
            if not supported:
                error = self.tr(
                    'Resolution {resolution} check failed, some tasks might not work correctly!').format(
                    resolution=resolution)
                if supported_ratio:
                    error += self.tr(', the supported ratio is {supported_ratio}').format(
                        supported_ratio=supported_ratio)
                if min_size:
                    error += self.tr(', the supported min resolution is {min_size}').format(
                        min_size=f'{min_size[0]}x{min_size[1]}')
                alert_error(error, True)
                # return error
            if device and device['device'] == "windows" and not is_admin():
                return self.tr(
                    f"PC version requires admin privileges, Please restart this app with admin privileges!")
            if device and device['device'] == "adb" and self.config.get('adb'):
                packages = self.config.get('adb').get('packages')
                if packages:
                    started = ok.gui.device_manager.adb_ensure_in_front(packages)
                    if not started:
                        return self.tr("Can't start game, make sure the game is installed")
        except Exception as e:
            logger.error(f'check_device_error exception: {str(e)}', e)
            return self.tr(str(e))

    @staticmethod
    def try_capture_a_frame():
        start = time.time()
        while True:
            frame = ok.gui.device_manager.capture_method.get_frame()
            if frame is not None:
                return frame
            if time.time() - start > 5:
                logger.error(f'time out try_capture_a_frame')
                return None
            time.sleep(0.1)
