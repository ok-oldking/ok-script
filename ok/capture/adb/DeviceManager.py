from adbutils import AdbTimeout

from ok.alas.platform_windows import get_emulator_exe
from ok.capture.HwndWindow import HwndWindow, find_hwnd
from ok.capture.adb.ADBCaptureMethod import ADBCaptureMethod, do_screencap
from ok.capture.adb.WindowsCaptureFactory import update_capture_method
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
        self._adb = None
        self.windows_capture_config = windows_capture_config
        self.adb_capture_config = adb_capture_config
        self.debug = debug
        self.interaction = None
        self.device_dict = {}
        self.exit_event = exit_event
        if windows_capture_config is not None:
            self.hwnd = HwndWindow(exit_event, windows_capture_config.get('title'),
                                   windows_capture_config.get('exe'))
        self.config = Config({"preferred": "none", "pc_full_path": "none", 'capture': 'windows'}, config_folder,
                             "devices")
        self.capture_method = None
        self.handler = Handler(exit_event, 'RefreshAdb')
        self.handler.post(self.do_refresh, 3)

    def refresh(self):
        logger.debug('calling refresh')
        self.handler.post(self.do_refresh, remove_existing=True, skip_if_running=True)

    @property
    def adb(self):
        if self._adb is None:
            import adbutils
            self._adb = adbutils.AdbClient(host="127.0.0.1")
            logger.debug(f'connect adb')
        return self._adb

    def adb_connect(self, addr):
        try:
            for info in self.adb.list():
                if info.serial == addr:
                    if info.state == 'offline':
                        logger.debug(f'adb_connect offline disconnect first {addr}')
                        self.adb.disconnect(addr)
                    else:
                        logger.debug(f'adb_connect already connected {addr}')
                        return self.adb.device(addr)
            self.adb.connect(addr, timeout=5)
            device = self.adb.device(addr)
            logger.debug(f'adb_connect {addr} device {device}')
            return device
        except AdbTimeout as e:
            logger.error(f"adb connect error try kill server {addr}", e)
            # self.adb.server_kill()
            # self._adb = None
        except Exception as e:
            logger.error(f"adb connect error return none {addr}", e)

    def get_devices(self):
        return list(self.device_dict.values())

    def update_pc_device(self):
        if self.windows_capture_config is not None:
            name, hwnd, full_path, x, y, width, height = find_hwnd(self.windows_capture_config.get('title'),
                                                                   self.windows_capture_config.get('exe'))
            nick = name or self.windows_capture_config.get('exe')
            pc_device = {"address": "", "imei": 'pc', "device": "windows",
                         "model": "", "nick": nick, "width": width,
                         "height": height,
                         "hwnd": nick, "capture": "windows",
                         "connected": hwnd is not None,
                         "full_path": full_path or self.config.get('pc_full_path')
                         }
            if full_path and full_path != self.config.get('pc_full_path'):
                self.config['pc_full_path'] = full_path

            if width != 0:
                pc_device["resolution"] = f"{width}x{height}"
            self.device_dict['pc'] = pc_device

    def do_refresh(self, fast=False):
        self.update_pc_device()

        self.refresh_emulators()

        self.refresh_phones()

        if self.exit_event.is_set():
            return
        self.start()

        logger.debug(f'refresh {self.device_dict}')

    def refresh_phones(self):
        for adb_device in self.adb.iter_device():
            imei = self.adb_get_imei(adb_device)
            if imei is not None:
                found = False
                for device in self.device_dict.values():
                    if device.get('adb_imei') == imei:
                        found = True
                        break
                if not found:
                    logger.debug(f'refresh_phones found an phone {adb_device}')
                    phone_device = {"address": adb_device.serial, "device": "adb", "connected": True, "imei": imei,
                                    "nick": adb_device.prop.model or imei,
                                    "resolution": self.get_resolution(adb_device)}
                    self.device_dict[imei] = phone_device

    def refresh_emulators(self):
        from ok.alas.emulator_windows import EmulatorManager
        manager = EmulatorManager()
        installed_emulators = manager.all_emulator_instances
        for emulator in installed_emulators:
            adb_device = self.adb_connect(emulator.serial)
            name, hwnd, full_path, x, y, width, height = find_hwnd(None,
                                                                   emulator.path)
            connected = adb_device is not None and name is not None
            emulator_device = {"address": emulator.serial, "device": "adb",
                               "full_path": emulator.path, "connected": connected,
                               "nick": name or emulator.name, "emulator": emulator}
            if adb_device is not None:
                emulator_device["resolution"] = f"{width}x{height}"
                emulator_device["imei"] = emulator.name
                emulator_device["adb_imei"] = self.adb_get_imei(adb_device)
            self.device_dict[emulator.name] = emulator_device
        logger.debug(f'refresh emulators {self.device_dict}')

    def get_resolution(self, device=None):
        if device is None:
            device = self.device
        width, height = 0, 0
        if device is not None:
            frame = do_screencap(device)
            if frame is not None:
                height, width, _ = frame.shape
        return height, width

    def set_preferred_device(self, imei=None, index=-1):
        logger.debug(f"set_preferred_device {imei} {index}")
        if index != -1:
            imei = self.get_devices()[index]['imei']
        elif imei is None:
            imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        if preferred is None:
            if len(self.device_dict) > 0:
                preferred = next(iter(self.device_dict.values()))
                imei = preferred['imei']
            else:
                logger.warning(f'no devices')
                return
        if self.config.get("preferred") != imei:
            logger.info(f'preferred device did change {imei}')
            self.config["preferred"] = imei
            self.handler.post(self.start, remove_existing=True, skip_if_running=True)
        logger.debug(f'preferred device: {preferred}')

    def adb_get_imei(self, device):
        try:
            return device.shell("settings get secure android_id") or device.shell(
                "service call iphonesubinfo 4") or device.prop.model
        except Exception as e:
            logger.error(f"adb_get_imei error {device}", e)
            return None

    def get_preferred_device(self):
        imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        return preferred

    def get_preferred_capture(self):
        return self.config.get("capture")

    def set_hwnd_name(self, hwnd_name):
        preferred = self.get_preferred_device()
        if preferred.get("hwnd") != hwnd_name:
            preferred['hwnd'] = hwnd_name
            if self.hwnd:
                self.hwnd.title = hwnd_name
            self.config.save_file()

    def set_capture(self, capture):
        if self.config.get("capture") != capture:
            self.config['capture'] = capture
            self.handler.post(self.start, remove_existing=True, skip_if_running=True)

    def get_hwnd_name(self):
        preferred = self.get_preferred_device()
        return preferred.get('hwnd')

    def ensure_hwnd(self, title, exe, frame_width=0, frame_height=0):
        if self.hwnd is None:
            self.hwnd = HwndWindow(self.exit_event, title, exe, frame_width, frame_height)
        else:
            self.hwnd.update_window(title, exe, frame_width, frame_height)

    def use_windows_capture(self, override_config=None, require_bg=False, use_bit_blt_only=False):
        if not override_config:
            override_config = self.windows_capture_config
        self.capture_method = update_capture_method(override_config, self.capture_method, self.hwnd,
                                                    require_bg, use_bit_blt_only=use_bit_blt_only)
        if self.capture_method is None:
            logger.error(f'can find a usable windows capture')
        else:
            logger.info(f'capture method {type(self.capture_method)}')

    def start(self):
        self.handler.post(self.do_start, remove_existing=True, skip_if_running=True)

    def do_start(self):
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
            height, width = self.get_resolution()
            if self.config.get('capture') == "windows":
                self.ensure_hwnd(None, preferred.get('full_path'), width, height)
                self.use_windows_capture({'can_bit_blt': True}, require_bg=True, use_bit_blt_only=True)
            elif not isinstance(self.capture_method, ADBCaptureMethod):
                logger.debug(f'use adb capture')
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = ADBCaptureMethod(self, self.exit_event, width=width,
                                                       height=height)
                if self.debug:
                    self.ensure_hwnd(None, preferred.get('full_path'), width, height)
                elif self.hwnd is not None:
                    self.hwnd.stop()
                    self.hwnd = None
            if not isinstance(self.interaction, ADBBaseInteraction):
                self.interaction = ADBBaseInteraction(self, self.capture_method, width, height)
            else:
                self.interaction.capture = self.capture_method
                self.interaction.width = width
                self.interaction.height = height

        communicate.adb_devices.emit(True)

    def update_resolution_for_hwnd(self):
        if self.hwnd is not None and self.hwnd.frame_aspect_ratio == 0:
            height, width = self.get_resolution()
            logger.debug(f'update resolution for {self.hwnd} {width}x{height}')
            self.hwnd.update_frame_size(width, height)

    @property
    def device(self):
        if preferred := self.get_preferred_device():
            if self._device is None:
                logger.debug(f'get device connect {preferred}')
                self._device = self.adb_connect(preferred.get('address'))
            if self._device is not None and self._device.serial != preferred.get('address'):
                logger.info(f'get device adb device addr changed {preferred}')
                self._device = self.adb_connect(preferred.get('address'))
        else:
            logger.error(f'self.get_preferred_device returned None')
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
        # Set default timeout to 5 if not provided
        kwargs.setdefault('timeout', 5)

        device = self.device
        if device is not None:
            try:
                return device.shell(*args, **kwargs)
            except Exception as e:
                addr = self.get_preferred_device()['address']
                self.refresh_emulators()
                new_addr = self.get_preferred_device()['address']
                logger.error(f"shell_wrapper error occurred, try refresh_emulators {addr} {new_addr}", e)
                return None
        else:
            raise Exception('Device is none')

    def device_connected(self):
        if self.get_preferred_device()['device'] == 'windows':
            return True
        elif self.device is not None:
            try:
                state = self.shell('echo 1')
                logger.debug(f'device_connected check device state is {state}')
                return state is not None
            except Exception as e:
                logger.error(f'device_connected error occurred, {e}')

    def get_exe_path(self, device):
        path = device.get('full_path')
        if device.get('device') == 'windows' and self.windows_capture_config and self.windows_capture_config.get(
                'calculate_pc_exe_path'):
            return self.windows_capture_config.get('calculate_pc_exe_path')(path)
        elif emulator := device.get('emulator'):
            return get_emulator_exe(emulator)
        else:
            return None

    def adb_check_installed(self, packages):
        installed = self.shell('pm list packages')
        if isinstance(packages, str):
            packages = [packages]
        for package in packages:
            if package in installed:
                return package

    def adb_check_in_front(self, packages):
        front = self.device.app_current()
        logger.debug(f'adb_check_in_front {front}')
        if front:
            if isinstance(packages, str):
                packages = [packages]
            for package in packages:
                if package == front.package:
                    return package

    def adb_start_package(self, package):
        self.shell(f'monkey -p {package} -c android.intent.category.LAUNCHER 1')

    def adb_ensure_in_front(self, packages):
        front = self.adb_check_in_front(packages)
        logger.debug(f'adb_ensure_in_front {front}')
        if front:
            return front
        elif installed := self.adb_check_installed(packages):
            self.adb_start_package(installed)
            return True
