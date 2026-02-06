import time
import subprocess
import os

from PySide6.QtCore import QObject

from ok import Handler, og
from ok import Logger
from ok.device.capture import BaseWindowsCaptureMethod, BrowserCaptureMethod
from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_error
from ok.util.GlobalConfig import basic_options
from ok.util.process import is_admin, execute, read_game_gpu_pref, read_global_gpu_pref

logger = Logger.get_logger(__name__)


class StartController(QObject):
    def __init__(self, app_config, exit_event):
        super().__init__()
        self.config = app_config
        self.exit_event = exit_event
        self.handler = Handler(exit_event, __name__)
        self.start_timeout = app_config.get('start_timeout', 60)

    def start(self, task=None, exit_after=False):
        self.handler.post(lambda: self.do_start(task, exit_after))

    def do_start(self, task=None, exit_after=False):
        communicate.starting_emulator.emit(False, None, self.start_timeout)
        try:
            logger.info(f'do_start: call do_refresh')
            og.device_manager.do_refresh(True)
        except Exception as e:
            communicate.starting_emulator.emit(True, self.tr(str(e)), 0)
            return

        if not self.start_device():
            return

        if isinstance(task, int):
            task = og.executor.onetime_tasks[task]
            logger.info(f"enable task {task}")
            if exit_after and task:
                task.exit_after_task = True
                communicate.task.emit(task)
        if task:
            task.enable()
            task.unpause()

        og.executor.start()
        communicate.starting_emulator.emit(True, None, 0)

    def start_device(self):
        device = og.device_manager.get_preferred_device()
        logger.info(f'start_device: {device}')

        if device and not device['connected'] and device.get('full_path'):
            if device['device'] == "windows" and not is_admin():
                communicate.starting_emulator.emit(True,
                                                   "PC version requires admin privileges, Please restart this app with admin privileges!",
                                                   0)
                communicate.restart_admin.emit()
                return False
            path = og.device_manager.get_exe_path(device)
            if path:
                logger.info(f"starting game {path}")
                launch_with_dx11 = og.executor.global_config.get_config(basic_options).get('Launch with DX11')

                if launch_with_dx11:
                    logger.info(f"Start with DX11: {path} -dx11")
                    try:
                        subprocess.Popen([path, '-dx11'], cwd=os.path.dirname(path), creationflags=0x00000008)
                    except Exception as e:
                        logger.error(f"Error launching with DX11: {e}")
                        communicate.starting_emulator.emit(True, self.tr("Start game failed, please start game first"), 0)
                        return False
                elif not execute(path):
                    communicate.starting_emulator.emit(True, self.tr("Start game failed, please start game first"), 0)
                    return False
                wait_until = time.time() + self.start_timeout
                while not self.exit_event.is_set():
                    og.device_manager.do_refresh(True)
                    error = self.check_device_error()
                    if error is None:
                        break
                    logger.error(f'waiting for game to start error {error}')
                    remaining_time = wait_until - time.time()
                    if remaining_time <= 0:
                        communicate.starting_emulator.emit(True, self.tr('Start game timeout!'), 0)
                        return False
                    communicate.starting_emulator.emit(False, None, int(remaining_time))
                    time.sleep(2)
            else:
                communicate.starting_emulator.emit(True,
                                                   self.tr('Game path does not exist, Please open game manually!'), 0)
                return False
        else:
            error = self.check_device_error()
            if error:
                communicate.starting_emulator.emit(True, error, 0)
                return False
        communicate.starting_emulator.emit(True, None, 0)
        return True

    def check_resolution(self):
        error = None
        supported_resolution = self.config.get(
            'supported_resolution', {})
        supported_ratio = supported_resolution.get('ratio')
        min_size = supported_resolution.get('min_size')
        resize_to = supported_resolution.get('resize_to')
        force_ratio = supported_resolution.get('force_ratio')
        supported, resolution = og.executor.check_frame_and_resolution(supported_ratio, min_size)
        if not supported:
            resize_success = False
            if resize_to and isinstance(og.device_manager.capture_method, BaseWindowsCaptureMethod):
                resize_success = og.device_manager.capture_method.hwnd_window.try_resize_to(resize_to)
            if not resize_success:
                error = self.tr(
                    'Resolution {resolution} check failed, some tasks might not work correctly!').format(
                    resolution=resolution)
                if supported_ratio:
                    error += self.tr(', the supported ratio is {supported_ratio}').format(
                        supported_ratio=supported_ratio)
                if min_size:
                    error += self.tr(', the supported min resolution is {min_size}').format(
                        min_size=f'{min_size[0]}x{min_size[1]}')
        if force_ratio:
            return error
        elif error:
            alert_error(error, tray=True)

    def check_device_error(self):
        try:
            device = og.device_manager.get_preferred_device()
            error_msg = self.tr("{} is not connected, please select the game window.").format(
                device['nick'])
            logger.debug(f'test check_device_error msg: {error_msg}')
            if not device:
                return self.tr('No game selected!')
            if og.device_manager.capture_method is None:
                return self.tr("Selected capture method is not supported by the game or your system!")
            if not og.device_manager.device_connected():
                logger.error(f'Emulator is not connected {og.device_manager.device}')
                return self.tr("Emulator is not connected, start the emulator first!")
            if isinstance(og.device_manager.capture_method,
                          BrowserCaptureMethod) and not og.device_manager.capture_method.connected():
                logger.info(f"start browser")
                og.device_manager.capture_method.start_browser()
            if not og.device_manager.capture_method.connected():
                logger.error(f'Game window is not connected {og.device_manager.capture_method}')
                return error_msg
            if isinstance(og.device_manager.capture_method, BaseWindowsCaptureMethod):
                if self.config.get('windows', {}).get('check_hdr', False):
                    path = og.device_manager.get_exe_path(device)
                    if path:
                        hdr_enabled, swap_enabled = read_game_gpu_pref(path)
                        logger.info(f'hdr_enabled {path} {hdr_enabled}')
                        if hdr_enabled == True or (hdr_enabled is None and read_global_gpu_pref()[0]):
                            if self.config.get('windows', {}).get('force_no_hdr', False):
                                return self.tr(f'Auto HDR is enabled, please turn it off first.')
                            else:
                                alert_error(self.tr('Auto HDR is enabled, tasks might not work correctly!'), True)
                if not og.device_manager.capture_method.hwnd_window.pos_valid:
                    return self.tr(f'Window is minimized or out of screen, and don\'t use full-screen exclusive mode!')
            frame = self.try_capture_a_frame()
            if frame is None:
                return self.tr('Capture failed, please check game window')
            if og.executor.feature_set is not None and not og.executor.feature_set.check_size(frame):
                return self.tr(
                    'Image resource load failed, please try install again.(Don\'t put the app in Downloads folder)')

            resolution_error = self.check_resolution()
            if resolution_error:
                return resolution_error

            if device and device['device'] == "adb" and self.config.get('adb'):
                started = og.device_manager.adb_ensure_in_front()
                if not started:
                    return self.tr("Can't start game, make sure the game is installed")
        except Exception as e:
            logger.error(f'check_device_error exception: {str(e)}', e)
            return self.tr(str(e))

    @staticmethod
    def try_capture_a_frame():
        start = time.time()
        while True:
            frame = og.device_manager.capture_method.get_frame()
            if frame is not None:
                return frame
            if time.time() - start > 5:
                logger.error(f'time out try_capture_a_frame')
                return None
            time.sleep(0.1)
