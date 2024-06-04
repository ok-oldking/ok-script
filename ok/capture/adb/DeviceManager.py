import win32gui
from adbutils import AdbTimeout

from ok.alas.platform_windows import get_emulator_exe
from ok.capture.HwndWindow import HwndWindow, find_hwnd_by_title_and_exe, enum_windows
from ok.capture.adb.ADBCaptureMethod import ADBCaptureMethod, do_screencap
from ok.capture.adb.WindowsCaptureFactory import update_capture_method
from ok.capture.windows.BitBltCaptureMethod import bit_blt_test_hwnd
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
        self._adb = None
        self.windows_capture_config = windows_capture_config
        self.adb_capture_config = adb_capture_config
        self.pc_device = None
        self.debug = debug
        self.interaction = None
        self.emulator_dict = {}
        self.exit_event = exit_event
        if windows_capture_config is not None:
            self.hwnd = HwndWindow(exit_event, windows_capture_config.get('title'),
                                   windows_capture_config.get('exe'))
        self.config = Config({"devices": {}, "preferred": "none", "pc_full_path": None}, config_folder,
                             "DeviceManager")
        self.capture_method = None
        self.handler = Handler(exit_event, 'RefreshAdb')
        self.handler.post(self.do_refresh, 3)

    def refresh(self):
        logger.debug('calling refresh')
        self.handler.post(self.do_refresh, remove_existing=True, skip_if_running=True)

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
            self.adb.connect(addr, timeout=5)
            device = self.adb.device(addr)
            logger.debug(f'adb_connect {addr} device {device}')
            # for adb_device in self.adb.device_list():
            #     if addr == adb_device.serial:
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

    def do_refresh(self, fast=False):
        self.update_pc_device()

        self.refresh_emulators()

        if self.exit_event.is_set():
            return
        self.start()

        logger.debug(f'refresh {self.device_dict}')

    def refresh_emulators(self):
        from ok.alas.emulator_windows import EmulatorManager
        manager = EmulatorManager()
        installed_emulators = manager.all_emulator_instances
        to_delete = []
        # delete no exist and update old
        for imei, device in self.config.get("devices").items():
            if device["device"] == 'adb':
                found = False
                for emulator in installed_emulators:
                    if emulator.serial == device['address']:
                        found = True
                        break
                if not found:
                    to_delete.append(imei)
        logger.debug(f'emulator delete {to_delete}')
        for key in to_delete:
            del self.config.get("devices")[key]
        for emulator in installed_emulators:
            self.emulator_dict[emulator.serial] = emulator
            found = None
            adb_device = self.adb_connect(emulator.serial)
            windows = enum_windows(emulator.path)
            connected = adb_device is not None and len(windows) > 0
            height, width = self.get_resolution(adb_device)
            to_update = {"address": emulator.serial, "imei": emulator.name, "device": "adb",
                         "full_path": emulator.path, "connected": connected,
                         "nick": emulator.name}
            if adb_device is not None:
                to_update["resolution"] = f"{width}x{height}"
            for imei, device in self.config.get("devices").items():
                if device["device"] == 'adb':
                    if emulator.serial == device['address']:
                        device.update(to_update)
                        found = device
                        break
            if not found or found.get('hwnd') is None:
                if len(windows) > 0:
                    for hwnd, title, _, _ in windows:
                        if bit_blt_test_hwnd(hwnd):
                            to_update["hwnd"] = title
                            if found:
                                found['hwnd'] = title
                            logger.info(f'update hwnd from emulator {title}')
                            break
            if not found:
                to_update['capture'] = 'windows'
                self.config.get("devices")[emulator.name] = to_update
        logger.debug(f'refresh emulators {self.config.get("devices")}')

    def get_resolution(self, device=None):
        if device is None:
            device = self.device
        width, height = 0, 0
        if device is not None:
            frame = do_screencap(device)
            if frame is not None:
                height, width, _ = frame.shape
        return height, width

    def update_device(self, imei, device=None):
        devices = self.config.get("devices", {})
        devices[imei] = device
        self.config["devices"] = devices

    def update_device_value(self, imei, key, value):
        devices = self.config.get("devices", {})
        if imei in devices:
            devices[imei][key] = value
        self.config["devices"] = devices

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
            self.config.save_file()
            self.handler.post(self.start, remove_existing=True, skip_if_running=True)
        logger.debug(f'preferred device: {preferred}')

    def get_preferred_device(self):
        imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        return preferred

    def set_hwnd_name(self, hwnd_name):
        preferred = self.get_preferred_device()
        if preferred.get("hwnd") != hwnd_name:
            preferred['hwnd'] = hwnd_name
            if self.hwnd:
                self.hwnd.title = hwnd_name
            self.config.save_file()

    def set_capture(self, capture):
        preferred = self.get_preferred_device()
        if preferred.get("capture") != capture:
            preferred['capture'] = capture
            self.config.save_file()
            self.handler.post(self.start, remove_existing=True, skip_if_running=True)

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
            hwnd_name = preferred.get('hwnd')
            height, width = self.get_resolution()
            if preferred.get('capture') == "windows":
                self.ensure_hwnd(hwnd_name, preferred.get('full_path'), width, height)
                self.use_windows_capture({'can_bit_blt': True}, require_bg=True)
            elif not isinstance(self.capture_method, ADBCaptureMethod):
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = ADBCaptureMethod(self, self.exit_event, width=width,
                                                       height=height)
                if self.debug and hwnd_name:
                    self.ensure_hwnd(hwnd_name, None, width, height)
                elif self.hwnd is not None:
                    self.hwnd.stop()
                    self.hwnd = None
            if not isinstance(self.interaction, ADBBaseInteraction):
                self.interaction = ADBBaseInteraction(self, self.capture_method, width, height)
            else:
                self.interaction.capture = self.capture_method
                self.interaction.width = width
                self.interaction.height = height

        self.config.save_file()
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
        device = self.device
        if device is not None:
            try:
                return device.shell(*args, **kwargs)
            except Exception as e:
                addr = self.get_preferred_device()['address']
                self.refresh_emulators()
                new_addr = self.get_preferred_device()['address']
                logger.error(f"shell_wrapper error occurred,try refresh_emulators {addr} {new_addr}", e)
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
        elif emulator := self.emulator_dict.get(device.get('address')):
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
