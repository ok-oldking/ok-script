# __init__.py
import hashlib
import importlib
import logging
import os
import platform
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

# Fix for PySide6 KeyError: 'PATH'
if "PATH" not in os.environ:
    os.environ["PATH"] = ""

from ok.util.handler import Handler, ExitEvent
from ok.util.logger import Logger
from ok.util.file import get_path_relative_to_exe
os.environ["PYTHONIOENCODING"] = "utf-8"

if TYPE_CHECKING:
    from ok.device.DeviceManager import DeviceManager
    from ok.device.capture import (
        ADBCaptureMethod,
        BaseCaptureMethod,
        BitBltCaptureMethod,
        BrowserCaptureMethod,
        DesktopDuplicationCaptureMethod,
        ForegroundBitBltCaptureMethod,
        ImageCaptureMethod,
        NemuIpcCaptureMethod,
        WindowsGraphicsCaptureMethod,
    )
    from ok.device.interaction import (
        BaseInteraction,
        BrowserInteraction,
        DoNothingInteraction,
        ForegroundPostMessageInteraction,
        GenshinInteraction,
        PostMessageInteraction,
        PyDirectInteraction,
    )
    from ok.feature.Box import (
        Box,
        average_width,
        crop_image,
        find_box_by_name,
        find_boxes_by_name,
        find_boxes_within_boundary,
        find_highest_confidence_box,
        get_bounding_box,
        relative_box,
        sort_boxes,
    )
    from ok.feature.Feature import Feature
    from ok.feature.FeatureSet import FeatureSet
    from ok.gui.Communicate import communicate
    from ok.gui.MainWindow import MainWindow
    from ok.task.DiagnosisTask import DiagnosisTask
    from ok.task.TaskExecutor import TaskExecutor
    from ok.task.exceptions import (
        CannotFindException,
        CaptureException,
        FinishedException,
        TaskDisabledException,
        WaitFailedException,
    )
    from ok.task.task import BaseTask, FindFeature, OCR, TriggerTask
    from ok.util.Analytics import Analytics
    from ok.util.GlobalConfig import GlobalConfig, register_app_launcher_options, register_basic_options
    from ok.util.clazz import init_class_by_name
    from ok.util.collection import safe_get
    from ok.util.color import (
        calculate_color_percentage,
        color_range_to_bound,
        find_color_rectangles,
        get_mask_in_color_range,
        is_pure_black,
        mask_white,
    )
    from ok.util.config import Config, ConfigOption
    from ok.util.file import install_path_isascii
    from ok.util.logger import config_logger
    from ok.util.process import (
        WINDOWS_START_METHOD_START,
        check_mutex,
        get_first_gpu_free_memory_mib,
        parse_arguments_to_map,
    )
    from ok.util.window import windows_graphics_available

_LAZY_IMPORTS = {
    'communicate': ('ok.gui.Communicate', 'communicate'),
    'MainWindow': ('ok.gui.MainWindow', 'MainWindow'),
    'TaskExecutor': ('ok.task.TaskExecutor', 'TaskExecutor'),
    'DeviceManager': ('ok.device.DeviceManager', 'DeviceManager'),
    'FeatureSet': ('ok.feature.FeatureSet', 'FeatureSet'),
    'Analytics': ('ok.util.Analytics', 'Analytics'),
    'GlobalConfig': ('ok.util.GlobalConfig', 'GlobalConfig'),
    'register_app_launcher_options': ('ok.util.GlobalConfig', 'register_app_launcher_options'),
    'register_basic_options': ('ok.util.GlobalConfig', 'register_basic_options'),
    'Config': ('ok.util.config', 'Config'),
    'ConfigOption': ('ok.util.config', 'ConfigOption'),
    'init_class_by_name': ('ok.util.clazz', 'init_class_by_name'),
    'config_logger': ('ok.util.logger', 'config_logger'),
    'check_mutex': ('ok.util.process', 'check_mutex'),
    'get_first_gpu_free_memory_mib': ('ok.util.process', 'get_first_gpu_free_memory_mib'),
    'parse_arguments_to_map': ('ok.util.process', 'parse_arguments_to_map'),
    'WINDOWS_START_METHOD_START': ('ok.util.process', 'WINDOWS_START_METHOD_START'),
    'install_path_isascii': ('ok.util.file', 'install_path_isascii'),
    'windows_graphics_available': ('ok.util.window', 'windows_graphics_available'),
    'DoNothingInteraction': ('ok.device.interaction', 'DoNothingInteraction'),
    'BaseInteraction': ('ok.device.interaction', 'BaseInteraction'),
    'BrowserInteraction': ('ok.device.interaction', 'BrowserInteraction'),
    'PostMessageInteraction': ('ok.device.interaction', 'PostMessageInteraction'),
    'GenshinInteraction': ('ok.device.interaction', 'GenshinInteraction'),
    'ForegroundPostMessageInteraction': ('ok.device.interaction', 'ForegroundPostMessageInteraction'),
    'PyDirectInteraction': ('ok.device.interaction', 'PyDirectInteraction'),
    'ImageCaptureMethod': ('ok.device.capture', 'ImageCaptureMethod'),
    'BaseCaptureMethod': ('ok.device.capture', 'BaseCaptureMethod'),
    'BrowserCaptureMethod': ('ok.device.capture', 'BrowserCaptureMethod'),
    'ADBCaptureMethod': ('ok.device.capture', 'ADBCaptureMethod'),
    'WindowsGraphicsCaptureMethod': ('ok.device.capture', 'WindowsGraphicsCaptureMethod'),
    'BitBltCaptureMethod': ('ok.device.capture', 'BitBltCaptureMethod'),
    'NemuIpcCaptureMethod': ('ok.device.capture', 'NemuIpcCaptureMethod'),
    'DesktopDuplicationCaptureMethod': ('ok.device.capture', 'DesktopDuplicationCaptureMethod'),
    'ForegroundBitBltCaptureMethod': ('ok.device.capture', 'ForegroundBitBltCaptureMethod'),
    'DiagnosisTask': ('ok.task.DiagnosisTask', 'DiagnosisTask'),
    'BaseTask': ('ok.task.task', 'BaseTask'),
    'TriggerTask': ('ok.task.task', 'TriggerTask'),
    'FindFeature': ('ok.task.task', 'FindFeature'),
    'OCR': ('ok.task.task', 'OCR'),
    'Feature': ('ok.feature.Feature', 'Feature'),
    'Box': ('ok.feature.Box', 'Box'),
    'find_boxes_by_name': ('ok.feature.Box', 'find_boxes_by_name'),
    'relative_box': ('ok.feature.Box', 'relative_box'),
    'crop_image': ('ok.feature.Box', 'crop_image'),
    'average_width': ('ok.feature.Box', 'average_width'),
    'find_boxes_within_boundary': ('ok.feature.Box', 'find_boxes_within_boundary'),
    'get_bounding_box': ('ok.feature.Box', 'get_bounding_box'),
    'find_box_by_name': ('ok.feature.Box', 'find_box_by_name'),
    'find_highest_confidence_box': ('ok.feature.Box', 'find_highest_confidence_box'),
    'sort_boxes': ('ok.feature.Box', 'sort_boxes'),
    'CannotFindException': ('ok.task.exceptions', 'CannotFindException'),
    'TaskDisabledException': ('ok.task.exceptions', 'TaskDisabledException'),
    'FinishedException': ('ok.task.exceptions', 'FinishedException'),
    'WaitFailedException': ('ok.task.exceptions', 'WaitFailedException'),
    'CaptureException': ('ok.task.exceptions', 'CaptureException'),
    'safe_get': ('ok.util.collection', 'safe_get'),
    'find_color_rectangles': ('ok.util.color', 'find_color_rectangles'),
    'mask_white': ('ok.util.color', 'mask_white'),
    'color_range_to_bound': ('ok.util.color', 'color_range_to_bound'),
    'calculate_color_percentage': ('ok.util.color', 'calculate_color_percentage'),
    'get_mask_in_color_range': ('ok.util.color', 'get_mask_in_color_range'),
    'is_pure_black': ('ok.util.color', 'is_pure_black'),
}

__all__ = [
    'App',
    'BaseScene',
    'ExitEvent',
    'Handler',
    'HeadlessApp',
    'Logger',
    'OK',
    'OkGlobals',
    'Response',
    'og',
    'run_task',
    *_LAZY_IMPORTS,
]


def __getattr__(name):
    target = _LAZY_IMPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def _resolve(name):
    if name in globals():
        return globals()[name]
    return __getattr__(name)

logger = Logger.get_logger("ok")


class CommunicateHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        from ok.gui.Communicate import communicate
        self.communicate = communicate

    def emit(self, record):
        log_message = self.format(record)
        self.communicate.log.emit(record.levelno, log_message)


class App:
    def __init__(self, config, task_executor,
                 exit_event=None):
        from PySide6.QtGui import QIcon
        from ok.gui.Communicate import communicate
        from ok.util.clazz import init_class_by_name
        from ok.util.config import Config

        super().__init__()
        og.exit_event = exit_event
        og.handler = Handler(exit_event, 'global')
        self.config = config
        self.auth_config = None
        self.global_config = task_executor.global_config if task_executor else None
        from ok.gui.util.app import init_app_config
        self.app, self.locale = init_app_config()
        self.ok_config = Config('_ok', {'window_x': -1, 'window_y': -1, 'window_width': -1, 'window_height': -1,
                                        'window_maximized': False, 'navigation_expanded': True,
                                        'use_overlay': False, 'show_overlay_logs': True})
        communicate.quit.connect(self.quit)

        self.about = self.config.get('about')
        self.title = self.config.get('gui_title')
        self.app.setApplicationName(self.title)
        self.app.setApplicationDisplayName(self.title)
        self.version = self.config.get('version')
        self.app.setApplicationVersion(self.version)
        self.debug = self.config.get('debug', False)
        logger.debug(f'locale name {self.locale.name()}')

        self.loading_window = None
        self.overlay_window = None
        self.main_window = None
        self.exit_event = exit_event
        self.icon = QIcon(get_path_relative_to_exe(config.get('gui_icon')) or ":/icon/icon.ico")

        from ok.gui.StartController import StartController
        self.start_controller = StartController(self.config, exit_event)
        if self.config.get('debug'):
            self.to_translate = set()
        else:
            self.to_translate = None
            
        self.po_translation = None
        if not config.get('window_size'):
            logger.info(f'no config.window_size was set use default')
            config['window_size'] = {
                'width': 1000,
                'height': 800,
                'min_width': 600,
                'min_height': 450,
            }
        og.app = self
        og.executor = task_executor
        if task_executor:
            og.device_manager = task_executor.device_manager

        if my_app := self.config.get('my_app'):
            og.my_app = init_class_by_name(my_app[0], my_app[1], exit_event)
            if not hasattr(og.my_app, 'get_overlay_view'):
                og.my_app.get_overlay_view = self.get_overlay_view

        if self.config.get('analytics'):
            from ok.util.Analytics import Analytics
            self.fire_base_analytics = Analytics(self.config, self.exit_event, og.handler, og.device_manager)
        logger.debug('init app end')

    def quit(self):
        self.exit_event.set()
        from PySide6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(self.app, "quit", Qt.QueuedConnection)

    def tr(self, key):
        from PySide6.QtCore import QCoreApplication

        if not key:
            return key
        if ok_tr := QCoreApplication.translate("app", key):
            if ok_tr != key:
                return ok_tr
        if self.to_translate is not None:
            self.to_translate.add(key)
        if self.po_translation is None:
            locale_name = self.locale.name()
            try:
                from ok.gui.i18n.GettextTranslator import get_translations
                self.po_translation = get_translations(locale_name)
                self.po_translation.install()
                logger.info(f'translation installed for {locale_name}')
            except:
                logger.error(f'install translations error for {locale_name}')
                self.po_translation = "Failed"
        if self.po_translation != 'Failed':
            translated = self.po_translation.gettext(key)
            return translated or key
        else:
            return key

    def gen_tr_po_files(self):
        folder = ""
        from ok.gui.common.config import Language
        for locale in Language:
            from ok.gui.i18n.GettextTranslator import update_po_file
            folder = update_po_file(self.to_translate, locale.value.name())
        return folder

    def show_message_window(self, title, message):
        from ok.gui.MessageWindow import MessageWindow
        message_window = MessageWindow(self.icon, title, message, exit_event=self.exit_event)
        message_window.show()

    def show_already_running_error(self):
        from PySide6.QtCore import QCoreApplication

        title = QCoreApplication.translate("app", 'Error')
        content = QCoreApplication.translate("app",
                                             "Another instance is already running")
        self.show_message_window(title, content)

    def show_path_ascii_error(self, path):
        from PySide6.QtCore import QCoreApplication

        title = QCoreApplication.translate("app", 'Error')
        content = QCoreApplication.translate("app",
                                             "Install dir {path} must be an English path, move to another path.").format(
            path=path)
        self.show_message_window(title, content)

    def update_overlay(self, visible, x, y, window_width, window_height, width, height, scaling):
        overlay_view = self.get_overlay_view()
        if overlay_view:
            overlay_view.update_overlay(visible, x, y, window_width, window_height, width, height, scaling)

    def get_overlay_view(self):
        """Return the overlay widget exposed to tasks, custom tabs, and my_app."""
        if self.overlay_window is None:
            from ok.gui.Communicate import communicate
            from ok.gui.overlay.OverlayWindow import OverlayWindow
            self.overlay_window = OverlayWindow(og.device_manager.hwnd_window)
            communicate.window.connect(self.overlay_window.update_overlay)
            self.overlay_window.set_boxes_enabled(self.ok_config.get('use_overlay', False))
        return self.overlay_window

    def show_main_window(self):
        self.do_show_main()

    def do_show_main(self):
        from ok.gui.MainWindow import MainWindow

        if self.ok_config.get('use_overlay', False) or callable(self.config.get('blur_area')):
            self.get_overlay_view()

        self.main_window = MainWindow(self, self.config, self.ok_config, self.icon, self.title, self.version,
                                      self.debug,
                                      self.about,
                                      self.exit_event, self.global_config, og.executor, og.handler)
        og.set_dpi_scaling(self.main_window)
        # Set the window title here
        self.main_window.setWindowIcon(self.icon)

        self.main_window.set_window_size(self.config['window_size']['width'], self.config['window_size']['height'],
                                         self.config['window_size']['min_width'],
                                         self.config['window_size']['min_height'])

        og.main_window = self.main_window

        if og.my_app:
            if hasattr(og.my_app, 'on_show_main_window'):
                og.my_app.on_show_main_window(self.main_window)

        self.main_window.show()
        self.main_window.bring_to_front()

        logger.debug(f'show_main_window end')

    def exec(self):
        logger.info('app.exec()')
        import signal
        from PySide6.QtCore import QTimer

        def handle_sigint(signum, frame):
            logger.info("SIGINT received, quitting")
            self.quit()

        signal.signal(signal.SIGINT, handle_sigint)

        self.timer = QTimer()
        self.timer.start(1000)
        self.timer.timeout.connect(lambda: None)

        sys.exit(self.app.exec())


class HeadlessApp:
    """Small app facade for running tasks without creating any UI windows."""

    def __init__(self, config, exit_event=None):
        from ok.gui.Communicate import communicate
        from ok.util.clazz import init_class_by_name

        og.exit_event = exit_event
        og.handler = Handler(exit_event, 'global')
        self.config = config
        self.debug = config.get('debug', False)
        self.headless = True
        self.global_config = og.global_config
        self.icon = None
        self.exit_event = exit_event
        self.po_translation = None
        self.to_translate = None
        communicate.quit.connect(self.quit)

        from ok.gui.common.config import cfg
        self.locale = cfg.get(cfg.language).value
        from ok.gui.StartController import StartController
        self.start_controller = StartController(self.config, exit_event)

        og.app = self
        if my_app := self.config.get('my_app'):
            og.my_app = init_class_by_name(my_app[0], my_app[1], exit_event)
            if not hasattr(og.my_app, 'get_overlay_view'):
                og.my_app.get_overlay_view = self.get_overlay_view
        logger.debug('init headless app end')

    def tr(self, key):
        from PySide6.QtCore import QCoreApplication

        if not key:
            return key
        if ok_tr := QCoreApplication.translate("app", key):
            if ok_tr != key:
                return ok_tr
        if self.po_translation is None:
            locale_name = self.locale.name()
            try:
                from ok.gui.i18n.GettextTranslator import get_translations
                self.po_translation = get_translations(locale_name)
                self.po_translation.install()
                logger.info(f'headless translation installed for {locale_name}')
            except:
                logger.error(f'install headless translations error for {locale_name}')
                self.po_translation = "Failed"
        if self.po_translation != 'Failed':
            translated = self.po_translation.gettext(key)
            return translated or key
        return key

    def quit(self):
        if self.exit_event:
            self.exit_event.set()

    def get_overlay_view(self):
        return None


def get_my_id():
    mac = uuid.getnode()
    value_with_salt = 'mac123:' + str(mac)
    hashed_value = hashlib.md5(value_with_salt.encode()).hexdigest()
    return hashed_value[:8]

def get_my_id_with_cwd():
    mac = uuid.getnode()
    value_with_salt = 'mac123:' + str(mac) + os.getcwd()
    hashed_value = hashlib.md5(value_with_salt.encode()).hexdigest()
    return hashed_value[:8]

k = None


class Response:
    def __init__(self):
        self.code = 0
        self.message = ""
        self.data = None


## OK.py


class OK:
    executor = None
    adb = None
    adb_device = None
    feature_set = None
    hwnd = None
    device_manager = None
    ocr = None
    overlay_window = None
    app = None
    screenshot = None
    exit_event = ExitEvent()
    init_error = None

    def __init__(self, config):
        import pyappify
        from ok.util.config import Config

        check_mutex_fn = _resolve('check_mutex')
        config_logger_fn = _resolve('config_logger')
        global_config_class = _resolve('GlobalConfig')
        register_launcher = _resolve('register_app_launcher_options')
        register_basic = _resolve('register_basic_options')
        parse_arguments = _resolve('parse_arguments_to_map')
        default_start_method = _resolve('WINDOWS_START_METHOD_START')
        wgc_available = _resolve('windows_graphics_available')

        if config.get('check_mutex', True):
            check_mutex_fn()
        og.ok = self
        if pyappify.app_version:
            config['version'] = pyappify.app_version
        if pyappify.app_profile:
            config['profile'] = pyappify.app_profile
        og.config = config
        self.config = config
        config["config_folder"] = config.get("config_folder") or 'configs'
        Config.config_folder = config["config_folder"]
        config['debug'] = config.get("debug", False)
        self.debug = config['debug']
        config_logger_fn(self.config)
        logger.info(f"ok-script init {config.get('version')}, {sys.argv}, pid={os.getpid()} config: {config}")
        if self.debug:
            logger.debug(f"environment contains {len(os.environ)} entries")
        pyappify.logger = logger
        logger.info(
            f"pyappify  app_version:{pyappify.app_version}, app_profile:{pyappify.app_profile}, pyappify_version:{pyappify.pyappify_version} pyappify_upgradeable:{pyappify.pyappify_upgradeable}, pyappify_executable:{pyappify.pyappify_executable}")
        self.args = parse_arguments()
        self.task_executor = None
        self._app = None
        self._headless_app = None
        self.global_config = global_config_class(config.get('global_configs'))
        windows_config = config.get('windows')
        if windows_config:
            windows_config.setdefault('start_exe', True)
            windows_config.setdefault('start_method', default_start_method)
            capture_methods = windows_config.get('capture_method', [])
            available_methods = []
            for method in capture_methods:
                if method == 'WGC':
                    if wgc_available():
                        available_methods.append(method)
                else:
                    available_methods.append(method)

        register_basic(self.global_config, enable_blur=callable(config.get('blur_area')))
        register_launcher(self.global_config, pyappify)
        og.global_config = self.global_config
        og.set_use_dml()
        try:
            import ctypes
            # Set DPI Awareness (Windows 10 and 8)
            errorCode = ctypes.windll.shcore.SetProcessDpiAwareness(2)
            logger.info(f'SetProcessDpiAwareness {errorCode}')
            if self.debug:
                import win32api
                win32api.SetConsoleCtrlHandler(self.console_handler, True)
        except Exception as e:
            logger.error(f'SetProcessDpiAwareness error', e)
        self.config = config
        try:
            self.do_init()
        except Exception as e:
            logger.error(f'__init__ error', e)
            self.quit()
            raise e

    @property
    def app(self):
        if self._app is None:
            self._app = App(self.config, self.task_executor, self.exit_event)
        return self._app

    @property
    def headless_app(self):
        if self._headless_app is None:
            self._headless_app = HeadlessApp(self.config, self.exit_event)
        return self._headless_app

    def should_init_task_manager_headless(self):
        return not self.config.get("use_gui") or self.args.get('headless', False)

    def start(self):
        logger.info(f'OK start id:{id(self)} pid:{os.getpid()}')
        try:
            use_gui = self.config.get("use_gui") and not self.args.get('headless', False)
            if not use_gui and self.args.get('task', 0) > 0:
                self.run_task(self.args.get('task'), exit_after=self.args.get('exit', False))
                return
            if use_gui:
                if not self.init_error:
                    self.app.show_main_window()
                logger.debug('start app.exec()')
                self.app.exec()
            else:
                self.task_executor.start()
                if self.config.get("debug"):
                    from ok.gui.Communicate import communicate
                    from PySide6.QtWidgets import QApplication
                    app = QApplication(sys.argv)
                    from ok.gui.overlay.OverlayWindow import OverlayWindow
                    self.overlay_window = OverlayWindow(og.device_manager.hwnd_window)
                    communicate.window.connect(self.overlay_window.update_overlay)
                    app.exec()
                else:
                    try:
                        # Starting the task in a separate thread (optional)
                        # This allows the main thread to remain responsive to keyboard interrupts
                        task_thread = threading.Thread(target=self.wait_task)
                        task_thread.start()

                        # Wait for the task thread to end (which it won't, in this case, without an interrupt)
                        task_thread.join()
                    except KeyboardInterrupt:
                        self.exit_event.set()
                        logger.info("Keyboard interrupt received, exiting script.")
                    finally:
                        # Clean-up code goes here (if any)
                        # This block ensures that the script terminates gracefully,
                        # releasing resources or performing necessary clean-up operations.
                        logger.info("Script has terminated.")
        except Exception as e:
            logger.error("start error", e)
            self.exit_event.set()
            if self._app or self._headless_app:
                self.quit()

    def run_task(self, task=1, exit_after=False):
        """
        Run a task without showing the main UI.

        Args:
            task: 1-based one-time task index, task name, task class, or task instance.
            exit_after: exit the game and app after a successful one-time task.
        """
        task, is_trigger_task = self.get_task(task)
        if is_trigger_task:
            return self.run_trigger_task(task)
        return self.run_onetime_task(task, exit_after=exit_after)

    def run_onetime_task(self, task, exit_after=False):
        logger.info(f'run one-time task without ui: {task.name}')
        started = self.headless_app.start_controller.do_start(task, exit_after=exit_after)
        if not started:
            raise RuntimeError(f'Start task failed: {task.name}')
        self.wait_task(task)
        return True

    def run_trigger_task(self, task):
        logger.info(f'run trigger task without ui: {task.name}')
        self.config['trigger_tasks'] = [[task.__class__.__module__, task.__class__.__name__]]
        for trigger_task in self.task_executor.trigger_tasks:
            if trigger_task is not task:
                trigger_task.disable()
        self.task_executor.trigger_tasks = [task]

        started = self.headless_app.start_controller.do_start(task, exit_after=False)
        if not started:
            raise RuntimeError(f'Start trigger task failed: {task.name}')
        self.wait_task()
        return True

    def get_task(self, task):
        from ok.task.task import BaseTask, TriggerTask

        if isinstance(task, int):
            return self.get_onetime_task(task), False
        if isinstance(task, TriggerTask):
            return self.get_trigger_task(task), True
        if isinstance(task, BaseTask):
            return self.get_onetime_task(task), False
        if isinstance(task, type):
            if not issubclass(task, BaseTask):
                raise ValueError(f'Task class must inherit BaseTask: {task}')
            if issubclass(task, TriggerTask):
                return self.get_trigger_task(task), True
            return self.get_onetime_task(task), False
        if isinstance(task, str):
            onetime_task = self.find_task_by_name(self.task_executor.onetime_tasks, task)
            if onetime_task:
                return onetime_task, False
            trigger_task = self.find_task_by_name(self.task_executor.trigger_tasks, task)
            if trigger_task:
                return trigger_task, True
            raise ValueError(f'Task not found: {task}')
        if task in self.task_executor.trigger_tasks:
            return self.get_trigger_task(task), True
        return self.get_onetime_task(task), False

    def find_task_by_name(self, tasks, task):
        normalized_task = task.lower()
        exact_matches = [
            candidate for candidate in tasks
            if candidate.name.lower() == normalized_task or candidate.__class__.__name__.lower() == normalized_task
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            names = ', '.join(candidate.__class__.__name__ for candidate in exact_matches)
            raise ValueError(f'Multiple tasks matched "{task}": {names}')

        partial_matches = [
            candidate for candidate in tasks
            if normalized_task in candidate.name.lower()
            or normalized_task in candidate.__class__.__name__.lower()
        ]
        if len(partial_matches) == 1:
            return partial_matches[0]
        if len(partial_matches) > 1:
            names = ', '.join(candidate.__class__.__name__ for candidate in partial_matches)
            raise ValueError(f'Multiple tasks matched "{task}": {names}')

        for candidate in tasks:
            if candidate.name == task or candidate.__class__.__name__ == task:
                return candidate
        return None

    def get_onetime_task(self, task):
        from ok.task.task import BaseTask, TriggerTask

        if isinstance(task, int):
            task_index = task - 1
            if task_index < 0 or task_index >= len(self.task_executor.onetime_tasks):
                raise IndexError(
                    f'Task index {task} is out of range. Available range is 1-{len(self.task_executor.onetime_tasks)}')
            return self.task_executor.onetime_tasks[task_index]
        if isinstance(task, str):
            matched_task = self.find_task_by_name(self.task_executor.onetime_tasks, task)
            if matched_task:
                return matched_task
            raise ValueError(f'Task not found: {task}')
        if isinstance(task, type):
            for candidate in self.task_executor.onetime_tasks:
                if isinstance(candidate, task):
                    return candidate
            if not issubclass(task, BaseTask):
                raise ValueError(f'Task class must inherit BaseTask: {task}')
            if issubclass(task, TriggerTask):
                raise ValueError(f'run_task only supports one-time BaseTask classes, got TriggerTask: {task}')
            task_instance = task(executor=self.task_executor, app=self.headless_app)
            task_instance.after_init(executor=self.task_executor, scene=self.task_executor.scene)
            task_instance.post_init()
            self.task_executor.onetime_tasks.append(task_instance)
            logger.info(f'created headless task from class: {task_instance}')
            return task_instance
        if task in self.task_executor.onetime_tasks:
            return task
        raise ValueError(f'Unsupported one-time task selector: {task}')

    def get_trigger_task(self, task):
        from ok.task.task import TriggerTask

        if isinstance(task, str):
            matched_task = self.find_task_by_name(self.task_executor.trigger_tasks, task)
            if matched_task:
                return matched_task
            raise ValueError(f'Trigger task not found: {task}')
        if isinstance(task, type):
            for candidate in self.task_executor.trigger_tasks:
                if isinstance(candidate, task):
                    return candidate
            if not issubclass(task, TriggerTask):
                raise ValueError(f'Trigger task class must inherit TriggerTask: {task}')
            task_instance = task(executor=self.task_executor, app=self.headless_app)
            task_instance.after_init(executor=self.task_executor, scene=self.task_executor.scene)
            task_instance.post_init()
            self.task_executor.trigger_tasks.append(task_instance)
            logger.info(f'created headless trigger task from class: {task_instance}')
            return task_instance
        if isinstance(task, TriggerTask):
            if task not in self.task_executor.trigger_tasks:
                task._executor = self.task_executor
                task._app = self.headless_app
                task.after_init(executor=self.task_executor, scene=self.task_executor.scene)
                task.post_init()
                self.task_executor.trigger_tasks.append(task)
            return task
        raise ValueError(f'Unsupported trigger task selector: {task}')

    def do_init(self):
        from ok.feature.FeatureSet import FeatureSet
        from ok.task.TaskExecutor import TaskExecutor
        from ok.util.file import install_path_isascii

        logger.info(f"do_init, config: {self.config}")
        self.init_device_manager()
        from ok.gui.debug.Screenshot import Screenshot
        self.screenshot = Screenshot(self.exit_event, self.debug)

        template_matching = self.config.get('template_matching')
        if template_matching is not None:
            coco_feature_json = self.config.get('template_matching').get('coco_feature_json')
            self.feature_set = FeatureSet(self.debug, coco_feature_json,
                                          default_horizontal_variance=template_matching.get(
                                              'default_horizontal_variance', 0.002),
                                          default_vertical_variance=template_matching.get('default_vertical_variance',
                                                                                          0.002),
                                          default_threshold=template_matching.get('default_threshold', 0.8),
                                          feature_processor=template_matching.get('feature_processor'),
                                          hcenter_features=template_matching.get('hcenter_features'),
                                          vcenter_features=template_matching.get('vcenter_features'))
        ocr_target_height = 0
        if ocr := self.config.get('ocr'):
            isascii, path = install_path_isascii()
            ocr_target_height = ocr.get('target_height', 0)
            if not isascii:
                logger.info(f'show_path_ascii_error')
                self.init_error = True
                if self.should_init_task_manager_headless():
                    raise RuntimeError(f'Install dir {path} must be an English path, move to another path.')
                else:
                    self.app.show_path_ascii_error(path)
                    self.app.exec()
                return False

        self.task_executor = TaskExecutor(self.device_manager, exit_event=self.exit_event,
                                          wait_until_settle_time=self.config.get('wait_until_settle_time', 1),
                                          feature_set=self.feature_set,
                                          config_folder=self.config.get("config_folder"), debug=self.debug,
                                          global_config=self.global_config, ocr_target_height=ocr_target_height,
                                          config=self.config)
        from ok.gui.tasks.TaskManger import TaskManager
        task_app = self.headless_app if self.should_init_task_manager_headless() else self.app
        og.task_manager = TaskManager(task_executor=self.task_executor, app=task_app,
                                      onetime_tasks=self.config.get('onetime_tasks', []),
                                      trigger_tasks=self.config.get('trigger_tasks', []),
                                      scene=self.config.get('scene'))
        og.executor = self.task_executor
        logger.info(f"do_init, end")
        return True

    def wait_task(self, task=None):
        try:
            while not self.exit_event.is_set():
                if task is not None and not task.enabled and self.task_executor.current_task is not task:
                    logger.info(f'task finished without ui: {task.name}')
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, exiting script.")
            self.exit_event.set()
        finally:
            if task is not None:
                self.exit_event.set()
            if (self.exit_event.is_set() and self.task_executor.thread
                    and self.task_executor.thread != threading.current_thread()):
                self.task_executor.thread.join(timeout=10)

    def console_handler(self, event):
        import win32con
        if event == win32con.CTRL_C_EVENT:
            logger.info("CTRL+C event dump threads")
            from ok.capture.windows.dump import dump_threads
            dump_threads()
            self.quit()
        elif event == win32con.CTRL_CLOSE_EVENT:
            logger.info("Close event quit")
            self.quit()
        elif event == win32con.CTRL_LOGOFF_EVENT:
            logger.info("Logoff event quit")
            self.quit()
        elif event == win32con.CTRL_SHUTDOWN_EVENT:
            logger.info("Shutdown event quit")
            self.quit()
        else:  # Perform clean-up tasks here
            logger.info("Performing clean-up...")
        return True

    def quit(self):
        logger.info('quit app')
        self.exit_event.set()
        if self._app:
            self._app.quit()
        if self._headless_app:
            self._headless_app.quit()

    def init_device_manager(self):
        if self.device_manager is None:
            from ok.device.DeviceManager import DeviceManager
            self.device_manager = DeviceManager(self.config,
                                                self.exit_event, self.global_config)
            og.device_manager = self.device_manager


def run_task(config, task=1, debug=False, exit_after=False):
    """
    Convenience entrypoint for scripts that only need to run one task.

    Example:
        from ok import run_task
        from src.config import config

        if __name__ == "__main__":
            run_task(config, task=1)
    """
    from ok.task.task import TriggerTask

    headless_config = dict(config)
    headless_config["use_gui"] = False
    headless_config["debug"] = debug
    if isinstance(task, type) and issubclass(task, TriggerTask):
        headless_config["trigger_tasks"] = [[task.__module__, task.__name__]]
    elif isinstance(task, TriggerTask):
        headless_config["trigger_tasks"] = [[task.__class__.__module__, task.__class__.__name__]]
    return OK(headless_config).run_task(task, exit_after=exit_after)


class BaseScene:
    def reset(self):
        pass


## globals.py
class OkGlobals:

    def __init__(self):
        super().__init__()
        self.app = None
        self.executor = None
        self.device_manager = None
        self.handler = None
        self.auth_uid = None
        self.auth_rd = None
        self.auth_expire = 0
        self.trial_expire = 0
        self.main_window = None
        self.my_app = None
        self.dpi_scaling = 1.0
        self.ok = None
        self.config = None
        self.task_manager = None
        self.app_path = get_path_relative_to_exe()
        self.use_dml = False
        self.global_config = None
        logger.info(f'app path {self.app_path}')

    def set_use_dml(self):
        from ok.util.process import get_first_gpu_free_memory_mib

        use_dml_txt_option = self.global_config.get_config('Basic Options').get('Use DirectML')
        use_dml = False
        if use_dml_txt_option == 'Auto':
            nv_free_gpu_memory = get_first_gpu_free_memory_mib()
            if nv_free_gpu_memory > 3000:
                use_dml = True
            logger.info(f'Use DirectML is auto nv_free_gpu_memory: {nv_free_gpu_memory}, use_dml: {use_dml}')
        elif use_dml_txt_option == 'Yes':
            use_dml = True
        if use_dml:
            window_build_number_str = platform.version().split(".")[-1]
            window_build_number = int(window_build_number_str) if window_build_number_str.isdigit() else 0
            use_dml = window_build_number >= 18362
        logger.info(f'use_dml result is {use_dml}')
        self.use_dml = use_dml

    def get_overlay_view(self):
        if self.app and hasattr(self.app, 'get_overlay_view'):
            return self.app.get_overlay_view()
        return None

    def get_trial_expire_util_str(self):
        # Convert the timestamp to a datetime object
        expire_date = datetime.fromtimestamp(self.trial_expire)

        # Format the datetime object to a string
        expire_date_str = expire_date.strftime('%Y-%m-%d %H:%M:%S')

        return expire_date_str

    def get_expire_util_str(self):
        # Convert the timestamp to a datetime object
        expire_date = datetime.fromtimestamp(self.auth_expire)

        # Format the datetime object to a string
        expire_date_str = expire_date.strftime('%Y-%m-%d %H:%M:%S')

        return expire_date_str

    def set_dpi_scaling(self, window):
        window_handle = window.windowHandle()
        screen = window_handle.screen()
        self.dpi_scaling = screen.devicePixelRatio()
        logger.debug('dpi_scaling: {}'.format(self.dpi_scaling))


og = OkGlobals()
