import subprocess
import threading

import adbutils
import win32gui
from adbutils import adb_path
from adbutils.errors import AdbConnectionError, AdbTimeout

from ok.capture.HwndWindow import HwndWindow, find_hwnd_by_title_and_exe
from ok.capture.adb.ADBCaptureMethod import ADBCaptureMethod, do_screencap
from ok.capture.adb.vbox import installed_emulator
from ok.capture.windows.WindowsGraphicsCaptureMethod import WindowsGraphicsCaptureMethod
from ok.capture.windows.window import get_window_bounds
from ok.config.Config import Config
from ok.gui.Communicate import communicate
from ok.interaction.ADBInteraction import ADBBaseInteraction
from ok.interaction.Win32Interaction import Win32Interaction
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


def fix_adbutils_safe_connect(self):
    try:
        return self._create_socket()
    except (AdbConnectionError, AdbTimeout):
        subprocess.run([adb_path(), "start-server"], timeout=20.0)  # 20s should enough for adb start
        return self._create_socket()


adbutils._adb.AdbConnection._safe_connect = fix_adbutils_safe_connect


class DeviceManager:

    def __init__(self, config_folder, hwnd_title=None, exe_name=None, debug=False, exit_event=None):
        self._device = None
        self._connect_all = False
        self.adb = self.adb = adbutils.AdbClient(host="127.0.0.1")
        logger.debug(f'connect adb')
        self.hwnd_title = hwnd_title
        self.exe_name = exe_name
        self.debug = debug
        self.interaction = None
        self.exit_event = exit_event
        if hwnd_title is not None:
            self.hwnd = HwndWindow(exit_event, hwnd_title, exe_name)
        self.config = Config({"devices": {}, "preferred": "none"}, config_folder, "DeviceManager")
        self.thread = None
        self.capture_method = None
        self.start()

    def refresh(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.do_refresh, name="refresh adb")
            self.thread.start()

    @property
    def device_dict(self):
        return self.config.get("devices")

    def connect_all(self):
        if not self._connect_all:
            for device in self.device_dict.values():
                if device["device"] == "adb":
                    try:
                        self.adb.connect(device['address'])
                    except Exception as e:
                        logger.error("adb connect error", e)
            self._connect_all = True
            logger.debug(f'connect_all {self.adb.device_list()}')

    def get_devices(self):
        return list(self.device_dict.values())

    def do_refresh(self):
        self.connect_all()

        if self.hwnd_title:
            nick = ""
            width = 0
            height = 0
            hwnd = find_hwnd_by_title_and_exe(self.hwnd_title, self.exe_name)
            if hwnd is not None:
                nick = win32gui.GetWindowText(hwnd)
                _, _, _, _, width, height, _ = get_window_bounds(
                    hwnd)
            if not nick:
                nick = self.exe_name
            self.device_dict[self.hwnd_title] = {"address": "", "imei": self.hwnd_title, "device": "windows",
                                                 "model": "", "nick": nick, "width": width,
                                                 "height": height,
                                                 "hwnd": nick, "capture": "windows",
                                                 "connected": hwnd is not None
                                                 }
            if width != 0:
                self.device_dict[self.hwnd_title]["resolution"] = f"{width}x{height}"
            communicate.adb_devices.emit(False)

        installed_emulators = installed_emulator()
        for device in self.adb.list():
            logger.debug(f'adb.list() {device}')

        for emulator in installed_emulators:
            logger.debug(f"installed_emulator: {emulator}")
            self.adb.connect(emulator.adb_address)

        device_list = self.adb.device_list()

        device_list = sorted(device_list, key=lambda x: x.serial)

        adb_connected = []

        for device in device_list:
            imei = device.shell("settings get secure android_id") or device.shell(
                "service call iphonesubinfo 4") or device.prop.model
            frame = do_screencap(device)
            width, height = 0, 0
            if frame is not None:
                height, width, _ = frame.shape
            adb_device = {"address": device.serial, "imei": imei, "device": "adb", "capture": "adb", "width": width,
                          "height": height,
                          "model": device.prop.model, "nick": device.prop.model, "connected": True,
                          "resolution": f"{width}x{height}"}
            found = False
            for emulator in installed_emulators:
                if emulator.adb_address == adb_device['address']:
                    adb_device['nick'] = emulator.description
                    found = True
            if self.device_dict.get(imei):
                if found or not self.device_dict[imei]['connected']:
                    old_capture = self.device_dict[imei].get("capture")
                    old_hwnd = self.device_dict[imei].get("hwnd")
                    self.device_dict[imei] = adb_device
                    if old_capture is not None:
                        self.device_dict[imei]['capture'] = old_capture
                    if old_hwnd is not None:
                        self.device_dict[imei]['hwnd'] = old_hwnd
            else:
                self.device_dict[imei] = adb_device
            adb_connected.append(imei)
        for imei in self.device_dict:
            if imei not in adb_connected and self.device_dict[imei]['device'] == 'adb':
                self.device_dict[imei]['connected'] = False

        self.config.save_file()

        if self.exit_event.is_set():
            return
        self.start()
        communicate.adb_devices.emit(True)
        logger.debug(f'refresh {self.device_dict}')

    def set_preferred_device(self, imei=None):
        logger.debug(f"set_preferred_device {imei}")
        if imei is None:
            imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        if preferred is None and len(self.device_dict) > 0:
            preferred = next(iter(self.device_dict.values()))
            imei = preferred['imei']
        if self.config.get("preferred") != imei:
            self.config["preferred"] = imei
            self.config.save_file()
        logger.debug(f'preferred device: {preferred}')
        self.start()
        return preferred

    def get_preferred_device(self):
        imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        return preferred

    def set_hwnd_name(self, hwnd_name):
        preferred = self.get_preferred_device()
        if preferred.get("hwnd") != hwnd_name:
            preferred['hwnd'] = hwnd_name
            self.config.save_file()
            self.start()

    def set_capture(self, capture):
        preferred = self.get_preferred_device()
        if preferred.get("capture") != capture:
            preferred['capture'] = capture
            self.config.save_file()
        self.start()

    def get_hwnd_name(self):
        preferred = self.get_preferred_device()
        return preferred.get('hwnd')

    def ensure_hwnd(self, title, exe, frame_width=0, frame_height=0):
        if self.hwnd is None:
            self.hwnd = HwndWindow(self.exit_event, title, exe, frame_width, frame_height)
        else:
            self.hwnd.update_frame_size(frame_width, frame_height)
            self.hwnd.update_title_and_exe(title, exe)

    def start(self):
        preferred = self.get_preferred_device()
        if preferred is None:
            if self.device_dict:
                self.set_preferred_device()
            return

        if preferred['device'] == 'windows':
            self.ensure_hwnd(self.hwnd_title, self.exe_name)
            if not isinstance(self.capture_method, WindowsGraphicsCaptureMethod):
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = WindowsGraphicsCaptureMethod(self.hwnd)
                self.interaction = Win32Interaction(self.capture_method)
            self.capture_method.hwnd_window = self.hwnd
        else:
            self.connect_all()
            for adb_device in self.adb.device_list():
                if adb_device.serial == preferred.get('address'):
                    logger.debug(f"set device {adb_device}")
                    self._device = adb_device
            hwnd_name = preferred.get('hwnd')
            width = preferred.get('width', 0)
            height = preferred.get('height', 0)
            if preferred.get('capture') == "windows":
                self.ensure_hwnd(hwnd_name, None, width, height)
                if not isinstance(self.capture_method, WindowsGraphicsCaptureMethod):
                    if self.capture_method is not None:
                        self.capture_method.close()
                    self.capture_method = WindowsGraphicsCaptureMethod(self.hwnd)
                self.capture_method.hwnd_window = self.hwnd
            elif not isinstance(self.capture_method, ADBCaptureMethod):
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = ADBCaptureMethod(self._device, self.exit_event, width=width,
                                                       height=height)
            self.interaction = ADBBaseInteraction(self, self.capture_method, width, height)
            if self.debug and hwnd_name:
                self.ensure_hwnd(hwnd_name, None, width, height)
            elif self.hwnd is not None:
                self.hwnd.stop()
                self.hwnd = None

    @property
    def device(self):
        return self._device

    def stop(self):
        if self.adb is not None:
            self.adb.server_kill()
            logger.debug('adb kill_server')

    @property
    def width(self):
        if self.capture_method is not None:
            return self.capture_method.width
        return 0

    @property
    def height(self):
        if self.capture_method is not None:
            return self.capture_method.height
        return 0

    def update_device_list(self):
        pass

    def shell(self, *args, **kwargs):
        device = self.device
        if device is not None:
            try:
                return device.shell(*args, **kwargs)
            except Exception as e:
                logger.error(f"shell_wrapper error occurred: {e}")
