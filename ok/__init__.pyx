# __init__.pyx
import hashlib
import logging
import os
import platform
import sys
import threading
import time
import uuid
from datetime import datetime

import pyappify
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon
from ok.device.DeviceManager import DeviceManager
from ok.feature.FeatureSet import FeatureSet
from ok.gui.Communicate import communicate
from ok.gui.MainWindow import MainWindow
from ok.task.TaskExecutor import TaskExecutor
from ok.util.Analytics import Analytics
from ok.util.GlobalConfig import GlobalConfig, basic_options
from ok.util.clazz import init_class_by_name
from ok.util.config import Config, ConfigOption
from ok.util.handler import Handler, ExitEvent
from ok.util.logger import config_logger, Logger
from ok.util.process import check_mutex, get_first_gpu_free_memory_mib
from ok.util.file import get_path_relative_to_exe, install_path_isascii
from ok.device.intercation import DoNothingInteraction, BaseInteraction, BrowserInteraction, PostMessageInteraction, \
    GenshinInteraction, ForegroundPostMessageInteraction, PyDirectInteraction
from ok.device.capture import ImageCaptureMethod, BaseCaptureMethod, BrowserCaptureMethod, ADBCaptureMethod, \
    WindowsGraphicsCaptureMethod, BitBltCaptureMethod, NemuIpcCaptureMethod, DesktopDuplicationCaptureMethod, \
    ImageCaptureMethod
from ok.task.DiagnosisTask import DiagnosisTask
from ok.task.task import BaseTask, TriggerTask, FindFeature, OCR
from ok.feature.Feature import Feature
from ok.feature.Box import Box, find_boxes_by_name, relative_box, crop_image, average_width, find_boxes_within_boundary, \
    get_bounding_box, find_box_by_name, find_highest_confidence_box, sort_boxes
from ok.task.exceptions import CannotFindException, TaskDisabledException, FinishedException, WaitFailedException, \
    CaptureException
from ok.util.collection import safe_get

from ok.util.color import find_color_rectangles, mask_white, find_color_rectangles, color_range_to_bound, \
    calculate_color_percentage, get_mask_in_color_range, is_pure_black
os.environ["PYTHONIOENCODING"] = "utf-8"

cdef logger = Logger.get_logger("ok")


class CommunicateHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        from ok.gui.Communicate import communicate
        self.communicate = communicate

    def emit(self, record):
        log_message = self.format(record)
        self.communicate.log.emit(record.levelno, log_message)


cdef class App:
    cdef public object global_config, app, ok_config, auth_config, locale, overlay, start_controller, loading_window, overlay_window, main_window, exit_event, icon, fire_base_analytics, to_translate, po_translation, updater, timer
    cdef public dict config
    cdef public str about, title, version
    cdef bint debug

    def __init__(self, config, task_executor,
                 exit_event=None):
        super().__init__()
        og.exit_event = exit_event
        og.handler = Handler(exit_event, 'global')
        self.config = config
        self.auth_config = None
        self.global_config = task_executor.global_config if task_executor else None
        from ok.gui.util.app import init_app_config
        self.app, self.locale = init_app_config()
        self.ok_config = Config('_ok', {'window_x': -1, 'window_y': -1, 'window_width': -1, 'window_height': -1,
                                        'window_maximized': False})
        communicate.quit.connect(self.app.quit)

        self.about = self.config.get('about')
        self.title = self.config.get('gui_title')
        self.app.setApplicationName(self.title)
        self.app.setApplicationDisplayName(self.title)
        self.version = self.config.get('version')
        self.app.setApplicationVersion(self.version)
        self.debug = self.config.get('debug', False)
        if self.config.get(
                'git_update') and not pyappify.app_version and self.version != "dev" and not os.path.exists(
            '.venv'):
            from ok.update.GitUpdater import GitUpdater
            self.updater = GitUpdater(self.config, exit_event)
        else:
            self.updater = None

        logger.debug(f'locale name {self.locale.name()}')

        self.loading_window = None
        self.overlay_window = None
        self.main_window = None
        self.exit_event = exit_event
        self.icon = QIcon(get_path_relative_to_exe(config.get('gui_icon')) or ":/icon/icon.ico")

        from ok.gui.StartController import StartController
        self.start_controller = StartController(self.config, exit_event)
        if self.config.get('debug') or self.config.get('use_overlay'):
            logger.debug('init overlay')
            from ok.gui.overlay.OverlayWindow import OverlayWindow
            self.overlay_window = OverlayWindow(og.device_manager.hwnd_window)
            self.to_translate = set()
        else:
            self.to_translate = None
        self.po_translation = None
        if not config.get('window_size'):
            logger.info(f'no config.window_size was set use default')
            config['window_size'] = {
                'width': 800,
                'height': 600,
                'min_width': 600,
                'min_height': 450,
            }
        og.app = self
        og.executor = task_executor
        if task_executor:
            og.device_manager = task_executor.device_manager
        if my_app := self.config.get('my_app'):
            og.my_app = init_class_by_name(my_app[0], my_app[1], exit_event)

        if self.config.get('analytics'):
            self.fire_base_analytics = Analytics(self.config, self.exit_event, og.handler, og.device_manager)
        logger.debug('init app end')

    def quit(self):
        self.exit_event.set()
        from PySide6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(self.app, "quit", Qt.QueuedConnection)

    def tr(self, key):
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
            return self.po_translation.gettext(key)
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
        title = QCoreApplication.translate("app", 'Error')
        content = QCoreApplication.translate("app",
                                             "Another instance is already running")
        self.show_message_window(title, content)

    def show_path_ascii_error(self, path):
        title = QCoreApplication.translate("app", 'Error')
        content = QCoreApplication.translate("app",
                                             "Install dir {path} must be an English path, move to another path.").format(
            path=path)
        self.show_message_window(title, content)

    def update_overlay(self, visible, x, y, window_width, window_height, width, height, scaling):

        self.overlay_window.update_overlay(visible, x, y, window_width, window_height, width, height, scaling)

    def show_main_window(self):
        self.do_show_main()

    def do_show_main(self):
        if self.debug:
            communicate.window.connect(self.overlay_window.update_overlay)

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

        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

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

cdef class Response:
    cdef public int code
    cdef public str message
    cdef public object data


## OK.pyx


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
        check_mutex()
        og.ok = self
        if pyappify.app_version:
            config['version'] = pyappify.app_version
        if pyappify.app_profile:
            config['profile'] = pyappify.app_profile
        og.config = config
        self.config = config
        config["config_folder"] = config.get("config_folder") or 'configs'
        Config.config_folder = config["config_folder"]
        config_logger(self.config)
        logger.info(f"ok-script init {config.get('version')}, {sys.argv}, pid={os.getpid()} config: {config}")
        pyappify.logger = logger
        logger.info(
            f"pyappify  app_version:{pyappify.app_version}, app_profile:{pyappify.app_profile}, pyappify_version:{pyappify.pyappify_version} pyappify_upgradeable:{pyappify.pyappify_upgradeable}, pyappify_executable:{pyappify.pyappify_executable}")
        config['debug'] = config.get("debug", False)
        self.task_executor = None
        self._app = None
        self.debug = config['debug']
        self.global_config = GlobalConfig(config.get('global_configs'))
        self.global_config.get_config(basic_options)
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

    def start(self):
        logger.info(f'OK start id:{id(self)} pid:{os.getpid()}')
        try:
            if self.config.get("use_gui"):
                if not self.init_error:
                    self.app.show_main_window()
                logger.debug('start app.exec()')
                self.app.exec()
            else:
                self.task_executor.start()
                if self.config.get("debug") or self.config.get('use_overlay'):
                    from PySide6.QtWidgets import QApplication
                    app = QApplication(sys.argv)
                    from ok.gui.overlay.OverlayWindow import OverlayWindow
                    self.overlay_window = OverlayWindow(og.device_manager.hwnd_window)
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
            if self.app:
                self.quit()

    def do_init(self):
        logger.info(f"do_init, config: {self.config}")
        self.init_device_manager()
        from ok.gui.debug.Screenshot import Screenshot
        self.screenshot = Screenshot(self.exit_event, self.debug)

        template_matching = self.config.get('template_matching')
        if template_matching is not None:
            coco_feature_json = self.config.get('template_matching').get('coco_feature_json')
            self.feature_set = FeatureSet(self.debug, coco_feature_json,
                                          default_horizontal_variance=template_matching.get(
                                              'default_horizontal_variance', 0),
                                          default_vertical_variance=template_matching.get('default_vertical_variance',
                                                                                          0),
                                          default_threshold=template_matching.get('default_threshold', 0),
                                          feature_processor=template_matching.get('feature_processor'))
        ocr_target_height = 0
        if ocr := self.config.get('ocr'):
            isascii, path = install_path_isascii()
            ocr_target_height = ocr.get('target_height', 0)
            if not isascii:
                logger.info(f'show_path_ascii_error')
                self.app.show_path_ascii_error(path)
                self.init_error = True
                self.app.exec()
                return False

        self.task_executor = TaskExecutor(self.device_manager, exit_event=self.exit_event,
                                          wait_until_settle_time=self.config.get('wait_until_settle_time', 1),
                                          feature_set=self.feature_set,
                                          config_folder=self.config.get("config_folder"), debug=self.debug,
                                          global_config=self.global_config, ocr_target_height=ocr_target_height,
                                          config=self.config)
        from ok.gui.tasks.TaskManger import TaskManager
        og.task_manager = TaskManager(task_executor=self.task_executor, app=self.app,
                                      onetime_tasks=self.config.get('onetime_tasks', []),
                                      trigger_tasks=self.config.get('trigger_tasks', []),
                                      scene=self.config.get('scene'))
        og.executor = self.task_executor
        logger.info(f"do_init, end")
        return True

    def wait_task(self):
        while not self.exit_event.is_set():
            time.sleep(1)

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

    def init_device_manager(self):
        if self.device_manager is None:
            self.device_manager = DeviceManager(self.config,
                                                self.exit_event, self.global_config)
            og.device_manager = self.device_manager


cdef class BaseScene:
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
