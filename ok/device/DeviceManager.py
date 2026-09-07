from __future__ import annotations

import ntpath
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from ok.device.capabilities import DeviceCapabilities, NO_DEVICE_CAPABILITIES
from ok.device.capture_methods import ADBCaptureMethod, NemuIpcCaptureMethod
from ok.device.interaction_methods import ADBInteraction, BrowserInteraction
from ok.device.services import create_cursor_service
from ok.core.events import communicate
from ok.platform import (
    MACOS,
    PlatformUnavailableError,
    is_macos,
    is_windows,
    require_platform,
    require_windows,
)
from ok.util.collection import parse_ratio
from ok.util.config import Config
from ok.util.file import delete_if_exists
from ok.util.handler import Handler
from ok.util.logger import Logger
from ok.util.process import kill_exe


if is_windows():
    from ok.device.capture import HwndWindow, BrowserCaptureMethod, update_capture_method
    from ok.device.interaction import (
        PostMessageInteraction,
        GenshinInteraction,
        ForegroundPostMessageInteraction,
        PynputInteraction,
        PyDirectInteraction,
    )
    from ok.util.window import windows_graphics_available, find_hwnd
else:
    class _UnavailableWindowsComponent:
        def __init__(self, *_args, **_kwargs):
            require_windows(type(self).__name__)

    HwndWindow = _UnavailableWindowsComponent
    BrowserCaptureMethod = _UnavailableWindowsComponent
    PostMessageInteraction = _UnavailableWindowsComponent
    GenshinInteraction = _UnavailableWindowsComponent
    ForegroundPostMessageInteraction = _UnavailableWindowsComponent
    PynputInteraction = _UnavailableWindowsComponent
    PyDirectInteraction = _UnavailableWindowsComponent

    def update_capture_method(*_args, **_kwargs):
        raise PlatformUnavailableError('Windows capture is unavailable on this platform')

    def windows_graphics_available():
        return False

    def find_hwnd(*_args, **_kwargs):
        raise PlatformUnavailableError('Win32 window discovery is unavailable on this platform')

logger = Logger.get_logger(__name__)


def resolve_emulator_window_exe(exe_path, instance_name=None):
    """Resolve an emulator launcher path to the instance window executable."""
    if not exe_path:
        return exe_path

    # Emulator paths are Windows paths even when this pure helper is tested
    # from another host, so use ntpath rather than the host path module.
    normalized_path = ntpath.normpath(exe_path)
    if ntpath.basename(normalized_path).lower() != 'mumunxmain.exe':
        return exe_path

    match = re.search(r'-(\d+(?:\.\d+)+)-\d+$', instance_name or '')
    version = match.group(1) if match else '12.0'
    install_root = ntpath.dirname(ntpath.dirname(normalized_path))
    return ntpath.join(
        install_root, 'nx_device', version, 'shell', 'MuMuNxDevice.exe')


def method_name(method):
    return method.__name__ if isinstance(method, type) else str(method)


def _windows_interaction_class(selected_interaction):
    require_windows('Windows interaction backend selection')
    mapping = {
        'PostMessage': PostMessageInteraction,
        'Genshin': GenshinInteraction,
        'ForegroundPostMessage': ForegroundPostMessageInteraction,
        'Pynput': PynputInteraction,
        'PyDirect': PyDirectInteraction,
    }
    if isinstance(selected_interaction, type):
        return selected_interaction
    if selected_interaction:
        return mapping.get(selected_interaction, selected_interaction)
    return PynputInteraction


class DeviceManager:

    def __init__(self, app_config, exit_event=None, global_config=None):
        logger.info('__init__ start')
        self._device = None
        self._adb = None
        self.executor = None
        self.capture_method = None
        self.cursor_service = create_cursor_service()
        self.global_config = global_config
        self._adb_lock = threading.Lock()
        self._device_lifecycle_lock = threading.RLock()
        self._closing = False
        if app_config.get('adb'):
            self.packages = app_config.get('adb').get('packages')
        else:
            self.packages = None
        supported_resolution = app_config.get(
            'supported_resolution', {})
        self.supported_ratio = parse_ratio(supported_resolution.get('ratio'))
        self.coordinate_mode = supported_resolution.get('coordinate_mode', 'legacy')
        if self.coordinate_mode not in ('legacy', 'anchored'):
            raise ValueError('unknown supported_resolution coordinate_mode')
        configured_windows = app_config.get('windows')
        configured_macos = app_config.get('macos')
        configured_browser = app_config.get('browser')
        self.windows_capture_config = configured_windows if is_windows() else None
        self.macos_window_config = configured_macos if is_macos() else None
        self.adb_capture_config = app_config.get('adb')
        # The existing browser capture implementation is HWND/WGC based. Keep
        # it available on Windows without importing it into the Darwin graph.
        self.browser_config = configured_browser if is_windows() else None
        self.debug = app_config.get('debug')
        self.interaction = None
        self.device_dict = {}
        self.exit_event = exit_event
        self.resolution_dict = {}
        self.win_interaction_class = None
        self.hwnd_window = None
        self.window_target = None
        self.window_discovery = None
        self.permission_service = None

        if configured_windows and not is_windows():
            logger.info('Windows desktop configuration is unavailable on this platform')
        if configured_browser and not is_windows():
            logger.info('The current browser capture provider is Windows-only')
        if configured_macos and not is_macos():
            logger.info('macOS desktop configuration is unavailable on this platform')

        if self.windows_capture_config is not None:
            default_capture = 'windows'
        elif self.macos_window_config is not None:
            default_capture = 'macos'
        elif self.browser_config is not None:
            default_capture = 'browser'
        elif self.adb_capture_config is not None:
            default_capture = 'adb'
        else:
            default_capture = ''
        device_defaults = {
            "preferred": "",
            "pc_full_path": "",
            'capture': default_capture,
            'selected_exe': '',
            'selected_hwnd': 0,
            'interaction': '',
        }
        if self.macos_window_config is not None:
            device_defaults['macos_target_hint'] = {}
        self.config = Config("devices", device_defaults)
        self.handler = Handler(exit_event, 'RefreshAdb')
        if self.windows_capture_config is not None:
            if isinstance(self.windows_capture_config.get('exe'), str):
                self.windows_capture_config['exe'] = [self.windows_capture_config.get('exe')]

            self.hwnd_window = HwndWindow(exit_event, self.windows_capture_config.get('title'),
                                          self.windows_capture_config.get('exe'),
                                          hwnd_class=self.windows_capture_config.get('hwnd_class'),
                                          global_config=self.global_config, device_manager=self,
                                          top_hwnd_class=self.windows_capture_config.get('top_hwnd_class'))
            from ok.device.window_target.windows import WindowsHwndWindowTarget
            self.window_target = WindowsHwndWindowTarget(self.hwnd_window)
            interaction = self.windows_capture_config.get('interaction')
            if isinstance(interaction, list):
                selected_interaction = interaction[0] if interaction else 'Pynput'
            else:
                selected_interaction = interaction

            saved_interaction = self.config.get('interaction')
            if saved_interaction:
                if isinstance(interaction, list):
                    for item in interaction:
                        item_name = item.__name__ if isinstance(item, type) else item
                        if saved_interaction == item_name:
                            selected_interaction = item
                            break
                else:
                    item_name = interaction.__name__ if isinstance(interaction, type) else interaction
                    if saved_interaction == item_name:
                        selected_interaction = interaction

            self.win_interaction_class = _windows_interaction_class(selected_interaction)

        self.update_macos_device()
        logger.info('__init__ end')

    def stop_hwnd(self):
        if self.hwnd_window:
            logger.info(f'stop_hwnd {self.hwnd_window.exe_full_path}')
            if self.hwnd_window.exe_full_path:
                kill_exe(abs_path=self.hwnd_window.exe_full_path)

    def close(self):
        """Block/release input before capture and Qt/Python teardown."""
        lock = getattr(self, '_device_lifecycle_lock', None)
        if lock is None:
            return self._close_locked()
        with lock:
            self._closing = True
            return self._close_locked()

    def _close_locked(self):
        interaction = self.interaction
        if interaction is not None:
            try:
                interaction.on_destroy()
            except Exception as e:
                logger.error(f'interaction close failed: {e}')
                try:
                    interaction.invalidate('device manager closing', shutdown=True)
                except Exception as invalidate_error:
                    logger.error(f'interaction invalidation failed: {invalidate_error}')
        self.interaction = None
        hwnd_window = self.hwnd_window
        if hwnd_window is not None:
            hwnd_window.stop()

        capture_method = self.capture_method
        self.capture_method = None
        if capture_method is not None:
            try:
                capture_method.close()
            except Exception as e:
                logger.error(f'capture method close failed: {e}')

    def select_hwnd(self, exe, hwnd):
        self.config['selected_exe'] = exe
        self.config['selected_hwnd'] = hwnd

    def _require_macos_window_config(self):
        require_platform('macOS desktop window target', (MACOS,))
        if self.macos_window_config is None:
            raise PlatformUnavailableError(
                'macOS desktop window target is not configured by this application')

    def _macos_hints(self):
        self._require_macos_window_config()
        from ok.device.window_target import WindowMatchHints
        return WindowMatchHints.from_mapping(self.macos_window_config)

    def _macos_stable_hint(self):
        from ok.device.window_target import StableWindowHint
        return StableWindowHint.from_mapping(
            self.config.get('macos_target_hint', {}))

    def _ensure_macos_window_services(self):
        self._require_macos_window_config()
        if self.window_discovery is None:
            from ok.device.window_target import create_macos_window_discovery
            self.window_discovery = create_macos_window_discovery()
        if self.permission_service is None:
            from ok.device.services import create_permission_service
            self.permission_service = create_permission_service()

    def discover_macos_windows(self, manual_window_id=None):
        """Enumerate/select without binding or starting capture/input providers."""
        self._ensure_macos_window_services()
        return self.window_discovery.select(
            self._macos_hints(),
            stable_hint=self._macos_stable_hint(),
            manual_window_id=manual_window_id,
        )

    def bind_macos_window(self, manual_window_id=None):
        """Bind an unambiguous or explicitly selected macOS window target."""
        self._invalidate_macos_capture('macOS target selection started')
        selection = self.discover_macos_windows(manual_window_id)
        if selection.selected is None:
            self.window_target = None
            self.update_macos_device()
            return selection

        stable_hint = selection.stable_hint
        self.window_target = None
        self.update_macos_device()
        target = self.window_discovery.bind(
            selection.selected,
            self._macos_hints(),
            stable_hint=stable_hint,
        )
        self.window_target = target
        self.config['macos_target_hint'] = stable_hint.to_mapping()
        self.update_macos_device()
        return selection

    def refresh_macos_window_target(self):
        self._require_macos_window_config()
        if self.window_target is None:
            return self.bind_macos_window()
        self._invalidate_macos_capture('macOS target refresh started')
        try:
            return self.window_target.refresh()
        finally:
            self.update_macos_device()

    def prepare_macos_capture(self, timeout=8.0, *, manual_window_id=None):
        """Prepare capture only; all GUI/start/resume callers share this contract.

        Selection, provider creation and bounded fresh-frame recovery are owned
        here. Input remains stopped until Quartz performs its final handoff.
        """
        with self._device_lifecycle_lock:
            if self._closing or self.exit_event.is_set():
                raise RuntimeError('macOS device is stopping')
            if manual_window_id is not None:
                selection = self.bind_macos_window(manual_window_id=manual_window_id)
                if selection.selected is None:
                    raise RuntimeError(f'MAC_GAME_WINDOW_NOT_FOUND: {selection.status.value}')
            self.prepare_macos_device()
            return self.capture_method.wait_until_ready(timeout=timeout)

    def prepare_macos_device(self):
        """Explicit startup only: bind a unique target before creating providers."""
        self._require_macos_window_config()
        with self._device_lifecycle_lock:
            if self._closing or self.exit_event.is_set():
                raise RuntimeError('macOS device is stopping')
            if self.window_target is None:
                selection = self.bind_macos_window()
                if selection.selected is None:
                    raise RuntimeError(
                        'MAC_GAME_WINDOW_NOT_FOUND: select the official game window; '
                        f'window selection: {selection.status.value}')
            elif not self.window_target.exists():
                # Start is recovery of this binding, not permission to replace
                # a dead process or guess between multiple game surfaces.
                result = self.refresh_macos_window_target()
                if not result.current.exists:
                    code = getattr(self.window_target, 'unavailable_code', 'MAC_TARGET_UNAVAILABLE')
                    raise RuntimeError(
                        f'{code}: window recovery {result.status.value}; '
                        'wait and retry, or manually select and bind the game window')
            self.config['preferred'] = 'macos'
            self._do_start_locked(notify=False)

    def macos_permission_status(self):
        self._ensure_macos_window_services()
        return self.permission_service.snapshot()

    def request_macos_permission(self, kind):
        self._ensure_macos_window_services()
        return self.permission_service.request(kind)

    def _invalidate_macos_capture(self, reason):
        self._invalidate_macos_input(reason)
        capture_method = getattr(self, 'capture_method', None)
        invalidator = getattr(capture_method, 'invalidate', None)
        if callable(invalidator):
            invalidator(reason)

    def _invalidate_macos_input(self, reason):
        interaction = getattr(self, 'interaction', None)
        invalidator = getattr(interaction, 'invalidate', None)
        if callable(invalidator):
            invalidator(reason)

    def _on_macos_capture_input_invalidated(self, capture, reason):
        """Ignore callbacks from a capture provider that has been replaced."""
        if capture is self.capture_method:
            self._invalidate_macos_input(reason)

    def _on_macos_interaction_invalidated(self, reason):
        """Pause automation after a foreground/input safety gate closes."""
        logger.error(f'macOS foreground automation paused: {reason}')
        executor = getattr(self, 'executor', None)
        exit_event = getattr(self, 'exit_event', None)
        if executor is None or (exit_event is not None and exit_event.is_set()):
            return
        pause = getattr(executor, 'pause', None)
        if callable(pause):
            pause()

    def macos_capture_diagnostics(self):
        capture_method = getattr(self, 'capture_method', None)
        diagnostics = getattr(capture_method, 'diagnostics', None)
        return diagnostics() if callable(diagnostics) else None

    def refresh(self):
        logger.debug('calling refresh')
        return self.handler.post(self.do_refresh, remove_existing=True, skip_if_running=True)

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
        devices = list(self.device_dict.values())
        def sort_key(d):
            device_type = d.get('device')
            if device_type == 'adb':
                return 0
            if device_type == 'windows':
                return 1
            if device_type == 'browser':
                return 2
            return 3
        return sorted(devices, key=sort_key)

    def _replace_pc_devices(self, pc_devices):
        """Replace window records from the previous Windows enumeration."""
        old_pc_keys = [key for key in self.device_dict if key == 'pc' or key.startswith('pc_')]
        for key in old_pc_keys:
            del self.device_dict[key]
        self.device_dict.update(pc_devices)

    def update_pc_device(self):
        if self.windows_capture_config is not None:
            if not self.windows_capture_config.get('exe') and not self.windows_capture_config.get('hwnd_class') and not self.windows_capture_config.get('title'):
                from ok.util.window import find_all_visible_windows, get_window_bounds
                windows = find_all_visible_windows()
                pc_devices = {}
                for hwnd, title, exe_name, full_path in windows:
                    x, y, _, _, width, height, m_scaling = get_window_bounds(hwnd)
                    if width > 0 and height > 0:
                        imei = f"pc_{hwnd}"
                        pc_device = {
                            "address": "", "imei": imei, "device": "windows",
                            "model": "", "nick": title, "width": width,
                            "height": height, "hwnd": title, "capture": "windows",
                            "connected": True, "full_path": full_path,
                            "real_hwnd": hwnd, "exe": exe_name,
                            "resolution": f"{width}x{height}"
                        }
                        pc_devices[imei] = pc_device
                self._replace_pc_devices(pc_devices)
                return None

            name, hwnd, full_path, x, y, width, height, hwnds = find_hwnd(self.windows_capture_config.get('title'),
                                                                   self.windows_capture_config.get(
                                                                       'exe') or self.config.get('selected_exe'), 0, 0,
                                                                   player_id=-1,
                                                                   class_name=self.windows_capture_config.get(
                                                                       'hwnd_class'),
                                                                   selected_hwnd=self.config.get('selected_hwnd'),
                                                                   top_hwnd_class=self.windows_capture_config.get('top_hwnd_class'))
            exe_list = self.windows_capture_config.get('exe') or self.config.get('selected_exe')
            if isinstance(exe_list, str):
                exe_list = [exe_list]
            nick = name or (exe_list[0] if exe_list else "PC")
            imei = f"pc_{hwnd}" if hwnd else "pc"
            pc_device = {"address": "", "imei": imei, "device": "windows",
                         "model": "", "nick": nick, "width": width,
                         "height": height,
                         "hwnd": nick, "capture": "windows",
                         "connected": hwnd > 0,
                         "full_path": full_path or self.config.get('pc_full_path'),
                         "real_hwnd": hwnd,
                         "exe": exe_list
                         }
            logger.info(f'update_pc_device pc_device: {pc_device}')
            if full_path and full_path != self.config.get('pc_full_path'):
                logger.info(f'start update_pc_device pc_full_path {full_path}')
                self.config['pc_full_path'] = full_path

            if width != 0:
                pc_device["resolution"] = f"{width}x{height}"
            self._replace_pc_devices({imei: pc_device})
            return imei

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

    def update_macos_device(self):
        """Expose target identity and the current Stage D capture state."""
        if self.macos_window_config is None:
            return
        target = self.window_target
        if target is None:
            target_bound = False
            snapshot = None
        else:
            target_bound = bool(target.exists())
            snapshot = target.snapshot if target_bound else None
        candidate = snapshot.candidate if snapshot is not None else None
        nick = (
            candidate.application_name or candidate.title
            if candidate is not None else 'macOS Window'
        )
        capture_diagnostics = self.macos_capture_diagnostics()
        capture_state = getattr(capture_diagnostics, 'state', None)
        capture_state_value = getattr(capture_state, 'value', None)
        self.device_dict['macos'] = {
            'address': '',
            'imei': 'macos',
            'device': 'macos',
            'nick': nick,
            'capture': 'ScreenCaptureKit',
            'connected': target_bound and capture_state_value == 'running',
            'capture_state': capture_state_value or 'unavailable',
            'target_bound': target_bound,
            'process_id': candidate.process_id if candidate is not None else 0,
            'window_id': candidate.window_id if candidate is not None else 0,
            'bundle_identifier': (
                candidate.bundle_identifier if candidate is not None else None),
        }

    def do_refresh(self, current=False):
        try:
            preferred = self.get_preferred_device()
            macos_selected = bool(
                preferred is not None and preferred.get('device') == 'macos')
            if not macos_selected:
                self.refresh_emulators(current)
                self.refresh_phones(current)
            self.update_pc_device()
            self.update_macos_device()
            self.update_browser_device()
        except Exception as e:
            logger.error('refresh error', e)

        if self.exit_event.is_set():
            return
        try:
            self.do_start(notify=False)
        finally:
            communicate.adb_devices.emit(True)

        logger.debug(f'refresh {self.device_dict}')

    def refresh_phones(self, current=False):
        if self.adb_capture_config is None:
            return

        def refresh_one(adb_device):
            imei = self.adb_get_imei(adb_device)
            if imei is not None:
                preferred = self.get_preferred_device()
                if current and preferred is not None and preferred['imei'] != imei:
                    logger.debug(f"refresh current only skip others {preferred['imei']} != {imei}")
                    return None
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
                                    "resolution": f'{width}x{height}', "adb_imei": imei}
                    return imei, phone_device
            return None

        devices = list(self.adb.iter_device())
        if self.exit_event.is_set():
            return
            
        try:
            with ThreadPoolExecutor(max_workers=min(len(devices), 8) if devices else 1) as executor:
                results = list(executor.map(refresh_one, devices))

            for result in results:
                if result:
                    imei, device = result
                    self.device_dict[imei] = device
        except RuntimeError as e:
            if 'shutdown' in str(e):
                logger.debug(f'ThreadPoolExecutor failed during shutdown: {e}')
            else:
                raise
        logger.debug(f'refresh_phones done')

    def refresh_emulators(self, current=False):
        if self.adb_capture_config is None or not is_windows():
            return
        from ok.alas.emulator_windows import EmulatorManager
        manager = EmulatorManager()
        installed_emulators = manager.all_emulator_instances
        logger.info(f'installed emulators {installed_emulators}')

        def refresh_one(emulator):
            preferred = self.get_preferred_device()
            if current and preferred is not None and preferred['imei'] != emulator.name:
                logger.debug(f"refresh current only skip others {preferred['imei']} != {emulator.name}")
                return None
            adb_device = self.adb_connect(emulator.serial)
            if adb_device is not None:
                adb_width, adb_height = self.get_resolution(adb_device)
            else:
                adb_width, adb_height = 0, 0
            window_exe = resolve_emulator_window_exe(emulator.path, emulator.name)
            name, hwnd, full_path, x, y, width, height, _ = find_hwnd(
                None, window_exe, adb_width, adb_height, emulator.player_id)
            logger.info(
                f'adb_connect emulator result {window_exe} {emulator.player_id} {emulator.type} {adb_device} hwnd_size {width, height} adb_size {adb_width, adb_height} {name, hwnd}')
            connected = adb_device is not None
            emulator_device = {"address": emulator.serial, "device": "adb", "full_path": emulator.path,
                               "connected": connected, "imei": emulator.name, "player_id": emulator.player_id,
                               "nick": name or emulator.name, "emulator": emulator}
            if adb_device is not None:
                emulator_device["resolution"] = f"{adb_width}x{adb_height}"
                emulator_device["adb_imei"] = self.adb_get_imei(adb_device)
            return emulator.name, emulator_device

        if self.exit_event.is_set():
            return
            
        try:
            with ThreadPoolExecutor(max_workers=min(len(installed_emulators), 8) if installed_emulators else 1) as executor:
                results = list(executor.map(refresh_one, installed_emulators))

            for result in results:
                if result:
                    name, device = result
                    self.device_dict[name] = device
        except RuntimeError as e:
            if 'shutdown' in str(e):
                logger.debug(f'ThreadPoolExecutor failed during shutdown: {e}')
            else:
                raise
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
            if preferred.get('device') == 'windows' and preferred.get('real_hwnd'):
                self.select_hwnd(preferred.get('exe'), preferred.get('real_hwnd'))
            self.start()
        logger.debug(f'preferred device: {preferred}')

    def shell_device(self, device, *args, **kwargs):
        logger.debug(f'adb shell {device} {args} {kwargs}')
        if device is not None:
            try:
                return device.shell(*args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                if 'offline' in error_msg or 'closed' in error_msg:
                    logger.warning(f"shell_device: Device {device.serial} offline or closed, disconnecting to force reconnect. ({e})")
                    try:
                        self.adb.disconnect(device.serial)
                    except Exception as disc_e:
                        logger.error(f'shell_device disconnect failed: {disc_e}')
                raise
        else:
            raise Exception('Device is none')

    def adb_get_imei(self, device):
        try:
            return (self.shell_device(device, "settings get secure android_id", timeout=5) or
                    self.shell_device(device, "service call iphonesubinfo 4", timeout=5) or device.prop.model)
        except Exception as e:
            logger.error(f"adb_get_imei exception: {e}")
            return None

    def do_screencap(self, device) -> np.ndarray | None:
        if device is None:
            return None
        try:
            import cv2
            import numpy as np

            png_bytes = self.shell_device(device, "screencap -p", encoding=None, timeout=10)
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
                dump_output = self.shell_device(device, ["uiautomator", "dump"], encoding='utf-8', timeout=60)
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

    @property
    def capabilities(self) -> DeviceCapabilities:
        """返回当前 interaction 后端声明的能力，未就绪时 fail closed。"""
        interaction = self.interaction
        if interaction is None:
            return NO_DEVICE_CAPABILITIES
        getter = getattr(interaction, 'get_capabilities', None)
        capabilities = getter() if callable(getter) else getattr(interaction, 'capabilities', None)
        return capabilities if isinstance(capabilities, DeviceCapabilities) else NO_DEVICE_CAPABILITIES

    def get_preferred_capture(self):
        return self.config.get("capture")

    def available_capture_methods(self, device=None):
        """Return valid capture method identifiers for a selected device."""
        device = device or self.get_preferred_device()
        if not device:
            return []
        kind = device.get('device')
        if kind == 'windows':
            configured = (self.windows_capture_config or {}).get('capture_method', [])
            methods = configured if isinstance(configured, list) else [configured]
            return [method_name(item) for item in (methods or ['windows']) if item]
        if kind == 'browser':
            return ['browser']
        if kind == 'macos':
            return ['ScreenCaptureKit']
        methods = ['adb']
        emulator = device.get('emulator')
        if emulator is not None:
            try:
                from ok.alas.emulator_windows import Emulator
                if (emulator and emulator.type == Emulator.MuMuPlayer12
                        and 'MuMuPlayerGlobal' not in str(emulator.path)):
                    methods.append('ipc')
            except (AttributeError, ImportError):
                pass
        return methods

    def available_interaction_methods(self, device=None):
        """Return valid interaction method identifiers for a selected device."""
        device = device or self.get_preferred_device()
        if not device:
            return []
        kind = device.get('device')
        if kind == 'windows':
            configured = (self.windows_capture_config or {}).get('interaction', [])
            methods = configured if isinstance(configured, list) else [configured]
            return [method_name(item) for item in (methods or ['Pynput']) if item]
        if kind == 'browser':
            return ['BrowserInteraction']
        if kind == 'adb':
            return ['ADBInteraction']
        if kind == 'macos':
            return ['QuartzForegroundInteraction']
        return ['Default Interaction']

    def set_hwnd_name(self, hwnd_name):
        preferred = self.get_preferred_device()
        if preferred.get("hwnd") != hwnd_name:
            preferred['hwnd'] = hwnd_name
            if self.hwnd_window:
                self.hwnd_window.title = hwnd_name
            self.config.save_file()

    def set_capture(self, capture):
        if self.config.get("capture") != capture:
            self.config['capture'] = capture
            self.start()

    def set_interaction(self, interaction):
        interaction_name = interaction.__name__ if isinstance(interaction, type) else interaction
        preferred = self.get_preferred_device() or {}
        is_windows_device = preferred.get('device') == 'windows'

        if is_windows_device:
            require_windows('Windows interaction selection')
            config_interaction = (
                self.windows_capture_config.get('interaction')
                if self.windows_capture_config else None
            )
            if isinstance(interaction, str):
                if isinstance(config_interaction, list):
                    for item in config_interaction:
                        if isinstance(item, type) and item.__name__ == interaction:
                            interaction = item
                            break
                elif (isinstance(config_interaction, type)
                      and config_interaction.__name__ == interaction):
                    interaction = config_interaction

        if self.config.get("interaction") != interaction_name:
            self.config['interaction'] = interaction_name
            if is_windows_device:
                self.win_interaction_class = _windows_interaction_class(interaction)
            self.start()

    def get_hwnd_name(self):
        preferred = self.get_preferred_device()
        return preferred.get('hwnd')

    def ensure_hwnd(self, title, exe, frame_width=0, frame_height=0, player_id=-1, hwnd_class=None, top_hwnd_class=None):
        require_windows('HWND window management')
        if self.hwnd_window is None:
            self.hwnd_window = HwndWindow(self.exit_event, title, exe, frame_width, frame_height, player_id,
                                          hwnd_class, global_config=self.global_config, device_manager=self, top_hwnd_class=top_hwnd_class)
            from ok.device.window_target.windows import WindowsHwndWindowTarget
            self.window_target = WindowsHwndWindowTarget(self.hwnd_window)
        else:
            self.hwnd_window.update_window(title, exe, frame_width, frame_height, player_id, hwnd_class, top_hwnd_class)

    def use_windows_capture(self):
        require_windows('Windows capture provider')
        selected_method = self.config.get('capture')
        valid_methods = self.windows_capture_config.get('capture_method', [])
        if not selected_method or selected_method not in valid_methods:
             if valid_methods:
                 selected_method = valid_methods[0]
        self.capture_method = update_capture_method(self.windows_capture_config, self.capture_method, self.hwnd_window,
                                                    exit_event=self.exit_event, selected_method=selected_method)
        if self.capture_method is None:
            logger.error(f'cant find a usable windows capture')
        else:
            logger.info(f'capture method {type(self.capture_method)}')
            if self.interaction:
                self.interaction.capture = self.capture_method

    def start(self):
        self.handler.post(self.do_start, remove_existing=True, skip_if_running=True)

    def do_start(self, notify=True):
        lock = getattr(self, '_device_lifecycle_lock', None)
        if lock is None:
            return self._do_start_locked(notify)
        with lock:
            exit_event = getattr(self, 'exit_event', None)
            if self._closing or (exit_event is not None and exit_event.is_set()):
                logger.info('skip device start while closing')
                return
            return self._do_start_locked(notify)

    def _do_start_locked(self, notify=True):
        logger.debug(f'do_start')
        preferred = self.get_preferred_device()
        if preferred is None:
            if self.device_dict:
                self.set_preferred_device()
            if notify:
                communicate.adb_devices.emit(True)
            return

        if preferred['device'] == 'windows':
            require_windows('Windows desktop device')
            title = self.windows_capture_config.get('title')
            exe = self.windows_capture_config.get('exe')
            if not exe and not title and preferred.get('real_hwnd'):
                exe = preferred.get('exe')
                
            self.ensure_hwnd(title, exe,
                             hwnd_class=self.windows_capture_config.get('hwnd_class'),
                             top_hwnd_class=self.windows_capture_config.get('top_hwnd_class'))
            self.use_windows_capture()
            if not isinstance(self.interaction, self.win_interaction_class):
                self.interaction = self.win_interaction_class(self.capture_method, self.hwnd_window)
            elif self.interaction:
                self.interaction.capture = self.capture_method
            preferred['connected'] = self.capture_method is not None and self.capture_method.connected()
        elif preferred['device'] == 'macos':
            require_platform('macOS desktop device', (MACOS,))
            from ok.device.capture_methods import ScreenCaptureKitCaptureMethod
            from ok.device.interaction_methods import QuartzForegroundInteraction
            target_available = bool(
                self.window_target is not None and self.window_target.exists())
            if target_available:
                self._ensure_macos_window_services()
                if (
                        not isinstance(
                            self.capture_method, ScreenCaptureKitCaptureMethod)
                        or self.capture_method.target is not self.window_target):
                    if self.capture_method is not None:
                        self.capture_method.close()
                    self.capture_method = ScreenCaptureKitCaptureMethod(
                        self.exit_event,
                        self.window_target,
                        self.permission_service,
                        on_input_invalidated=self._on_macos_capture_input_invalidated,
                    )
                if (
                        not isinstance(self.interaction, QuartzForegroundInteraction)
                        or self.interaction.capture is not self.capture_method
                        or self.interaction.target is not self.window_target):
                    if self.interaction is not None:
                        destroy = getattr(self.interaction, 'on_destroy', None)
                        if callable(destroy):
                            destroy()
                    self.interaction = QuartzForegroundInteraction(
                        self.capture_method,
                        self.window_target,
                        self.permission_service,
                        exit_event=self.exit_event,
                        on_invalidated=self._on_macos_interaction_invalidated,
                    )
                    self.cursor_service = self.interaction.cursor_service
            else:
                self._invalidate_macos_input('selected macOS target is unavailable')
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = None
                self.interaction = None
                self.cursor_service = create_cursor_service()
            preferred['target_bound'] = bool(
                self.window_target is not None and self.window_target.exists())
            preferred['connected'] = bool(
                preferred['target_bound']
                and self.capture_method is not None
                and self.capture_method.connected())
            capture_diagnostics = self.macos_capture_diagnostics()
            capture_state = getattr(capture_diagnostics, 'state', None)
            preferred['capture_state'] = (
                getattr(capture_state, 'value', None) or 'unavailable')
            logger.info(
                'macOS capture/input state: '
                f'{capture_diagnostics}; capabilities={self.capabilities.enabled_names()}')
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
                    emulator = preferred.get('emulator')
                    window_exe = resolve_emulator_window_exe(
                        preferred.get('full_path'), getattr(emulator, 'name', None))
                    self.ensure_hwnd(None, window_exe,
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

        if notify:
            communicate.adb_devices.emit(True)

    def update_resolution_for_hwnd(self):
        if self.hwnd_window is not None and self.hwnd_window.frame_aspect_ratio == 0 and self.adb_capture_config:
            width, height = self.get_resolution()
            logger.debug(f'update resolution for {self.hwnd_window} {width}x{height}')
            self.hwnd_window.update_frame_size(width, height)

    @property
    def device(self):
        if preferred := self.get_preferred_device():
            if preferred.get('device') == 'macos':
                return None
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

    def clear_devices(self):
        logger.info('clear_devices')
        self.device_dict.clear()
        self.config['preferred'] = ''
        self.config['selected_hwnd'] = 0
        self.config['pc_full_path'] = ''
        self._device = None
        self.resolution_dict.clear()

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
        if preferred['device'] == 'macos':
            return bool(
                self.capture_method is not None
                and self.capture_method.connected())
        elif self.device is not None:
            try:
                state = self.shell('echo 1', timeout=3)
                logger.debug(f'device_connected check device state is {state}')
                return state is not None
            except Exception as e:
                logger.error(f'device_connected error occurred, {e}')

    def get_exe_path(self, device):
        path = device.get('full_path')
        if device.get(
                'device') == 'windows' and self.windows_capture_config:
            if not path or path == "none":
                path = None
            if calculate := self.windows_capture_config.get(
                    'calculate_pc_exe_path'):
                calculate_path = path
                if isinstance(calculate, str):
                    path = calculate
                else:
                    try:
                        path = calculate(calculate_path)
                    except Exception as e:
                        logger.error(
                            f'calculate_pc_exe_path failed for caller path {calculate_path}: {e}', e)
                        return None
                logger.info(
                    f'calculate_pc_exe_path caller path {calculate_path}, result {path}')
                if isinstance(path, str) and '://' in path:
                    logger.info(f'path is a url skip checking {path}')
                    return path
            if path and os.path.exists(path):
                return path
            return None
        if not path:
            return None
        elif emulator := device.get('emulator'):
            require_windows('Windows emulator launch')
            from ok.alas.platform_windows import get_emulator_exe
            return get_emulator_exe(emulator)
        else:
            return None

    def adb_check_installed(self, packages):
        installed = self.shell('pm list packages', timeout=30)
        if isinstance(packages, str):
            packages = [packages]
        for package in packages:
            if package in installed:
                return package

    def adb_check_in_front(self, packages):
        if not packages:
            return True
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

    def update_capture(self, config: dict):
        import time
        logger.info(f'update_capture {config}')
        if 'windows' in config:
            require_windows('Windows capture update')
            win_config = config['windows']
            reset_selected_hwnd = any(
                key in win_config for key in ('title', 'exe', 'hwnd_class', 'top_hwnd_class', 'selected_hwnd')
            )
            selected_hwnd = self.config.get('selected_hwnd')
            self.clear_devices()
            if not reset_selected_hwnd:
                self.config['selected_hwnd'] = selected_hwnd
            for key in ('title', 'hwnd_class', 'top_hwnd_class'):
                if key in win_config:
                    self.windows_capture_config[key] = win_config[key]
            if 'exe' in win_config:
                exe_val = win_config['exe']
                self.windows_capture_config['exe'] = [exe_val] if isinstance(exe_val, str) else exe_val
                self.config['selected_exe'] = exe_val if isinstance(exe_val, str) else exe_val[0]
            if 'selected_hwnd' in win_config:
                self.config['selected_hwnd'] = win_config['selected_hwnd']

            imei = self.update_pc_device()
            if not imei:
                raise Exception("Cannot find window")

            pc = self.device_dict.get(imei)
            if not pc or not pc.get('connected'):
                logger.error(f"Cannot find window. PC device data: {pc}, config: {self.windows_capture_config}")
                raise Exception("Cannot find window")

            self.set_preferred_device(imei)

            if 'interaction' in win_config:
                self.set_interaction(win_config['interaction'])
            if 'capture_method' in win_config:
                self.set_capture(win_config['capture_method'])
            elif 'capture' in win_config:
                self.set_capture(win_config['capture'])

            if 'resolution' in win_config:
                resolution = win_config['resolution']
                if getattr(self, 'hwnd_window', None):
                    for _ in range(50):
                        if self.hwnd_window.hwnd:
                            break
                        time.sleep(0.1)
                    if self.hwnd_window.hwnd:
                        logger.info(f'update_capture try_resize_to {resolution}')
                        res = self.hwnd_window.try_resize_to([resolution])
                        if not res:
                            raise Exception(f"Failed to resize window to {resolution}")
            if getattr(self, 'hwnd_window', None):
                self.hwnd_window.do_update_window_size()
                logger.info(f'update_capture window size {self.hwnd_window.width}x{self.hwnd_window.height}')

        elif 'adb' in config:
            adb_config = config['adb']
            self.clear_devices()
            if 'packages' in adb_config:
                self.packages = adb_config['packages']

            self.refresh_phones()
            self.refresh_emulators()

            connected_adb = None
            for device in self.get_devices():
                if device.get('device') == 'adb' and device.get('connected'):
                    connected_adb = device
                    break

            if not connected_adb:
                raise Exception("Cannot find an connected ADB device")

            self.set_preferred_device(connected_adb['imei'])

            if 'interaction' in adb_config:
                self.set_interaction(adb_config['interaction'])
            if 'capture_method' in adb_config:
                self.set_capture(adb_config['capture_method'])
            elif 'capture' in adb_config:
                self.set_capture(adb_config['capture'])

            if self.packages:
                if not self.adb_ensure_in_front():
                    raise Exception("Failed to start app packages")

            if 'resolution' in adb_config:
                resolution = adb_config['resolution']
                current_res = self.get_resolution()
                if current_res[0] != resolution[0] or current_res[1] != resolution[1]:
                    try:
                        self.shell(f"wm size {resolution[0]}x{resolution[1]}")
                        self.resolution_dict.clear() # clear cache
                    except Exception as e:
                        raise Exception(f"Failed to resize ADB to {resolution}: {e}")

        elif 'browser' in config:
            require_windows('Current browser capture provider')
            browser_config = config['browser']
            self.clear_devices()
            if not getattr(self, 'browser_config', None):
                self.browser_config = {}
            self.browser_config.update(browser_config)

            self.update_browser_device()
            bd = self.device_dict.get('browser')
            if not bd:
                 raise Exception("Cannot initialize browser device")

            self.set_preferred_device('browser')
            self.set_capture('browser')

            if 'resolution' in browser_config:
                resolution = browser_config['resolution']
                try:
                    if getattr(self, 'capture_method', None) and hasattr(self.capture_method, 'page'):
                         async def _resize():
                             await self.capture_method.page.set_viewport_size({'width': resolution[0], 'height': resolution[1]})
                         self.capture_method.run_in_loop(_resize())
                except Exception as e:
                    raise Exception(f"Failed to resize browser to {resolution}: {e}")

    def ensure_capture(self, config: dict):
        import time
        logger.info(f'ensure_capture {config}')
        self.clear_devices()
        if 'windows' in config:
            require_windows('Windows capture ensure')
            win_config = config['windows']
            for key in ('title', 'hwnd_class', 'top_hwnd_class'):
                if key in win_config:
                    self.windows_capture_config[key] = win_config[key]
                else:
                    self.windows_capture_config.pop(key, None)
            if 'exe' in win_config:
                exe_val = win_config['exe']
                self.windows_capture_config['exe'] = [exe_val] if isinstance(exe_val, str) else exe_val
                self.config['selected_exe'] = exe_val if isinstance(exe_val, str) else exe_val[0]
                
            self.config['selected_hwnd'] = 0
                
            imei = self.update_pc_device()
            if not imei:
                raise Exception("Cannot find window")
            
            pc = self.device_dict.get(imei)
            if not pc or not pc.get('connected'):
                logger.error(f"Cannot find window. PC device data: {pc}, config: {self.windows_capture_config}")
                raise Exception("Cannot find window")
            
            self.set_preferred_device(imei)
            
            if 'interaction' in win_config:
                self.set_interaction(win_config['interaction'])
            if 'capture_method' in win_config:
                self.set_capture(win_config['capture_method'])
            else:
                self.set_capture('windows')
                
            if 'resolution' in win_config:
                resolution = win_config['resolution']
                if getattr(self, 'hwnd_window', None):
                    for _ in range(50):
                        if self.hwnd_window.hwnd:
                            break
                        time.sleep(0.1)
                    if self.hwnd_window.hwnd:
                        logger.info(f'ensure_capture try_resize_to {resolution}')
                        res = self.hwnd_window.try_resize_to([resolution])
                        if not res:
                            raise Exception(f"Failed to resize window to {resolution}")
            if getattr(self, 'hwnd_window', None):
                self.hwnd_window.do_update_window_size()
                logger.info(f'ensure_capture window size {self.hwnd_window.width}x{self.hwnd_window.height}')

        elif 'adb' in config:
            adb_config = config['adb']
            if 'packages' in adb_config:
                self.packages = adb_config['packages']
                
            self.refresh_phones()
            self.refresh_emulators()
            
            connected_adb = None
            for device in self.get_devices():
                if device.get('device') == 'adb' and device.get('connected'):
                    connected_adb = device
                    break
                    
            if not connected_adb:
                raise Exception("Cannot find an connected ADB device")
                
            self.set_preferred_device(connected_adb['imei'])
            
            if 'interaction' in adb_config:
                self.set_interaction(adb_config['interaction'])
            if 'capture_method' in adb_config:
                self.set_capture(adb_config['capture_method'])
            elif self.config.get('capture') not in ('adb', 'ipc'):
                self.set_capture('adb')
                
            if self.packages:
                if not self.adb_ensure_in_front():
                    raise Exception("Failed to start app packages")
                    
            if 'resolution' in adb_config:
                resolution = adb_config['resolution']
                current_res = self.get_resolution()
                if current_res[0] != resolution[0] or current_res[1] != resolution[1]:
                    try:
                        self.shell(f"wm size {resolution[0]}x{resolution[1]}")
                        self.resolution_dict.clear() # clear cache
                    except Exception as e:
                        raise Exception(f"Failed to resize ADB to {resolution}: {e}")

        elif 'browser' in config:
            require_windows('Current browser capture provider')
            browser_config = config['browser']
            if not getattr(self, 'browser_config', None):
                self.browser_config = {}
            self.browser_config.update(browser_config)
            
            self.update_browser_device()
            bd = self.device_dict.get('browser')
            if not bd:
                 raise Exception("Cannot initialize browser device")
            
            self.set_preferred_device('browser')
            self.set_capture('browser')
            
            if 'resolution' in browser_config:
                resolution = browser_config['resolution']
                try:
                    if getattr(self, 'capture_method', None) and hasattr(self.capture_method, 'page'):
                         async def _resize():
                             await self.capture_method.page.set_viewport_size({'width': resolution[0], 'height': resolution[1]})
                         self.capture_method.run_in_loop(_resize())
                except Exception as e:
                    raise Exception(f"Failed to resize browser to {resolution}: {e}")
