import time

from PySide6.QtCore import QObject

import ok.gui
from ok.alas.platform_windows import execute
from ok.gui.Communicate import communicate
from ok.interaction.PyDirectInteraction import is_admin
from ok.logging.Logger import get_logger
from ok.util.Handler import Handler

logger = get_logger(__name__)


class StartController(QObject):
    def __init__(self, app_config, exit_event):
        super().__init__()
        self.config = app_config
        self.exit_event = exit_event
        self.handler = Handler(exit_event, __name__)

    def start(self, task=None):
        self.handler.post(lambda: self.do_start(task))

    def do_start(self, task=None):
        communicate.starting_emulator.emit(False, None, 50)
        ok.gui.device_manager.do_refresh(True)

        device = ok.gui.device_manager.get_preferred_device()

        if device and not device['connected'] and device.get('full_path'):
            path = ok.gui.device_manager.get_exe_path(device)
            if path:
                logger.info(f"starting game {path}")
                execute(path)
                wait_until = time.time() + 50
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
        supported_resolution = self.config.get(
            'supported_resolution', {})
        supported_ratio = supported_resolution.get('ratio')
        min_size = supported_resolution.get('min_size')
        supported, resolution = ok.gui.executor.check_frame_and_resolution(supported_ratio, min_size)
        if not supported:
            error = self.tr(
                "Game resolution {resolution} is not supported").format(resolution=resolution)
            if supported_ratio:
                error += self.tr(', the supported ratio is {supported_ratio}').format(supported_ratio=supported_ratio)
            if min_size:
                error += self.tr(', the supported min resolution is {min_size}').format(
                    min_size=f'{min_size[0]}x{min_size[1]}')
            error += self.tr(', check if game windows is minimized, resized or out of screen.')
            return error
        if device and device['device'] == "windows" and not is_admin():
            return self.tr(
                f"PC version requires admin privileges, Please restart this app with admin privileges!")
        if device and device['device'] == "adb" and self.config.get('adb'):
            packages = self.config.get('adb').get('packages')
            if packages:
                started = ok.gui.device_manager.adb_ensure_in_front(packages)
                if not started:
                    return self.tr("Can't start game, make sure the game is installed")
