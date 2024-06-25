import os
import threading

import cv2
import numpy as np
from adbutils import AdbError

from ok.alas.platform_windows import get_emulator_exe
from ok.capture.HwndWindow import HwndWindow, find_hwnd
from ok.capture.adb.ADBCaptureMethod import ADBCaptureMethod
from ok.capture.adb.WindowsCaptureFactory import update_capture_method
from ok.config.Config import Config
from ok.gui.Communicate import communicate
from ok.interaction.ADBInteraction import ADBBaseInteraction
from ok.interaction.Win32Interaction import Win32Interaction
from ok.logging.Logger import get_logger
from ok.util.Handler import Handler

logger = get_logger(__name__)


class DeviceManager:

    def __init__(self, app_config, exit_event=None):
        self._device = None
        self._adb = None
        self._adb_lock = threading.Lock()
        supported_resolution = app_config.get(
            'supported_resolution', {})
        self.supported_ratio = parse_ratio(supported_resolution.get('ratio'))
        self.windows_capture_config = app_config.get('windows')
        self.adb_capture_config = app_config.get('adb')
        self.debug = app_config.get('debug')
        self.interaction = None
        self.device_dict = {}
        self.exit_event = exit_event
        self.resolution_dict = {}
        if self.windows_capture_config is not None:
            self.hwnd = HwndWindow(exit_event, self.windows_capture_config.get('title'),
                                   self.windows_capture_config.get('exe'))
        else:
            self.hwnd = None
        self.config = Config({"preferred": "none", "pc_full_path": "none", 'capture': 'windows'},
                             app_config.get('config_folder'),
                             "devices")
        self.capture_method = None
        self.handler = Handler(exit_event, 'RefreshAdb')
        self.handler.post(self.do_refresh, 3)

    def refresh(self):
        logger.debug('calling refresh')
        self.handler.post(self.do_refresh, remove_existing=True, skip_if_running=True)

    @property
    def adb(self):
        with self._adb_lock:
            if self._adb is None:
                import adbutils
                logger.debug(f'init adb')
                from adbutils._utils import _get_bin_dir
                bin_dir = _get_bin_dir()
                exe = os.path.join(bin_dir, "adb.exe" if os.name == 'nt' else 'adb')
                from adbutils._utils import _is_valid_exe
                if os.path.isfile(exe) and _is_valid_exe(exe):
                    os.environ['ADBUTILS_ADB_PATH'] = exe
                    logger.info(f'set ADBUTILS_ADB_PATH {os.getenv("ADBUTILS_ADB_PATH")}')
                else:
                    logger.error(f'set ADBUTILS_ADB_PATH failed {exe}')
                self._adb = adbutils.AdbClient(host="127.0.0.1", socket_timeout=4)
                try:
                    self._adb.device_list()
                except AdbError as e:
                    self.try_kill_adb(e)
            return self._adb

    def try_kill_adb(self, e=None):
        logger.error('try kill adb server', e)
        import psutil
        for proc in psutil.process_iter():
            # Check whether the process name matches
            if proc.name() == 'adb.exe' or proc.name() == 'adb':
                logger.info(f'kill adb by process name {proc.cmdline()}')
                try:
                    proc.kill()
                except Exception as e:
                    logger.error(f'kill adb server failed', e)
        logger.info('try kill adb end')
        # self._adb.server_kill()

    def adb_connect(self, addr, try_connect=True):
        try:
            for device in self.adb.device_list():
                if self.exit_event.is_set():
                    logger.error(f"adb_connect exit_event is set")
                    return None
                if device.serial == addr:
                    if device.info['state'] == 'offline':
                        logger.debug(f'adb_connect offline disconnect first {addr}')
                        self.adb.disconnect(addr)
                    else:
                        logger.debug(f'adb_connect already connected {addr}')
                        return device
            if try_connect:
                self.adb.connect(addr, timeout=5)
                logger.debug(f'adb_connect {addr}')
                return self.adb_connect(addr, try_connect=False)
        except AdbError as e:
            logger.error(f"adb connect error {addr}", e)
            self.try_kill_adb(e)
        except Exception as e:
            logger.error(f"adb connect error return none {addr}", e)

    def get_devices(self):
        return list(self.device_dict.values())

    def update_pc_device(self):
        if self.windows_capture_config is not None:
            name, hwnd, full_path, x, y, width, height = find_hwnd(self.windows_capture_config.get('title'),
                                                                   self.windows_capture_config.get('exe'), 0, 0)
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

    def do_refresh(self, current=False):
        self.update_pc_device()
        self.refresh_emulators(current)
        self.refresh_phones(current)

        if self.exit_event.is_set():
            return
        self.do_start()

        logger.debug(f'refresh {self.device_dict}')

    def refresh_phones(self, current=False):
        if self.adb_capture_config is None:
            return
        for adb_device in self.adb.iter_device():
            imei = self.adb_get_imei(adb_device)
            if imei is not None:
                preferred = self.get_preferred_device()
                if current and preferred is not None and preferred['imei'] != imei:
                    logger.debug(f"refresh current only skip others {preferred['imei']} != {imei}")
                    continue
                found = False
                for device in self.device_dict.values():
                    if device.get('adb_imei') == imei:
                        found = True
                        break
                if not found:
                    width, height = self.get_resolution(adb_device)
                    logger.debug(f'refresh_phones found an phone {adb_device}')
                    phone_device = {"address": adb_device.serial, "device": "adb", "connected": True, "imei": imei,
                                    "nick": adb_device.prop.model or imei, "player_id": -1,
                                    "resolution": f'{width}x{height}'}
                    self.device_dict[imei] = phone_device

    def refresh_emulators(self, current=False):
        if self.adb_capture_config is None:
            return
        from ok.alas.emulator_windows import EmulatorManager
        manager = EmulatorManager()
        installed_emulators = manager.all_emulator_instances
        logger.info(f'installed emulators {installed_emulators}')
        for emulator in installed_emulators:
            preferred = self.get_preferred_device()
            if current and preferred is not None and preferred['imei'] != emulator.name:
                logger.debug(f"refresh current only skip others {preferred['imei']} != {emulator.name}")
                continue
            adb_device = self.adb_connect(emulator.serial)
            width, height = self.get_resolution(adb_device) if adb_device is not None else 0, 0
            name, hwnd, full_path, x, y, width, height = find_hwnd(None,
                                                                   emulator.path, width, height, emulator.player_id)
            connected = adb_device is not None and name is not None
            emulator_device = {"address": emulator.serial, "device": "adb",
                               "full_path": emulator.path, "connected": connected,
                               "imei": emulator.name, "player_id": emulator.player_id,
                               "nick": name or emulator.name, "emulator": emulator}
            if adb_device is not None:
                emulator_device["resolution"] = f"{width}x{height}"
                emulator_device["adb_imei"] = self.adb_get_imei(adb_device)
            self.device_dict[emulator.name] = emulator_device
        logger.debug(f'refresh emulators {self.device_dict}')

    def get_resolution(self, device=None):
        if device is None:
            device = self.device
        width, height = 0, 0
        if device is not None:
            if resolution := self.resolution_dict.get(device.serial):
                return resolution
            frame = self.do_screencap(device)
            if frame is not None:
                height, width, _ = frame.shape
                if self.supported_ratio is None or abs(width / height - self.supported_ratio) < 0.01:
                    self.resolution_dict[device.serial] = (width, height)
                else:
                    logger.warning(f'resolution error {device.serial} {self.supported_ratio} {width, height}')
        return width, height

    def set_preferred_device(self, imei=None, index=-1):
        logger.debug(f"set_preferred_device {imei} {index}")
        if index != -1:
            imei = self.get_devices()[index]['imei']
        elif imei is None:
            imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        if preferred is None:
            if len(self.device_dict) > 0:
                connected_device = None
                for device in self.device_dict.values():
                    if device.get('connected') or connected_device is None:
                        connected_device = device
                logger.info(f'first start use first or connected device {connected_device}')
                preferred = connected_device
                imei = preferred['imei']
            else:
                logger.warning(f'no devices')
                return
        if self.config.get("preferred") != imei:
            logger.info(f'preferred device did change {imei}')
            self.config["preferred"] = imei
            self.start()
        logger.debug(f'preferred device: {preferred}')

    def shell_device(self, device, *args, **kwargs):
        kwargs.setdefault('timeout', 5)
        try:
            return device.shell(*args, **kwargs)
        except AdbError as e:
            logger.error(f"adb shell AdbError try kill server {device}", e)
            self.try_kill_adb(e)
            addr = self.get_preferred_device()['address']
            self.refresh_emulators()
            self.refresh_phones()
            new_addr = self.get_preferred_device()['address']
            logger.error(f"shell_wrapper error occurred, try refresh_emulators {addr} {new_addr}", e)
            device = self.adb_connect(device.serial)
            return device.shell(*args, **kwargs)
        except Exception as e:
            logger.error(f"adb shell error maybe offline {device}", e)
            return None

    def adb_get_imei(self, device):
        return (self.shell_device(device, "settings get secure android_id") or
                self.shell_device(device, "service call iphonesubinfo 4") or device.prop.model)

    def do_screencap(self, device) -> np.ndarray | None:
        if device is None:
            return None
        try:
            png_bytes = self.shell_device(device, "screencap -p", encoding=None)
            if png_bytes is not None and len(png_bytes) > 0:
                image_data = np.frombuffer(png_bytes, dtype=np.uint8)
                image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
                if image is not None:
                    return image
                else:
                    logger.error(f"Screencap image decode error, probably disconnected")
        except Exception as e:
            logger.error('screencap', e)

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
            self.start()

    def get_hwnd_name(self):
        preferred = self.get_preferred_device()
        return preferred.get('hwnd')

    def ensure_hwnd(self, title, exe, frame_width=0, frame_height=0, player_id=-1):
        if self.hwnd is None:
            self.hwnd = HwndWindow(self.exit_event, title, exe, frame_width, frame_height, player_id)
        else:
            self.hwnd.update_window(title, exe, frame_width, frame_height, player_id)

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
            preferred['connected'] = self.capture_method is not None and self.capture_method.connected()
        else:
            width, height = self.get_resolution()
            if self.config.get('capture') == "windows":
                self.ensure_hwnd(None, preferred.get('full_path'), width, height, preferred['player_id'])
                self.use_windows_capture({'can_bit_blt': True}, require_bg=True, use_bit_blt_only=False)
            else:
                if not isinstance(self.capture_method, ADBCaptureMethod):
                    logger.debug(f'use adb capture')
                    if self.capture_method is not None:
                        self.capture_method.close()
                    self.capture_method = ADBCaptureMethod(self, self.exit_event, width=width,
                                                           height=height)
                if self.debug and preferred.get('full_path'):
                    self.ensure_hwnd(None, preferred.get('full_path'), width, height, preferred['player_id'])
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
        if self.hwnd is not None and self.hwnd.frame_aspect_ratio == 0 and self.adb_capture_config:
            width, height = self.get_resolution()
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

        device = self.device
        if device is not None:
            return self.shell_device(device, *args, **kwargs)
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
                    return True

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


def parse_ratio(ratio_str):
    if ratio_str:
        # Split the string into two parts: '16' and '9'
        numerator, denominator = ratio_str.split(':')
        # Convert the strings to integers and perform the division
        ratio_float = int(numerator) / int(denominator)
        return ratio_float
