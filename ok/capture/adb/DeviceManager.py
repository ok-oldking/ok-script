import win32gui

from ok.capture.HwndWindow import HwndWindow, find_hwnd_by_title_and_exe
from ok.capture.adb.ADBCaptureMethod import ADBCaptureMethod, do_screencap
from ok.capture.adb.WindowsCaptureFactory import update_capture_method
from ok.capture.windows.window import get_window_bounds
from ok.config.Config import Config
from ok.gui.Communicate import communicate
from ok.interaction.ADBInteraction import ADBBaseInteraction
from ok.interaction.Win32Interaction import Win32Interaction
from ok.logging.Logger import get_logger
from ok.util.Handler import Handler

logger = get_logger(__name__)


class DeviceManager:

    def __init__(self, config_folder, windows_capture_config, adb_capture_config, debug=False, exit_event=None):
        self._device = None
        self._connect_all = False
        self._adb = None
        self.windows_capture_config = windows_capture_config
        self.adb_capture_config = adb_capture_config
        self.pc_device = None
        self.debug = debug
        self.interaction = None
        self.exit_event = exit_event
        if windows_capture_config is not None:
            self.hwnd = HwndWindow(exit_event, windows_capture_config.get('title'),
                                   windows_capture_config.get('exe'))
        self.config = Config({"devices": {}, "preferred": "none", "pc_full_path": None}, config_folder,
                             "DeviceManager")
        self.capture_method = None
        self.handler = Handler(exit_event, 'RefreshAdb')
        self.handler.post(self.do_refresh, 5)

    def refresh(self):
        logger.debug('calling refresh')
        self.handler.post(self.do_refresh, remove_existing=True)

    @property
    def device_dict(self):
        device_dict = self.config.get("devices")
        if device_dict is None:
            device_dict = {}
        if self.pc_device is not None:
            full = {'pc': self.pc_device}
            full.update(device_dict)
            return full
        else:
            return device_dict

    @property
    def adb(self):
        if self._adb is None:
            import adbutils
            self._adb = adbutils.AdbClient(host="127.0.0.1")
            logger.debug(f'connect adb')
        return self._adb

    def adb_connect(self, addr):
        try:
            self.adb.connect(addr, timeout=2)
        except Exception as e:
            logger.error("adb connect error", e)

    def connect_all(self):
        if not self._connect_all:
            for device in self.device_dict.values():
                if device["device"] == "adb":
                    self.adb_connect(device['address'])
            self._connect_all = True
            logger.debug(f'connect_all')

    def get_devices(self):
        return list(self.device_dict.values())

    def update_pc_device(self):
        if self.windows_capture_config is not None:
            nick = ""
            width = 0
            height = 0
            hwnd, full_path = find_hwnd_by_title_and_exe(self.windows_capture_config.get('title'),
                                                         self.windows_capture_config.get('exe'))
            if hwnd is not None:
                nick = win32gui.GetWindowText(hwnd)
                _, _, _, _, width, height, _, _, _ = get_window_bounds(
                    hwnd)
            if not nick:
                nick = self.windows_capture_config.get('exe')
            self.pc_device = {"address": "", "imei": 'pc', "device": "windows",
                              "model": "", "nick": nick, "width": width,
                              "height": height,
                              "hwnd": nick, "capture": "windows",
                              "connected": hwnd is not None,
                              "full_path": full_path or self.config.get('pc_full_path')
                              }
            if full_path and full_path != self.config.get('pc_full_path'):
                self.config['pc_full_path'] = full_path

            if width != 0:
                self.pc_device["resolution"] = f"{width}x{height}"
            communicate.adb_devices.emit(False)

    def do_refresh(self, fast=False):
        self.update_pc_device()

        self.refresh_adb_device(fast)

        if self.exit_event.is_set():
            return
        self.start()
        communicate.adb_devices.emit(True)
        logger.debug(f'refresh {self.device_dict}')

    def refresh_adb_device(self, fast):
        if self.adb_capture_config is None:
            return
        if not fast:
            self.connect_all()
        from ok.capture.adb.vbox import installed_emulator
        installed_emulators = [] if fast else installed_emulator()
        for device in self.adb.list():
            logger.debug(f'adb.list() {device}')
        for emulator in installed_emulators:
            logger.debug(f"installed_emulator: {emulator}")
            self.adb_connect(emulator.adb_address)
        device_list = self.adb.device_list()
        device_list = sorted(device_list, key=lambda x: x.serial)
        adb_connected = []
        for device in device_list:
            imei = device.shell("settings get secure android_id") or device.shell(
                "service call iphonesubinfo 4") or device.prop.model
            frame = None if fast else do_screencap(device)
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
                        self.update_device_value(imei, 'capture', old_capture)
                    if old_hwnd is not None:
                        self.update_device_value(imei, 'hwnd', old_hwnd)
            else:
                self.update_device(imei, adb_device)
            adb_connected.append(imei)
        for imei in self.device_dict:
            if self.device_dict[imei]['device'] == 'adb':
                self.update_device_value(imei, 'connected', imei in adb_connected)
        self.config.save_file()

    def update_device(self, imei, device=None):
        devices = self.config.get("devices", {})
        devices[imei] = device
        self.config["devices"] = devices

    def update_device_value(self, imei, key, value):
        devices = self.config.get("devices", {})
        if imei in devices:
            devices[imei][key] = value
        self.config["devices"] = devices

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

    def use_windows_capture(self, override_config=None, require_bg=False):
        if not override_config:
            override_config = self.windows_capture_config
        self.capture_method = update_capture_method(override_config, self.capture_method, self.hwnd,
                                                    require_bg)
        if self.capture_method is None:
            logger.error(f'can find a usable windows capture')
        else:
            logger.info(f'capture method {type(self.capture_method)}')

    def start(self):
        preferred = self.get_preferred_device()
        if preferred is None:
            if self.device_dict:
                self.set_preferred_device()
            return

        if preferred['device'] == 'windows':
            self.ensure_hwnd(self.windows_capture_config.get('title'), self.windows_capture_config.get('exe'))
            self.use_windows_capture()
            if not isinstance(self.interaction, Win32Interaction):
                self.interaction = Win32Interaction(self.capture_method)
            preferred['connected'] = self.capture_method.connected()
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
                if self.hwnd.exe_full_path:
                    self.update_device_value(preferred['imei'], 'full_path', self.hwnd.exe_full_path)
                self.use_windows_capture({'can_bit_blt': True}, require_bg=True)
            elif not isinstance(self.capture_method, ADBCaptureMethod):
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = ADBCaptureMethod(self, self.exit_event, width=width,
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

    def adb_kill_server(self):
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
            from adbutils import AdbError
            try:
                return device.shell(*args, **kwargs)
            except AdbError as e:
                addr = self.get_preferred_device()['address']
                self.adb.connect(addr)
                logger.error(f"shell_wrapper error occurred: {e} ,try reconnect {addr}")
                return device.shell(*args, **kwargs)
        else:
            raise Exception('Device is none')

    def get_exe_path(self, device):
        path = device.get('full_path')
        if device.get('device') == 'windows' and self.windows_capture_config and self.windows_capture_config.get(
                'calculate_pc_exe_path'):
            return self.windows_capture_config.get('calculate_pc_exe_path')(path)
        else:
            return path
