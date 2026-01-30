import os
import re
import threading

import cv2
import numpy as np

from ok.device.capture import HwndWindow, find_hwnd, BrowserCaptureMethod, update_capture_method, NemuIpcCaptureMethod, \
    ADBCaptureMethod
from ok.device.intercation import PostMessageInteraction, GenshinInteraction, ForegroundPostMessageInteraction, \
    PynputInteraction, PyDirectInteraction, BrowserInteraction, ADBInteraction
from ok.gui.Communicate import communicate
from ok.util.collection import parse_ratio
from ok.util.config import Config
from ok.util.file import delete_if_exists
from ok.util.handler import Handler
from ok.util.logger import Logger
from ok.util.process import kill_exe
from ok.util.window import windows_graphics_available

logger = Logger.get_logger(__name__)

class DeviceManager:

    def __init__(self, app_config, exit_event=None, global_config=None):
        logger.info('__init__ start')
        self._device = None
        self._adb = None
        self.executor = None
        self.capture_method = None
        self.global_config = global_config
        self._adb_lock = threading.Lock()
        if app_config.get('adb'):
            self.packages = app_config.get('adb').get('packages')
        else:
            self.packages = None
        supported_resolution = app_config.get(
            'supported_resolution', {})
        self.supported_ratio = parse_ratio(supported_resolution.get('ratio'))
        self.windows_capture_config = app_config.get('windows')
        self.adb_capture_config = app_config.get('adb')
        self.browser_config = app_config.get('browser')
        self.debug = app_config.get('debug')
        self.interaction = None
        self.device_dict = {}
        self.exit_event = exit_event
        self.resolution_dict = {}
        default_capture = 'windows' if app_config.get('windows') else (
            'browser' if app_config.get('browser') else 'adb')
        self.config = Config("devices",
                             {"preferred": "", "pc_full_path": "", 'capture': default_capture, 'selected_exe': '',
                              'selected_hwnd': 0})
        self.handler = Handler(exit_event, 'RefreshAdb')
        if self.windows_capture_config is not None:
            if isinstance(self.windows_capture_config.get('exe'), str):
                self.windows_capture_config['exe'] = [self.windows_capture_config.get('exe')]

            self.hwnd_window = HwndWindow(exit_event, self.windows_capture_config.get('title'),
                                          self.windows_capture_config.get('exe'),
                                          hwnd_class=self.windows_capture_config.get('hwnd_class'),
                                          global_config=self.global_config, device_manager=self)
            if self.windows_capture_config.get(
                    'interaction') == 'PostMessage':
                self.win_interaction_class = PostMessageInteraction
            elif self.windows_capture_config.get(
                    'interaction') == 'Genshin':
                self.win_interaction_class = GenshinInteraction
            elif self.windows_capture_config.get(
                    'interaction') == 'ForegroundPostMessage':
                self.win_interaction_class = ForegroundPostMessageInteraction
            elif self.windows_capture_config.get(
                    'interaction') == 'Pynput':
                self.win_interaction_class = PynputInteraction
            elif self.windows_capture_config.get(
                    'interaction') and self.windows_capture_config.get(
                'interaction') != 'PyDirect':
                self.win_interaction_class = self.windows_capture_config.get(
                    'interaction')
            else:
                self.win_interaction_class = PyDirectInteraction
        else:
            self.hwnd_window = None

        logger.info('__init__ end')

    def stop_hwnd(self):
        if self.hwnd_window:
            logger.info(f'stop_hwnd {self.hwnd_window.exe_full_path}')
            if self.hwnd_window.exe_full_path:
                kill_exe(abs_path=self.hwnd_window.exe_full_path)

    def select_hwnd(self, exe, hwnd):
        self.config['selected_exe'] = exe
        self.config['selected_hwnd'] = hwnd

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
                from adbutils import AdbError
                try:
                    self._adb.device_list()
                except AdbError as e:
                    self.try_kill_adb(e)
            return self._adb

    def try_kill_adb(self, e=None):
        logger.error('try kill adb server', e)
        import psutil
        for proc in psutil.process_iter():
            if proc.name() == 'adb.exe' or proc.name() == 'adb':
                logger.info(f'kill adb by process name {proc.cmdline()}')
                try:
                    proc.kill()
                except Exception as e:
                    logger.error(f'kill adb server failed', e)
        logger.info('try kill adb end')

    def adb_connect(self, addr, try_connect=True):
        from adbutils import AdbError
        try:
            for device in self.adb.list():
                if self.exit_event.is_set():
                    logger.error(f"adb_connect exit_event is set")
                    return None
                if device.serial == addr:
                    if device.state == 'offline':
                        logger.info(f'adb_connect offline disconnect first {addr}')
                        self.adb.disconnect(addr)
                    else:
                        logger.info(f'adb_connect already connected {addr}')
                        return self.adb.device(serial=addr)
            if try_connect:
                ret = self.adb.connect(addr, timeout=5)
                logger.info(f'adb_connect try_connect {addr} {ret}')
                return self.adb_connect(addr, try_connect=False)
            else:
                logger.info(f'adb_connect {addr} not in device list {self.adb.list()}')
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
                                                                   self.windows_capture_config.get(
                                                                       'exe') or self.config.get('selected_exe'), 0, 0,
                                                                   player_id=-1,
                                                                   class_name=self.windows_capture_config.get(
                                                                       'hwnd_class'),
                                                                   selected_hwnd=self.config.get('selected_hwnd'))
            nick = name or self.windows_capture_config.get('exe')
            pc_device = {"address": "", "imei": 'pc', "device": "windows",
                         "model": "", "nick": nick, "width": width,
                         "height": height,
                         "hwnd": nick, "capture": "windows",
                         "connected": hwnd > 0,
                         "full_path": full_path or self.config.get('pc_full_path')
                         }
            logger.info(f'start update_pc_device {self.windows_capture_config}, pc_device: {pc_device}')
            if full_path and full_path != self.config.get('pc_full_path'):
                logger.info(f'start update_pc_device pc_full_path {full_path}')
                self.config['pc_full_path'] = full_path

            if width != 0:
                pc_device["resolution"] = f"{width}x{height}"
            self.device_dict['pc'] = pc_device

    def update_browser_device(self):
        if self.browser_config and windows_graphics_available():
            width, height = self.browser_config.get('resolution', (1280, 720))
            nick = self.browser_config.get('nick', 'Browser')
            connected = False
            if isinstance(self.capture_method, BrowserCaptureMethod):
                connected = self.capture_method.connected()
            self.device_dict['browser'] = {
                "address": self.browser_config.get('url'),
                "imei": 'browser',
                "device": "browser",
                "nick": nick,
                "width": width,
                "height": height,
                "connected": connected,
                "resolution": f"{width}x{height}"
            }

    def do_refresh(self, current=False):
        try:
            self.update_pc_device()
            self.update_browser_device()
            self.refresh_emulators(current)
            self.refresh_phones(current)
        except Exception as e:
            logger.error('refresh error', e)

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
        logger.debug(f'refresh_phones done')

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
            if adb_device is not None:
                adb_width, adb_height = self.get_resolution(adb_device)
            else:
                adb_width, adb_height = 0, 0
            name, hwnd, full_path, x, y, width, height = find_hwnd(None,
                                                                   emulator.path, adb_width, adb_height,
                                                                   emulator.player_id)
            logger.info(
                f'adb_connect emulator result {emulator.path} {emulator.player_id} {emulator.type} {adb_device} hwnd_size {width, height} adb_size {adb_width, adb_height} {name, hwnd}')
            connected = adb_device is not None
            emulator_device = {"address": emulator.serial, "device": "adb", "full_path": emulator.path,
                               "connected": connected, "imei": emulator.name, "player_id": emulator.player_id,
                               "nick": name or emulator.name, "emulator": emulator}
            if adb_device is not None:
                emulator_device["resolution"] = f"{adb_width}x{adb_height}"
                emulator_device["adb_imei"] = self.adb_get_imei(adb_device)
            self.device_dict[emulator.name] = emulator_device
        logger.info(f'refresh emulators {self.device_dict}')

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
                logger.info(f'get_resolution capture frame frame.shape {width, height}')
                if self.supported_ratio is None or abs(width / height - self.supported_ratio) < 0.01:
                    self.resolution_dict[device.serial] = (width, height)
                else:
                    logger.warning(f'resolution error {device.serial} {self.supported_ratio} {width, height}')
            else:
                logger.info(f'get_resolution capture frame is None')
        return width, height

    def set_preferred_device(self, imei=None, index=-1):
        logger.debug(f"set_preferred_device {imei} {index}")
        if self.executor:
            self.executor.stop_current_task()
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
        logger.debug(f'adb shell {device} {args} {kwargs}')
        if device is not None:
            return device.shell(*args, **kwargs)
        else:
            raise Exception('Device is none')

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

    def adb_ui_dump(self):
        device = self.device
        if device:
            try:
                dump_output = self.shell_device(device, ["uiautomator", "dump"], encoding='utf-8')
                match = re.search(r"/sdcard/.*\.xml", dump_output)
                if match:
                    dump_file_path = match.group(0)
                    logger.debug(f"Dumped UI file at: {dump_file_path}")
                    xml_content = None
                    local_file_path = os.path.join('temp', 'window_dump.xml')

                    if not os.path.exists('temp'):
                        os.makedirs('temp')

                    delete_if_exists(local_file_path)

                    device.sync.pull(dump_file_path, local_file_path)
                    if os.path.isfile(local_file_path):
                        with open(local_file_path, 'r', encoding='utf-8') as f:
                            xml_content = f.read()
                    return xml_content
                else:
                    logger.error(f"Error: Could not extract the file path from the output:  {dump_output}")
                    return None
            except Exception as e:
                logger.error('adb_ui_dump exception', e)

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
            if self.hwnd_window:
                self.hwnd_window.title = hwnd_name
            self.config.save_file()

    def set_capture(self, capture):
        if self.config.get("capture") != capture:
            if self.executor:
                self.executor.stop_current_task()
            self.config['capture'] = capture
            self.start()

    def get_hwnd_name(self):
        preferred = self.get_preferred_device()
        return preferred.get('hwnd')

    def ensure_hwnd(self, title, exe, frame_width=0, frame_height=0, player_id=-1, hwnd_class=None):
        if self.hwnd_window is None:
            self.hwnd_window = HwndWindow(self.exit_event, title, exe, frame_width, frame_height, player_id,
                                          hwnd_class, global_config=self.global_config, device_manager=self)
        else:
            self.hwnd_window.update_window(title, exe, frame_width, frame_height, player_id, hwnd_class)

    def use_windows_capture(self):
        self.capture_method = update_capture_method(self.windows_capture_config, self.capture_method, self.hwnd_window,
                                                    exit_event=self.exit_event)
        if self.capture_method is None:
            logger.error(f'cant find a usable windows capture')
        else:
            logger.info(f'capture method {type(self.capture_method)}')

    def start(self):
        self.handler.post(self.do_start, remove_existing=True, skip_if_running=True)

    def do_start(self):
        logger.debug(f'do_start')
        preferred = self.get_preferred_device()
        if preferred is None:
            if self.device_dict:
                self.set_preferred_device()
            return

        if preferred['device'] == 'windows':
            self.ensure_hwnd(self.windows_capture_config.get('title'), self.windows_capture_config.get('exe'),
                             hwnd_class=self.windows_capture_config.get('hwnd_class'))
            self.use_windows_capture()
            if not isinstance(self.interaction, self.win_interaction_class):
                self.interaction = self.win_interaction_class(self.capture_method, self.hwnd_window)
            preferred['connected'] = self.capture_method is not None and self.capture_method.connected()
        elif preferred['device'] == 'browser':
            if not isinstance(self.capture_method, BrowserCaptureMethod):
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = BrowserCaptureMethod(self.browser_config, self.exit_event)
            if not isinstance(self.interaction, BrowserInteraction):
                self.interaction = BrowserInteraction(self.capture_method)

            if not self.capture_method.connected():
                self.capture_method.start_browser()

            preferred['connected'] = self.capture_method.connected()
        else:
            width, height = self.get_resolution()
            if self.config.get('capture') == "windows":
                self.ensure_hwnd(None, preferred.get('full_path'), width, height, preferred['player_id'])
                logger.info(f'do_start use windows capture {self.hwnd_window.title}')
                self.use_windows_capture()
            else:
                if self.config.get('capture') == 'ipc':
                    if not isinstance(self.capture_method, NemuIpcCaptureMethod):
                        if self.capture_method is not None:
                            self.capture_method.close()
                        self.capture_method = NemuIpcCaptureMethod(self, self.exit_event)
                    self.capture_method.update_emulator(self.get_preferred_device().get('emulator'))
                    logger.info(f'use ipc capture {preferred}')
                else:
                    if not isinstance(self.capture_method, ADBCaptureMethod):
                        logger.debug(f'use adb capture')
                        if self.capture_method is not None:
                            self.capture_method.close()
                        self.capture_method = ADBCaptureMethod(self, self.exit_event, width=width,
                                                               height=height)
                        logger.info(f'use adb capture {preferred}')
                if preferred.get('full_path'):
                    logger.info(f'ensure_hwnd for debugging {preferred} {width, height}')
                    self.ensure_hwnd(None, preferred.get('full_path').replace("nx_main/MuMuNxMain.exe",
                                                                              "nx_device/12.0/shell/MuMuNxDevice.exe"),
                                     width, height,
                                     preferred['player_id'])
                elif self.hwnd_window is not None:
                    self.hwnd_window.stop()
                    self.hwnd_window = None
                if not isinstance(self.interaction, ADBInteraction):
                    self.interaction = ADBInteraction(self, self.capture_method, width, height)
                else:
                    self.interaction.capture = self.capture_method
                    self.interaction.width = width
                    self.interaction.height = height

        communicate.adb_devices.emit(True)

    def update_resolution_for_hwnd(self):
        if self.hwnd_window is not None and self.hwnd_window.frame_aspect_ratio == 0 and self.adb_capture_config:
            width, height = self.get_resolution()
            logger.debug(f'update resolution for {self.hwnd_window} {width}x{height}')
            self.hwnd_window.update_frame_size(width, height)

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
        logger.debug(f'adb shell {device} {args} {kwargs}')
        if device is not None:
            return self.shell_device(device, *args, **kwargs)
        else:
            raise Exception('Device is none')

    def device_connected(self):
        preferred = self.get_preferred_device()
        if preferred['device'] == 'windows' or preferred['device'] == 'browser':
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
        if device.get(
                'device') == 'windows' and self.windows_capture_config:
            if path == "none":
                path = None
            if calculate := self.windows_capture_config.get(
                    'calculate_pc_exe_path'):
                if isinstance(calculate, str):
                    path = calculate
                else:
                    path = self.windows_capture_config.get('calculate_pc_exe_path')(path)
                logger.info(f'calculate_pc_exe_path {path}')
                if '://' in path:
                    logger.info(f'path is a url skip checking {path}')
                    return path
            if os.path.exists(path):
                return path
        elif emulator := device.get('emulator'):
            from ok.alas.platform_windows import get_emulator_exe
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
        front = self.device is not None and self.device.app_current()
        logger.debug(f'adb_check_in_front {front}')
        if front:
            if isinstance(packages, str):
                packages = [packages]
            for package in packages:
                if package == front.package:
                    return True

    def adb_start_package(self, package):
        self.shell(f'monkey -p {package} -c android.intent.category.LAUNCHER 1')

    def adb_ensure_in_front(self):
        front = self.adb_check_in_front(self.packages)
        logger.debug(f'adb_ensure_in_front {front}')
        if front:
            return front
        elif installed := self.adb_check_installed(self.packages):
            self.adb_start_package(installed)
            return True
