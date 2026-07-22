import json
import os

from ok.util.collection import deep_get
from ok.util.logger import Logger

from ok.device.capture_methods.base import BaseCaptureMethod

logger = Logger.get_logger(__name__)

class NemuIpcCaptureMethod(BaseCaptureMethod):
    name = "Nemu Ipc Capture"
    description = "mumu player 12 only"

    def __init__(self, device_manager, exit_event, width=0, height=0):
        super().__init__()
        self.device_manager = device_manager
        self.exit_event = exit_event
        self._connected = (width != 0 and height != 0)
        self.nemu_impl = None
        self.emulator = None

    def update_emulator(self, emulator):
        self.emulator = emulator
        logger.info(f'update_path_and_id {emulator}')
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    def init_nemu(self):
        if not self.nemu_impl:
            self.check_mumu_app_keep_alive_400()
            from ok.capture.adb.nemu_ipc import NemuIpc
            self.nemu_impl = NemuIpc(
                nemu_folder=self.base_folder(),
                instance_id=self.emulator.player_id,
                display_id=0
            )

    def base_folder(self):
        return os.path.dirname(os.path.dirname(self.emulator.path))

    def check_mumu_app_keep_alive_400(self):
        file = os.path.abspath(os.path.join(
            self.base_folder(),
            f'vms/MuMuPlayer-12.0-{self.emulator.player_id}/configs/customer_config.json'))

        try:
            with open(file, mode='r', encoding='utf-8') as f:
                s = f.read()
                data = json.loads(s)
        except FileNotFoundError:
            logger.warning(f'Failed to check check_mumu_app_keep_alive, file {file} not exists')
            return False
        value = deep_get(data, keys='customer.app_keptlive', default=None)
        if str(value).lower() == 'true':
            logger.error('Please turn off enable background keep alive in MuMuPlayer settings')
            raise Exception('Please turn off enable background keep alive in MuMuPlayer settings')
        return True

    def close(self):
        super().close()
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    def do_get_frame(self):
        if self.exit_event.is_set():
            return None
        self.init_nemu()
        if self.nemu_impl:
            return self.nemu_impl.screenshot(timeout=0.5)

    def connected(self):
        return True
