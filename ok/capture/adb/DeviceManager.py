import threading

import adbutils
import cv2
import numpy as np

from ok.capture.HwndWindow import HwndWindow
from ok.capture.adb.ADBCaptureMethod import ADBCaptureMethod
from ok.capture.adb.vbox import installed_emulator
from ok.capture.windows.WindowsGraphicsCaptureMethod import WindowsGraphicsCaptureMethod
from ok.config.Config import Config
from ok.gui.Communicate import communicate
from ok.interaction.ADBInteraction import ADBBaseInteraction
from ok.interaction.Win32Interaction import Win32Interaction
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class DeviceManager:

    def __init__(self, config_folder, hwnd_title=None, debug=False, exit_event=None):
        self._device = None
        self.adb = None
        self.hwnd_title = hwnd_title
        self.debug = debug
        self.interaction = None
        self.exit_event = exit_event
        if hwnd_title is not None:
            self.hwnd = HwndWindow(hwnd_title, exit_event)
        self.config = Config({"devices": {}}, config_folder, "DeviceManager")
        self._size = (0, 0)
        self.thread = None
        self.capture_method = None
        self.refresh()

    def refresh(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.do_refresh, name="refresh adb")
            self.thread.start()

    @property
    def device_dict(self):
        return self.config.get("devices")

    def connect_all(self):
        for device in self.device_dict.values():
            self.adb.connect(device['address'])
        logger.debug(f'connect_all {self.adb.device_list()}')

    def get_devices(self):
        return self.device_dict.values()

    def do_refresh(self):
        if self.adb is None:
            self.adb = adbutils.AdbClient(host="127.0.0.1")
            logger.debug(f'connect adb')
        self.connect_all()
        installed_emulators = installed_emulator()
        for device in self.adb.list():
            logger.debug(f'adb.list() {device}')

        for emulator in installed_emulators:
            logger.debug(f"installed_emulator: {emulator}")
            self.adb.connect(emulator.adb_address)

        device_list = self.adb.device_list()

        device_list = sorted(device_list, key=lambda x: x.serial)

        for device in self.device_dict.values():
            device['connected'] = False

        for device in device_list:
            imei = device.shell("settings get secure android_id") or device.shell(
                "service call iphonesubinfo 4") or device.prop.model
            frame = do_screencap(device)
            width, height = 0, 0
            if frame is not None:
                height, width, _ = frame.shape
            adb_device = {"address": device.serial, "imei": imei, "method": "adb",
                          "model": device.prop.model, "nick": device.prop.model, "connected": True, "preferred": False,
                          "resolution": f"{width}x{height}"}
            found = False
            for emulator in installed_emulators:
                if emulator.adb_address == adb_device['address']:
                    adb_device['nick'] = emulator.description
                    found = True
            if self.device_dict.get(imei):
                if found or not self.device_dict[imei]['connected']:
                    self.device_dict[imei] = adb_device
            else:
                self.device_dict[imei] = adb_device
        if self.hwnd_title:
            nick = self.hwnd_title
            width = 0
            height = 0
            if self.hwnd:
                nick = self.hwnd.title_text()
                width = self.hwnd.width
                height = self.hwnd.height
            self.device_dict[self.hwnd_title] = {"address": "", "imei": self.hwnd_title, "method": "windows",
                                                 "model": "", "nick": nick or self.hwnd_title,
                                                 "connected": self.hwnd is not None and self.hwnd.exists,
                                                 "resolution": f"{width}x{height}"}
        communicate.adb_devices.emit()
        self.config.save_file()
        logger.debug(f'refresh {self.device_dict}')

    def set_preferred_device(self, imei=None):
        logger.debug(f"set_preferred_device {imei}")
        if imei is None:
            imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        if preferred is None and len(self.device_dict) > 0:
            preferred = next(iter(self.device_dict.values()))
            imei = preferred['imei']
        self.config["preferred"] = imei
        self.config.save_file()
        logger.debug(f'preferred device: {preferred}')

    def get_preferred_device(self):
        imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        if preferred is None:
            raise ValueError(f"preferred device {imei} is none")
        return preferred

    def set_hwnd_name(self, hwnd_name):
        preferred = self.get_preferred_device()
        preferred['hwnd'] = hwnd_name
        self.config.save_file()

    def start(self):
        preferred = self.get_preferred_device()
        if preferred['method'] == 'windows':
            if not isinstance(self.capture_method, WindowsGraphicsCaptureMethod):
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = WindowsGraphicsCaptureMethod(self.hwnd)
                self.interaction = Win32Interaction(self.capture_method)
            self.capture_method.hwnd_window = self.hwnd
        else:
            for adb_device in self.adb.device_list():
                if adb_device.serial == preferred.get('address'):
                    self._device = adb_device
            if hwnd := preferred.get('hwnd'):
                if not isinstance(self.capture_method, WindowsGraphicsCaptureMethod):
                    if self.capture_method is not None:
                        self.capture_method.close()
                    self.capture_method = WindowsGraphicsCaptureMethod(self.hwnd)
                self.hwnd.title = hwnd
                self.capture_method.hwnd_window = self.hwnd
            elif not isinstance(self.capture_method, ADBCaptureMethod):
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = ADBCaptureMethod(self)
            self.interaction = ADBBaseInteraction(self, self.capture_method)
        if isinstance(self.capture_method, ADBCaptureMethod):
            if self.debug:
                if self.hwnd is None:
                    self.hwnd = HwndWindow("ok_debug", self.exit_event, self.capture_method.width,
                                           self.capture_method.height)
                self.hwnd.title = "ok_debug"
                self.hwnd.update_frame_size(self.capture_method.width, self.capture_method.height)
            elif self.hwnd is not None:
                self.hwnd.stop()
                self.hwnd = None

    @property
    def device(self):
        return self._device

    @property
    def width(self):
        if self._size[0] == 0:
            self.screencap()
        return self._size[0]

    @property
    def height(self):
        if self._size[1] == 0:
            self.screencap()
        return self._size[1]

    def update_device_list(self):
        pass

    def shell(self, *args, **kwargs):
        device = self.device
        if device is not None:
            try:
                return device.shell(*args, **kwargs)
            except Exception as e:
                logger.error(f"shell_wrapper error occurred: {e}")

    def screencap(self):
        if self.exit_event.is_set():
            return None
        self._size = (0, 0)
        frame = do_screencap(self.device)
        if frame is not None:
            height, width, _ = frame.shape
            self._size = (width, height)
        return frame


def do_screencap(device) -> np.ndarray | None:
    if device is not None:
        png_bytes = device.shell("screencap -p", encoding=None)
        if png_bytes is not None and len(png_bytes) > 0:
            image_data = np.frombuffer(png_bytes, dtype=np.uint8)
            image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
            if image is not None:
                return image
            else:
                logger.error(f"Screencap image decode error, probably disconnected")
