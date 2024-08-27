# original https://github.com/Toufool/AutoSplit/blob/master/src/capture_method/WindowsGraphicsCaptureMethod.py
import json
import os

import numpy as np
from typing_extensions import override

from ok.alas.emulator_windows import EmulatorInstance
from ok.capture.BaseCaptureMethod import BaseCaptureMethod
from ok.capture.adb.nemu_ipc import NemuIpcImpl
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class NemuIpcCaptureMethod(BaseCaptureMethod):
    name = "Nemu Ipc Capture"
    description = "mumu player 12 only"

    def __init__(self, device_manager, exit_event, width=0, height=0):
        super().__init__()
        self.device_manager = device_manager
        self.exit_event = exit_event
        self._connected = (width != 0 and height != 0)
        self.nemu_impl: NemuIpcImpl | None = None
        self.emulator: EmulatorInstance | None = None

    def update_emulator(self, emulator: EmulatorInstance):
        self.emulator = emulator
        logger.info(f'update_path_and_id {emulator}')
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    def init_nemu(self):
        self.check_mumu_app_keep_alive_400()
        if not self.nemu_impl:
            self.nemu_impl = NemuIpcImpl(
                nemu_folder=self.base_folder(),
                instance_id=self.emulator.player_id,
                display_id=0
            ).__enter__()

    def base_folder(self):
        return os.path.dirname(os.path.dirname(self.emulator.path))

    def check_mumu_app_keep_alive_400(self):
        """
        Check app_keep_alive from emulator config if version >= 4.0

        Args:
            file: E:/ProgramFiles/MuMuPlayer-12.0/vms/MuMuPlayer-12.0-1/config/customer_config.json

        Returns:
            bool: If success to read file
        """
        file = os.path.abspath(os.path.join(
            self.base_folder(),
            f'vms/MuMuPlayer-12.0-{self.emulator.player_id}/configs/customer_config.json'))

        # with E:\ProgramFiles\MuMuPlayer-12.0\shell\MuMuPlayer.exe
        # config is E:\ProgramFiles\MuMuPlayer-12.0\vms\MuMuPlayer-12.0-1\config\customer_config.json
        try:
            with open(file, mode='r', encoding='utf-8') as f:
                s = f.read()
                data = json.loads(s)
        except FileNotFoundError:
            logger.warning(f'Failed to check check_mumu_app_keep_alive, file {file} not exists')
            return False
        value = deep_get(data, keys='customer.app_keptlive', default=None)
        logger.info(f'customer.app_keptlive {value}')
        if str(value).lower() == 'true':
            # https://mumu.163.com/help/20230802/35047_1102450.html
            logger.error('Please turn off enable background keep alive in MuMuPlayer settings')
            raise Exception('Please turn off enable background keep alive in MuMuPlayer settings')
        return True

    @override
    def close(self):
        super().close()
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    @override
    def do_get_frame(self) -> np.ndarray | None:
        self.init_nemu()
        return self.screencap()

    def screencap(self):
        if self.exit_event.is_set():
            return None
        if self.nemu_impl:
            frame = self.nemu_impl.screenshot(timeout=0.5)
            return frame

    def connected(self):
        return True


def deep_get(d, keys, default=None):
    """
    Get values in dictionary safely.
    https://stackoverflow.com/questions/25833613/safe-method-to-get-value-of-nested-dictionary

    Args:
        d (dict):
        keys (str, list): Such as `Scheduler.NextRun.value`
        default: Default return if key not found.

    Returns:

    """
    if isinstance(keys, str):
        keys = keys.split('.')
    assert type(keys) is list
    if d is None:
        return default
    if not keys:
        return d
    return deep_get(d.get(keys[0]), keys[1:], default)
