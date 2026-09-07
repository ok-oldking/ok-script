import time
import threading
import math

from ok import Handler, og
from ok import Logger
from ok.device.capture_methods.base import BaseWindowsCaptureMethod
from ok.core.events import communicate
from ok.core.notifications import alert_error, alert_info
from ok.util.process import is_admin, execute, WINDOWS_START_METHOD_START

logger = Logger.get_logger(__name__)


class StartController:
    STARTED_WINDOW_MIN_SIZE = (100, 100)
    STARTED_WINDOW_STABLE_SECONDS = 2
    STARTED_WINDOW_POLL_INTERVAL = 0.2

    def __init__(self, app_config, exit_event):
        self.config = app_config
        self.exit_event = exit_event
        self.handler = Handler(exit_event, __name__)
        self.start_timeout = app_config.get('start_timeout', 60)
        windows_config = app_config.get('windows') or {}
        self.start_exe = windows_config.get('start_exe', True)
        self.start_method = windows_config.get('start_method', WINDOWS_START_METHOD_START)
        self.starting = False
        self._start_cancel = threading.Event()
        self._handoff_lock = threading.Lock()
        self._handoff_pending = False

    def tr(self, message):
        app = getattr(og, "app", None)
        return app.tr(message) if app is not None else message

    @staticmethod
    def _mark_task_enabled(task):
        task.ensure_device_capabilities()
        if not task.enabled:
            task._enabled = True
            task.info_clear()
            task.executor.enqueue_onetime_task(task)
            logger.info(f"enabled task {task}")
        communicate.task.emit(task)

    def start(self, task=None, exit_after=False):
        if self.starting:
            return False
        self._start_cancel = threading.Event()
        self._handoff_pending = True
        self.starting = True
        try:
            self.handler.post(lambda: self.do_start(task, exit_after))
        except Exception:
            self.starting = False
            raise

    def cancel_start(self):
        # Cancellation belongs to the foreground handoff, not a running task.
        with self._handoff_lock:
            if self._handoff_pending:
                self._start_cancel.set()
                return True
        return False

    def _wait_for_macos_foreground(self):
        target = og.device_manager.window_target
        if target is None or not target.process_id:
            raise RuntimeError('请先绑定游戏主窗口 / Bind the game window first')
        process_id = target.process_id
        deadline = time.monotonic() + min(self.start_timeout, 30)
        last_seconds = None
        while not self.exit_event.is_set() and not self._start_cancel.is_set():
            remaining = max(0, math.ceil(deadline - time.monotonic()))
            if remaining != last_seconds:
                self._publish_macos_status('foreground', remaining)
                last_seconds = remaining
            # Observe only: do not invalidate a minimized target while the user
            # is switching apps. The normal startup checks the actual binding,
            # capture, geometry and fresh frame again after this wait.
            if target.discovery.system.frontmost_process_id() == process_id:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError('等待游戏前台超时 / Timed out waiting for game foreground')
            self._start_cancel.wait(.1)
        raise RuntimeError('启动已取消 / Start cancelled')

    def do_start(self, task=None, exit_after=False):
        self.starting = True
        self._prepared_macos_capture = None
        previous = []
        macos = False
        try:
            device = og.device_manager.get_preferred_device() if og.device_manager is not None else None
            macos = isinstance(device, dict) and device.get('device') == 'macos'
            if macos:
                if not hasattr(self, '_start_cancel'):
                    self._start_cancel = threading.Event()
                self._connect_macos_for_task(task)
                self._prepared_macos_capture = og.device_manager.capture_method
                self._wait_for_macos_foreground()
                self._wait_for_macos_preparation(task)
                with self._handoff_lock:
                    self._check_start_cancelled()
                    self._handoff_pending = False
                communicate.starting_emulator.emit(True, None, 0)
                # Snapshot immediately before mutation, not before user handoff.
                previous = [(item, item.enabled, getattr(item, 'exit_after_task', False),
                             getattr(item, 'paused', False))
                            for item in og.executor.get_all_tasks()]
            result = self._do_start(task, exit_after)
            if macos and not result:
                self._rollback_start(previous)
            return result
        except Exception as error:
            if not macos:
                raise
            self._rollback_start(previous)
            logger.error(f'macOS start failed: {error}')
            communicate.starting_emulator.emit(True, str(error), 0)
            return False
        finally:
            self._prepared_macos_capture = None
            if macos:
                self._publish_macos_status('done', 0)
            self.starting = False
            self._handoff_pending = False

    def _publish_macos_status(self, phase, seconds):
        communicate.macos_start_status.emit(self._start_cancel, phase, seconds)

    def _connect_macos_for_task(self, task):
        # Clicking a task is also an explicit connection attempt. Discovery still
        # requires a unique credible window; input is not armed by capture setup.
        self._check_start_cancelled()
        og.device_manager.prepare_macos_capture(timeout=8.0)
        communicate.adb_devices.emit(True)
        self._check_start_cancelled()
        if isinstance(task, int):
            task = og.executor.onetime_tasks[task]
        if task is not None:
            task.ensure_device_capabilities()

    def _wait_for_macos_preparation(self, task):
        if isinstance(task, int):
            task = og.executor.onetime_tasks[task]
        seconds = getattr(task, 'config', {}).get('Preparation Seconds', 8)
        if type(seconds) is not int or not 0 <= seconds <= 300:
            raise RuntimeError('准备时间须为 0–300 的整数秒 / Invalid preparation delay')
        target = og.device_manager.window_target
        process_id = target.process_id
        deadline = time.monotonic() + seconds
        logger.info(f'MAC_START_PREPARATION: seconds={seconds}')
        last_seconds = None
        while True:
            self._check_start_cancelled()
            if (og.device_manager.window_target is not target or not process_id
                    or target.discovery.system.frontmost_process_id() != process_id):
                raise RuntimeError('准备期间游戏失去前台，启动已取消 / Preparation cancelled: game lost foreground')
            remaining = deadline - time.monotonic()
            display_seconds = max(0, math.ceil(remaining))
            if display_seconds != last_seconds:
                self._publish_macos_status('preparation', display_seconds)
                last_seconds = display_seconds
            if remaining <= 0:
                return
            self._start_cancel.wait(min(.1, remaining))

    @staticmethod
    def _rollback_start(previous):
        # Undo only this attempt's newly enabled tasks, never the user's existing
        # enabled/queued work or persisted Trigger preferences.
        for task, enabled, exit_after, paused in previous:
            if not enabled and task.enabled:
                task._enabled = False
                task.executor.remove_onetime_task(task)
            task.exit_after_task = exit_after
            task._paused = paused
            communicate.task.emit(task)

    def _do_start(self, task=None, exit_after=False):
        device = og.device_manager.get_preferred_device() if og.device_manager is not None else None
        if not (isinstance(device, dict) and device.get('device') == 'macos'):
            communicate.starting_emulator.emit(False, None, self.start_timeout)
        tasks_to_enable = []
        try:
            if isinstance(task, int):
                task = og.executor.onetime_tasks[task]
                logger.info(f"enable param task {task}")

            if task and task.enabled and task.paused:
                self._check_start_cancelled()
                logger.info(f"resume paused task {task}")
                if exit_after:
                    task.exit_after_task = True
                    communicate.task.emit(task)
                task.unpause()
                communicate.starting_emulator.emit(True, None, 0)
                return True

            if task and og.executor.current_task and og.executor.current_task != task:
                self._check_start_cancelled()
                logger.info(f"queue task while another task is running {task}")
                if exit_after:
                    task.exit_after_task = True
                self._mark_task_enabled(task)
                if og.executor.paused:
                    og.executor.start()
                communicate.starting_emulator.emit(True, None, 0)
                return True
        except Exception as e:
            logger.error(f'do_start resume exception: {e}', e)
            communicate.starting_emulator.emit(True, self.tr(f'Start failed: {e}'), 0)
            return False

        try:
            logger.info(f'do_start: call do_refresh {self.start_exe}')
            og.device_manager.do_refresh(True)
        except Exception as e:
            logger.error(f'do_start do_refresh exception: {e}', e)
            communicate.starting_emulator.emit(True, self.tr(str(e)), 0)
            return False

        try:
            if self.start_exe:
                if not self.start_device(initial_refresh_done=True):
                    return False
            else:
                logger.info('windows.start_exe is False, skip start_device')
            self.check_gpu_driver_post_processing()

            def add_task_to_enable(enable_task):
                if enable_task and enable_task not in tasks_to_enable:
                    tasks_to_enable.append(enable_task)

            for start_task in og.executor.get_all_tasks():
                if getattr(start_task, 'enable_after_start', False):
                    logger.info(f"enable_after_start task {start_task}")
                    add_task_to_enable(start_task)

            if task:
                add_task_to_enable(task)
                if exit_after:
                    task.exit_after_task = True

            for task in tasks_to_enable:
                self._check_start_cancelled()
                self._mark_task_enabled(task)

            self._check_start_cancelled()
            og.executor.start()
            communicate.starting_emulator.emit(True, None, 0)
            return True
        except Exception as e:
            logger.error(f'do_start exception: {e}', e)
            communicate.starting_emulator.emit(True, self.tr(f'Start failed: {e}'), 0)
            return False

    def _check_start_cancelled(self):
        cancel = getattr(self, '_start_cancel', None)
        if self.exit_event.is_set() or (cancel is not None and cancel.is_set()):
            raise RuntimeError('启动已取消 / Start cancelled')

    def _wait_until_device_ready(self, refresh_first=True):
        wait_until = time.time() + self.start_timeout
        first_check = True
        while not self.exit_event.is_set():
            if refresh_first or not first_check:
                og.device_manager.do_refresh(True)
            first_check = False
            error = self.check_device_error()
            if error is None:
                return True
            logger.error(f'waiting for game to start error {error}')
            remaining_time = wait_until - time.time()
            if remaining_time <= 0:
                communicate.starting_emulator.emit(True, self.tr('Start game timeout!'), 0)
                return False
            device = og.device_manager.get_preferred_device()
            if not (device and device.get('device') == 'macos'):
                communicate.starting_emulator.emit(False, None, int(remaining_time))
            time.sleep(2)
        return False

    def _wait_until_started_window_stable(self):
        wait_until = time.monotonic() + self.start_timeout
        stable_size = None
        stable_since = None
        min_width, min_height = self.STARTED_WINDOW_MIN_SIZE

        while not self.exit_event.is_set():
            hwnd_window = getattr(og.device_manager, 'hwnd_window', None)
            if hwnd_window is not None:
                hwnd_window.do_update_window_size()
                size = (hwnd_window.width, hwnd_window.height)
                if hwnd_window.hwnd and size[0] >= min_width and size[1] >= min_height:
                    now = time.monotonic()
                    if size != stable_size:
                        logger.info(f'waiting for started window to stabilize, current size {size[0]}x{size[1]}')
                        stable_size = size
                        stable_since = now
                    elif now - stable_since >= self.STARTED_WINDOW_STABLE_SECONDS:
                        logger.info(f'started window size stable for {self.STARTED_WINDOW_STABLE_SECONDS}s: {size[0]}x{size[1]}')
                        return True
                else:
                    stable_size = None
                    stable_since = None

            remaining_time = wait_until - time.monotonic()
            if remaining_time <= 0:
                communicate.starting_emulator.emit(True, self.tr('Start game timeout!'), 0)
                return False
            time.sleep(self.STARTED_WINDOW_POLL_INTERVAL)
        return False

    def start_device(self, initial_refresh_done=False):
        device = og.device_manager.get_preferred_device()
        logger.info(f'start_device: {device}')

        if device and device['device'] == 'macos':
            # do_start already prepared this provider before user handoff.
            # Direct callers (or provider replacement) still use the same owner.
            prepared = getattr(self, '_prepared_macos_capture', None)
            if prepared is None or prepared is not og.device_manager.capture_method:
                og.device_manager.prepare_macos_capture(timeout=8.0)
            return True

        if device and not device['connected']:
            if device['device'] == "windows" and not is_admin():
                communicate.starting_emulator.emit(True,
                                                   "PC version requires admin privileges, Please restart this app with admin privileges!",
                                                   0)
                communicate.restart_admin.emit()
                return False
            path = og.device_manager.get_exe_path(device)
            if path:
                logger.info(f"starting game {path}")
                args = None
                dx11_config = og.global_config.get_config('Launch with DX11')
                if dx11_config and dx11_config.get('Launch with DX11'):
                    args = "-dx11 -d3d11 -force-d3d11"
                if not execute(path, arguments=args, start_method=self.start_method):
                    communicate.starting_emulator.emit(True, self.tr("Start game failed, please start game first"), 0)
                    return False
                if device['device'] == "windows" and not self._wait_until_started_window_stable():
                    return False
                if not self._wait_until_device_ready():
                    return False
            else:
                communicate.starting_emulator.emit(True,
                                                   self.tr('Game path does not exist, Please open game manually!'), 0)
                return False
        elif not self._wait_until_device_ready(refresh_first=not initial_refresh_done):
            return False
        communicate.starting_emulator.emit(True, None, 0)
        return True

    def check_gpu_driver_post_processing(self):
        try:
            from ok.util.gpu_driver_settings import get_enabled_gpu_driver_post_processing
            device_manager = getattr(og, 'device_manager', None)
            hwnd_window = getattr(device_manager, 'hwnd_window', None)
            target_exe_path = getattr(hwnd_window, 'exe_full_path', None) if hwnd_window else None
            target_hwnd = getattr(hwnd_window, 'hwnd', None) if hwnd_window else None
            if not target_exe_path and device_manager:
                device = device_manager.get_preferred_device()
                target_exe_path = device.get('full_path') if device else None
            enabled_features = get_enabled_gpu_driver_post_processing(target_exe_path, target_hwnd)
        except Exception as e:
            logger.error(f'check_gpu_driver_post_processing exception: {e}', e)
            return

        if enabled_features:
            warning_lines = [
                self.tr('{vendor} {feature} is enabled and may cause malfunctions!').format(
                    vendor=feature.vendor,
                    feature=feature.feature,
                )
                for feature in enabled_features
            ]
            logger.warning('\n'.join(warning_lines))
            communicate.notification.emit(
                '\n'.join(warning_lines),
                self.tr('GPU Driver Warning'),
                True,
                True,
                'start',
                None,
                None,
            )

    def check_resolution(self):
        error = None
        supported_resolution = self.config.get(
            'supported_resolution', {})
        supported_ratio = supported_resolution.get('ratio')
        min_size = supported_resolution.get('min_size')
        resize_to = supported_resolution.get('resize_to')
        force_ratio = supported_resolution.get('force_ratio')
        capture_method = og.device_manager.capture_method
        is_windows_capture = isinstance(capture_method, BaseWindowsCaptureMethod)
        auto_resize_enabled = (
            not is_windows_capture
            or og.global_config.get_config('Basic Options').get('Auto Resize Game Window', True)
        )
        allowed_ratios = supported_resolution.get('allowed_ratios')
        if allowed_ratios is None:
            supported, resolution = og.executor.check_frame_and_resolution(supported_ratio, min_size)
        else:
            supported, resolution = og.executor.check_frame_and_resolution(
                supported_ratio, min_size, allowed_ratios=allowed_ratios)
        if not supported:
            resize_success = False
            if resize_to and is_windows_capture and auto_resize_enabled:
                resize_success = capture_method.hwnd_window.try_resize_to(resize_to)
            if not resize_success:
                error = self.tr(
                    'Resolution {resolution} check failed, some tasks might not work correctly!').format(
                    resolution=resolution)
                if supported_ratio:
                    error += self.tr(', the supported ratio is {supported_ratio}').format(
                        supported_ratio=' / '.join(allowed_ratios) if allowed_ratios is not None else supported_ratio)
                if min_size:
                    error += self.tr(', the supported min resolution is {min_size}').format(
                        min_size=f'{min_size[0]}x{min_size[1]}')
        if error and not auto_resize_enabled:
            logger.info(f'check_resolution: {error}')
            alert_info(error)
            return None
        if force_ratio:
            return error
        elif error:
            alert_error(error, tray=True)

    def check_device_error(self):
        try:
            device = og.device_manager.get_preferred_device()
            if not device:
                return self.tr('No game selected!')
            error_msg = self.tr("{} is not connected, please select the game window.").format(
                device['nick'])
            logger.info(f'test check_device_error msg: {error_msg}')
            if og.device_manager.capture_method is None:
                return self.tr("Selected capture method is not supported by the game or your system!")
            if not og.device_manager.device_connected():
                logger.error(f'Emulator is not connected {og.device_manager.device}')
                return self.tr("Emulator is not connected, start the emulator first!")
            if (device and device.get('device') == 'browser'
                    and not og.device_manager.capture_method.connected()):
                logger.info(f"start browser")
                og.device_manager.capture_method.start_browser()
            if not og.device_manager.capture_method.connected():
                logger.error(f'Game window is not connected {og.device_manager.capture_method}')
                return error_msg
            if isinstance(og.device_manager.capture_method, BaseWindowsCaptureMethod):

                if not og.device_manager.capture_method.hwnd_window.pos_valid:
                    hwnd_window = og.device_manager.capture_method.hwnd_window
                    if hwnd_window.hwnd and hwnd_window.window_width > 0 and hwnd_window.window_height > 0:
                        from ok.util.window import resize_window
                        logger.info(
                            f"Window pos invalid, trying to center window with size {hwnd_window.window_width}x{hwnd_window.window_height}")
                        resize_window(hwnd_window.hwnd, hwnd_window.window_width, hwnd_window.window_height)
                        hwnd_window.do_update_window_size()
                    if not og.device_manager.capture_method.hwnd_window.pos_valid:
                        return self.tr(
                            f'Window is minimized or out of screen, and don\'t use full-screen exclusive mode!')
            frame = self.try_capture_a_frame()
            if frame is None:
                logger.error(f'check_device_error: try_capture_a_frame returned None')
                return self.tr('Capture failed, please check game window')
            logger.info(f'check_device_error: capturing frame {frame.shape[1], frame.shape[0]}')
            if og.executor.feature_set is not None:
                logger.info(f'check_device_error: checking feature_set size')
                if not og.executor.feature_set.check_size(frame):
                    logger.error(f'check_device_error: feature_set check_size failed')
                    return self.tr(
                        'Image resource load failed, please try install again.(Don\'t put the app in Downloads folder)')
            else:
                logger.info(f'check_device_error: feature_set is None')

            logger.info(f'check_device_error: checking resolution')
            resolution_error = self.check_resolution()
            if resolution_error:
                logger.error(f'check_device_error: resolution_error: {resolution_error}')
                return resolution_error

            if device and device['device'] == "adb" and self.config.get('adb'):
                started = og.device_manager.adb_ensure_in_front()
                if not started:
                    return self.tr("Can't start game, make sure the game is installed")
        except FileNotFoundError as e:
            raise e
        except Exception as e:
            logger.error(f'check_device_error exception: {str(e)}', e)
            return self.tr(str(e))

    @staticmethod
    def try_capture_a_frame():
        start = time.time()
        while True:
            frame = og.device_manager.capture_method.get_frame()
            if frame is not None:
                return frame
            logger.info(f'try_capture_a_frame: frame is None, retrying...')
            if time.time() - start > 5:
                logger.error(f'time out try_capture_a_frame')
                return None
            time.sleep(0.1)
